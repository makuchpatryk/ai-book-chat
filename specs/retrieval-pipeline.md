# Phase 3 — Retrieval Pipeline — Implementation Plan

## Summary

Phase 2 left the database full of embedded chunks that nothing reads. Phase 3 adds the read
path: embed a question, find the nearest chunks in one document, have Claude Haiku re-rank
them, and refuse to answer when nothing is relevant. It ships as a real endpoint
(`POST /documents/{id}/search`) plus a service layer that Phase 4's chat generation calls
directly.

## Success Criteria

- `POST /documents/{id}/search` on a READY document returns ≤ 8 chunks with `page_start`,
  `page_end`, `content`, and a re-rank `score`, ordered by score descending.
- A question with no relevant content returns `200 {"results": [], "grounded": false,
  "reason": "no_relevant_chunks"}` — never a fabricated match.
- A Haiku failure (timeout, 5xx, malformed JSON) still returns results, ordered by cosine
  distance, with `"reranked": false` in the response and a WARNING in the logs.
- Retrieval latency (embed + search + re-rank) stays under 2 s p50 on a 300-page book, leaving
  headroom inside the PRD's 3-second first-token budget.
- `pytest apps/api/tests` passes offline — no OpenAI or Anthropic key required.

## Scope & Constraints

**In scope**
- Vector search over `chunks`, scoped to one `document_id` (PRD §5 step 2).
- LLM re-rank with Claude Haiku, one request for all candidates (PRD §5 step 3).
- Grounding guard (PRD §5 step 4).
- `POST /documents/{id}/search`, its schemas, and a retrieval service Phase 4 reuses.
- Token-usage logging for the re-rank call (PRD §2.4 "cost tracking, logged server-side").

**Out of scope**
- Query rewriting (PRD §5 step 1) — Phase 4. Search takes a standalone query string.
- Answer generation, conversations, messages, SSE — Phase 4.
- Cross-document search — PRD §2.3, out of scope for v1.
- Quality evaluation against a real book. Tests use synthetic fixtures with a mocked LLM;
  they prove the plumbing, not the answers. See **Risks**.

**Hard constraints**
- Retrieval must not block the event loop. The API is async (asyncpg); the OpenAI embedder
  and Anthropic SDK clients are sync.
- Search on a non-READY document must not return partial results.

**Trade-offs**
- Correctness of plumbing over proof of quality: the chosen test strategy (synthetic + mocked)
  is fast and deterministic but tells us nothing about whether retrieval actually finds the
  right pages. Accepted deliberately; mitigation below.
- Availability over precision on re-rank failure: degraded (unranked) results beat a 503.

---

## Architecture & Design

### High-Level Flow

```
POST /documents/{id}/search  { "query": "..." }
  │
  ├─ 404 if document unknown
  ├─ 409 if document.status != READY
  │
  ▼
app.retrieval.pipeline.search(session, document_id, query, settings)
  │
  1. embed query          anyio.to_thread → Embedder.embed([query])  → vector(1536)
  2. vector search        SET LOCAL hnsw.ef_search; cosine top-K (30) WHERE document_id = ?
  │                       → [Candidate(chunk, distance)]
  │                       → empty? return SearchOutcome(grounded=False, reason="no_chunks")
  3. re-rank              anyio.to_thread → Reranker.score(query, candidates)
  │                       → [0..10] per candidate
  │                       ↳ on failure: log WARNING, scores=None, reranked=False
  4. guard + cut          drop score < RERANK_MIN_SCORE, keep top RERANK_TOP_N (8)
  │                       nothing left? grounded=False, reason="no_relevant_chunks"
  ▼
SearchOutcome(results, grounded, reranked, reason)
```

Step 4's guard only fires when re-ranking actually ran. If the re-ranker degraded, there are
no scores to threshold, so the pipeline returns the top-N by cosine distance with
`grounded=True, reranked=False` — Phase 4 can then decide whether to trust it.

### Key Changes

**New package `app/retrieval/`** — mirrors `app/ingestion/`'s shape (Protocol + real impl +
deterministic fake + `build_*` factory), so the two halves of the system read the same way.

- **`app/retrieval/search.py`** — `vector_search(session, document_id, query_vector, limit)`.
  Async SQLAlchemy select using `Chunk.embedding.cosine_distance(query_vector)` from
  `pgvector.sqlalchemy`, joined to `Section` for the section title, ordered by distance,
  limited to `retrieval_top_k`. Issues `SET LOCAL hnsw.ef_search = <2×k, min 64>` on the same
  connection first — pgvector's default `ef_search` is 40, and asking for 30 neighbours with a
  40-wide search list measurably loses recall. `SET LOCAL` scopes it to the transaction, so it
  never leaks to another request on a pooled connection.

- **`app/retrieval/rerank.py`** — the LLM seam.
  - `Reranker` Protocol: `score(query: str, chunks: Sequence[RerankCandidate]) -> list[int]`,
    one score per input, same order.
  - `ClaudeReranker` — one `client.messages.parse()` call with all 30 candidates numbered in
    the user turn, a Pydantic `RerankScores` output model, `model="claude-haiku-4-5"`,
    `max_tokens=2048`, no `thinking` (Haiku 4.5 has no thinking by default, and `effort` is
    rejected on it). Wrapped in `tenacity` retry on `RateLimitError | APIConnectionError |
    APITimeoutError | InternalServerError`, matching `embeddings.py`'s `MAX_ATTEMPTS`/backoff
    so the two providers behave the same under load. Logs `usage.input_tokens` /
    `usage.output_tokens` on every call.
  - `FakeReranker` — deterministic, offline: scores by term overlap between query and chunk
    content, so tests can assert ordering and threshold behaviour without a key.
  - `build_reranker(settings)` — `ClaudeReranker` when `anthropic_api_key` is set, else
    `FakeReranker` with the same WARNING shape `build_embedder` already uses.

- **`app/retrieval/pipeline.py`** — orchestrates the four steps, owns the degrade and the
  guard, returns a `SearchOutcome` dataclass. This is what Phase 4 imports; the HTTP route is
  a thin shell over it.

**`app/schemas/search.py`** — wire shapes:

```python
class SearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=1000)
    top_k: int | None = Field(default=None, ge=1, le=100)      # per-request override
    min_score: int | None = Field(default=None, ge=0, le=10)   # per-request override

class SearchResultRead(BaseModel):
    chunk_id: UUID
    content: str
    page_start: int
    page_end: int
    section_title: str | None
    score: int | None        # re-rank score; None when degraded
    distance: float          # cosine distance, always present

class SearchResponse(BaseModel):
    results: list[SearchResultRead]
    grounded: bool
    reranked: bool
    reason: str | None       # "no_chunks" | "no_relevant_chunks" | None
    candidate_count: int      # how many the vector search returned, for debugging
```

`top_k` / `min_score` are experiment knobs on the debug-friendly endpoint; Phase 4's chat path
passes neither and takes the configured defaults.

**`app/api/routes/search.py`** — one route, registered in `app/api/routes/__init__.py`. Lives
in its own module rather than `documents.py` because Phase 4 adds conversation routes under the
same `/documents/{id}` prefix and `documents.py` should stay about documents.

**`app/config.py`** — five settings, all overridable via `.env`:

```python
    # Retrieval
    retrieval_top_k: int = 30        # vector candidates fed to the re-ranker
    rerank_model: str = "claude-haiku-4-5"
    rerank_top_n: int = 8            # chunks returned after re-ranking
    rerank_min_score: int = 5        # 0–10; below this a chunk is dropped
    rerank_max_tokens: int = 2048
```

**`.env.example`** — same five keys, commented.

**Dependencies** — `anthropic>=0.69` added to `apps/api/pyproject.toml`. `anyio` and `tenacity`
are already present transitively via FastAPI and `embeddings.py`.

**No migration.** `ix_chunks_embedding_hnsw` (HNSW, `vector_cosine_ops`) already exists in
`alembic/versions/0002_ingestion_tables.py`.

### The re-rank prompt

System: scoring rubric only — stable across every request, which is what makes it cacheable
later if volume ever justifies it.

```
You score passages from a single book for relevance to a reader's question.
For each numbered passage return an integer 0-10:
  0-2  unrelated to the question
  3-5  same topic, does not answer the question
  6-8  contains part of the answer
  9-10 directly answers the question
Judge only the passage text. Never infer content that is not present.
Return one score per passage, in the order given.
```

User turn: the question, then `[1] <content>` … `[30] <content>`.

Output is constrained with `client.messages.parse(output_format=RerankScores)` where
`RerankScores` is `list[ScoredPassage(index: int, score: int)]` — indices come back explicitly
so a short or reordered list is detectable rather than silently misaligned. A response whose
indices don't cover 1..N exactly is treated as malformed → degrade path.

**Cost per query**: 30 × ~600 tokens ≈ 18k input + ~400 output ≈ **$0.020** at Haiku 4.5's
$1/$5 per MTok. Logged, not surfaced (PRD §1).

### Alternative Approaches Considered

**Re-rank call shape** — *chosen: one call with all 30.*
- One call (chosen): 1 request, ~1.5 s, $0.02, scores mutually comparable because the model
  sees the whole candidate set. Cost: a ~20k-token prompt and known LLM position bias toward
  early items.
- 3 parallel batches of 10: shorter prompts, less position bias, but scores from different
  calls aren't on a shared scale — merging them to pick a global top-8 is unsound without a
  second normalisation pass.
- 30 parallel single-chunk calls: cleanest scores, 30× request overhead and a rate-limit
  hazard on every question.

**Async seam** — *chosen: `anyio.to_thread.run_sync` around sync clients.*
- `anyio.to_thread` (chosen): `embeddings.py` stays untouched, one seam pattern for both
  providers, and the same code is callable from the sync Celery worker if retrieval is ever
  needed there. A single 1-vector embed and one Haiku call per request make threadpool
  overhead irrelevant next to network latency.
- `AsyncAnthropic` + a parallel `AsyncEmbedder`: native async I/O, but two Protocols, two
  fakes, and two code paths to keep in sync for no measurable gain at this concurrency.
- Sync `def` route: FastAPI would threadpool the whole request, but the DB session is async —
  it would force a second sync session layer into the request path.

**Grounding-guard response** — *chosen: 200 with `grounded: false`.*
"Not in this document" is a correct answer (US-5), not an error. A 404 would conflate it with
an unknown document id; returning low-scoring chunks anyway would push the refusal decision
onto Phase 4 with no clear signal.

**Re-rank failure** — *chosen: degrade to vector order.*
A 503 makes one Haiku blip break chat entirely. Degrading keeps the product working; the
`reranked: false` flag plus a WARNING log means it's visible rather than silent. The residual
risk is a caller ignoring the flag — noted in **Risks**.

---

## Implementation Steps

1. Add the five retrieval settings to `app/config.py` and `.env.example`; extend
   `tests/test_config.py` with their defaults.
2. Add `anthropic` to `apps/api/pyproject.toml`; `uv sync`.
3. `app/retrieval/search.py`: `vector_search()` with the `SET LOCAL hnsw.ef_search` statement
   and the cosine-distance ordered select, returning `Candidate(chunk, section_title, distance)`.
4. `tests/test_search.py`: insert a document with hand-built unit vectors via the `sync_session`
   fixture, assert ordering by cosine distance, `document_id` scoping (a chunk in another
   document never appears), and the `limit`.
5. `app/retrieval/rerank.py`: `RerankCandidate`, the `Reranker` Protocol, `FakeReranker`,
   `build_reranker`. Fake first — it's what steps 7–10 test against.
6. `app/retrieval/rerank.py`: `ClaudeReranker` with the prompt, the `RerankScores` Pydantic
   model, tenacity retry, usage logging, and index-coverage validation.
7. `app/retrieval/pipeline.py`: `search()` — embed via `anyio.to_thread`, vector search,
   re-rank, guard, assemble `SearchOutcome`. Degrade path catches `Exception` from the
   re-ranker, logs WARNING with `document_id` + exception type, continues.
8. `app/schemas/search.py`: the four models above.
9. `app/api/routes/search.py`: the route — 404 unknown document, 409 non-READY, otherwise call
   the pipeline and map `SearchOutcome` to `SearchResponse`. Register in
   `app/api/routes/__init__.py`.
10. `tests/test_retrieval_pipeline.py`: pipeline-level tests with `FakeEmbedder` +
    `FakeReranker` — threshold cut, top-N cut, `grounded=False` on an empty candidate set,
    `grounded=False` when everything scores below threshold, and a `RaisingReranker` proving
    the degrade path returns vector order with `reranked=False`.
11. `tests/test_rerank.py`: `ClaudeReranker` against a stubbed Anthropic client — happy path,
    a response missing an index (→ raises, so the pipeline degrades), and a retry that
    succeeds on the second attempt.
12. `tests/test_search_api.py`: endpoint tests through the existing `client` fixture — 404,
    409 on a PENDING document, a grounded 200, an ungrounded 200, and the per-request
    `top_k` / `min_score` overrides.
13. Update `README.md` with the endpoint and the five settings.

### Risks & Mitigations

- **Risk: the chosen test strategy proves nothing about retrieval quality.** Synthetic
  fixtures with a mocked LLM can pass while real search returns garbage — wrong pages, useless
  chunks, a threshold set at the wrong level.
  - Mitigation: manual verification is now the gate before Phase 4 — ingest a real book and
    run 10–15 questions with known answers through the endpoint, checking pages by hand.
    Budget time for it; it is not covered by `pytest`.
  - Mitigation: `candidate_count` and `distance` are in the response specifically so a bad
    result is diagnosable without a debugger.
  - Mitigation: if this becomes painful, the opt-in live-test pattern already exists in
    `tests/test_embeddings_live.py` and can be extended later.

- **Risk: `rerank_min_score = 5` is a guess.** Too high and every question hits the guard
  ("not in this document" for content that *is* there — the most damaging failure for US-5);
  too low and the guard never fires and hallucination risk moves to Phase 4.
  - Mitigation: it's a setting, tunable from `.env` with no redeploy, and overridable
    per-request on the search endpoint for sweeps.
  - Mitigation: log every guard trip at INFO with the top score seen — a guard that fires with
    a top score of 4 is a threshold problem, one that fires at 0 is a retrieval problem.

- **Risk: silent quality collapse when re-rank degrades.** `reranked: false` is easy for a
  caller to ignore; chat would keep answering off unranked chunks and nobody would notice.
  - Mitigation: WARNING-level log on every degrade, with the exception type.
  - Mitigation: Phase 4 must read `reranked` — noted as an explicit input to that phase.

- **Risk: position bias in the single 30-candidate call.** LLMs over-score early items; chunk
  order is cosine order, so the model is nudged to agree with the vector search it's supposed
  to correct.
  - Mitigation: measure during manual verification — if the top-8 always mirrors the vector
    top-8, that's the tell.
  - Mitigation: falling back to `retrieval_top_k = 15` (PRD §9's own suggested lever) shortens
    the prompt and reduces the effect; it's a config change.

- **Risk: HNSW recall at k=30.** An approximate index can miss a true nearest neighbour, and
  the missed chunk is invisible — no error, just an absent answer.
  - Mitigation: `ef_search` raised to ≥ 64 (≥ 2×k) per transaction.
  - Mitigation: at single-user scale, an exact scan is affordable; if recall is ever suspect,
    compare against `SET LOCAL enable_indexscan = off` on a real book.

- **Risk: an oversized chunk blows the prompt.** `chunk_target_tokens` is a target, not a cap;
  a pathological section could produce a chunk far larger, and 30 of them could approach
  Haiku's 200K window.
  - Mitigation: truncate each candidate's content to ~1200 tokens in the re-rank prompt only.
    Relevance is judgeable from a prefix; the full chunk still goes to Phase 4's generation.

## Test Strategy

**Unit (offline, deterministic)**
- `vector_search`: distance ordering, `document_id` scoping, limit.
- `FakeReranker`: stable scores for the same input.
- `ClaudeReranker`: prompt assembly, score parsing, index-coverage validation, retry, usage
  logging — all against a stubbed client, no network.
- Pipeline: threshold cut, top-N cut, both `grounded=False` paths, degrade path.

**Integration (through the ASGI client, real Postgres)**
- 404 unknown document; 409 PENDING/FAILED/PARSING document.
- Grounded search returns ordered results with correct page numbers.
- Ungrounded search returns `[]` with `grounded=false, reason="no_relevant_chunks"`.
- Per-request `top_k` / `min_score` overrides take effect.

**Manual (required before Phase 4 — the real quality gate)**
- Ingest a 300-page book. Run 10–15 questions with known page answers; verify the correct page
  appears in the returned set, and check where in the ranking it lands.
- Ask three questions about content that is definitely absent; verify all three trip the guard.
- Ask one question, then revoke `ANTHROPIC_API_KEY` mid-run (or point it at a bad host);
  verify results still come back with `reranked: false`.

**Performance**
- Time embed / search / re-rank separately on the real book, logged per request. Target: under
  2 s total p50. If re-rank dominates, `retrieval_top_k = 15` is the first lever.

## Success Checklist

- [ ] All success criteria met, with the manual verification run recorded
- [ ] `pytest apps/api/tests` passes with no API keys set
- [ ] `ruff` / `mypy` clean, matching the Phase 2 bar
- [ ] Threshold and top-k tuned against a real book, not left at the guessed defaults
- [ ] `README.md` documents the endpoint and the five settings
- [ ] No regression: document upload and ingestion still pass end to end

## Timeline & Estimates

| Phase | Est. |
|---|---|
| Implementation (steps 1–9) | ~5 h |
| Tests (steps 10–12) | ~3 h |
| Manual verification + threshold tuning | ~2 h |
| Docs + polish | ~1 h |
| **Total** | **~11 h** |

Rough. The manual tuning is the most likely to run over — it is the step that can send you back
into chunking decisions from Phase 2.

## Open Questions

- [ ] None blocking. Two settle themselves during manual verification: the final
      `rerank_min_score`, and whether `retrieval_top_k` stays at 30 or drops to 15.
