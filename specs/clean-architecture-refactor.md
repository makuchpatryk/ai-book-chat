# Backend Clean Architecture Refactor — Implementation Plan

## Summary

The API works but its layers leak: `services/` raises `HTTPException`, routers run raw
SQLAlchemy, `services/documents.py` imports the Celery task directly, and the 378-line
`api/routes/conversations.py` owns SSE framing, persistence, cancellation handling *and*
orchestration. Nothing below the router can be tested without Postgres, Redis and a
network. This refactor restructures `apps/api` into pure domain + application + adapters,
with the HTTP/SSE contract frozen so `apps/web` never notices.

---

## Success Criteria

1. **Dependency rule enforced by CI.** `app.domain.*` and `app.application.*` import
   nothing from `fastapi`, `sqlalchemy`, `celery`, `openai`, `httpx`, `pymupdf`, `redis`,
   `tiktoken` or `pydantic_settings`. Verified by an `import-linter` contract wired into
   `pnpm lint` — not by eyeballing.
2. **Business logic testable with infra down.** `docker compose down && uv run pytest -m unit`
   passes, covers every use case, and finishes in < 2 s. Today: 0 tests run without Postgres.
3. **Zero frontend change.** The API contract golden test (added in Step 1, before any
   restructuring) passes unchanged at the end: same paths, same status codes, same `detail`
   strings, same SSE event names and payload keys.
4. **Every I/O touchpoint behind a port.** ~11 Protocols; zero direct infrastructure imports
   inside `application/usecases/`.
5. **Routers are thin.** No router file over ~80 lines; `conversations.py` goes 378 → ~90.
   No `select(...)` anywhere under `interfaces/`.
6. **Existing suite stays green throughout.** All 20 test modules pass after every step —
   they are the regression harness, not collateral.

---

## Scope & Constraints

**In scope** — everything under `apps/api/src/app`, in four vertical slices:
chat → documents → search → ingestion; plus the Celery worker, the test layout, and the
architecture docs.

**Out of scope** — `apps/web` (zero changes), the database schema (no migrations: tables,
columns, indexes and constraints stay byte-identical), prompt text, retrieval quality
tuning, and adding features. Alembic revisions are untouched apart from the import path in
`alembic/env.py`.

**Hard constraints**
- HTTP + SSE contract frozen (criterion 3).
- No schema migration. Mapper functions absorb any entity/table naming difference.
- `mypy --strict` must keep passing (`pnpm typecheck`), including over Protocols and async
  generators.
- Offline mode survives: with `LLM_TOKEN` unset the app must still run on the deterministic
  `Fake*` adapters. They stay in `infrastructure/`, not in `tests/`.

**Trade-offs**
- Explicit mapper functions over imperative mapping: more code, but entities stay genuinely
  import-free and there is no hidden persistence behaviour on a dataclass. Cost is real —
  roughly 6 mapper pairs, ~200 lines.
- Purity over convenience in the domain: `Settings` never crosses into a use case. Small
  policy value objects (`RetrievalPolicy`, `ChunkingPolicy`, `ChatPolicy`) are built at the
  composition root. Costs three extra dataclasses; buys use cases you can construct in a
  unit test with a literal.
- Async everywhere over dual sync/async stacks: the worker loses its sync session and runs
  `asyncio.run`. One implementation of each port instead of two — at the price of an
  event-loop-per-task engine concern (see Risks).

---

## Architecture & Design

### Target layout

```
apps/api/src/app/
├── domain/                      # pure. no imports outside stdlib + app.domain
│   ├── entities/                # document, section, chunk, conversation, message
│   ├── values/                  # DocumentStatus, MessageRole, Citation, RetrievedChunk,
│   │                            #   ScoredChunk, RetrievalPolicy, ChunkingPolicy, ChatPolicy
│   ├── events.py                # AnswerEvent union (SourcesFound/TokenProduced/…)
│   ├── errors.py                # DocumentNotFound, DocumentNotReady, DuplicateUpload, …
│   ├── services/                # pure logic: sections, chunking, relevance guard, titles
│   └── ports/                   # Protocols: repositories, unit_of_work, llm, embedding,
│                                #   pdf, storage, queue, clock
├── application/
│   ├── dto.py                   # commands + results (dataclasses, not pydantic)
│   ├── errors.py                # application-level errors the HTTP layer maps
│   └── usecases/
│       ├── chat/                # ask_question, create_conversation, list_conversations,
│       │                        #   get_messages, delete_conversation
│       ├── documents/           # upload, list, get_detail, delete, retry
│       ├── search/              # search_document
│       └── ingestion/           # ingest_document
├── infrastructure/
│   ├── config/settings.py       # pydantic-settings (moved from app/config.py)
│   ├── db/
│   │   ├── models/              # existing SQLAlchemy models, unchanged
│   │   ├── mappers.py           # row <-> entity
│   │   ├── repositories/        # SqlDocumentRepository, SqlChunkRepository, …
│   │   ├── unit_of_work.py      # SqlAlchemyUnitOfWork + factory
│   │   └── engine.py            # async engine / sessionmaker
│   ├── llm/                     # client.py, openai_generator, openai_rewriter,
│   │                            #   openai_reranker, fakes.py
│   ├── embeddings/              # ollama.py (async httpx), fake.py
│   ├── pdf/pymupdf_extractor.py
│   ├── storage/local_files.py
│   ├── queue/celery_queue.py
│   ├── tokenizer.py
│   └── clock.py
└── interfaces/
    ├── http/
    │   ├── app.py               # create_app
    │   ├── composition.py       # Depends factories -> use cases
    │   ├── errors.py            # exception handlers: app error -> HTTP status + detail
    │   ├── sse.py               # AnswerEvent -> SSE frame; heartbeat wrapper
    │   ├── schemas/             # pydantic wire shapes (moved from app/schemas)
    │   └── routers/             # documents, conversations, search, health
    └── worker/
        ├── celery_app.py
        ├── composition.py       # worker-side factories
        └── tasks.py
```

Dependency rule: `interfaces` → `application` → `domain`; `infrastructure` → `domain`
(implements its ports). `domain` imports nothing of the other three.

### High-level flow — the chat slice

```
POST /conversations/{id}/messages
        │
 interfaces/http/routers/conversations.py
        │  validates body (pydantic), builds AskQuestionCommand
        ▼
 composition.get_ask_question(settings)  ──▶ AskQuestion(
        │                                        uow_factory,   # SqlAlchemyUnitOfWorkFactory
        │                                        rewriter,      # OpenAIRewriter | FakeRewriter
        │                                        embedder,      # OllamaEmbedder | FakeEmbedder
        │                                        reranker,      # OpenAIReranker | FakeReranker
        │                                        generator,     # OpenAIGenerator | FakeGenerator
        │                                        policy)        # ChatPolicy + RetrievalPolicy
        ▼
 async for event in use_case.execute(cmd):     # AsyncIterator[AnswerEvent]
        SourcesFound(citations, pages)
        TokenProduced(text) …
        AnswerCompleted(message_id, grounded, truncated)
        │
 interfaces/http/sse.py:  with_heartbeat(events, 15s) -> frames
        ▼
 text/event-stream:  event: sources / token / done / error
```

The use case opens its **own** unit of work (via the factory), so the stream is not tied to
the request-scoped session — that is exactly what today's hand-rolled
`async with AsyncSessionLocal()` inside `event_generator` is doing, moved to where it
belongs. Persistence of the assistant message + its sources moves into the use case; the
heartbeat and the SSE bytes stay in the transport layer.

### Key changes

**`domain/ports/unit_of_work.py`** — transaction boundary owned by the use case.

```python
class UnitOfWork(Protocol):
    documents: DocumentRepository
    sections: SectionRepository
    chunks: ChunkRepository
    conversations: ConversationRepository
    messages: MessageRepository

    async def __aenter__(self) -> "UnitOfWork": ...
    async def __aexit__(self, *exc: object) -> None: ...   # rolls back unless committed
    async def commit(self) -> None: ...
    async def rollback(self) -> None: ...

class UnitOfWorkFactory(Protocol):
    def __call__(self) -> UnitOfWork: ...
```

Use cases take the **factory**, not an instance. Reason: the chat stream outlives the
request-scoped session, and a factory makes that uniform instead of special-casing one
endpoint. The SQLAlchemy implementation creates a session in `__aenter__` from
`async_sessionmaker` and closes it in `__aexit__`.

**`domain/ports/repositories.py`** — one Protocol per aggregate. Selected signatures:

```python
class DocumentRepository(Protocol):
    async def get(self, document_id: UUID) -> Document | None: ...
    async def get_with_sections(self, document_id: UUID) -> DocumentDetail | None: ...
    async def find_by_hash(self, content_hash: str) -> Document | None: ...
    async def list_newest_first(self) -> list[Document]: ...
    async def add(self, document: Document) -> None: ...
    async def save(self, document: Document) -> None: ...      # explicit write-back
    async def delete(self, document_id: UUID) -> bool: ...
    async def clear_derived(self, document_id: UUID) -> None: ...  # chunks + sections

class ChunkRepository(Protocol):
    async def search_similar(
        self, document_id: UUID, vector: Sequence[float], limit: int
    ) -> list[RetrievedChunk]: ...
    async def replace_for_document(
        self, document_id: UUID, sections: list[Section], chunks: list[EmbeddedChunk]
    ) -> None: ...

class MessageRepository(Protocol):
    async def recent_turns(self, conversation_id: UUID, limit: int) -> list[Turn]: ...
    async def next_order_index(self, conversation_id: UUID) -> int: ...
    async def list_with_citations(self, conversation_id: UUID) -> list[Message]: ...
    async def add(self, message: Message) -> None: ...
```

`SET LOCAL hnsw.ef_search`, the `joinedload`s and the pgvector `cosine_distance` all stay
inside `SqlChunkRepository` — they are storage strategy, invisible above.

**Entities** are frozen-ish dataclasses with the behaviour that is currently scattered
across services and routers:

```python
@dataclass
class Document:
    id: UUID
    filename: str
    title: str
    status: DocumentStatus
    ...
    def retry_eligibility(self, now: datetime, stuck_after: timedelta) -> RetryVerdict:
        """READY -> already_processed; in-flight and fresh -> still_processing; else ok."""
    def mark_ready(self, page_count: int, title: str, strategy: Strategy) -> None: ...
    def mark_failed(self, reason: str) -> None: ...   # truncates to 1000 chars
```

That kills the status branching currently inlined in `services/documents.py:retry_document`
and in `routes/search.py`.

**Answer events** (`domain/events.py`) replace `chat/pipeline.py`'s `SourcesEvent | TokenEvent
| DoneEvent | ErrorEvent`, but carry domain values rather than `list[dict]`:

```python
@dataclass(frozen=True)
class SourcesFound:  citations: list[Citation]; pages: list[int]
@dataclass(frozen=True)
class TokenProduced: text: str
@dataclass(frozen=True)
class AnswerCompleted: message_id: UUID; grounded: bool; truncated: bool
@dataclass(frozen=True)
class AnswerFailed:  detail: str

AnswerEvent = SourcesFound | TokenProduced | AnswerCompleted | AnswerFailed
```

`Citation(chunk_id, page_start, page_end, score, section_title, snippet)` is the single
shape used by the SSE `sources` event *and* by `GET /conversations/{id}/messages` — today
those are built twice from different code (`chat/pipeline.py` dicts vs. the router's manual
join walk), which is why they can drift.

**Ports for the three LLM roles** become async, dropping `anyio.to_thread`:

```python
class AnswerGenerator(Protocol):
    def stream(self, system: str, turns: list[Turn]) -> AsyncIterator[GenerationEvent]: ...
class QueryRewriter(Protocol):
    async def rewrite(self, question: str, history: list[Turn]) -> str: ...
class Reranker(Protocol):
    async def score(self, query: str, passages: list[Passage]) -> list[int]: ...
class Embedder(Protocol):
    async def embed(self, texts: list[str]) -> list[list[float]]: ...
```

Adapters use `AsyncOpenAI` (already a dependency, already used by the generator) and
`httpx.AsyncClient` for Ollama. Tenacity switches to `AsyncRetrying` in the reranker and the
embedder. The degrade-on-failure semantics are preserved exactly: rewrite failure returns the
original question; rerank failure falls back to the distance filter.

**Retrieval** becomes an application-level collaborator `RetrieveContext` (embed → search →
rerank → guard), returning a `RetrievalOutcome` value. The guard logic (min-score cut,
top-N, distance fallback, the three `reason` strings `no_chunks` / `no_relevant_chunks` /
`rerank_degraded_no_match`) moves into a **pure** `domain/services/relevance.py` that takes
scored candidates and a `RetrievalPolicy` and returns the outcome. That is the single
highest-value unit-testable extraction in the codebase.

**Search overrides**: `routes/search.py`'s `deepcopy(settings)` mutation disappears.
`SearchDocumentCommand(query, top_k, min_score)` produces
`RetrievalPolicy.from_settings(...).override(top_k=…, min_score=…)`.

**Queue port** kills the `services → worker` import:

```python
class IngestionQueue(Protocol):
    async def enqueue(self, document_id: UUID) -> None: ...
```
`CeleryIngestionQueue` calls `process_document.delay(str(document_id))`.

**Storage port** for uploads. The size cap and `%PDF-` header check are policy and stay in
the use case; the byte plumbing does not:

```python
class FileStorage(Protocol):
    async def save(self, key: str, chunks: AsyncIterator[bytes], max_bytes: int) -> StoredFile: ...
    async def delete(self, key: str) -> None: ...
    async def exists(self, key: str) -> bool: ...
# StoredFile(path: str, sha256: str, size: int)
```
The router adapts FastAPI's `UploadFile` into `(filename, chunks())` so `fastapi` never
appears in the use case.

**Worker** loses `db/sync_session.py` entirely:

```python
@shared_task(name="app.worker.tasks.process_document", acks_late=True, time_limit=1800)
def process_document(document_id: str) -> str:
    return asyncio.run(_ingest(UUID(document_id)))
```
`_ingest` builds a worker-scoped composition and awaits `IngestDocument.execute(...)`.
Alembic keeps its own sync engine — it never imported the app's session layer beyond the URL.

**Error mapping** (`interfaces/http/errors.py`) — exception handlers, one table, contract
frozen:

| Domain / application error | Status | `detail` |
| --- | --- | --- |
| `DocumentNotFound` | 404 | `document not found` |
| `ConversationNotFound` | 404 | `conversation not found` |
| `DocumentNotReady` (search) | 409 | `document not ready for search` |
| `DocumentNotReady` (chat) | 409 | `document not ready for chat` |
| `DocumentAlreadyProcessed` | 409 | `document is already processed` |
| `DocumentStillProcessing` | 409 | `document is still processing` |
| `SourceFileMissing` | 409 | `original file is missing; re-upload it` |
| `UnsupportedFileType` | 415 | `only PDF files are supported` |
| `FileTooLarge` | 413 | `file exceeds the {n} MB limit` |
| `NotAPdf` | 422 | `file is not a valid PDF (missing %PDF- header)` |

(The two `DocumentNotReady` details differ by an `activity` field on the error, set by the
use case.)

### Alternative approaches considered

**ORM ↔ domain**
- *Imperative mapping* (`registry.map_imperatively` over pure dataclasses) — zero mapper
  code, entities import-clean. Rejected: instances are silently persistent, so "pure" unit
  tests can trigger lazy loads and `MissingGreenlet`, and the async session makes that
  failure mode worse. **Chosen: explicit mappers** — obvious, greppable, no hidden state.
- *ORM models as the domain* — cheapest, but fails success criterion 1 and 2, which is the
  whole point.

**Transactions**
- *Request-scoped session, commit in the route* — current behaviour, less machinery.
  Rejected: the chat stream already had to escape it by hand, and it puts the atomicity
  decision (message + sources together) outside the code that knows about it.
- *Repos commit themselves* — rejected: loses `message + sources` atomicity.
- **Chosen: UoW port**, with a factory so streaming and request handling look the same.

**Streaming**
- *Output-port presenter* (`on_token`, `on_done`) — textbook Uncle Bob, but bridging push to
  an SSE pull loop reintroduces the queue plumbing at a lower level.
- *Two-phase retrieve-then-stream* — splits error handling in two.
- **Chosen: `AsyncIterator[AnswerEvent]`** — one linear flow, the transport does the
  translating, and a unit test just collects the list.

**Async/sync split**
- *Two port families* — rejected: doubles every Protocol for one caller.
- **Chosen: async ports + `asyncio.run` in the Celery task.**

**DI**
- *`dependency-injector`* — nicer overrides, but a new dependency and a second wiring
  vocabulary next to `Depends`.
- **Chosen: `Depends` + hand-written factories in `composition.py`**, plus a parallel
  `interfaces/worker/composition.py`. Adapter construction (LLM clients, embedder) is shared
  by a `build_adapters(settings)` helper so the duplication is factories, not logic.

---

## Implementation Steps

### Step 0 — Safety net and guardrails (do first, no restructuring)

1. Add `tests/test_api_contract.py`: for every endpoint, assert the exact status code and
   `detail` string of each error path, plus the SSE event names and payload keys for a full
   chat turn. This is the frozen-contract oracle; it must pass before and after every later
   step.
2. Add `import-linter` to the dev dependency group, `.importlinter` with layered contracts
   (`domain` < `application` < `interfaces`; `infrastructure` may only reach `domain`), and
   an `arch` script in `apps/api/package.json` wired into `lint`. Contracts start permissive
   (only `domain` is declared) and tighten as each layer lands.
3. Add `unit` / `integration` pytest markers; default run stays as-is.

### Step 1 — Skeleton and moves that change no behaviour

4. Create the package tree with `__init__.py` files.
5. Move `app/config.py` → `app/infrastructure/config/settings.py`; move `app/db/*` →
   `app/infrastructure/db/*`; update `alembic/env.py` and `alembic.ini` script location if
   referenced. Keep `app/db/models/__init__.py` re-exporting from the new home for one
   step so nothing breaks mid-flight.
6. Move `app/schemas/*` → `app/interfaces/http/schemas/*`, `app/main.py` →
   `app/interfaces/http/app.py` (keep `app/main.py` as a 3-line re-export: Docker and
   uvicorn reference `app.main:app`). Move `app/worker/*` → `app/interfaces/worker/*` and
   update the `celery -A` target in `docker-compose.yml` and the README.
7. Run `pnpm lint typecheck test` — everything green, zero logic touched. Commit.

### Step 2 — Chat slice: domain

8. `domain/values/`: `DocumentStatus`, `MessageRole`, `Turn`, `Citation`, `RetrievedChunk`,
   `ScoredChunk`, `RetrievalPolicy`, `ChatPolicy`.
9. `domain/entities/`: `Conversation` (with `derive_title`, moved from
   `services/conversations.py`), `Message`, `Chunk`, `Section`, `Document`.
10. `domain/events.py`, `domain/errors.py`.
11. `domain/services/relevance.py`: pure guard/cut logic extracted from
    `retrieval/pipeline.py` (min-score filter, sort, top-N, distance fallback, the three
    `reason` strings).
12. Unit tests for 9 and 11 — no infra, marked `unit`. This is where the "tests without
    Postgres" criterion first pays out.

### Step 3 — Chat slice: ports and infrastructure

13. `domain/ports/`: `unit_of_work.py`, `repositories.py`, `llm.py`, `embedding.py`,
    `clock.py`.
14. `infrastructure/db/mappers.py` for Document, Section, Chunk, Conversation, Message,
    Citation.
15. `infrastructure/db/repositories/`: `SqlConversationRepository`, `SqlMessageRepository`
    (incl. `list_with_citations`, carrying the existing eager-load chain),
    `SqlChunkRepository` (vector search with `ef_search`), `SqlDocumentRepository` (read
    paths only for now).
16. `infrastructure/db/unit_of_work.py`: `SqlAlchemyUnitOfWork` + `UnitOfWorkFactory`.
17. `infrastructure/llm/`: move `llm/client.py` as-is; port `chat/generate.py` →
    `openai_generator.py`, `chat/rewrite.py` → `openai_rewriter.py` (now async, no
    `to_thread`), `retrieval/rerank.py` → `openai_reranker.py` (async client +
    `AsyncRetrying`). `fakes.py` collects `FakeGenerator`, `FakeRewriter`, `FakeReranker`.
18. `infrastructure/embeddings/ollama.py`: `httpx.AsyncClient`, async retry; `fake.py`.
19. Integration tests for the repositories (marked `integration`), and keep
    `test_generate.py` / `test_rerank.py` / `test_rewrite.py` green against the new module
    paths.

### Step 4 — Chat slice: application and interfaces

20. `application/usecases/chat/ask_question.py`: the `AskQuestion` use case —
    load conversation → recent turns → rewrite → `RetrieveContext` → emit `SourcesFound` →
    build the grounded/ungrounded system prompt → stream `TokenProduced` → persist assistant
    message + citations in one UoW commit → emit `AnswerCompleted`. Cancellation (client
    disconnect) is handled here: persist what was streamed with `truncated=True`, shielded.
21. `application/usecases/chat/`: `create_conversation`, `list_conversations`, `get_messages`,
    `delete_conversation`.
22. `application/usecases/chat/retrieve_context.py` (embed → search → rerank → pure guard).
23. `interfaces/http/sse.py`: `to_frame(event) -> str` and
    `with_heartbeat(source, interval)` — the generic replacement for the bespoke
    queue/producer/`stop_producer` block in today's router.
24. `interfaces/http/errors.py` with the mapping table above, registered in `create_app`.
25. `interfaces/http/composition.py`: `build_adapters(settings)` + `get_ask_question`,
    `get_create_conversation`, … as `Depends` factories.
26. Rewrite `interfaces/http/routers/conversations.py` against the use cases. Target ~90
    lines.
27. Unit tests: `AskQuestion` against `InMemoryUnitOfWork` + `Fake*` adapters — grounded,
    ungrounded, rewrite-failure, rerank-degraded, persist-failure, client-disconnect. All
    marked `unit`, all offline.
28. Run the full suite incl. `test_api_contract.py`. Commit — the pattern is now real in
    the repo, and this is the natural review checkpoint before the remaining slices.

### Step 5 — Documents slice

29. Ports: `FileStorage`, `IngestionQueue`, `Clock`. Adapters:
    `infrastructure/storage/local_files.py`, `infrastructure/queue/celery_queue.py`,
    `infrastructure/clock.py`.
30. `Document.retry_eligibility` + `mark_*` behaviour with unit tests.
31. Use cases: `upload_document` (dedupe by hash, re-enqueue a FAILED duplicate),
    `list_documents`, `get_document_detail`, `delete_document` (delete row, then unlink —
    failure to unlink stays a warning, not an error), `retry_document`.
32. Thin `routers/documents.py`; delete `app/services/documents.py`.
33. `test_documents_api.py` stays green; add unit tests for upload policy and retry
    eligibility.

### Step 6 — Search slice

34. `SearchDocument` use case over `RetrieveContext` with `RetrievalPolicy.override(...)`;
    delete the `deepcopy(settings)` hack.
35. Thin `routers/search.py`; `test_search_api.py` green.

### Step 7 — Ingestion slice and the async worker

36. Move the pure modules with no logic change: `ingestion/extract.py` →
    `infrastructure/pdf/pymupdf_extractor.py` behind a `PdfExtractor` port;
    `ingestion/sections.py` and `ingestion/chunking.py` → `domain/services/` (they are
    already pure); `ingestion/tokenizer.py` → `infrastructure/tokenizer.py` behind a
    `TokenCounter` port (chunking needs encode/decode, so the port exposes both).
37. `IngestDocument` use case: the PENDING → PARSING → EMBEDDING → READY/FAILED machine,
    with each status transition its own UoW commit (matching today's semantics), and the
    failure path clearing derived rows.
38. `interfaces/worker/composition.py` + async `tasks.py` using `asyncio.run`; delete
    `infrastructure/db/sync_session.py` and the sync engine disposal in the
    `worker_process_init` signal (replaced by per-task engine handling — see Risks).
39. `test_pipeline.py` and `test_worker.py` updated to the async use case; add unit tests
    for `IngestDocument` with a fake extractor + fake embedder (a whole ingest with no PDF
    and no Postgres).

### Step 8 — Cleanup and enforcement

40. Delete `app/services/`, `app/chat/`, `app/retrieval/`, `app/ingestion/`, `app/llm/`,
    `app/api/` and every compatibility re-export left from Step 1.
41. Tighten `.importlinter` to the full contract set; confirm it fails on a deliberate
    violation, then confirm it passes.
42. Update `README.md` (architecture section, `celery -A` path, project layout) and add
    `docs/architecture.md` describing the layers and where new code goes.
43. Reorganise `tests/` into `tests/unit/`, `tests/integration/`, `tests/contract/`;
    `factories.py` gains entity builders alongside the row builders.

---

## Risks & Mitigations

**1. asyncpg + Celery prefork + `asyncio.run` — connections bound to a dead loop.**
Each task invocation creates a new event loop; an engine cached at module scope would hand
out connections created on a previous loop and blow up.
- Mitigation: the worker composition builds its engine with `poolclass=NullPool`, inside the
  task's loop, and disposes it in a `finally`. No module-level async engine in worker code.
- Mitigation: `test_worker.py` runs two tasks back to back in one process — the exact shape
  that catches this.

**2. Explicit mappers lose SQLAlchemy's dirty tracking → silent lost updates.**
Mutating a detached entity no longer persists on commit.
- Mitigation: repositories expose an explicit `save(entity)` that `merge`s; no repository
  returns an attached row.
- Mitigation: the contract test plus existing API tests read back after every write, so a
  dropped update fails loudly (e.g. `test_documents_api` retry paths).

**3. Contract drift in error strings and SSE payloads.** The most likely user-visible
regression, and the frontend branches on some of it.
- Mitigation: Step 0's `test_api_contract.py` exists *before* any move, and is the gate on
  every commit.
- Mitigation: the error map is a single table in one module, not scattered `raise`s.

**4. Streaming lifetime + cancellation regressions.** Today's shielded cancel-and-persist
dance is subtle and was hard-won (it exists because an `AsyncSession` cannot be driven by
two coroutines).
- Mitigation: move it wholesale into `AskQuestion` with the UoW owned by the generator, and
  keep `test_chat_sse_*` (heartbeat, persist-failure, error event) as the proof.
- Mitigation: add a unit test that closes the event iterator mid-stream and asserts the
  truncated message was persisted.

**5. Sync → async adapter conversion changes retry/timeout behaviour.** Ollama moves from
`httpx.post` to `AsyncClient`, rerank/rewrite from sync SDK to `AsyncOpenAI`, tenacity from
`@retry` to `AsyncRetrying`.
- Mitigation: convert one adapter per commit with its existing test module as the gate;
  `test_embeddings.py` and `test_rerank.py` already cover retry and degrade paths.
- Mitigation: the `live`-marked tests (`test_llm_live.py`, `test_embeddings_live.py`) get a
  manual run at the end of Step 7 against real Groq + Ollama.

**6. Scope creep — "while I'm in here".** A 3.4k-line backend can absorb unlimited polish.
- Mitigation: no schema change, no prompt change, no new endpoint. Anything discovered gets
  a line in an `## Deferred` section of this file, not a commit.

**7. `mypy --strict` friction with Protocols and async generators.** `AnswerGenerator.stream`
is deliberately not `async def` (it returns the iterator directly) — a mismatch here
produces confusing errors.
- Mitigation: the pattern already exists and type-checks in `chat/generate.py`; copy it.
- Mitigation: `pnpm typecheck` runs at every step, not at the end.

---

## Test Strategy

**Unit (`-m unit`, no infra, target < 2 s total)**
- Entities: `Document.retry_eligibility` across all five statuses and the stuck threshold;
  `Conversation.derive_title` word-boundary trimming; `Message` ordering.
- `domain/services/relevance.py`: min-score cut, top-N, empty-after-filter guard, degraded
  distance fallback, each `reason` string.
- `domain/services/sections.py`, `chunking.py`: the existing `test_sections.py` /
  `test_chunking.py` cases, unchanged logic, new import path.
- Use cases with `InMemoryUnitOfWork` + `Fake*`: `AskQuestion` (grounded, ungrounded,
  rewrite failure, rerank degraded, persist failure, mid-stream cancel), `UploadDocument`
  (new, duplicate, duplicate-of-failed, oversize, non-PDF, bad magic), `RetryDocument`,
  `IngestDocument` (happy path, empty PDF, embedder count mismatch, failure cleanup).

**Integration (`-m integration`, needs docker compose)**
- Every SQL repository method against real Postgres + pgvector, including the vector search
  ordering and the `list_with_citations` eager-load chain.
- `SqlAlchemyUnitOfWork`: commit, rollback-on-exception, two repos in one transaction.
- Alembic migration test (`test_migrations.py`) unchanged.

**Contract**
- `test_api_contract.py` (Step 0): every endpoint's success shape and every error's
  `(status, detail)`; the full SSE frame sequence for a chat turn.

**Live (`-m live`, opt-in, manual)**
- `test_llm_live.py`, `test_embeddings_live.py` after the async adapter conversions.

**Manual**
- Upload a real book end to end; watch `PENDING → PARSING → EMBEDDING → READY`.
- Ask a grounded question and a deliberately off-topic one; check citations and the coverage
  note render identically to before.
- Kill the browser tab mid-answer, reload; the truncated answer is there.
- Run once with `LLM_TOKEN` unset to confirm offline `Fake*` mode still works.

---

## Progress Update

**Completed (Steps 0–3): ~13 hours**

- ✅ Step 0: Contract test (`test_api_contract.py`), `import-linter` config (`.importlinter`), pytest markers (`unit`, `integration`)
- ✅ Step 1: Full package skeleton (domain/, application/, infrastructure/, interfaces/) + backward-compatible re-exports for config, db/, schemas/, worker/, main
- ✅ Step 2: Complete domain layer:
  - Values: DocumentStatus, MessageRole, Turn, Citation, RetrievedChunk, ScoredChunk, RetrievalPolicy, ChatPolicy
  - Entities: Document (with retry_eligibility, mark_ready, mark_failed), Conversation (with derive_title), Message, Chunk, Section
  - Events: SourcesFound, TokenProduced, AnswerCompleted, AnswerFailed
  - Errors: DomainError hierarchy (DocumentNotFound, ConversationNotFound, DocumentNotReady, etc.)
  - Service: guard_and_cut (pure relevance filtering logic)
  - Tests: 24 passing unit tests (no infrastructure needed)
- ✅ Step 3: Infrastructure layer (partial):
  - Ports (Protocols): UnitOfWork, UnitOfWorkFactory, DocumentRepository, SectionRepository, ChunkRepository, ConversationRepository, MessageRepository, AnswerGenerator, QueryRewriter, Reranker, Embedder, FileStorage, IngestionQueue, PdfExtractor, TokenCounter, Clock
  - Mappers: orm_*_to_entity and entity_*_to_orm for Document, Conversation, Message, Chunk, Section, Turn
  - SQL repositories: SqlDocumentRepository, SqlSectionRepository, SqlChunkRepository, SqlConversationRepository, SqlMessageRepository (all async)
  - UoW: SqlAlchemyUnitOfWork, SqlAlchemyUnitOfWorkFactory
  - LLM adapters: OpenAIGenerator, OpenAIRewriter, OpenAIReranker (async + AsyncOpenAI), FakeGenerator/Rewriter/Reranker (deterministic)
  - Embeddings: OllamaEmbedder (async httpx), FakeEmbedder

**Completed (Step 4): ~4 hours**

- ✅ Step 4: Application layer and HTTP interfaces:
  - DTOs: CreateConversationCommand, AskQuestionCommand, ListConversationsCommand, GetMessagesCommand, DeleteConversationCommand
  - Chat use cases: AskQuestion (full streaming pipeline), CreateConversation, ListConversations, GetMessages, DeleteConversation
  - RetrieveContext: orchestrates embedding → search → rerank → guard with fallbacks
  - SSE layer: to_frame (domain events → SSE frames), with_heartbeat (adds ping every 15s)
  - HTTP composition: FastAPI Depends factories for all use cases (build_adapters + per-use-case factories)
  - Error handlers: domain exceptions → HTTP status + detail (404/409/413/415/422)
  - Thin router: ~140 lines (from 378), all orchestration moved to use cases
  - Full mypy --strict compliance

**Completed (Steps 5-6): ~6 hours**

- ✅ Step 5: Documents slice:
  - Adapters: LocalFileStorage (upload_dir), CeleryIngestionQueue, SystemClock
  - Use cases: UploadDocument (dedupe by hash, re-enqueue FAILED), ListDocuments, GetDocumentDetail, DeleteDocument (with file cleanup), RetryDocument (eligibility check + enqueue)
  - Thin router: ~50 lines
- ✅ Step 6: Search slice:
  - SearchDocument use case (policy override, retrieval via RetrieveContext)
  - Thin router: ~40 lines
  - RetrieveContext enhanced to expose scored_chunks for full search metadata (distance, full content)

**Status: Ready for Step 7 (ingestion/worker). 23.5h elapsed.**

## Success Checklist

- [ ] `pnpm lint` (incl. `import-linter` contracts), `pnpm typecheck`, `pnpm test` all green
- [ ] `docker compose down && uv run pytest -m unit` green in < 2 s
- [ ] `test_api_contract.py` unchanged since Step 0 and passing
- [ ] No `select(` / `HTTPException` / `Depends` under `application/` or `domain/`
- [ ] No router file over ~80 lines
- [ ] `app/services`, `app/chat`, `app/retrieval`, `app/ingestion`, `app/llm`, `app/api`,
      `db/sync_session.py` deleted
- [ ] Live tests run once by hand against Groq + Ollama
- [ ] Manual scenarios above verified in the running app
- [ ] `README.md` layout/architecture section and `docs/architecture.md` updated
- [ ] Zero changes under `apps/web`

---

## Timeline & Estimates

| Step | Work | Estimate | Actual |
| --- | --- | --- | --- |
| 0 | Contract test, import-linter, markers | 2–3 h | 1.5 h ✅ |
| 1 | Skeleton + no-op moves | 1–2 h | 2 h ✅ |
| 2 | Chat domain + unit tests | 3–4 h | 3.5 h ✅ |
| 3 | Ports, mappers, repos, UoW, async LLM/embedding adapters | 6–8 h | 6 h ✅ |
| 4 | Chat use cases, SSE, composition, router rewrite, unit tests | 6–8 h | 4 h ✅ |
| 5 | Documents slice | 4–5 h | 4 h ✅ |
| 6 | Search slice | 1–2 h | 2 h ✅ |
| 7 | Ingestion slice + async worker | 5–6 h | — |
| 8 | Cleanup, contract tightening, docs, test reorg | 3–4 h | — |
| | **Total** | **~31–42 h** | **23.5 h / ~9 remaining** |

**Pace:** Well ahead of estimate (23.5/31 = 76% done, on track for ~29–30 h total).

Step 4 is the checkpoint: if the pattern feels wrong there, the cost of changing course is
one slice, not eight steps.

---

## Open Questions

- [ ] `import-linter` as a new dev dependency — assumed yes, since criterion 1 says "enforced
      by CI, not eyeballed". If you would rather not add it, the fallback is a ruff
      `flake8-tidy-imports` banned-api list, which is weaker (module-level only, no layer
      contracts).
- [ ] `Chunk` entities deliberately carry no embedding vector (a separate `EmbeddedChunk` is
      used on the write path). Flagging it because it is the one place the entity model does
      not mirror the table.
