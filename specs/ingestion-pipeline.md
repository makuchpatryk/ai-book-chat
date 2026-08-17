# Phase 2 — Ingestion Pipeline — Implementation Plan

> **Partly superseded (2026-08-18).** Embeddings no longer go through OpenAI: `OpenAIEmbedder`,
> `EMBEDDING_PROVIDER`, `EMBEDDING_MODEL` and `OPENAI_API_KEY` are gone, replaced by a local Ollama
> `nomic-embed-text`, and `chunks.embedding` narrowed from `Vector(1536)` to `Vector(768)`
> (migration 0004). Read every "1536" and "text-embedding-3-small" below as historical. The
> `Embedder` protocol, chunking, section detection and the Celery flow are unchanged. Current state:
> README "LLM configuration", PRD §8 Phase 8.

## Summary

Turn an uploaded PDF into embedded, page-attributed chunks: `POST /documents` stores the file and enqueues a Celery job that extracts text, detects chapter/section bounds, chunks within those bounds, embeds via OpenAI, and bulk-inserts vectors — driving the document through `PENDING → PARSING → EMBEDDING → READY` (or `FAILED` with a readable reason).

This is the foundation for Phase 3 retrieval: nothing can be searched until chunks and their `vector(1536)` embeddings exist. It also builds the domain schema (`documents`, `sections`, `chunks`) that Phase 1 deliberately deferred.

## Success Criteria

- A 300-page PDF goes from `POST /documents` to `status=READY` in **under 120 s** end-to-end (PRD §2.5), measured on a real book.
- `GET /documents/{id}` returns `page_count`, the detected `sections` list, and `chunk_count > 0`; every chunk row has a non-null 1536-dim `embedding` and a `page_start`/`page_end` inside the document's page range.
- Chunk token counts sit within **450–750** tokens (target ~600) for ≥95% of chunks, and no chunk spans two sections.
- Re-uploading the identical file returns the **same document id** with no second embedding run (verified by an embedder call counter).
- A scanned/image-only PDF ends in `FAILED` with `error_message` naming the cause, and leaves **zero** chunk/section rows.
- `pnpm test` stays green with no network access: the default embedder in tests is a deterministic fake; the real-API test is opt-in.

## Scope & Constraints

**In scope**
- Alembic migration `0002`: `documents`, `sections`, `chunks` + HNSW index on `chunks.embedding`
- SQLAlchemy models + Pydantic schemas
- `POST /documents` (multipart), `GET /documents`, `GET /documents/{id}`
- Celery task `process_document` and the extraction → sections → chunking → embedding pipeline
- SHA-256 dedupe, size/type validation, status machine, failure rollback
- OpenAI embedding client with batching + retry, behind a `Protocol` with a fake implementation
- Tests for every pipeline stage plus an end-to-end run against the real database

**Out of scope**
- `POST /documents/{id}/retry`, `DELETE /documents/{id}` — Phase 6 (schema is built cascade-ready)
- Vector search, re-ranking, chat, conversations, messages — Phases 3–4
- Any frontend work — Phase 5 (verify with curl/psql/pytest)
- OCR, EPUB/DOCX, cross-document queries — out of scope for v1 per PRD §2.3

**Hard constraints**
- Under 2 min to ready for a 300-page book; processing asynchronous, upload response immediate
- Embeddings: `text-embedding-3-small`, 1536 dims, cosine distance
- Chunks ~600 tokens, 15% overlap, never crossing a section boundary
- Failed processing leaves no orphan chunks and is retryable (Phase 6 hooks into the same task)
- Worker is sync SQLAlchemy (`session_scope`); API path stays async — established in Phase 1

**Trade-offs**
- **PyMuPDF replaces the PRD's pdfplumber.** pdfplumber needs ~0.3–1 s/page, which alone risks the 2-min budget on a 300-page book; PyMuPDF does the same work 10–40× faster *and* exposes the outline and per-span font sizes that section detection needs, from one library. Cost: AGPL-3.0 — irrelevant for a local single-user app, relevant if this is ever shipped closed-source. **This is a deliberate deviation from PRD §1's locked decision.**
- Dedupe returns the existing document (200) rather than 409, so the future upload UI needs no error branch.
- Embedding batches run sequentially, not concurrently. Simpler, and the estimate below shows sequential already fits the budget; concurrency is the first lever if it doesn't.

## Architecture & Design

### High-Level Flow

```
POST /documents (multipart)
  ├─ validate: .pdf, %PDF- magic bytes, ≤ 50 MB (streamed, capped)
  ├─ sha256 over the stream
  ├─ existing doc with same hash & status != FAILED?  ── yes ──► 200 {existing id}
  ├─ save to  UPLOAD_DIR/{uuid}.pdf
  ├─ INSERT documents (status=PENDING)
  ├─ process_document.delay(id)
  └─ 201 {id, status: PENDING}                    (returns in < 1 s)

worker: process_document(document_id)          [sync session_scope]
  1. status ← PARSING
  2. extract.py      PyMuPDF: page texts, page_count, title, outline
                     no extractable text ──► EmptyDocumentError
  3. sections.py     outline ─fallback→ font/numbering headings ─fallback→ flat
                     records which strategy won on documents.chunking_strategy
  4. chunking.py     per section: ~600-token windows, 90-token overlap,
                     page_start/page_end from token→page map
  5. status ← EMBEDDING
  6. embeddings.py   OpenAI, 100 inputs/request, retry w/ backoff
  7. bulk INSERT sections + chunks (single transaction)
  8. status ← READY,  page_count set
  on any exception → rollback, DELETE chunks/sections for doc, status ← FAILED + error_message
```

### Data Model (migration `0002_ingestion_tables`)

```sql
CREATE TYPE document_status AS ENUM ('PENDING','PARSING','EMBEDDING','READY','FAILED');

CREATE TABLE documents (
  id            uuid PRIMARY KEY,
  filename      varchar(512) NOT NULL,
  title         varchar(512) NOT NULL,
  page_count    integer,                       -- NULL until parsed
  status        document_status NOT NULL DEFAULT 'PENDING',
  error_message text,
  file_path     varchar(1024) NOT NULL,
  content_hash  char(64) NOT NULL,
  chunking_strategy varchar(16),               -- outline | headings | flat
  created_at    timestamptz NOT NULL DEFAULT now(),
  updated_at    timestamptz NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX ix_documents_content_hash ON documents (content_hash);
CREATE INDEX ix_documents_created_at ON documents (created_at DESC);

CREATE TABLE sections (
  id          uuid PRIMARY KEY,
  document_id uuid NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
  title       varchar(512) NOT NULL,
  order_index integer NOT NULL,
  start_page  integer NOT NULL,
  end_page    integer NOT NULL,
  UNIQUE (document_id, order_index)
);

CREATE TABLE chunks (
  id          uuid PRIMARY KEY,
  document_id uuid NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
  section_id  uuid REFERENCES sections(id) ON DELETE CASCADE,
  content     text NOT NULL,
  page_start  integer NOT NULL,
  page_end    integer NOT NULL,
  token_count integer NOT NULL,
  order_index integer NOT NULL,
  embedding   vector(1536) NOT NULL,
  UNIQUE (document_id, order_index)
);
CREATE INDEX ix_chunks_document_id ON chunks (document_id);
CREATE INDEX ix_chunks_embedding_hnsw ON chunks
  USING hnsw (embedding vector_cosine_ops) WITH (m = 16, ef_construction = 64);
```

`content_hash` is unique across all statuses; a `FAILED` row is reused (updated back to `PENDING`) rather than duplicated, which keeps retry cheap. Cascades are declared now so Phase 6's `DELETE /documents/{id}` is a one-liner.

### Key Changes

**New package `apps/api/src/app/ingestion/`** — pure, DB-free logic wherever possible, so most tests need no database:

| Module | Contract |
| --- | --- |
| `extract.py` | `extract_pdf(path) -> ExtractedPdf(page_count, title, pages: list[PageText], outline: list[OutlineEntry])`; raises `EmptyDocumentError` when total extracted characters < 200 or fewer than 10% of pages carry text |
| `sections.py` | `detect_sections(extracted) -> tuple[list[SectionSpec], Strategy]` — outline → heading heuristics → flat |
| `tokenizer.py` | `encode/decode/count_tokens` over `tiktoken.get_encoding("cl100k_base")`, cached module-level |
| `chunking.py` | `chunk_document(pages, sections, size=600, overlap_ratio=0.15) -> list[ChunkSpec]` with `page_start/page_end/token_count/order_index` |
| `embeddings.py` | `Embedder` Protocol (`embed(texts: list[str]) -> list[list[float]]`); `OpenAIEmbedder` (batch 100, tenacity retry) and `FakeEmbedder` (seeded, deterministic, normalized) |
| `pipeline.py` | `process_document(session, document_id, embedder)` — the status machine and persistence; the only module that touches the DB |

**`app/services/documents.py`** — `create_document(session, upload)` (validate, hash, dedupe, save, insert, enqueue), `list_documents`, `get_document_detail`.

**`app/worker/tasks.py`** — adds:
```python
@shared_task(name="app.worker.tasks.process_document", acks_late=True, time_limit=1800)
def process_document(document_id: str) -> str:
    with session_scope() as session:
        return process_document_pipeline(session, UUID(document_id), build_embedder())
```

**API contracts** (PRD §6 shapes, minus retry/delete):
```
POST /documents      multipart file → 201 {id, filename, title, status, page_count, created_at}
                     duplicate → 200, same body, existing id
                     wrong type → 415   too large → 413   corrupt PDF → 422
GET  /documents      → DocumentRead[]  (created_at desc)
GET  /documents/{id} → DocumentRead + {sections: SectionRead[], chunk_count: int}   404 if unknown
```

**Dependencies added to `apps/api/pyproject.toml`**: `pymupdf`, `openai`, `tiktoken`, `tenacity`. The Dockerfile bakes the tiktoken BPE file (`ENV TIKTOKEN_CACHE_DIR=/opt/tiktoken` + a build-time `tiktoken.get_encoding("cl100k_base")`) so the worker never fetches it at runtime.

**Config additions**: `embedding_model="text-embedding-3-small"`, `embedding_dimensions=1536`, `embedding_batch_size=100`, `chunk_target_tokens=600`, `chunk_overlap_ratio=0.15`.

**Compose**: worker command gains `--concurrency=2` — PDF parsing is CPU-bound and the default (one per core) would let two big books starve the box.

### Section Detection, Concretely

1. **Outline** — `doc.get_toc()` gives `[level, title, page]`. Keep level-1 entries (level-2 if level-1 yields fewer than 3 sections); `end_page` = next start − 1; drop entries with out-of-range pages. Strategy = `outline`.
2. **Heading heuristics** — from `page.get_text("dict")` spans, compute the modal body font size. A line is a heading if it is ≤ 80 chars, is a single span, and either `size ≥ 1.25 × body` or matches `^(chapter|part|section)\s+[\dIVXLC]+` / `^\d+(\.\d+)?\s+\S` (case-insensitive). Require ≥ 3 detections, otherwise fall through. Strategy = `headings`.
3. **Flat** — one pseudo-section spanning pages 1..N, `title = document title`. Chunking then just walks pages. Strategy = `flat`.

The winning strategy is stored on `documents.chunking_strategy` — PRD §9 explicitly asks to log which one ran.

### Chunking, Concretely

Per section: build `[(page_number, token_ids)]` for its page range, flatten into one token stream while keeping a token-index → page map. Slide a 600-token window with a 90-token step-back overlap. For each window: `content = decode(tokens)`, `page_start` = page of the first token, `page_end` = page of the last, `token_count` = window length. A trailing window shorter than 150 tokens merges into the previous chunk instead of standing alone. Windows never cross a section boundary because each section is chunked independently.

### Alternative Approaches Considered

**Extraction library** — PyMuPDF chosen (speed + outline + font metrics in one lib; AGPL accepted for local use). pdfplumber: PRD-locked, MIT, richer char boxes, but 10–40× slower and needs a second library for the outline. pypdf: MIT and fast enough, but its weak layout data makes heading heuristics unreliable.

**Chunk boundary unit** — token windows over a section's text chosen: predictable sizes, exact control of the embedding input limit. Sentence/paragraph splitting produces more natural chunks but highly variable sizes; a recursive character splitter is simpler still but its "tokens" drift from real ones, which matters when re-rank context is budgeted in Phase 3.

**Where embeddings are generated** — in the Celery task, synchronously per batch. Alternative: a separate `embed_chunk_batch` task per 100 chunks with a chord callback. That parallelizes and survives partial failure, but makes the status machine and rollback substantially harder for a single-user app whose sequential path already meets the target.

**Duplicate handling** — hash dedupe returning the existing row. Alternative: no dedupe (costs a full re-embed per re-upload); or 409 (forces error handling into the future UI).

**Storing page text** — not stored; chunks carry their own text and the original PDF is retained per PRD §2.4. A `pages` table would allow re-chunking without re-parsing, but PyMuPDF re-parses a 300-page book in seconds, so it earns nothing yet.

## Implementation Steps

1. **Dependencies** — add `pymupdf`, `openai`, `tiktoken`, `tenacity` to `pyproject.toml`; `uv sync`. Add `TIKTOKEN_CACHE_DIR` + warm-up `RUN` to `apps/api/Dockerfile`.
2. **Config** — extend `Settings` with the embedding/chunking fields listed above; document them in `.env.example`.
3. **Models** — `app/db/models/document.py`, `section.py`, `chunk.py` (SQLAlchemy 2.0 `Mapped[...]`, `pgvector.sqlalchemy.Vector(1536)`), all re-exported from `app/db/models/__init__.py` so Alembic autogenerate sees them.
4. **Migration `0002_ingestion_tables`** — autogenerate, then hand-edit: native enum creation, `Vector` column import, and the HNSW index (autogenerate won't emit `USING hnsw ... WITH (...)`). Verify `upgrade → downgrade → upgrade` on the scratch DB.
5. **`ingestion/tokenizer.py`** — cached encoder, `count_tokens`, `encode`, `decode`.
6. **`ingestion/extract.py`** — `extract_pdf()` returning `ExtractedPdf`; title from PDF metadata falling back to the filename stem; `EmptyDocumentError` on the scanned-PDF signal; `CorruptPdfError` wrapping PyMuPDF open failures.
7. **`ingestion/sections.py`** — the three strategies plus `Strategy` enum, in the order above.
8. **`ingestion/chunking.py`** — `chunk_document()` per the algorithm above, returning `ChunkSpec` objects with page attribution.
9. **`ingestion/embeddings.py`** — `Embedder` Protocol; `OpenAIEmbedder` (batching, `tenacity` retry on `RateLimitError`/`APIConnectionError`/5xx, 6 attempts, exponential backoff, jitter); `FakeEmbedder` (SHA-seeded, unit-normalized, counts calls); `build_embedder()` factory returning the fake when `OPENAI_API_KEY` is unset.
10. **`ingestion/pipeline.py`** — `process_document(session, document_id, embedder)`: status transitions, `page_count`/`chunking_strategy` writes, bulk `insert()` of sections then chunks, and the failure path (rollback → delete this document's chunks/sections in a fresh transaction → `FAILED` + truncated `error_message`).
11. **Worker task** — `process_document` in `app/worker/tasks.py` (`acks_late=True`, `time_limit=1800`); add `--concurrency=2` to the compose worker command.
12. **Schemas** — `app/schemas/documents.py`: `DocumentRead`, `SectionRead`, `DocumentDetail` (`model_config = ConfigDict(from_attributes=True)`).
13. **Service layer** — `app/services/documents.py`: streamed save with a 50 MB cap (abort + unlink on overflow → 413), magic-byte check, SHA-256, dedupe lookup, insert, `process_document.delay(str(doc.id))`.
14. **Routes** — `app/api/routes/documents.py` with the three endpoints; register in `app/api/routes/__init__.py`.
15. **Test fixtures** — `tests/factories.py` building synthetic PDFs with PyMuPDF (a "book" with an outline and known page text, a heading-only variant, and an image-only variant for the scanned case).
16. **Unit tests** — extraction, section detection (all three strategies), chunking invariants, tokenizer, embedder batching/retry.
17. **Integration tests** — pipeline against the real DB with `FakeEmbedder` (happy path + failure/rollback path); API tests for upload/list/detail including dedupe, 413, 415, 404.
18. **Live test** — `tests/test_embeddings_live.py` marked `@pytest.mark.live`, skipped unless `OPENAI_API_KEY` is set; registers the `live` marker in `pyproject.toml` and excludes it from the default run via `addopts = "-q -m 'not live'"`.
19. **Manual verification + docs** — ingest a real 300-page book, record wall-clock time and chunk stats; update `README.md` (new env vars, ingestion flow, `-m live`) and note the pdfplumber→PyMuPDF deviation in `PRD.md` §1.

### Risks & Mitigations

- **Deviating from the PRD's locked pdfplumber choice.** Mitigation: the deviation is recorded in PRD §1 and here, with the timing rationale. Extraction sits behind `extract_pdf()`, so swapping back means rewriting one module and its tests, nothing else.
- **300-page book misses the 2-min target anyway.** Budget: parse ~5 s, chunk ~3 s, embed ~800 chunks = 8 sequential batches ≈ 15–40 s. Mitigation if reality is worse: raise `embedding_batch_size`, then run batches concurrently with a bounded `ThreadPoolExecutor` (the OpenAI SDK is thread-safe) — a contained change inside `OpenAIEmbedder`.
- **Heading heuristics fire on page headers/footers or catch nothing**, producing hundreds of one-page "sections" or a single blob. Mitigation: require ≥ 3 detections *and* cap at 200 sections before falling back to flat; drop candidate headings that repeat on more than half the pages (running headers). The chosen strategy is stored per document so bad output is diagnosable.
- **Embedding cost/rate limits on a large book.** Mitigation: hash dedupe prevents re-embedding; batching keeps request count low; tenacity backoff absorbs 429s; total tokens are logged per document so spend is auditable (PRD §2.5).
- **Partial writes on failure leave orphan chunks.** Mitigation: all inserts happen in one transaction *after* embeddings return, so the common failure modes commit nothing; the failure handler additionally issues an explicit delete in a fresh transaction. An integration test asserts zero rows after an induced mid-pipeline failure.
- **Celery task loses the DB session across forks / long parses hit the time limit.** Mitigation: `worker_process_init` already disposes the engine (Phase 1); `session_scope()` opens per task; `time_limit=1800` with `acks_late=True` so a killed task is redelivered rather than silently lost.

## Test Strategy

**Unit (no DB, no network)**
- `test_extract.py` — synthetic PDF: page count, per-page text, title from metadata, outline parsed; image-only PDF raises `EmptyDocumentError`; truncated bytes raise `CorruptPdfError`.
- `test_sections.py` — outline PDF → `outline` strategy with correct `start_page`/`end_page` chaining; heading PDF → `headings`; plain PDF → `flat` with one section spanning all pages; running-header PDF does not produce a section per page.
- `test_chunking.py` — every chunk ≤ 750 and ≥ 150 tokens (except a lone final chunk), consecutive chunks overlap by ~90 tokens, `order_index` is dense and ordered, `page_start ≤ page_end` and both inside the section range, no chunk's page range crosses a section boundary.
- `test_embeddings.py` — `FakeEmbedder` is deterministic and returns 1536 dims; `OpenAIEmbedder` splits 250 inputs into 3 calls (mocked client); retries a 429 then succeeds; gives up after 6 attempts.

**Integration (real Postgres, fake embedder)**
- `test_pipeline.py` — happy path ends `READY` with `page_count`, sections, chunks, non-null embeddings, and `chunking_strategy` set; a raised error mid-embedding ends `FAILED` with `error_message` and leaves 0 chunks and 0 sections; a cosine `ORDER BY embedding <=> :q LIMIT 1` query returns the expected chunk (proves the HNSW index and the vector round-trip).
- `test_documents_api.py` — upload returns 201 + `PENDING`; a 51 MB body → 413 and no file left on disk; a `.txt` upload → 415; re-upload of the same bytes → 200 with the same id and no extra embedder calls; list ordering; detail includes sections and `chunk_count`; unknown id → 404.
- `test_migrations.py` extends to assert the HNSW index exists on the scratch DB (`pg_indexes` lookup).

**Live (opt-in)** — `-m live` with a real key: embeds three short strings, asserts 1536 dims and that a near-duplicate string scores higher cosine similarity than an unrelated one.

**Manual**
1. Ingest a real 300-page book; record wall-clock upload→READY and confirm < 120 s.
2. `psql`: eyeball 5 random chunks against those pages in a PDF viewer — text and page numbers must match.
3. Compare section titles against the book's actual table of contents.
4. Kill the worker mid-run, restart it → task is redelivered (`acks_late`) and the document still reaches `READY`.

**Performance** — log per-stage durations and token totals at INFO; the manual 300-page run is the gate.

## Success Checklist

- [ ] All success criteria verified with recorded evidence (timings, row counts, chunk-size distribution)
- [ ] `pnpm test` green offline; `-m live` green with a key
- [ ] `pnpm lint` / `pnpm typecheck` green (ruff + mypy strict over the new package)
- [ ] Migration `0002` round-trips on a clean database; HNSW index present
- [ ] Failure path leaves no orphan rows (asserted by test, spot-checked in psql)
- [ ] README + PRD §1 updated (PyMuPDF deviation, new env vars, live-test flag)
- [ ] `/health` and Phase 1 tests still pass — no regressions

## Timeline & Estimates

| Work | Estimate |
| --- | --- |
| Steps 1–4: deps, config, models, migration | ~2 h |
| Steps 5–8: tokenizer, extraction, sections, chunking | ~4 h |
| Steps 9–11: embedder, pipeline, worker task | ~3 h |
| Steps 12–14: schemas, service, routes | ~2 h |
| Steps 15–18: fixtures and tests | ~4 h |
| Step 19: real-book run, tuning, docs | ~2 h |
| **Total** | **~17 h** (+3 h buffer for section-detection tuning on real books) |

## Open Questions

None blocking. Assumptions made where the answer doesn't change the design:
- Duplicate detection keys on raw file bytes, not extracted text — a re-exported PDF of the same book counts as new.
- `title` comes from PDF metadata when present, else the filename stem; no LLM-based titling.
- Uploaded files are kept on `FAILED` so Phase 6 retry can re-run without a re-upload.
- Chunk text is stored verbatim (no header/footer stripping); if citations look noisy on a real book, that is a Phase 6 tuning item, not a blocker.
