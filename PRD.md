# PDF RAG Chat — Implementation Plan

Upload a book (PDF), ask questions in natural language, get grounded, analytical answers with page citations.

---

## 1. Locked decisions

| Area | Choice |
|---|---|
| Frontend | React 19 + TypeScript + Vite (TanStack Query, React Router, Tailwind 4) |
| Backend | FastAPI (Python) |
| Storage | PostgreSQL 16 + pgvector (docker-compose) |
| Background jobs | Celery + Redis (docker-compose) |
| Embeddings | OpenAI `text-embedding-3-small` (1536d) |
| LLM (default) | Anthropic Claude Haiku / Sonnet |
| LLM (configurable) | Mistral, Ollama, or offline fallback (term overlap) |
| Retrieval | Top-k vector search + LLM re-rank (pluggable) |
| Chunking | Chapter/section aware |
| Citations | Page number only |
| Answer style | Detailed / analytical, streamed |
| Cost tracking | Logged server-side, not surfaced in UI |
| Auth | None (single-user, local) |

---

## 2. Business requirements

### 2.1 Core value

The user uploads a document and asks questions about it. Answers are grounded strictly in that document's content, with page references so the user can verify.

### 2.2 User stories (MVP)

| ID | Story | Acceptance criteria |
|---|---|---|
| US-1 | Upload a PDF | File ≤ 50 MB, PDF only. Processing status visible (queued → parsing → embedding → ready). Failure shows a readable reason. |
| US-2 | See my documents | List with title, page count, upload date, status. Delete removes document, chunks and chat history. |
| US-3 | Ask a question | Answer streams token by token. Content derived only from the document. |
| US-4 | See sources | Each answer lists the page numbers it drew from. |
| US-5 | Honest "I don't know" | If retrieval finds nothing relevant, the answer states the information isn't in the document. No invented content. |
| US-6 | Follow-up questions | Pronouns and implicit references resolve against prior turns ("and what about his brother?"). |
| US-7 | Resume past chats | Conversations are persisted per document, listed, and resumable. |

### 2.3 Out of scope (v1)

- Cross-document queries (asking across the whole library)
- Non-PDF formats (EPUB, DOCX)
- Scanned PDFs / OCR
- User accounts, auth, multi-tenancy
- Sharing, export, collaboration

### 2.4 Business rules

- **Grounding** — every answer either cites retrieved chunks or explicitly says the information isn't present.
- **Isolation** — a conversation is scoped to exactly one document.
- **Idempotent cost** — embedding runs once per document; conversation history sent to the LLM is capped.
- **Retention** — the original PDF is kept (needed to reference pages).

### 2.5 Non-functional targets

- Upload → ready: under 2 minutes for a 300-page book
- First token of an answer: under 3 seconds
- Processing is asynchronous — the UI never blocks
- Failed processing is retryable and leaves no orphan chunks

---

## 3. Data model

```
documents
  id, filename, title, page_count, status, error_message,
  file_path, content_hash, chunking_strategy, created_at, updated_at
  status: PENDING | PARSING | EMBEDDING | READY | FAILED
  UNIQUE(content_hash)          -- re-uploading the same bytes returns the existing row

sections                       -- detected chapters
  id, document_id, title, order_index, start_page, end_page

chunks
  id, document_id, section_id, content, page_start, page_end,
  token_count, order_index, embedding vector(1536)
  INDEX: hnsw on embedding (cosine)

conversations
  id, document_id, title (nullable — set from the first question), created_at, updated_at

messages
  id, conversation_id, role (user|assistant), content, order_index,
  grounded (null|bool), truncated (bool, default false), created_at
  UNIQUE(conversation_id, order_index)

message_sources                -- citations
  id, message_id, chunk_id, score, rank
  UNIQUE(message_id, chunk_id)
```

---

## 4. Ingestion pipeline

```
upload → save file → PENDING
  ↓ Celery task (Redis broker), worker concurrency 2
1. Extract text per page          PyMuPDF  (was pdfplumber — see note below)
2. Detect sections                PDF outline/bookmarks
                                  → fallback: heading heuristics (font size, numbering)
                                  → fallback: flat page chunking
3. Chunk within section bounds    ~600 tokens, 15% overlap, never crosses a section
4. Batch embed                    OpenAI, 100 chunks per request
5. Bulk insert chunks + vectors
6. READY
```

Any failure sets `FAILED` with `error_message`; partial chunks are rolled back. A retry endpoint re-runs from step 1 (Phase 6, not yet built).

**Deviation from §1 (Phase 2): Celery + Redis instead of in-process background tasks.** PDF parsing
and embedding are CPU- and IO-heavy and outlive a request; FastAPI `BackgroundTasks` would tie them
to the API process, lose them on reload/restart, and make the retry endpoint unimplementable. The
worker runs as its own docker-compose service (`--concurrency=2`, since two 300-page books would
otherwise saturate the box). Cost: two extra services (Redis, worker) and a sync DB session
(`app.db.sync_session`) alongside the async one the API uses.

**Deviation from §1 (Phase 2): PyMuPDF replaces pdfplumber.** pdfplumber needs ~0.3–1 s per page,
which alone puts the 2-minute budget for a 300-page book at risk, and it exposes neither the outline
nor per-span font sizes — both of which step 2 needs. PyMuPDF supplies all three from one library
(measured: 1.1 s to parse 300 pages). Cost: AGPL-3.0, which is irrelevant for a local single-user
app but would matter if this ever shipped closed-source. Extraction lives behind
`app.ingestion.extract.extract_pdf()`, so reverting means rewriting one module and its tests.

---

## 5. Retrieval pipeline (per question)

```
1. Query rewriting
   last N turns + new question → Claude Haiku → standalone question

2. Vector search
   embed(standalone_q) → cosine top-30, scoped to document_id

3. Re-rank (pluggable provider)
   Anthropic Claude Haiku | Mistral | Ollama | FakeReranker
   → scores each candidate 0–10 for relevance
   → keep top-8, drop anything below threshold

4. Grounding guard
   no chunk above threshold → return "not in this document", skip generation

5. Generate
   Claude Sonnet, streamed
   system: analytical answer, cite [p.N], never invent
   context: 8 chunks with page metadata + last 6 turns

6. Persist
   message + message_sources; log token usage
```

**Re-ranker providers:**
- **Anthropic** (default): Claude Haiku via structured output, retries on failure
- **Mistral**: Large model via Mistral API, JSON response parsing
- **Ollama**: Local HTTP endpoint (no API key needed)
- **FakeReranker**: Deterministic fallback (term-overlap scoring, no LLM call)

---

## 6. API contracts

```
POST   /documents                     multipart → { id, status }
                                      201 on create; 200 + existing row when content_hash matches
GET    /documents                     → Document[]
GET    /documents/{id}                → Document + sections + chunk_count
POST   /documents/{id}/search         { query, top_k?, min_score? }
                                      → { results[], grounded, reranked, reason, candidate_count }
POST   /documents/{id}/retry          → 200 DocumentRead / 409 ineligible / 404 unknown
DELETE /documents/{id}                → 204 / 404 unknown

POST   /documents/{id}/conversations  → { id }
GET    /documents/{id}/conversations  → Conversation[]
GET    /conversations/{id}/messages   → Message[] (with sources)
DELETE /conversations/{id}

POST   /conversations/{id}/messages   { content }
       → SSE stream:
         event: sources  { results: [{chunk_id, page_start, page_end, score, section_title, snippet}],
                           pages: [12, 47, 103] }
         event: token    { text: "..." }
         event: done     { message_id, grounded, truncated }
         event: error    { detail }
```

---

## 7. Frontend structure

```
src/
  api/            client (typed fetch), sse (POST + ReadableStream parser),
                  documents, conversations, chat, health
  features/
    documents/    UploadDropzone, DocumentList, DocumentListItem, StatusBadge,
                  useDocuments (polls 2 s while PENDING|PARSING|EMBEDDING), useUploadDocument
    chat/         ConversationList, MessageList, MessageBubble, MessageInput,
                  StreamingMessage, MarkdownAnswer, PageCitations, SourcesPanel,
                  useChatStream, useConversations, useCreateConversation, useMessages, useDocument
  components/ui/  shadcn primitives (alert, badge, button, card, input, separator, skeleton, textarea)
  layouts/        AppLayout
  routes/         DocumentsPage, DocumentPage, ChatPage, HealthPage
  lib/  types/
```

Layout: sidebar (documents → conversations), main panel (chat).

Routes are deep-linkable — `/documents/:documentId/c/:conversationId` — so a refresh restores the
thread (and an answer that finished while unmounted) from `GET /conversations/{id}/messages`.

Streaming uses `fetch` + `ReadableStream`, not `EventSource`: the message endpoint is a `POST` and
`EventSource` is GET-only.

---

## 8. Delivery phases

**Phase 1 — Infrastructure** ✓ DONE
docker-compose (Postgres + pgvector, Redis, api, worker), FastAPI skeleton, Alembic migrations,
config/env handling.

**Phase 2 — Ingestion** ✓ DONE
Upload endpoint, text extraction, section detection, chunking, embedding, status machine.
*Verifiable: upload a book, inspect chunks and sections in the DB.*

**Phase 3 — Retrieval** ✓ DONE
Vector search, re-ranker, grounding guard, `POST /documents/{id}/search`.
*Verifiable: a query endpoint returns sensible chunks with correct pages.*

**Phase 4 — Chat** ✓ DONE
Conversations, messages, query rewriting, streaming generation, citation persistence.
*Deviations from §3 and §6:*
- Messages include `order_index` (deterministic ordering, not timestamp-based) and `grounded` / `truncated` flags.
- `message_sources` tracks `rank` (0-based position in final ordering) and `score` (re-ranker score, nullable on degrade).
- SSE `sources` event is a superset: includes chunk details (chunk_id, page_start, page_end, section_title, snippet) not just page numbers. Allows citation UI to render without a second fetch.
- SSE includes `error` event for in-stream failures (rewrite, generation, etc.).

**Phase 5 — Frontend** ✓ DONE
Upload + document list + status polling, then the chat UI with streaming and citations.
*Deviations from §7:*
- Split into `layouts/` + `routes/` with deep-linkable URLs instead of local selection state, so
  refresh restores the thread.
- Answers render as markdown (react-markdown + remark-gfm) with throttled flushes during streaming.
- Citations expand into a `SourcesPanel` fed by the `sources` SSE event — no second fetch.
- Delete document / retry document / delete conversation UX surfaces with confirm dialogs (Phase 6).

**Phase 6 — Hardening** ✓ shipped
- `DELETE /documents/{id}` removes row and cascades to chunks, sections, conversations, messages, sources; unlinks PDF file.
- `POST /documents/{id}/retry` moves FAILED or stuck (PENDING|PARSING|EMBEDDING older than 30 min) back to PENDING, clears chunks/sections, re-enqueues.
- Retry re-run idempotent: `_persist` deletes existing chunks/sections first.
- Chat correctness: `DoneEvent` drops fabricated `message_id`; route owns persistence and id; `truncated` flag set from `stop_reason == "max_tokens"`.
- Generation/rewrite usage logging: `phase`, `provider`, `model`, `input_tokens`, `output_tokens` per call.
- Re-ranker degrade guard: when scoring fails, filter candidates by `distance <= 0.75`, return `grounded=false, reason="rerank_degraded_no_match"` if nothing survives.
- SSE heartbeat: `wait_for(queue.get(), timeout=chat_heartbeat_seconds)` emits `: ping\n\n` comment frames on timeout; browser `parseSse` drops them.
- Frontend: delete document/conversation buttons (behind confirm dialogs), retry (FAILED only), global error toast surface via QueryClient cache hooks, error boundary on render crash.
- Deviations: three bugfixes (message_id, truncated, degrade guard) not in Phase 5 scope; `stuck_after_minutes=30` matches Celery `time_limit=1800`.

---

## 9. Risks

| Risk | Mitigation |
|---|---|
| Section detection fails (no outline, image-based headings) | Fall back to flat page chunking; log which strategy was used |
| Re-ranking adds latency | Haiku with parallel batching; if slow, reduce candidates to top-15 |
| Scanned PDF yields no text | Detect empty extraction, fail fast with a clear message (OCR out of scope) |
| Follow-up questions lose context | Query rewriting step, evaluated manually against a test set |
| Embedding cost on large books | One-time per document; batch requests; token usage logged |