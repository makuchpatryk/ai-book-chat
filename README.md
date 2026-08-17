# AI Book Chat

Upload a book as a PDF, ask questions about it in natural language, and get detailed,
streamed answers that cite the pages they came from.

It is a local, single-user RAG application: a FastAPI backend that parses, chunks and
embeds documents, a Celery worker that does that work off the request path, Postgres +
pgvector for storage and search, and a React frontend for uploading and chatting.

---

## What it does

- **Upload a PDF** (≤ 50 MB). Processing is asynchronous and its status is visible in the
  UI: `PENDING → PARSING → EMBEDDING → READY`, or `FAILED` with a readable reason.
  Re-uploading the same bytes returns the existing document instead of duplicating it.
- **Chunk with structure in mind.** Sections come from the PDF outline, falling back to
  heading heuristics (font size, numbering), falling back to flat page chunking. Chunks are
  ~600 tokens with 15% overlap and never cross a section boundary.
- **Ask questions and get grounded answers.** Each question is rewritten into a standalone
  query using the recent turns, matched against the document by cosine vector search, and
  the top candidates are re-ranked by an LLM before generation.
- **See the sources.** Every answer streams a `sources` event first: page ranges, section
  titles, snippets and re-ranker scores, rendered as expandable citations.
- **Honest about coverage.** When retrieval finds nothing relevant, the answer says up front
  that the document does not cover the question and then answers from general knowledge —
  without attributing any of it to the book or citing pages.
- **Follow-ups work.** "And what about his brother?" resolves against prior turns via the
  rewrite step.
- **Conversations persist.** They are scoped to one document, listed in the sidebar, and
  deep-linkable (`/documents/:documentId/c/:conversationId`), so a refresh restores the
  thread — including an answer that finished while the tab was closed.
- **Manage the library.** Delete a document (cascades to chunks, sections, conversations,
  messages and the file on disk) or retry one that failed or got stuck.

Out of scope for now: cross-document queries, non-PDF formats, OCR for scanned PDFs,
accounts and auth, sharing and export.

---

## Stack

| Layer | Choice |
| --- | --- |
| Frontend | React 19, TypeScript, Vite, TanStack Query, React Router 7, Tailwind 4, shadcn-style primitives |
| Backend | FastAPI (Python 3.12), SQLAlchemy 2 async |
| Storage | PostgreSQL 16 + pgvector (HNSW, cosine) |
| Jobs | Celery + Redis, worker concurrency 2 |
| PDF parsing | PyMuPDF |
| Embeddings | Local Ollama `nomic-embed-text` (768d) |
| Chat / rewrite / re-rank | Any OpenAI-compatible endpoint (default: Groq) |
| Monorepo | pnpm workspaces + Turborepo |

---

## Architecture

```
apps/web  ──HTTP/SSE──▶  apps/api (FastAPI)  ──▶  Postgres + pgvector
                              │                        ▲
                              └──enqueue──▶ Redis ──▶ Celery worker
                                                        │
                                            PyMuPDF → chunk → Ollama embed
```

**Ingestion** (worker): extract text per page → detect sections → chunk within section
bounds → batch-embed 100 chunks per request → bulk insert → `READY`. Any failure rolls back
partial chunks and records `error_message`.

**Retrieval** (per question): rewrite the question → embed it → cosine top-30 scoped to the
document → LLM re-rank to top-8 above a score threshold → grounding guard → stream the
answer → persist the message and its citations, logging token usage server-side.

---

## Quick start

Requirements: Node ≥ 22, pnpm 11, Docker, [uv](https://docs.astral.sh/uv/), and
[Ollama](https://ollama.com/) running on the host.

```bash
# 1. Embedding model (local, free)
ollama pull nomic-embed-text

# 2. Config
cp .env.example .env      # set LLM_TOKEN (e.g. a free key from console.groq.com)

# 3. Dependencies
pnpm install

# 4. Everything: Postgres, Redis, API, Celery worker, Vite dev server
pnpm dev
```

The API listens on http://localhost:8000 (docs at `/docs`), the frontend on
http://localhost:5173. Vite proxies `/api/*` to the backend, so there is no CORS in dev.

Migrations run against the host from `apps/api`:

```bash
cd apps/api && pnpm migrate
```

Infrastructure only, without the app services:

```bash
pnpm infra:up      # postgres + redis
pnpm infra:down
```

`LLM_TOKEN` is optional. Leave it empty and the deterministic `Fake*` adapters take over:
the whole flow still runs end to end — upload, retrieval, streaming, citations — but the
answers are canned.

---

## LLM configuration

Two backends, no provider switch:

| Stage | Backend | Config | Fallback when unconfigured |
| --- | --- | --- | --- |
| chat, query rewriting, re-ranking | any OpenAI-compatible chat endpoint | `LLM_BASE_URL`, `LLM_TOKEN`, `CHAT_MODEL`, `CHAT_REWRITE_MODEL`, `RERANK_MODEL` | deterministic `Fake*` adapters |
| embeddings | local Ollama | `OLLAMA_BASE_URL`, `OLLAMA_EMBEDDING_MODEL`, `EMBEDDING_DIMENSIONS` | none — Ollama must be reachable |

`LLM_BASE_URL` defaults to Groq's free tier. Any other OpenAI-protocol gateway
works by changing that one URL plus the model ids — the HF router
(`https://router.huggingface.co/v1`), OpenAI, or a local vLLM. There is no code
path per vendor.

Embeddings are deliberately not switchable: `chunks.embedding` is a fixed-width
`Vector(768)` column, so another model is a migration and a re-ingest, not a
config edit. `build_embedder` refuses to start if `EMBEDDING_DIMENSIONS` and the
column disagree, and the embedder re-checks the model's real width on its first
batch.

Every other knob (chunk size, `RETRIEVAL_TOP_K`, `RERANK_TOP_N`, history depth, upload
limit) is documented with its default in `.env.example`.

---

## API

```
POST   /documents                     multipart → { id, status }   201 new / 200 duplicate
GET    /documents                     → Document[]
GET    /documents/{id}                → Document + sections + chunk_count
POST   /documents/{id}/search         { query, top_k?, min_score? } → results + grounding info
POST   /documents/{id}/retry          → 200 / 409 ineligible / 404
DELETE /documents/{id}                → 204

POST   /documents/{id}/conversations  → { id }
GET    /documents/{id}/conversations  → Conversation[]
GET    /conversations/{id}/messages   → Message[] (with sources)
DELETE /conversations/{id}

POST   /conversations/{id}/messages   { content } → SSE:
       event: sources  { results: [...], pages: [12, 47, 103] }
       event: token    { text: "..." }
       event: done     { message_id, grounded, truncated }
       event: error    { detail }
```

Streaming uses `fetch` + `ReadableStream` rather than `EventSource`, because the message
endpoint is a `POST`. The stream emits comment heartbeats while the model is thinking, so
proxies do not time it out.

---

## Layout

```
apps/api/          FastAPI app
  src/app/
    api/routes/    documents, conversations, search, health
    ingestion/     extraction, section detection, chunking, embedding
    retrieval/     vector search, re-ranking, grounding guard
    chat/          query rewriting, prompts, generation, pipeline
    llm/           OpenAI-protocol client, adapters, Fake* fallbacks
    db/  schemas/  services/  worker/
  alembic/         migrations
  tests/
apps/web/          React frontend (api/, features/documents, features/chat, routes/, components/ui)
specs/             per-phase design specs
PRD.md             product requirements, data model, delivery phases and deviations
docs/              generated diagrams (chat-flow.html)
```

---

## Development

Turborepo drives both apps from the root:

```bash
pnpm test        # pytest + vitest
pnpm lint        # ruff + eslint
pnpm typecheck   # mypy (strict) + tsc
pnpm format      # ruff format + prettier
pnpm build
```

The default test run is fully offline. Live checks against the real endpoints are opt-in:

```bash
cd apps/api && uv run pytest -m live   # needs LLM_TOKEN and/or a running Ollama
```
