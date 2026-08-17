# Phase 4 — Chat Pipeline — Implementation Plan

> **Partly superseded (2026-08-18).** The four-provider adapter switch this plan chose (option A in
> "Generation provider") was collapsed to one path. `AnthropicGenerator`, `MistralGenerator`,
> `OllamaGenerator` and their rewriter twins are deleted, as are `chat_provider` and the
> `LLM_API_KEY` fallback; what remains is `LLMGenerator` / `LLMRewriter` over an OpenAI-compatible
> endpoint (`LLM_BASE_URL`, `LLM_TOKEN`), with `FakeGenerator` / `FakeRewriter` when no token is
> set. The `Generator` and `Rewriter` protocols, SSE contract, prompts, history capping and
> persistence are unchanged. Current state: README "LLM configuration", PRD §8 Phase 8.

## Summary

Phase 3 shipped a search endpoint that returns chunks; nothing turns them into an answer. Phase 4
adds the conversation layer: persisted conversations and messages, query rewriting for follow-ups,
streamed answer generation over SSE, and citation persistence. After this phase the backend is
feature-complete for US-3, US-4, US-5, US-6 and US-7 — Phase 5 is pure frontend.

## Success Criteria

- `POST /conversations/{id}/messages` streams `sources` → `token`* → `done` as `text/event-stream`,
  with the first byte on the wire in under 3 s on a READY 300-page book (PRD §2.5).
- Answers cite pages as `[p.N]` and are drawn only from the retrieved chunks; a question with no
  relevant content streams the canned refusal and persists `grounded=false` with zero
  `message_sources` rows (US-5).
- A follow-up like "and what about his brother?" resolves against the prior turns — the rewritten
  standalone question is what gets embedded, not the raw pronoun form (US-6).
- `GET /conversations/{id}/messages` returns the full thread, in order, with per-message page
  citations, after a server restart (US-7).
- A client that disconnects mid-stream leaves a persisted assistant message flagged `truncated=true`
  — no orphan user message, no silently-complete-looking partial.
- `pytest apps/api/tests` passes offline — no Anthropic or OpenAI key required.

## Scope & Constraints

**In scope**
- `conversations`, `messages`, `message_sources` tables + migration `0003` (PRD §3).
- Query rewriting (PRD §5 step 1).
- Streamed generation with a pluggable provider (PRD §5 step 5), mirroring `build_reranker`.
- Citation persistence (PRD §5 step 6, message + `message_sources`).
- Endpoints: create/list conversations, list messages, delete conversation, send message (SSE).

**Out of scope**
- Token/cost logging for the chat calls — Phase 6 (`re-rank` already logs its own usage). The
  generator interface carries a terminal usage event so Phase 6 is a wiring change, not a rewrite.
- Concurrency guard (409 on a second in-flight stream per conversation) — not in the PRD.
- Explicit cancel endpoint — plain disconnect is handled, that is enough for v1.
- Retry, delete cascade for documents, size validation — Phase 6.
- Any frontend work — Phase 5.

**Hard constraints**
- The API is async (asyncpg). Generation must stream without blocking the event loop, so the chat
  providers use **async** clients (`AsyncAnthropic`, `httpx.AsyncClient`) rather than the
  `anyio.to_thread.run_sync` trick `retrieval/pipeline.py` uses for the sync embedder/reranker.
- First token under 3 s. Rewrite + embed + search + re-rank all happen *before* generation starts,
  so the pre-generation phase is the latency budget — see **Risks**.
- The request-scoped `DbSession` is closed when the response generator is torn down. Persistence
  inside the stream must use its own session.

**Trade-offs**
- One roundtrip (SSE straight off the POST) over reconnectable streaming (POST + GET). Matches PRD
  §6 exactly and keeps server-side stream state at zero; the cost is that the frontend must use
  `fetch` + `ReadableStream` instead of native `EventSource`. We control the client, so this is free.
- Availability over strictness on rewrite: a rewrite failure degrades to the raw question rather
  than failing the request — same posture as the re-rank degrade in Phase 3.
- Superset of the PRD's `sources` event shape (chunk-level, not just page numbers) so Phase 5 can
  build a citation panel without a second endpoint. Costs a few KB per answer.

---

## Architecture & Design

### High-Level Flow

```
POST /conversations/{id}/messages  { "content": "..." }
  │
  ├─ 404 if conversation unknown
  ├─ 409 if its document.status != READY
  │
  ▼  (still on the request session — errors here are real HTTP errors)
persist user message (order_index = n)
set conversation.title if unset
  │
  ▼  200 text/event-stream — from here every failure is an in-stream `error` event
  │   [own AsyncSessionLocal() session opens; heartbeats every 15 s until first token]
  │
1. Rewrite          prior turns + question → Haiku → standalone question
                    no prior turns → skip. failure → raw question, WARNING logged
  │
2. Retrieve         retrieval.pipeline.search(session, document_id, standalone_q)
  │
  ├─ not grounded ─→ event: sources { results: [], pages: [] }
  │                  event: token   { text: "I couldn't find that in this document." }
  │                  persist assistant message (grounded=false, no sources)
  │                  event: done    { message_id }
  │
3. Generate         event: sources { results: [...8 chunks...], pages: [12, 47] }
                    Sonnet 5, streamed → event: token { text } per delta
                    context: 8 chunks with page metadata + last 6 turns
  │
4. Persist          assistant message + message_sources rows (score, rank)
                    event: done { message_id }
                    [disconnect → same write, truncated=true, under a shielded scope]
```

### Key Changes

**`app/db/models/conversation.py`, `message.py`, `message_source.py`** — new. Registered in
`app/db/models/__init__.py` (the module docstring already promises "conversations/messages land in
Phase 4").

```python
class Conversation(Base):
    __tablename__ = "conversations"
    id: UUID (pk)
    document_id: UUID  FK documents.id ON DELETE CASCADE, indexed
    title: str | None  String(200)
    created_at, updated_at: datetime (server_default now(), onupdate now())
    document: Document
    messages: list[Message]  # cascade all, delete-orphan, order_by Message.order_index

class MessageRole(enum.StrEnum):
    USER = "user"
    ASSISTANT = "assistant"

class Message(Base):
    __tablename__ = "messages"
    id: UUID (pk)
    conversation_id: UUID  FK conversations.id ON DELETE CASCADE, indexed
    role: MessageRole      Enum(native_enum=True, name="message_role")
    content: str           Text
    order_index: int       UniqueConstraint(conversation_id, order_index)
    # assistant-only, NULL on user rows:
    grounded: bool | None       # False → the guard fired, US-5 is verifiable from the DB
    truncated: bool             # default False; True when the client disconnected mid-stream
    created_at: datetime
    sources: list[MessageSource]  # cascade all, delete-orphan, order_by MessageSource.rank

class MessageSource(Base):
    __tablename__ = "message_sources"
    id: UUID (pk)
    message_id: UUID  FK messages.id ON DELETE CASCADE, indexed
    chunk_id: UUID    FK chunks.id ON DELETE CASCADE
    score: int | None   # re-rank score, NULL when the re-ranker degraded
    rank: int           # 0-based position in the final ordering
    UniqueConstraint(message_id, chunk_id)
```

`order_index` rather than ordering on `created_at`: the user row and the assistant row are written
seconds apart in the same logical turn, and deterministic ordering makes the message-list test an
equality assertion instead of a timestamp comparison. Same pattern as `Chunk.order_index`.

`message_sources.chunk_id` cascades: deleting a document already takes its chunks and (via
`conversations.document_id`) its conversations, so there is no window where a citation outlives its
chunk.

**`alembic/versions/0003_chat_tables.py`** — creates the three tables and the `message_role` enum.
Follows `0002`'s shape: explicit `sa.Enum(..., name="message_role")`, dropped in `downgrade()`.

**`app/chat/generate.py`** — new. The generation seam, shaped like `retrieval/rerank.py`:

```python
@dataclass
class ChatMessage:
    role: str      # "user" | "assistant"
    content: str

@dataclass
class TextDelta:
    text: str

@dataclass
class GenerationDone:
    input_tokens: int | None
    output_tokens: int | None

StreamEvent = TextDelta | GenerationDone

class Generator(Protocol):
    def stream(
        self, system: str, messages: list[ChatMessage]
    ) -> AsyncIterator[StreamEvent]:
        """Yield text deltas, then exactly one GenerationDone."""
        ...

def build_generator(settings: Settings | None = None) -> Generator: ...
```

Implementations: `AnthropicGenerator`, `MistralGenerator`, `OllamaGenerator`, `FakeGenerator`.
`build_generator` follows `build_reranker` exactly — Ollama needs no key, a missing `llm_api_key`
falls back to `FakeGenerator` with a WARNING, an unknown provider does the same.

`AnthropicGenerator` uses the **async** client, unlike the reranker's sync one:

```python
from anthropic import AsyncAnthropic

async def stream(self, system, messages):
    async with self._client.messages.stream(
        model=self._model,
        max_tokens=self._max_tokens,
        system=system,
        thinking={"type": "disabled"},
        messages=[{"role": m.role, "content": m.content} for m in messages],
    ) as stream:
        async for text in stream.text_stream:
            yield TextDelta(text=text)
        final = await stream.get_final_message()
    yield GenerationDone(
        input_tokens=final.usage.input_tokens,
        output_tokens=final.usage.output_tokens,
    )
```

Three API details that are easy to get wrong and worth pinning here:

- **`thinking={"type": "disabled"}` is required.** On `claude-sonnet-5` adaptive thinking is on
  when the field is omitted (this changed from Sonnet 4.6). Thinking would spend seconds before the
  first visible token and blow the 3 s budget for a task that needs no multi-step reasoning.
- **No `temperature` / `top_p` / `top_k`.** Sonnet 5 rejects non-default sampling parameters with a
  400. Answer style is steered by the system prompt only.
- **`max_tokens` covers thinking + text together**, so with thinking off it is purely the answer
  budget. 2048 is roughly 1500 words — ample for a detailed answer.

`FakeGenerator` yields the retrieved page numbers plus a deterministic sentence, word by word, with
no sleep — enough for tests to assert citation persistence and streaming shape without a network.

**`app/chat/rewrite.py`** — new. `Rewriter` protocol + `build_rewriter(settings)`, same provider
switch, using the **sync** Anthropic client through `anyio.to_thread.run_sync` (one short
non-streaming call, so the reranker's pattern applies unchanged).

```python
async def rewrite(question, history, rewriter, settings) -> str
```

Returns `question` verbatim when `history` is empty (saves a roundtrip and ~300 ms on every new
conversation) and on any exception, malformed output, empty result, or a rewrite longer than 500
characters — logging a WARNING each time. Never raises.

**`app/chat/prompts.py`** — new. Two prompts, kept beside the re-ranker's `SCORING_PROMPT` in
spirit:

```python
ANSWER_PROMPT = """You answer questions about one book, using only the passages provided.
Cite the page for every claim, inline, as [p.N] — use the page range given with each passage.
If the passages do not contain the answer, say so plainly; never fill the gap from your own
knowledge. Write an analytical answer: explain the reasoning the text supports, not just a
one-line lookup."""

REWRITE_PROMPT = """Rewrite the user's latest message as a standalone question that makes sense
without the conversation history. Resolve pronouns and implicit references against the earlier
turns. Do not answer it. Return only the rewritten question."""
```

**`app/chat/pipeline.py`** — new. `answer()` is an async generator of `StreamEvent`-ish domain
events (`SourcesEvent`, `TokenEvent`, `DoneEvent`, `ErrorEvent`); the route only serializes them.
Keeping SSE framing out of the pipeline is what makes it testable without an HTTP client.

**`app/services/conversations.py`** — new. Create/list/get/delete plus `next_order_index()` and
`recent_turns(conversation_id, limit)`. Title is set on first message from the first 60 characters
of the question (word-boundary trimmed, `…` appended if cut).

**`app/api/routes/conversations.py`** — new, `APIRouter(tags=["chat"])` with explicit paths since
the endpoints straddle two prefixes:

```
POST   /documents/{document_id}/conversations  → ConversationRead        201
GET    /documents/{document_id}/conversations  → ConversationRead[]
GET    /conversations/{id}/messages            → MessageRead[]
DELETE /conversations/{id}                     → 204
POST   /conversations/{id}/messages            → SSE
```

Registered in `app/api/routes/__init__.py`.

**`app/schemas/chat.py`** — new. `ConversationRead`, `MessageRead` (with `sources: SourceRead[]`,
`grounded`, `truncated`), `SendMessageRequest { content: str = Field(min_length=1, max_length=4000) }`,
and the SSE payload models so the event shapes are typed rather than hand-built dicts.

**`app/config.py`** — six new settings, chat-scoped so the re-ranker can stay on a different
provider (Haiku re-ranking with Sonnet generation is exactly PRD §5):

```python
chat_provider: str = "anthropic"        # anthropic | mistral | ollama
chat_model: str = "claude-sonnet-5"
chat_rewrite_model: str = "claude-haiku-4-5"
chat_max_tokens: int = 2048
chat_history_turns: int = 6             # PRD §5: last 6 turns
chat_heartbeat_seconds: float = 15.0
```

### SSE wire format

`StreamingResponse(..., media_type="text/event-stream")` with
`Cache-Control: no-cache`, `Connection: keep-alive`, `X-Accel-Buffering: no` (the last one stops a
future nginx from buffering the whole answer into one chunk).

```
event: sources
data: {"results":[{"chunk_id":"…","page_start":12,"page_end":13,"score":9,
                   "section_title":"Chapter 2","snippet":"…240 chars…"}],
       "pages":[12,47,103]}

event: token
data: {"text":"The "}

event: done
data: {"message_id":"…","grounded":true,"truncated":false}

event: error
data: {"detail":"generation failed"}
```

`pages` is the deduplicated, sorted union of each result's `page_start..page_end`, so a client that
only wants the PRD §6 shape reads one field and ignores the rest. A `:heartbeat` comment line goes
out every `chat_heartbeat_seconds` until the first real event.

### The two-session rule

The route validates on the injected `DbSession` and persists the user message there — those are
ordinary HTTP failures and belong before the 200. The streaming generator then opens its **own**
`AsyncSessionLocal()`, because FastAPI tears down request-scoped dependencies when the response
generator finishes, and on a client disconnect the teardown races the final write.

The final write is wrapped in `anyio.CancelScope(shield=True)` so that a cancellation delivered at
disconnect cannot interrupt it half-way:

```python
except anyio.get_cancelled_exc_class():
    with anyio.CancelScope(shield=True):
        await persist_assistant(session, buffer, truncated=True, ...)
    raise
```

### Alternative Approaches Considered

**Streaming transport.** (A) POST returns the stream — one roundtrip, matches PRD §6, no server-side
stream state; needs `fetch` on the client. (B) POST then `GET .../stream` — native `EventSource`,
reconnectable, but two roundtrips, a deviation from the contract, and a server-side buffer keyed by
message id that has to be evicted. **Chose A**; reconnect matters for hour-long agent runs, not for
a 10-second answer the user is watching.

**Generation provider.** (A) Mirror the reranker adapter — four implementations, `FakeGenerator`
drives CI. (B) Hardcode the Anthropic SDK and extract later. **Chose A**: PRD §1 lists the LLM as
configurable, and without a fake, every chat test needs HTTP mocking against a streaming SDK, which
is materially harder to keep honest than a 15-line fake.

**History cap.** (A) Fixed `chat_history_turns` — no tokenizer on the hot path, deterministic in
tests. (B) Token budget via tiktoken — handles one pathologically long answer better, costs a
tokenizer pass per request. (C) Both. **Chose A**; the PRD names 6 turns, and `max_tokens=2048`
already bounds how long any single stored answer can be, which is what a token budget would be
guarding against.

**Disconnect handling.** (A) Persist partial, flag `truncated`. (B) Discard. (C) Persist unflagged.
**Chose A**: (B) leaves a question with no answer on reload, which reads as data loss; (C) makes a
cut-off answer indistinguishable from a complete one, which is the same class of dishonesty US-5
exists to prevent.

---

## Implementation Steps

1. Add `conversation.py`, `message.py`, `message_source.py` under `app/db/models/`; export them from
   `__init__.py` and update its docstring.
2. Generate migration `0003_chat_tables.py`; verify `test_migrations.py` still round-trips
   upgrade→downgrade.
3. Extend `Settings` with the six `chat_*` fields; extend `test_config.py`.
4. `app/chat/prompts.py` — `ANSWER_PROMPT`, `REWRITE_PROMPT`.
5. `app/chat/generate.py` — protocol, dataclasses, `FakeGenerator`, `build_generator`. Anthropic,
   Mistral, Ollama implementations behind it.
6. `app/chat/rewrite.py` — protocol, `FakeRewriter` (echoes the question), `build_rewriter`,
   `rewrite()` with the skip-first-turn and degrade-on-failure rules.
7. `app/services/conversations.py` — CRUD, `next_order_index`, `recent_turns`, title derivation.
8. `app/chat/pipeline.py` — `answer()` async generator: rewrite → search → guard branch → generate →
   persist, with the shielded disconnect write.
9. `app/schemas/chat.py` — request/response and SSE payload models.
10. `app/api/routes/conversations.py` — the five endpoints; SSE serialization + heartbeat live here.
11. Register the router in `app/api/routes/__init__.py`.
12. Tests, in the order the modules land (see **Test Strategy**).
13. Update `PRD.md` §8 to mark Phase 4 done, noting the `sources` event superset and the
    `truncated` / `grounded` columns as deviations from §3 and §6.

### Risks & Mitigations

- **First token misses the 3 s budget.** Rewrite (~400 ms) + embed (~200 ms) + vector search
  (~50 ms) + re-rank over 30 candidates (~1–2 s) all precede the first generated token, so the
  budget is nearly spent before Sonnet is called.
  - Skipping rewrite on turn 1 removes one call from the worst-affected path (a fresh conversation).
  - `thinking={"type": "disabled"}` — non-negotiable; adaptive thinking alone would exceed 3 s.
  - If measured p50 still misses: drop `retrieval_top_k` 30 → 15, which the PRD §9 risk table
    already sanctions.
- **Cancellation eats the final write.** A disconnect cancels the task group the generator runs in;
  an unshielded `await session.commit()` there is lost or, worse, half-applied.
  - `anyio.CancelScope(shield=True)` around the persist, own session (not the request-scoped one).
  - Test asserts it directly by closing the httpx stream early.
- **The model cites pages that aren't in the context.** A `[p.999]` in the answer text is a
  fabrication the citation rows won't catch, since those come from retrieval, not from the text.
  - Prompt pins citations to the page ranges supplied with each passage.
  - `message_sources` is the source of truth the UI renders; the inline `[p.N]` is prose.
  - Logged as a known limitation, not solved in v1: validating inline citations against the context
    means parsing generated text, which is its own failure mode.
- **`FakeGenerator` hides a real streaming bug.** The whole suite passing offline says nothing about
  whether the Anthropic SDK's `text_stream` behaves as assumed.
  - One `-m live` test (`test_chat_live.py`) mirroring `test_embeddings_live.py`: real key, real
    stream, asserts deltas arrive and the final usage is populated.
- **Two writers on one conversation interleave.** Two concurrent sends both read `next_order_index`
  and get the same value.
  - `UniqueConstraint(conversation_id, order_index)` turns the race into an `IntegrityError` rather
    than silent corruption. A proper guard (409) is Phase 6; for a single-user local app the
    constraint is the whole mitigation.

## Test Strategy

Unit, offline, `FakeGenerator` / `FakeRewriter`:
- `test_generate.py` — `build_generator` provider switch and no-key fallback (mirrors
  `test_rerank.py`); `FakeGenerator` yields deltas then exactly one `GenerationDone`.
- `test_rewrite.py` — empty history returns the question verbatim with no rewriter call; a raising
  rewriter degrades to the raw question; over-long and empty rewrites are rejected.
- `test_chat_pipeline.py` — grounded path emits sources → tokens → done and writes N
  `message_sources` rows with correct `rank`; the not-grounded path writes `grounded=False` and zero
  source rows; history is capped at `chat_history_turns` turns.
- `test_conversations_service.py` — title derived from the first message and not overwritten on the
  second; `order_index` increments across turns.

Integration, against the docker-compose Postgres (as the existing `test_search_api.py` does):
- `test_chat_api.py` — 404 on unknown conversation, 409 on a non-READY document, full SSE parse of a
  send (event names and order), `GET /conversations/{id}/messages` returns both turns with sources,
  `DELETE` cascades to messages and sources.
- Disconnect: open the stream with `httpx`, read one `token` event, close, then assert a persisted
  assistant message with `truncated=True` and non-empty content.

Opt-in live (`-m live`, skipped without a key):
- `test_chat_live.py` — one real Sonnet stream: deltas arrive, `GenerationDone` carries non-zero
  usage.

Manual:
- Ingest a real book, ask a factual question, then a pronoun follow-up; confirm the rewritten
  question in the logs and that pages in the `sources` event actually contain the answer.
- Ask something plainly absent ("what does this book say about Kubernetes?") and confirm the refusal.

## Success Checklist

- [ ] All six success criteria met, with the latency number measured, not assumed
- [ ] `pytest apps/api/tests` green offline; `-m live` green with keys set
- [ ] `alembic upgrade head` / `downgrade -1` clean on a populated database
- [ ] `ruff` and `mypy --strict` clean (note: async generators need explicit
      `AsyncIterator[...]` returns to satisfy `disallow_untyped_defs`)
- [ ] PRD §8 updated; deviations from §3 and §6 documented as §4's PyMuPDF note was
- [ ] Phase 3's `POST /documents/{id}/search` still passes — the chat pipeline reuses
      `retrieval.pipeline.search` unchanged

## Timeline & Estimates

- Models, migration, settings, services: ~2 h
- `generate.py` + `rewrite.py` + prompts (4 providers, 2 fakes): ~3 h
- `pipeline.py` + SSE route (disconnect shielding is the fiddly part): ~3 h
- Tests: ~3 h
- Review + polish: ~1 h
- **Total**: ~12 h

## Open Questions

None blocking. Two things to revisit after the first real book:

- [ ] Is `chat_history_turns = 6` enough for the follow-up cases that matter, or does rewrite need
      more context to resolve a reference made ten turns back?
- [ ] Does the 240-character `snippet` in the `sources` event give Phase 5 enough to render a useful
      citation hover, or does the UI need the full chunk?
