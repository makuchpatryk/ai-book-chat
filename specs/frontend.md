# Phase 5 — Frontend — Implementation Plan

## Summary

The backend is feature-complete for US-1…US-7, but the web app is a scaffold: `AppLayout`, a health
page, a typed `request()` wrapper, and a `DocumentsPage` placeholder. Phase 5 builds the actual UI —
upload, document library with status polling, conversation list, and a streaming chat panel with
page citations — against the contracts that already exist. No backend changes.

## Success Criteria

- Uploading a PDF creates a document and its row reaches `READY` in the UI without a manual refresh:
  the list polls every 2 s while any document is `PENDING | PARSING | EMBEDDING` and stops on
  `READY | FAILED` (US-1).
- Asking a question renders tokens incrementally as they arrive — first painted token within ~3 s of
  send on a `READY` book — with the answer body rendered as markdown (US-3).
- Each assistant answer shows the pages it drew from; clicking a citation reveals the chunk snippet
  and section title already carried by the `sources` SSE event, with no second fetch (US-4).
- An ungrounded question renders the refusal answer plus a visible "not in this document" state, and
  no citations (US-5).
- Reloading `/documents/:documentId/c/:conversationId` restores the full thread with citations from
  `GET /conversations/{id}/messages`, including an answer that completed while unmounted (US-7).
- `pnpm turbo run lint typecheck test` passes from a clean checkout; no network needed (MSW).

## Scope & Constraints

**In scope**
- Upload (drop + file picker), client-side type/size guard, dedupe-aware navigation.
- Document library: list, status badge, page count, upload date, `FAILED` reason.
- Deep-linkable routes for document and conversation selection.
- Conversation list per document + "New chat".
- Chat: message thread, streamed answer, stop-generation, citations, grounding state.

**Out of scope (Phase 6)**
- Delete document, retry document — the endpoints do not exist yet (`documents.py` has only
  `POST ""`, `GET ""`, `GET /{id}`).
- Delete conversation — `DELETE /conversations/{id}` exists, but delete affordances belong to Phase 6
  per the strict phase split. Wiring it later is one button + one mutation.
- Rich/global error surfaces (toasts, retry-all, error boundaries beyond a per-panel message).
- Token/cost display — PRD §1 says server-side only.
- PDF viewer / page jumping. Citations show snippets, not the source PDF.

**Hard constraints**
- Streaming is `POST` + `text/event-stream`, so `EventSource` is unusable (GET-only). Transport is
  `fetch` + `ReadableStream`.
- Upload cap 50 MB, PDF only (`max_upload_mb`, `%PDF-` magic check server-side).
- Existing conventions hold: `@/` alias, Tailwind 4 + shadcn primitives in `components/ui`, react-query
  for server state, app-local types in `src/types` (not shared with the backend).

**Trade-offs**
- Markdown rendering (react-markdown + remark-gfm) over plain text: correct lists/tables/code in
  analytical answers, at the cost of re-parsing during streaming — mitigated by throttled flushes.
- Deep-linkable routes over local selection state: more router wiring, but refresh-safe and it makes
  the "refresh recovers the answer" requirement fall out of a normal query refetch.

## Architecture & Design

### High-Level Flow

```
UploadDropzone ──POST /documents (multipart)──▶ 201 new | 200 duplicate
      │                                              │
      └── invalidate ["documents"] ──▶ DocumentList ──┴─▶ navigate /documents/:id
                    ▲
                    └── refetchInterval 2s while any status ∈ {PENDING,PARSING,EMBEDDING}

/documents/:documentId/c/:conversationId
      │
      ├─ useMessages(convId)  GET /conversations/{id}/messages   (source of truth, persisted)
      └─ useChatStream(convId)
             POST /conversations/{id}/messages  { content }
             fetch → res.body → parseSse() ──▶ sources | token* | done | error
                 sources  → set live citations
                 token    → append to ref buffer, flush to state ≤ every 60 ms
                 done     → invalidate ["messages", convId], clear live state
                 error    → show inline error, keep partial text
                 abort    → server persists partial truncated=true → invalidate + refetch
```

### Layout

Sidebar is two stacked panes (PRD §7): documents on top, conversations of the selected document
below (rendered only when a `documentId` is in the URL). Main panel is the chat, or an empty state.
`AppLayout` grows from a 64-unit nav strip to a `w-80` sidebar; the existing Status link moves to a
footer row so `HealthPage` stays reachable.

### Routes (`src/router.tsx`)

```
/                                            → <Navigate to="/documents" replace />
/documents                                   → DocumentsPage      (empty main panel)
/documents/:documentId                       → DocumentPage       (conversation picker / new chat)
/documents/:documentId/c/:conversationId     → ChatPage
/health                                      → HealthPage         (moved off index)
```

Sidebar panes read `useParams()`, so selection state lives in the URL only.

### Key Changes

**`src/api/client.ts`** — add an upload path. Current `request()` hardcodes
`Content-Type: application/json`, which corrupts a multipart body (the browser must set the boundary
itself). Add:

```ts
export async function upload<T>(path: string, body: FormData): Promise<T>
```

sharing the same response/`ApiError` handling, without the JSON header. Do not change `request()`.

**`src/api/documents.ts`** (new)
```ts
listDocuments(): Promise<Document[]>            // GET /documents        (created_at desc)
getDocument(id): Promise<DocumentDetail>        // GET /documents/{id}   (+ sections, chunk_count)
uploadDocument(file: File): Promise<Document>   // POST /documents       (201 new | 200 duplicate)
```
Both statuses return `DocumentRead`, so the caller does not branch — it invalidates and navigates.

**`src/api/conversations.ts`** (new)
```ts
listConversations(documentId): Promise<Conversation[]>
createConversation(documentId): Promise<Conversation>
getMessages(conversationId): Promise<Message[]>
```

**`src/api/sse.ts`** (new) — transport-agnostic frame parser, unit-testable without React:
```ts
export interface SseFrame { event: string; data: string }
export async function* parseSse(body: ReadableStream<Uint8Array>): AsyncGenerator<SseFrame>
```
Uses `TextDecoder("utf-8")` with `{ stream: true }` (multi-byte characters split across network
chunks), buffers until `\n\n`, reads `event:` / `data:` lines, tolerates a leading space after the
colon and multiple `data:` lines per frame.

**`src/api/chat.ts`** (new) — types the frames into a discriminated union and drives the POST:
```ts
type ChatEvent =
  | { type: "sources"; results: Source[]; pages: number[] }
  | { type: "token";   text: string }
  | { type: "done";    messageId: string; grounded: boolean; truncated: boolean }
  | { type: "error";   detail: string };

streamMessage(conversationId, content, signal): AsyncGenerator<ChatEvent>
```
Non-2xx (e.g. 409 `document not ready for chat`, 404) is raised as `ApiError` before streaming starts.

**`src/types/index.ts`** — extend with `DocumentStatus`, `Document`, `Section`, `DocumentDetail`,
`Conversation`, `Message`, `Source`, mirroring `schemas/documents.py` and `schemas/chat.py`:
`Conversation.title` is `string | null` and `created_at` is an ISO string; `Message.grounded` is
`boolean | null` (null on user messages); `Source.score` is `number | null` (null when the re-ranker
degraded); `Document.page_count` and `error_message` are nullable.

**`src/features/documents/`**
- `useDocuments.ts` — `useQuery(["documents"])`, `refetchInterval: (q) => hasProcessing(q.state.data) ? 2000 : false`.
- `UploadDropzone.tsx` — native drag/drop + `<input type="file" accept="application/pdf">`. Rejects
  non-`.pdf` and `> 50 MB` locally with an inline message (mirrors the server's 415/413 rather than
  round-tripping 50 MB to be told no). Disabled while the mutation is in flight.
- `DocumentList.tsx` / `DocumentListItem.tsx` — title, `page_count ?? "—"` pages, relative upload
  date, `StatusBadge`; `FAILED` rows render `error_message` beneath.
- `StatusBadge.tsx` — maps the five statuses onto `Badge` variants: `READY` default, `FAILED`
  destructive, the rest secondary with a spinner glyph.

**`src/features/chat/`**
- `useConversations.ts`, `useCreateConversation.ts` (invalidate + navigate to the new conversation),
  `useMessages.ts`.
- `useChatStream.ts` — the one stateful hook. Holds `status: "idle" | "streaming" | "error"`,
  `liveText`, `liveSources`, `error`, and an `AbortController` ref. **Started from the submit
  handler, never from an effect** — React 19 StrictMode double-invokes effects and would fire two
  POSTs, producing two user rows. Token appends accumulate in a ref and flush on a ~60 ms timer so
  react-markdown re-parses ~16×/s instead of once per token. On `done` / `error` / abort it
  invalidates `["messages", conversationId]`; the refetched persisted thread replaces the live state
  in one commit.
- `ConversationList.tsx` — `title ?? "New chat"`, created date, active highlight; "New chat" button.
- `MessageList.tsx` / `MessageBubble.tsx` — role-styled bubbles; assistant bubbles render
  `MarkdownAnswer` + `PageCitations`; `grounded === false` adds a muted "Not found in this document"
  line; `truncated` adds "stopped early".
- `StreamingMessage.tsx` — the in-flight assistant bubble: sources appear first (they arrive before
  the first token), then text, then a caret. Unmounts when the persisted message lands.
- `MarkdownAnswer.tsx` — `react-markdown` + `remark-gfm`, no `rehype-raw` (the model's output is
  untrusted text; raw HTML stays off).
- `PageCitations.tsx` — one `Badge` per page from `pages`; clicking toggles `SourcesPanel`.
- `SourcesPanel.tsx` — the `results` rows: `p.start–end`, `section_title`, snippet, score when present.
- `MessageInput.tsx` — textarea, Enter to send / Shift+Enter newline, 4000-char cap (matches
  `SendMessageRequest`), disabled while streaming, Send swaps to Stop mid-stream.

**Autoscroll** — pin to bottom on new tokens unless the user has scrolled up (track
`scrollHeight - scrollTop - clientHeight > 80`).

**Dependencies**
- add: `react-markdown`, `remark-gfm`
- add (dev): `msw`
- shadcn primitives to generate: `input`, `textarea`, `alert`, `skeleton`, `separator`
  (`pnpm dlx shadcn@latest add …`) — `button`, `card`, `badge` already exist.

### Backend facts the UI must respect

1. **`done.message_id` is not always a real row.** On the ungrounded path `chat/pipeline.py:117`
   emits `DoneEvent(message_id=uuid.uuid4())`, and the route persists the assistant message
   separately. Never use it as a cache key or fetch target — refetch the thread on `done`.
2. **Abort is a supported, lossy-by-design path.** `conversations.py:237` shields a
   `persist_assistant_message(..., truncated=True)` on client disconnect, so Stop leaves a persisted
   partial. The UI must refetch after abort rather than discard the text locally.
3. **`error` ends the stream without `done`.** Treat the `error` frame as terminal.
4. **Chat 409s unless the document is `READY`** (`conversations.py:161`) — the composer is disabled
   with an explanatory line for any other status.
5. **Duplicate uploads return 200 with the existing row**, possibly already `READY`, and a previously
   `FAILED` duplicate is re-queued as `PENDING`. Navigating to the returned id is correct in both cases.
6. **Vite dev proxy rewrites `/api` → `/`**; the backend already sets `X-Accel-Buffering: no`.

### Alternative Approaches Considered

**SSE transport** — `@microsoft/fetch-event-source` handles POST + retry, but it is unmaintained
since 2022 and its auto-reconnect is actively wrong here: a replayed POST would duplicate the user
message. A ~60-line `parseSse` generator is testable in isolation and has no reconnect semantics to
disable. *Chosen: hand-rolled.*

**Streaming state** — keeping tokens in react-query cache via `setQueryData` per token was rejected;
it churns the cache on every token and fights the refetch on `done`. Local hook state with a single
invalidation at the end has one clear ownership handoff. *Chosen: local state.*

**Answer rendering** — plain `whitespace-pre-wrap` is free but shows raw `##` and `|` table pipes for
detailed analytical answers, which is the product's main output. *Chosen: markdown + throttling.*

**Test doubles** — hand-rolled `vi.stubGlobal("fetch")` matches the existing two tests but cannot
model a streaming body without re-implementing `Response`. MSW v2 returns a `ReadableStream` body
directly, so the SSE handler is a few lines and the same handlers cover REST. *Chosen: MSW.*

## Implementation Steps

1. Add deps (`react-markdown`, `remark-gfm`, dev `msw`) and generate the shadcn primitives.
2. Extend `src/types/index.ts` with the document/conversation/message/source types.
3. Add `upload()` to `src/api/client.ts` + a test that it sends `FormData` with no JSON content-type.
4. Write `src/api/sse.ts` (`parseSse`) and its unit tests — frames split mid-line, two frames in one
   chunk, multi-byte UTF-8 split across chunks, trailing frame with no terminating blank line.
5. Write `src/api/documents.ts` and `src/api/conversations.ts`.
6. Write `src/api/chat.ts` (`streamMessage`) over `parseSse`, including the pre-stream `ApiError`
   path and `AbortSignal` plumbing.
7. Stand up MSW: `src/test/handlers.ts` + `setupServer` in `src/test/setup.ts` (`onUnhandledRequest:
   "error"`), with an SSE helper that emits a scripted frame sequence.
8. Documents feature: `useDocuments` (polling), `useUploadDocument`, `StatusBadge`, `DocumentList`,
   `UploadDropzone`; rebuild `DocumentsPage` around them.
9. Rework `AppLayout` into the two-pane sidebar and update `router.tsx` with the four routes +
   `/` redirect.
10. Conversations: `useConversations`, `useCreateConversation`, `ConversationList`, `DocumentPage`
    (conversation picker + "New chat" + `FAILED`/processing states).
11. `useChatStream` — token buffering/throttle, abort, terminal invalidation.
12. Chat UI: `MarkdownAnswer`, `PageCitations`, `SourcesPanel`, `MessageBubble`, `MessageList`,
    `StreamingMessage`, `MessageInput`, `ChatPage` (autoscroll, composer gating on document status).
13. Component tests (see Test Strategy).
14. Manual pass against the live stack; update `README.md` run instructions if the dev flow changed.

## Risks & Mitigations

- **StrictMode double-fires the stream, creating two user messages.** The backend persists the user
  row before streaming and has no idempotency key, so this corrupts the thread.
  - Start streams from event handlers only; no `useEffect`-triggered POSTs.
  - Guard `useChatStream` with a "already streaming" check that returns early.
- **Markdown re-parse per token drops frames on long answers.** Throttle flushes to ~60 ms; if
  profiling still shows jank, render the in-flight bubble as plain text and swap to markdown on
  `done` (the persisted refetch already re-renders that bubble).
- **Buffering hides the stream in dev.** If tokens arrive in one burst, check the Vite proxy before
  the app: reproduce with `curl -N` straight at `:8000`. `X-Accel-Buffering: no` is already set
  server-side; if the proxy is at fault, set `proxy["/api"].configure` to disable compression.
- **jsdom streaming gaps.** `ReadableStream`/`TextDecoder` come from Node 22 under vitest, but
  `Response.body` in jsdom has historically been thin. Mitigation: `parseSse` takes a
  `ReadableStream`, not a `Response`, so its tests never touch fetch; if MSW's streamed body proves
  unreliable in jsdom, the chat tests inject a fake stream at the `streamMessage` boundary instead.
- **Stop leaves the UI and DB disagreeing.** Always refetch after abort rather than trusting local
  text; render `truncated` explicitly so a short answer is never mistaken for a complete one.
- **Polling never stops on a stuck document.** `refetchInterval` keys off status only, so a worker
  that dies mid-`PARSING` polls forever. Acceptable for v1 (single-user, local); Phase 6's retry work
  is where a stall timeout belongs.

## Test Strategy

**Unit**
- `parseSse`: frame boundary handling, multi-byte splits, `event:`-less frames, trailing data.
- `upload()`: no JSON content-type, `ApiError` on 413/415.
- `hasProcessing()` status predicate driving the poll interval.

**Component (RTL + MSW)**
- Upload: rejects a `.txt` file and a 51 MB file locally without a request; a good upload invalidates
  the list and navigates to `/documents/:id`.
- Polling: list starts with a `PARSING` doc, handler flips to `READY`, `vi.advanceTimersByTime(2000)`
  → badge updates and polling stops (assert no further requests).
- Streaming: scripted `sources → token×3 → done` renders sources first, accumulates text, and
  refetches the thread on `done`.
- Refusal: `sources(empty) → token(refusal) → done(grounded:false)` shows the not-found state and no
  citations.
- Error: `error` frame renders the detail inline and re-enables the composer.
- Stop: clicking Stop aborts and triggers a messages refetch; the refetched `truncated` message shows
  "stopped early".
- Citations: clicking a page badge reveals the snippet and section title with no extra request.
- Gating: a `PENDING` document disables the composer with an explanation.

**Manual**
- Real 300-page book: upload → watch statuses advance → ask a question, confirm first token < 3 s.
- Follow-up with a pronoun resolves correctly (US-6) and the thread survives a hard refresh.
- Ask something absent from the book → refusal state.
- Stop mid-answer, refresh, confirm the partial persisted once.

## Success Checklist

- [ ] All success criteria verified against a real book
- [ ] `pnpm turbo run lint typecheck test` green
- [ ] No `console.error` from React (keys, act warnings) in the test run
- [ ] `Message`/`Document`/`Source` types match the current pydantic schemas field-for-field
- [ ] README updated if dev flow changed
- [ ] No regression on `/health`

## Timeline & Estimates

- API layer + SSE parser + MSW setup (steps 1–7): ~3 h
- Documents feature + layout/routing (steps 8–10): ~3 h
- Chat feature (steps 11–12): ~4 h
- Tests + manual pass (steps 13–14): ~3 h
- **Total: ~13 h** plus buffer for streaming/jsdom friction.

## Open Questions

- [ ] None blocking. One judgment call flagged: conversation delete is left to Phase 6 despite its
      endpoint existing since Phase 4 — say so if it should land now (one button + one mutation).
