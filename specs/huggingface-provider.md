# Hugging Face Inference Providers — Implementation Plan

> **Superseded (2026-08-18).** The multi-provider switch this plan introduced was collapsed to a
> single OpenAI-compatible path. The Anthropic, Mistral and Ollama chat/rewrite/rerank adapters and
> the `CHAT_PROVIDER`/`RERANK_PROVIDER`/`EMBEDDING_PROVIDER` settings are gone; `HF_TOKEN` and
> `HF_BASE_URL` are now `LLM_TOKEN` and `LLM_BASE_URL` (default: Groq); `app/llm/hf_client.py` is
> `app/llm/client.py` and the `HF*` classes are `LLM*`; `HFEmbedder`, `hf_bill_to` and the
> `LLM_API_KEY` fallback were deleted, and the embeddings cutover sketched at the end happened
> against local Ollama at 768 dims instead. Current state: README "LLM configuration", PRD §8
> Phase 8. Kept as the record of why the OpenAI-protocol seam was built — the transport survived the
> cleanup unchanged, only its name was HF-specific.

## Summary

The three LLM seams in this codebase (`chat/generate.py`, `chat/rewrite.py`, `retrieval/rerank.py`)
currently default to Anthropic, which is the dominant per-request cost in the app. This plan adds a
fourth provider — Hugging Face Inference Providers, reached through the OpenAI-compatible router at
`https://router.huggingface.co/v1` — and makes it the default, while keeping Anthropic, Mistral and
Ollama adapters in place. It also builds (but does not activate) a Hugging Face embedder behind the
existing `Embedder` protocol, so the OpenAI → HF embedding cutover becomes a config + migration
decision later instead of a code project.

## Success Criteria

- With `CHAT_PROVIDER=huggingface` and `HF_TOKEN` set, a chat request streams a grounded answer end
  to end, and the `done` SSE event carries real `input_tokens`/`output_tokens` (not `None`).
- `truncated: true` is reported when the HF response stops on `finish_reason == "length"`, matching
  the Anthropic path's behaviour.
- `RERANK_PROVIDER=huggingface` returns one integer score per candidate, in order, for all 30
  retrieved chunks, and survives models that wrap JSON in prose, code fences, or `<think>` blocks.
- Per-answer LLM cost drops by ≥90% vs the `claude-sonnet-5` + `claude-haiku-4-5` baseline, measured
  from the structured usage log lines multiplied by the router's published per-model prices.
- Every existing test still passes with default settings, and no test makes a network call.
- `HFEmbedder` exists, is unit-tested against a stubbed client, and `build_embedder` returns it when
  `EMBEDDING_PROVIDER=huggingface` — but the default stays `openai`, so no re-ingest is triggered.

## Scope & Constraints

**In scope**

- `app/llm/hf_client.py` (new): shared router client construction + response-cleaning helpers.
- `HFGenerator` in `chat/generate.py` — async streaming via `AsyncOpenAI` against the router.
- `HFRewriter` in `chat/rewrite.py` — sync single-shot call.
- `HFReranker` in `retrieval/rerank.py` — sync scoring call with tolerant JSON parsing.
- `HFEmbedder` in `ingestion/embeddings.py` — built, tested, **not** default.
- `config.py`: `hf_token`, `hf_base_url`, `hf_bill_to`, `embedding_provider`, new model defaults,
  `chat_provider`/`rerank_provider` defaults flipped to `huggingface`.
- `.env.example`, `README.md`, `PRD.md` provider notes.
- New dependency: `huggingface_hub` (needed only for the embedder; chat/rerank/rewrite reuse the
  already-present `openai` client).

**Out of scope**

- The embeddings cutover itself: pgvector dimension migration, re-embedding existing documents,
  dual-column backfill. Called out as a follow-up phase at the end of this document.
- Fixing the pre-existing Mistral adapter defects (see Risks — `MistralReranker._score_impl` calls
  `client.messages.create`, which is the Anthropic shape, not the Mistral SDK's; `MistralGenerator`
  reads `self._client.api_key` off a `Mistral` object). User chose to keep all adapters; these are
  noted, not repaired, here.
- Any frontend change. The SSE contract is unchanged.

**Hard constraints**

- `mypy --strict` and `ruff` (line-length 100, `E,F,I,UP,B,C4,SIM`) must stay green.
- The default test run (`-m 'not live'`) must remain fully offline.
- The `Generator`/`Reranker`/`Rewriter`/`Embedder` protocols do not change — call sites in
  `api/routes/conversations.py`, `retrieval/pipeline.py`, `worker/tasks.py` stay untouched.

**Trade-offs**

- Prioritising cost over answer quality: `gpt-oss-120b` class models are meaningfully weaker than
  `claude-sonnet-5` at instruction-following and citation discipline. Anthropic stays one env var
  away, so a quality regression is a rollback, not a rewrite.
- Prioritising the OpenAI-compatible router over the `huggingface_hub.InferenceClient` for
  chat/rerank/rewrite: no new dependency, familiar streaming shape, server-side provider failover.
  The cost is that the router's `/v1` surface is chat-only, which is exactly why embeddings need a
  different client.

## Architecture & Design

### High-Level Flow

```
                     ┌──────────────────── config.py ────────────────────┐
                     │ chat_provider / rerank_provider / embedding_provider│
                     │ hf_token, hf_base_url, hf_bill_to, *_model          │
                     └───────────────┬───────────────────────────────────-┘
                                     │
        build_generator()   build_rewriter()   build_reranker()   build_embedder()
                │                  │                 │                  │
       ┌────────┴────────┐  ┌──────┴──────┐   ┌──────┴──────┐   ┌───────┴───────┐
       │ HFGenerator     │  │ HFRewriter  │   │ HFReranker  │   │ HFEmbedder    │
       │ (AsyncOpenAI)   │  │ (OpenAI)    │   │ (OpenAI)    │   │ (InferenceCl.)│
       └────────┬────────┘  └──────┬──────┘   └──────┬──────┘   └───────┬───────┘
                └──────────────────┴─────────────────┘                  │
                          router.huggingface.co/v1                      │
                          /chat/completions                    router.huggingface.co
                                                               feature-extraction task
```

Chat, rewrite and rerank all speak one protocol (OpenAI chat completions) to one base URL. Only the
model id and the parsing differ. Embeddings take a separate path because the router's OpenAI-
compatible surface **does not expose `/v1/embeddings`** — the docs state it is "currently available
for chat completion tasks only" — so the feature-extraction task must be called through
`huggingface_hub.InferenceClient`.

### Key Changes

#### `app/llm/hf_client.py` (new package `app/llm/`)

Single place that knows the router exists:

```python
HF_ROUTER_BASE_URL = "https://router.huggingface.co/v1"

def build_hf_sync_client(settings: Settings) -> OpenAI: ...
def build_hf_async_client(settings: Settings) -> AsyncOpenAI: ...
def hf_extra_headers(settings: Settings) -> dict[str, str]:
    """{'X-HF-Bill-To': org} when hf_bill_to is set, else {}."""

def strip_reasoning(text: str) -> str:
    """Drop <think>…</think> / <reasoning>…</reasoning> blocks some open models emit."""

def extract_json_object(text: str) -> str:
    """Unwrap ```json fences and return the outermost {...} span; raises ValueError if absent."""
```

`strip_reasoning` and `extract_json_object` are the difference between "works on the model I tested"
and "works across `:cheapest` routing". Open-weight models routinely emit a reasoning preamble or a
fenced block where Claude's structured-output API returned parsed objects.

The token comes from `settings.hf_token`, falling back to `settings.llm_api_key` so a single-key
deployment keeps working.

#### `chat/generate.py` — `HFGenerator`

```python
class HFGenerator:
    def __init__(self, client: Any, model: str, max_tokens: int,
                 extra_headers: dict[str, str] | None = None) -> None: ...

    async def stream(self, system: str, messages: list[ChatMessage]) -> AsyncIterator[StreamEvent]:
        stream = await self._client.chat.completions.create(
            model=self._model,
            max_tokens=self._max_tokens,
            messages=[{"role": "system", "content": system},
                      *({"role": m.role, "content": m.content} for m in messages)],
            stream=True,
            stream_options={"include_usage": True},   # ← without this, usage is never sent
            extra_headers=self._extra_headers,
        )
        ...
```

Three details that differ from the Anthropic adapter and are easy to get wrong:

1. **System prompt is a message**, not a top-level `system=` argument.
2. **`stream_options={"include_usage": True}`** is mandatory or the final chunk carries no `usage`,
   and `GenerationDone` degrades to `None`/`None` — which silently kills the cost measurement that
   justifies this whole change. Some providers still omit it; the adapter must tolerate `None`.
3. **`finish_reason`** arrives on the last choice-bearing chunk (`"stop"` / `"length"` / `"tool_calls"`),
   and the usage-only chunk that follows has an empty `choices` list. Capture `finish_reason` and
   `usage` independently, then emit one `GenerationDone(stop_reason=finish_reason)`. The chat
   pipeline's `truncated` flag depends on `"length"` surviving this.

Also: skip `delta.reasoning_content` / `delta.reasoning` if present — yield only `delta.content`.

#### `chat/rewrite.py` — `HFRewriter`

Straight port of `AnthropicRewriter`: system + one user message, `max_tokens=512`, read
`choices[0].message.content`, run it through `strip_reasoning`, keep the existing
empty-or-over-500-chars guard and the never-raise contract. Usage line logs
`provider="huggingface"` with `usage.prompt_tokens`/`usage.completion_tokens`.

#### `retrieval/rerank.py` — `HFReranker`

The Anthropic path uses `client.messages.parse(output_format=RerankScores)`. The router has no
equivalent guarantee — `response_format` support varies by underlying provider. Strategy:

1. Send `response_format={"type": "json_schema", "json_schema": {"name": "rerank_scores",
   "schema": RerankScores.model_json_schema(), "strict": True}}`, plus an explicit output shape in
   the prompt (`{"passages": [{"index": 0, "score": 7}, ...]}`) so unsupported-`response_format`
   models still produce the right thing.
2. On a 400 mentioning `response_format`, retry once without it (cached on the instance so the
   fallback is not re-discovered per call).
3. Parse with `strip_reasoning` → `extract_json_object` → `RerankScores.model_validate_json`.
4. Keep the existing index-set equality check and the `tenacity` retry (`MAX_ATTEMPTS = 6`).

`SCORING_PROMPT` gains one appended line describing the JSON shape; the Anthropic path is unaffected
by that addition (it already returns the same schema).

#### `ingestion/embeddings.py` — `HFEmbedder` (built, not enabled)

```python
class HFEmbedder:
    def __init__(self, client: Any, model: str, batch_size: int = 32,
                 query_prompt_name: str | None = None,
                 passage_prefix: str | None = None) -> None: ...

    def embed(self, texts: list[str]) -> list[list[float]]:
        # client.feature_extraction(text=batch, model=self._model, normalize=True)
```

Two model-specific gotchas worth encoding now rather than discovering during a re-ingest:

- **Asymmetric models need prefixes.** `intfloat/multilingual-e5-large-instruct` and the e5 family
  expect `"query: "` on queries and `"passage: "` on documents. Getting this wrong degrades recall
  quietly. The router exposes `prompt_name` for models with a `sentence-transformers` prompts dict;
  the adapter takes both a `prompt_name` and a literal prefix so either mechanism works.
- **Dimensions are not 1536.** `intfloat/multilingual-e5-large-instruct` → 1024,
  `thenlper/gte-large` → 1024, `Qwen/Qwen3-Embedding-8B` → 4096 (Matryoshka-truncatable). This is
  why the switch is deferred: `chunks.embedding` is `Vector(1536)` in migration
  `0002_ingestion_tables.py`, and `EMBEDDING_DIMENSIONS` is currently only a request parameter.

`build_embedder` gains an `embedding_provider` switch (`openai` default, `huggingface` opt-in) and
asserts that `settings.embedding_dimensions` matches the DB column dimension before returning a
non-OpenAI embedder — a loud failure at build time beats a `DataError` mid-ingest.

#### `config.py` additions

```python
# Providers
hf_token: str | None = None            # HF_TOKEN
hf_base_url: str = "https://router.huggingface.co/v1"
hf_bill_to: str | None = None          # X-HF-Bill-To for org billing

# Ingestion — embeddings
embedding_provider: str = "openai"     # openai | huggingface
hf_embedding_model: str = "intfloat/multilingual-e5-large-instruct"
hf_embedding_query_prefix: str = "query: "
hf_embedding_passage_prefix: str = "passage: "

# Retrieval
rerank_provider: str = "huggingface"           # was "anthropic"
rerank_model: str = "openai/gpt-oss-120b:cheapest"      # was "claude-haiku-4-5"

# Chat
chat_provider: str = "huggingface"             # was "anthropic"
chat_model: str = "openai/gpt-oss-120b:cheapest"        # was "claude-sonnet-5"
chat_rewrite_model: str = "openai/gpt-oss-20b:cheapest" # was "claude-haiku-4-5"
```

The `:cheapest` suffix is part of the model string, so pinning a provider (`:groq`, `:together`) or
a policy (`:fastest`, `:preferred`) is a `.env` edit with no code change — which is what was asked
for. Suffix semantics: `:fastest` is the router default, `:cheapest` picks lowest price per output
token, `:preferred` follows the account's provider order.

### Alternative Approaches Considered

**Transport for chat/rewrite/rerank**

- **OpenAI SDK against `router.huggingface.co/v1` — chosen.** `openai>=1.60` is already a dependency
  (embeddings use it). Async streaming, retries, and typed responses come free, and the router does
  server-side provider failover.
- `huggingface_hub.InferenceClient`: one client for chat *and* embeddings, plus client-side provider
  selection. Rejected for chat because it adds an async-streaming surface the team hasn't used and
  duplicates what the OpenAI client already does well. Still used for embeddings — no alternative.
- Raw `httpx`, like the existing `MistralGenerator`: rejected. That adapter is exactly the reason —
  hand-rolled SSE parsing with `except Exception: pass` swallowing every decode error, and no usage
  accounting.

**Embeddings via the router**

- `POST /v1/embeddings`: not available. HF documents the OpenAI-compatible endpoint as chat-only,
  with embeddings support listed as a future rollout. Only three partners expose feature-extraction
  at all today (HF Inference, Scaleway, Together), so a provider-pinning concern exists here that
  chat does not have.
- Keep OpenAI embeddings: chosen for now. Embeddings are a one-time-per-document cost; at
  `text-embedding-3-small` prices they are a rounding error next to per-answer generation. The cost
  argument for switching is weak; the migration cost is real.

**Rerank strategy**

- LLM-as-judge over the router — chosen, because it preserves the existing prompt, schema, and
  degrade path exactly.
- A dedicated cross-encoder (`BAAI/bge-reranker-v2-m3`) via the text-ranking task: likely better and
  cheaper per call, but it is not in the partner capability matrix on the Inference Providers index
  page, so availability is uncertain. Noted as a future optimisation, not a dependency of this plan.

## Implementation Steps

1. **Config** — add `hf_token`, `hf_base_url`, `hf_bill_to`, `embedding_provider`,
   `hf_embedding_model`, and the prefix settings to `Settings`. Do **not** flip the provider
   defaults yet (step 9), so intermediate commits keep the suite green.
2. **`app/llm/__init__.py` + `app/llm/hf_client.py`** — client builders, `hf_extra_headers`,
   `strip_reasoning`, `extract_json_object`. Pure functions, fully unit-testable.
3. **Tests for step 2** — `tests/test_hf_client.py`: fenced JSON, JSON with prose around it,
   `<think>` blocks, malformed input raising `ValueError`, bill-to header on/off.
4. **`HFGenerator`** in `chat/generate.py` + `huggingface` branch in `build_generator`. Handle
   usage-only trailing chunks, `finish_reason` capture, missing `usage`, and reasoning deltas.
5. **Tests for step 4** — `tests/test_generate.py` (new): a fake async client yielding a scripted
   chunk sequence; assert deltas in order, exactly one `GenerationDone`, correct token counts,
   `stop_reason == "length"` propagation, and graceful `None` usage.
6. **`HFRewriter`** + `build_rewriter` branch + tests (never raises; oversized/empty output falls
   back to the original question; reasoning stripped).
7. **`HFReranker`** + `build_reranker` branch + `SCORING_PROMPT` output-shape line. Tests cover
   clean JSON, fenced JSON, reasoning-prefixed JSON, index mismatch → `ValueError`, and the
   `response_format`-unsupported retry path.
8. **`HFEmbedder`** + `embedding_provider` switch in `build_embedder` + dimension guard + tests with
   a stub client (assert batching, prefixes applied, order preserved). Add `huggingface_hub` to
   `pyproject.toml` dependencies.
9. **Flip defaults** — `chat_provider`/`rerank_provider` → `huggingface`, model defaults to the
   `gpt-oss` ids. Fix any test that asserted the old defaults (`tests/test_config.py`,
   `tests/test_rerank.py::test_build_reranker_uses_anthropic_with_key` still passes since it sets
   the provider explicitly).
10. **Live smoke test** — `tests/test_hf_live.py`, marked `live`: one real chat completion (asserts
    non-empty text and non-zero usage) and one real rerank (asserts a parseable score list). Extend
    the `live` marker description in `pyproject.toml`, which currently names only OpenAI.
11. **Docs** — `.env.example` (HF_TOKEN, model id format with suffix semantics, note that
    LLM_API_KEY is the fallback), `README.md` provider table, `PRD.md` provider section.
12. **Manual verification** — run a real conversation against a seeded PDF, read the usage log
    lines, compute per-answer cost, and compare against the Anthropic baseline.

### Risks & Mitigations

- **Risk: no usage data returned.** Some routed providers ignore `stream_options.include_usage`, so
  `GenerationDone` gets `None`s and the cost success-criterion becomes unmeasurable.
  - Mitigation: adapter treats missing usage as `None` (no crash), and logs a one-time warning
    naming the model so it is visible rather than silent.
  - Mitigation: fall back to `tiktoken` (already a dependency) for an approximate output-token count
    in the usage log, flagged `estimated: true`.
- **Risk: `:cheapest` routes to a different provider between calls**, so JSON-mode support, latency,
  and `finish_reason` vocabulary vary run to run — a rerank that worked in testing 400s in prod.
  - Mitigation: the tolerant parse path (fence stripping, reasoning stripping, prompt-declared
    schema) means correctness never depends on `response_format` being honoured.
  - Mitigation: if instability shows up, pin `:together` or `:groq` in `.env` — no code change.
- **Risk: quality regression in grounded answers and citation discipline.** `gpt-oss-120b` is not
  `claude-sonnet-5`; expect weaker adherence to "cite only what's in the passages".
  - Mitigation: keep the Anthropic adapters and re-verify the ungrounded path
    ("I couldn't find information about this in the document") before flipping defaults.
  - Mitigation: rerank and rewrite can stay on Anthropic independently — the two providers are
    separate settings, and rerank/rewrite are the cheap calls anyway.
- **Risk: credits exhausted → HTTP 402.** Free accounts get $0.10/month of credits, PRO $2.00; past
  that, pay-as-you-go requires a credit purchase. A 402 mid-stream currently surfaces as a generic
  SSE error.
  - Mitigation: map 402/429 to a distinct log line and a user-facing error message that names
    billing rather than "generation failed".
  - Mitigation: `tenacity` must **not** retry 402 — retrying a hard billing failure six times with
    backoff just delays the error by ~a minute.
- **Risk: context window.** `retrieval_top_k=30` passages at up to 1200 chars each plus history is a
  large rerank prompt; smaller/cheaper models have tighter contexts than Claude's.
  - Mitigation: `GET /v1/models` on the router reports per-model context length — verify the chosen
    model's window before setting it as default, and keep `rerank_max_tokens=2048`.
- **Risk (pre-existing, unmasked by this work): the Mistral adapters are broken.**
  `MistralReranker._score_impl` and `MistralRewriter.rewrite` call `client.messages.create`, which
  is the Anthropic SDK shape, and `MistralGenerator` reads `.api_key` off the `Mistral` client
  object. `mistralai` is not even in `pyproject.toml`, so these paths always fall back to the fakes.
  - Mitigation: out of scope here, but the HF adapters should not copy their structure. Flagged for
    a separate cleanup ticket.

## Test Strategy

**Unit (offline, default run)**

- `hf_client`: JSON extraction (clean / fenced / prose-wrapped / `<think>`-prefixed / garbage),
  reasoning stripping, bill-to header presence.
- `HFGenerator`: scripted fake async client — delta ordering, single terminal `GenerationDone`,
  usage propagation, `finish_reason="length"` → `stop_reason`, usage-absent tolerance,
  `reasoning_content` ignored.
- `HFRewriter`: happy path; empty result → original question; >500 chars → original question;
  exception → original question (never raises).
- `HFReranker`: score extraction from each dirty-output variant; index-set mismatch raises;
  `response_format` 400 triggers the once-only fallback; retry count honoured.
- `HFEmbedder`: batching boundaries, prefix application, order preservation, dimension guard.
- `build_*` factories: correct class per `provider` value; fake fallback when no token.

**Integration (offline)**

- Existing `tests/test_chat_api.py` SSE flow, with `fake_llm` unchanged — proves the protocol
  boundary held and no call site needed edits.
- `tests/test_config.py` covers the new defaults and the `hf_token` → `llm_api_key` fallback.

**Live (opt-in, `-m live`)**

- One real streamed chat completion: non-empty text, usage present, `finish_reason` present.
- One real rerank over 3 short passages: parseable, correct index set.

**Manual**

- Full conversation over a seeded PDF: grounded answer with citations, a follow-up that exercises
  rewrite, and an off-topic question that must hit the ungrounded response.
- Compare answer quality side by side against `CHAT_PROVIDER=anthropic` on the same 5 questions.

## Cost Model (approximate — verify before quoting)

Per answer, roughly: rerank ~10–12k input / ~300 output; generation ~4–6k input / ~500 output;
rewrite ~500 input / ~50 output.

| Setup | Approx. $/1M in / out | Approx. $/answer |
| --- | --- | --- |
| `claude-sonnet-5` gen + `claude-haiku-4-5` rerank | 3.00 / 15.00 and 1.00 / 5.00 | ~$0.03 |
| `openai/gpt-oss-120b:cheapest` everywhere | ~0.04–0.15 / ~0.17–0.60 | ~$0.002 |

Third-party price aggregators disagree by 3–4× on open-model rates, and HF passes provider pricing
through with no markup, so treat the table as an order-of-magnitude sketch. The authoritative source
is `GET https://router.huggingface.co/v1/models`, which returns per-provider pricing, context length,
latency and throughput — hit it during step 12 and record the real numbers in the PR description.

## Success Checklist

- [ ] All success criteria met, with the measured cost figure recorded from real usage logs
- [ ] `uv run pytest` green (offline), `-m live` green with a real `HF_TOKEN`
- [ ] `ruff` and `mypy --strict` clean
- [ ] `.env.example`, `README.md`, `PRD.md` updated
- [ ] Manual side-by-side quality check done vs Anthropic; result written down
- [ ] Rollback verified: `CHAT_PROVIDER=anthropic RERANK_PROVIDER=anthropic` restores old behaviour
      with no code change

## Timeline & Estimates

- Steps 1–3 (config + shared client + tests): ~1.5 h
- Steps 4–7 (generator, rewriter, reranker + tests): ~4 h
- Step 8 (embedder + tests + dep): ~1.5 h
- Steps 9–11 (defaults flip, live test, docs): ~1.5 h
- Step 12 (manual verification + cost measurement): ~1 h
- **Total: ~9.5 h**, plus buffer for whatever the routed provider does differently than documented.

## Follow-Up: Embeddings Cutover (separate plan)

Not part of this work, but the shape is fixed by the decisions above:

1. Choose the model and lock its dimension (`multilingual-e5-large-instruct` → 1024).
2. Alembic migration adding `chunks.embedding_hf Vector(1024)`, nullable, plus its index.
3. Backfill job re-embedding every chunk into the new column (Celery task, resumable).
4. Flip `EMBEDDING_PROVIDER=huggingface` and switch `retrieval/search.py` to the new column.
5. Migration dropping the old column and renaming.

Doing it as a dual column is what keeps search working throughout; a straight `ALTER TYPE` on
`chunks.embedding` means broken retrieval until the last chunk is re-embedded.

## Open Questions

- [ ] Is the HF account free-tier ($0.10/month) or PRO ($2.00/month)? At free-tier credits, the
      manual verification pass in step 12 could exhaust the month's budget on its own.
- [ ] Should rerank stay on Anthropic (`claude-haiku-4-5`) initially, so only generation moves? It
      isolates the quality risk to one call, at ~20% of the cost saving.
