# Phase 6 — Hardening — Implementation Plan

## Summary

Phases 1–5 shipped the happy path: upload → ingest → retrieve → chat → UI. What's missing is
everything that happens when the happy path breaks or when the user wants to undo something. Phase 6
adds the two endpoints the PRD names as not built (`POST /documents/{id}/retry`,
`DELETE /documents/{id}`), the delete affordances the frontend deferred, global error surfaces,
generation token logging, and wires the unused `chat_heartbeat_seconds`. It also fixes three chat
bugs found while reading the code (wrong `message_id`, `truncated` always `false`, unguarded
re-ranker degrade) and backfills the chat test coverage that Phase 4 shipped without.

## Success Criteria

- `DELETE /documents/{id}` returns 204, removes the row, its chunks, sections, conversations,
  messages and citations, and unlinks the PDF from `upload_dir`; re-uploading the same bytes
  afterwards creates a fresh document instead of returning the deleted one (US-2).
- `POST /documents/{id}/retry` moves a `FAILED` document back to `PENDING` and re-enqueues it; a
  document stuck `PENDING|PARSING|EMBEDDING` for longer than `stuck_after_minutes` is also
  retryable; `READY` and freshly-in-flight documents get 409 (§2.5 "failed processing is
  retryable").
- The `done` SSE event carries the `message_id` of the row that was actually persisted — fetching
  `GET /conversations/{id}/messages` returns a message with that exact id.
- An answer cut off by `max_tokens` persists and reports `truncated: true`; today it always reports
  `false`.
- Every LLM call logs one structured usage line (`phase`, `provider`, `model`, `input_tokens`,
  `output_tokens`) — generation and rewrite join the re-rank lines that already exist.
- A stream that spends >`chat_heartbeat_seconds` in rewrite+retrieval emits SSE comment frames, and
  the browser client ignores them (no visible artifact in the answer text).
- Deleting a document or a conversation asks for confirmation first, and any failed mutation or
  query surfaces as a toast rather than a silent no-op; a render crash shows a recovery screen, not
  a white page.
- `pytest` covers the chat SSE route end-to-end (event order, persistence, ungrounded path, error
  event, disconnect→truncated) plus retry/delete; `pnpm turbo run lint typecheck test` stays green.

## Scope & Constraints

**In scope**

- Backend: `POST /documents/{id}/retry`, `DELETE /documents/{id}`, ingestion idempotency on re-run,
  generation/rewrite usage logging, SSE heartbeat, the three chat bugfixes.
- Frontend: delete document, retry document, delete conversation, confirm dialogs, toast surface,
  error boundary, redirect after deleting the document in view.
- Tests: chat SSE route + pipeline (pytest), new endpoints (pytest), new mutation hooks (vitest/MSW).

**Out of scope** (named so it doesn't creep in)

- Request-id correlation, deep `/health` (db/redis/worker probes), log polish — ops work, not asked
  for.
- `llm_usage` table and USD price math — logs only, per §1 "logged server-side, not surfaced".
- Retries/timeouts on the embedding and generation clients (the re-ranker already has tenacity
  retry; extending it is Phase 7).
- Full vitest coverage of the Phase 5 chat surface (`useChatStream`, `MessageList`, `SourcesPanel`).
  The gap is real; the decision was backend-focused testing this phase.
- Soft delete / undo. Deletes are permanent, which is why they get a confirm dialog.

**Hard constraints**

- No auth, single user, local — so no per-user authorization checks on delete/retry.
- No new database migration. Every cascade this needs already exists as `ondelete="CASCADE"` in
  migration `0003`; `truncated`/`grounded` columns already exist.
- New frontend dependency budget: one (`sonner`). `alert-dialog` comes from the `radix-ui` package
  that is already installed.

**Trade-offs**

- Retry re-runs the whole pipeline including embedding, so a retry costs money. It is gated behind
  status checks and a confirm dialog rather than made cheap/resumable — resumable ingestion is a
  much larger change for a case that should be rare.
- Heartbeat is implemented in the route (transport concern) rather than the pipeline, so the
  pipeline stays a pure `sources → token → done` generator that tests can consume directly.

---

## Architecture & Design

### High-Level Flow

```
DELETE /documents/{id}
  load row (404 if unknown) → remember file_path
  DELETE FROM documents WHERE id = …          -- DB cascades:
      chunks → message_sources                --   FK message_sources.chunk_id ON DELETE CASCADE
      sections → chunks
      conversations → messages → message_sources
  unlink(file_path)   (missing_ok; failure logs a warning, still 204)
  → 204

POST /documents/{id}/retry
  load row (404 if unknown)
  eligible?  FAILED                                   → yes
             PENDING|PARSING|EMBEDDING, updated_at older than stuck_after_minutes → yes
             PENDING|PARSING|EMBEDDING, recent          → 409 "still processing"
             READY                                      → 409 "already processed"
  file on disk missing                                  → 409 "original file is gone, re-upload"
  delete chunks + sections, status=PENDING, error_message=None, commit
  process_document.delay(id)
  → 200 { id, status: "PENDING", … }

POST /conversations/{id}/messages   (heartbeat + real ids)
  route spawns the pipeline generator into an asyncio.Queue
  loop: wait_for(queue.get(), timeout=chat_heartbeat_seconds)
        timeout → yield ": ping\n\n"        (comment frame; parseSse drops it)
        DoneEvent → persist message, then emit done with the PERSISTED id + pipeline's
                    grounded/truncated flags
```

### Key Changes

**`app/config.py`** — two new settings:
- `stuck_after_minutes: int = 30` — matches the Celery `time_limit=1800` on `process_document`, so a
  task that hit its limit is by definition stuck.
- `retrieval_max_distance: float = 0.75` — cosine-distance floor used **only** when the re-ranker
  degrades (see below). 0.75 distance ≈ 0.25 similarity, loose enough not to fire on a decent match.

**`app/services/documents.py`** — `delete_document()` and `retry_document()`.
- `delete_document` issues a Core `delete(Document).where(Document.id == …)` rather than
  `session.delete(orm_obj)`: the Core statement lets Postgres run the FK cascades in one round trip,
  where the ORM path would try to load and cascade `sections`/`chunks` in Python (thousands of
  rows). File unlink happens *after* commit — a deleted row with a stale file is recoverable garbage;
  a deleted file with a live row is a broken document.
- `retry_document` returns the refreshed `Document`; the eligibility rules and their HTTP codes live
  here, raising `HTTPException`, matching how `create_document` already raises 415/413/422.

**`app/api/routes/documents.py`** — `POST /{document_id}/retry` (200, `DocumentRead`) and
`DELETE /{document_id}` (204). Thin, like the existing handlers.

**`app/ingestion/pipeline.py`** — make a re-run idempotent: before `_persist`, delete any existing
`Chunk`/`Section` rows for the document. Today `_fail` cleans up on failure, but a retry of a *stuck*
run may find rows the previous run committed, and `UNIQUE(document_id, order_index)` would blow up
the retry. One extra statement pair, no behaviour change on a first run.

**`app/chat/generate.py`** — `GenerationDone` gains `stop_reason: str | None`. `AnthropicGenerator`
fills it from `final.stop_reason`; Mistral/Ollama/Fake pass `None`. This is the only place that knows
whether the model ran out of tokens.

**`app/chat/pipeline.py`** — four changes:
1. Stop fabricating ids. `DoneEvent` loses `message_id` entirely; the route owns persistence and
   therefore owns the id. `DoneEvent(grounded, truncated)`.
2. Consume `GenerationDone` instead of discarding it: set `truncated = stop_reason == "max_tokens"`,
   and log the usage line
   `logger.info("generation usage", extra={"phase": "generate", "provider", "model", "input_tokens",
   "output_tokens", "conversation_id", "document_id"})` — same shape as the `"rerank scores"` line in
   `retrieval/rerank.py:100`.
3. Drop the duplicate `recent_turns` call. It runs twice today (lines 75 and 127) with the same
   arguments; hold one result.
4. The ungrounded branch yields `DoneEvent(grounded=False, truncated=False)` and the route persists
   the refusal text as a real message, so a refusal survives a page reload like any other answer.

**`app/chat/rewrite.py`** — log a usage line (`phase: "rewrite"`) next to each successful provider
call, same fields.

**`app/retrieval/pipeline.py`** — guard the degrade path. When `scores is None` (re-ranker threw),
the code currently keeps all 30 candidates and reports `grounded=True` no matter how bad they are —
the grounding guard is effectively off exactly when it matters most. Replace with: filter candidates
to `distance <= settings.retrieval_max_distance`, and if nothing survives return
`SearchOutcome(grounded=False, reason="rerank_degraded_no_match")`. When the re-ranker works, nothing
changes.

**`app/api/routes/conversations.py`** — heartbeat + persistence ownership.
- `persist_assistant_message` returns the created `Message` (and stops swallowing failures silently
  — on failure it emits an `error` event instead of a `done` the client can't reconcile).
- The `done` payload uses `str(message.id)` and the pipeline's `grounded`/`truncated`.
- Heartbeat: a producer task pushes pipeline events into an `asyncio.Queue`; the generator loop does
  `await asyncio.wait_for(queue.get(), timeout=settings.chat_heartbeat_seconds)` and yields
  `": ping\n\n"` on `TimeoutError`. Producer signals completion with a sentinel. The existing
  `anyio.CancelScope(shield=True)` disconnect handler stays, and the producer task is cancelled in a
  `finally` so a client disconnect can't leak a running generation.

**API changes**

```
POST   /documents/{id}/retry   → 200 DocumentRead
                                 404 unknown · 409 "document is already processed"
                                              · 409 "document is still processing"
                                              · 409 "original file is missing; re-upload it"
DELETE /documents/{id}         → 204
                                 404 unknown
SSE                            → comment frames ": ping" may appear between events
                                 done.message_id is now a real message id
```

**Data model** — unchanged. No migration.

**Dependencies** — `sonner` (web). `alert-dialog` and `dropdown-menu` primitives come from the
already-installed `radix-ui` package; the shadcn wrappers land in `components/ui/`.

### Frontend Changes

```
api/documents.ts        + deleteDocument(id), retryDocument(id)
api/conversations.ts    + deleteConversation(id)

features/documents/useDeleteDocument.ts   invalidate ["documents"]
features/documents/useRetryDocument.ts    invalidate ["documents"], ["document", id]
features/chat/useDeleteConversation.ts    invalidate ["conversations", documentId]

components/ui/alert-dialog.tsx   shadcn (radix)
components/ui/sonner.tsx         shadcn Toaster
components/ConfirmDialog.tsx     shared: title, body, destructive confirm label
components/ErrorBoundary.tsx     class component; Alert + "reload" button

main.tsx        QueryClient gains queryCache/mutationCache onError → toast.error(...)
                (one central surface; no per-hook error wiring)
layouts/AppLayout.tsx   renders <Toaster /> and wraps <Outlet /> in <ErrorBoundary />
```

- `DocumentListItem` is a bare `NavLink` today, so action buttons can't be nested inside it (invalid
  HTML, and clicks would navigate). Restructure to a `relative` wrapper: `NavLink` fills it, action
  buttons sit absolutely positioned on the right, revealed on `group-hover`/`focus-within`. Retry
  button renders only for `FAILED`.
- Deleting the document currently in view: the mutation's `onSuccess` calls `navigate("/documents")`
  before invalidation, so the route doesn't render against a 404. `ChatPage` aborts any in-flight
  stream via `useChatStream().abort()` on unmount.
- Deleting the conversation currently in view: navigate to `/documents/:documentId`.

### Alternative Approaches Considered

**Retry eligibility — FAILED only vs. FAILED + stuck.** FAILED-only is simpler, but a worker that
dies mid-task leaves the row at `PARSING` forever with no way out of the UI — the exact scenario
retry exists for. Chosen: FAILED plus an `updated_at` age check. Rejected: allowing retry from
`READY` — an accidental click re-embeds a 300-page book for nothing.

**Where the heartbeat lives.** Putting it in `chat/pipeline.py` (yield a `HeartbeatEvent` between
steps) keeps the route dumb but pollutes the pipeline's event type with a transport concern and only
fires at step boundaries — it can't cover a single slow generation call. Chosen: queue + `wait_for`
in the route, which is time-based and covers every gap. Rejected: `sse-starlette` (a dependency for
one feature we can write in ~15 lines).

**Delete: Core statement vs. ORM cascade.** `session.delete(document)` with the ORM would load every
chunk into memory to cascade in Python. `delete(Document).where(...)` pushes it to Postgres, which
already has `ON DELETE CASCADE` on every FK in the chain. Chosen: Core.

**Fixing `message_id`: move persistence into the pipeline, or move id ownership to the route.**
Moving persistence into the pipeline would make the pipeline untestable without a session write path
and would duplicate the disconnect-handling that already lives in the route. Chosen: the route
persists and then emits the persisted id; `DoneEvent` stops carrying an id it can't know.

**Error surface: toasts vs. inline alerts.** Inline alerts avoid a dependency but need per-component
wiring for every mutation, and a stream error has no natural inline home. Chosen: `sonner` wired once
into the QueryClient caches, keeping the existing inline `Alert` for the persistent `FAILED` document
reason (that one isn't transient and shouldn't disappear).

---

## Implementation Steps

**Backend — endpoints**

1. `app/config.py`: add `stuck_after_minutes: int = 30` and `retrieval_max_distance: float = 0.75`.
2. `app/services/documents.py`: add `delete_document(session, document_id) -> bool` (Core delete,
   returns whether a row was removed; unlink `file_path` after commit, log a warning if unlink
   fails).
3. `app/services/documents.py`: add `retry_document(session, document_id, settings) -> Document`
   with the eligibility rules and their `HTTPException`s; clears `chunks`/`sections`, sets
   `PENDING`, clears `error_message`, commits, then `process_document.delay(...)`.
4. `app/api/routes/documents.py`: wire `DELETE /{document_id}` (204) and
   `POST /{document_id}/retry` (200, `DocumentRead`).
5. `app/ingestion/pipeline.py`: delete existing `Chunk`/`Section` rows for the document immediately
   before `_persist`, so a retry can't hit `UNIQUE(document_id, order_index)`.

**Backend — chat correctness**

6. `app/chat/generate.py`: add `stop_reason` to `GenerationDone`; populate it in
   `AnthropicGenerator` from `final.stop_reason`, `None` elsewhere.
7. `app/chat/pipeline.py`: drop `message_id` from `DoneEvent`; consume `GenerationDone` to set
   `truncated`; log the `"generation usage"` line; collapse the duplicate `recent_turns` call.
8. `app/chat/rewrite.py`: log a `phase: "rewrite"` usage line on each successful provider call.
9. `app/retrieval/pipeline.py`: apply the `retrieval_max_distance` floor on the degrade path; return
   `grounded=False, reason="rerank_degraded_no_match"` when nothing survives.
10. `app/api/routes/conversations.py`: `persist_assistant_message` returns the `Message` and no
    longer swallows errors; `done` payload uses the persisted id and the pipeline's flags; the
    ungrounded refusal is persisted.
11. `app/api/routes/conversations.py`: heartbeat — producer task → `asyncio.Queue` →
    `wait_for(timeout=chat_heartbeat_seconds)` → `": ping\n\n"` on timeout; cancel the producer in
    `finally`.

**Backend — tests**

12. `tests/conftest.py`: add a `fake_llm` fixture that monkeypatches
    `app.api.routes.conversations.build_generator` / `build_rewriter` (they're imported into the
    route module's namespace, so patch there, not at the source module), plus a helper to seed a
    `READY` document with chunks via `factories`.
13. `tests/test_chat_api.py` (new): event order `sources → token* → done`; `done.message_id` matches
    a row returned by `GET /conversations/{id}/messages`; persisted `message_sources` ranks match the
    `sources` event order; ungrounded question → refusal text, `grounded=false`, zero sources, still
    persisted; generator raises → `error` frame and no half-written `done`; client disconnect →
    message persisted with `truncated=true`; 409 when the document isn't `READY`; 404 on unknown
    conversation; slow generator + `chat_heartbeat_seconds=0.05` → at least one `: ping` frame and
    the answer text is unaffected.
14. `tests/test_chat_pipeline.py` (new): `stop_reason="max_tokens"` → `DoneEvent.truncated is True`;
    usage line asserted via `caplog`; history capped at `chat_history_turns`.
15. `tests/test_documents_api.py`: delete → 204, row/chunks/conversations gone, file unlinked,
    second delete → 404, re-upload of the same bytes creates a new id; retry from `FAILED` →
    `PENDING` + enqueued; retry from `READY` → 409; retry from a backdated `EMBEDDING` → `PENDING`;
    retry from a fresh `PENDING` → 409; retry with the file removed from disk → 409.
16. `tests/test_search_api.py`: with the re-ranker forced to raise, a query far from every chunk
    returns `grounded=false, reason="rerank_degraded_no_match"`; a close query still returns results.

**Frontend**

17. `pnpm add sonner` in `apps/web`; add `components/ui/sonner.tsx` and
    `components/ui/alert-dialog.tsx` (shadcn, new-york style, matching the existing primitives).
18. `components/ConfirmDialog.tsx` and `components/ErrorBoundary.tsx`.
19. `main.tsx`: QueryClient `queryCache`/`mutationCache` `onError` → `toast.error(err.message)`;
    `AppLayout`: render `<Toaster />`, wrap `<Outlet />` in `<ErrorBoundary />`.
20. `api/documents.ts` + `api/conversations.ts`: `deleteDocument`, `retryDocument`,
    `deleteConversation`. Note `request<T>` JSON-parses an empty body to `null`, which is already
    correct for a 204 — type these as `Promise<void>`.
21. `useDeleteDocument`, `useRetryDocument`, `useDeleteConversation` hooks with the invalidations
    listed above.
22. `DocumentListItem`: restructure to the `relative`/`group` wrapper; add delete (always) and retry
    (`FAILED` only) buttons behind `ConfirmDialog`; success toast on retry ("re-processing started").
23. `ConversationList`: per-row delete button behind `ConfirmDialog`.
24. Navigation on delete: document → `/documents`; conversation → `/documents/:documentId`; abort any
    in-flight stream first.
25. `src/test/handlers.ts`: MSW handlers for `DELETE /documents/:id`, `POST /documents/:id/retry`,
    `DELETE /conversations/:id`; vitest tests for the three hooks (success invalidates, failure
    toasts) and for `ConfirmDialog` gating the mutation until confirmed.

**Docs**

26. `PRD.md`: mark Phase 6 done, move the retry/delete endpoints out of "not built" in §6, record
    deviations (the three bugfixes, the degrade floor, `stuck_after_minutes`).

### Risks & Mitigations

- **Retry races a still-alive task.** A "stuck" document may just be slow; retrying gives two
  workers the same document and the second `_persist` hits `UNIQUE(document_id, order_index)`.
  - Mitigation: `stuck_after_minutes` defaults to 30, matching the Celery `time_limit=1800` — past
    that the first task has been killed.
  - Mitigation: step 5 makes `_persist` delete-then-insert, so the loser fails cleanly and `_fail`
    leaves no partial rows; worst case the user retries again.
- **Delete during an active stream.** The route's `stream_db` session queries a conversation that no
  longer exists mid-generation.
  - Mitigation: the pipeline already returns `ErrorEvent("conversation not found")` when the
    conversation is missing; the frontend aborts the stream before navigating away.
  - Mitigation: `persist_assistant_message` failing on a deleted conversation now emits an `error`
    frame instead of logging and pretending success.
- **Heartbeat frames corrupt the answer.** A comment frame parsed as data would inject `ping` into
  the answer text.
  - Mitigation: `parseSse` already returns `null` for frames without both `event:` and `data:`
    (`api/sse.ts:38`), so comments are dropped — covered by the step 13 heartbeat test and an
    `sse.test.ts` case.
- **The degrade floor makes the app refuse to answer when the re-ranker is down.** A badly chosen
  `retrieval_max_distance` turns a degraded-but-usable state into blanket "not in this document".
  - Mitigation: 0.75 cosine distance is deliberately loose, and it applies *only* when re-ranking
    failed. It is a setting, so it can be relaxed without a deploy.
- **`sonner` + the QueryClient error hook makes every background refetch shout.** `useDocuments`
  polls every 2 s while a document is processing; a flapping backend would spam toasts.
  - Mitigation: toast on mutation errors always; for query errors only when the query has no cached
    data (initial load), which is where the user is actually blind.
- **Deleting the PDF breaks a re-upload flow the user expects to dedupe.** After a delete, the same
  file uploads as a brand-new document with new embeddings — a real cost.
  - Mitigation: that's the intended semantic of a hard delete; the confirm dialog says the book will
    have to be processed again.

## Test Strategy

**Unit (pytest)**
- `retry_document` eligibility matrix (FAILED / READY / fresh in-flight / stale in-flight / missing
  file / unknown id).
- `process_document` re-run over a document that already has chunks — succeeds, ends with exactly
  one set of chunks.
- `DoneEvent.truncated` from `stop_reason`; usage log lines via `caplog`.
- Retrieval degrade floor with a raising re-ranker.

**Integration (pytest, real Postgres + stubbed queue/LLM)**
- Full SSE round trip against the ASGI app with `FakeGenerator`/`FakeReranker`: frame order,
  persistence, ids, sources, ungrounded, error, disconnect, heartbeat.
- `DELETE /documents/{id}` cascade verified by querying chunks, sections, conversations and messages
  afterwards, plus `Path(file_path).exists() is False`.
- `POST /documents/{id}/retry` verified by the `enqueued` fixture.

**Frontend (vitest + MSW)**
- The three mutation hooks: success invalidates the right query keys; failure produces a toast.
- `ConfirmDialog` does not call the mutation until confirmed.
- `parseSse` ignores comment frames.

**Manual**
- Upload a bad PDF → `FAILED` with a reason → retry → still fails with the same reason (no duplicate
  rows, no orphan chunks).
- Kill the worker mid-ingest, wait past `stuck_after_minutes` (or backdate `updated_at`), retry →
  completes.
- Delete a book being chatted with in another tab → that tab surfaces an error rather than hanging.
- Ask a question with the API's LLM key removed → `FakeGenerator` path still streams and persists.
- Watch `docker compose logs api` during one question: exactly three usage lines (rewrite, rerank,
  generate).

## Success Checklist

- [ ] All success criteria verified with evidence (test names or log excerpts)
- [ ] `pytest` green, including the new chat suite
- [ ] `pnpm turbo run lint typecheck test` green
- [ ] No new migration needed (schema untouched) — confirmed by `alembic check`
- [ ] `PRD.md` §6 and §8 updated; Phase 6 marked done with deviations recorded
- [ ] Manual pass through the five scenarios above
- [ ] No regression: upload → ready → ask → cite still works end to end

## Timeline & Estimates

| Block | Estimate |
|---|---|
| Retry + delete endpoints and services (steps 1–5) | ~3 h |
| Chat correctness: ids, truncated, usage logs, degrade guard, heartbeat (steps 6–11) | ~4 h |
| Backend tests (steps 12–16) | ~4 h |
| Frontend: deps, dialogs, toasts, boundary, hooks, wiring (steps 17–24) | ~4 h |
| Frontend tests + docs (steps 25–26) | ~2 h |
| **Total** | **~17 h** (plus buffer) |

## Open Questions

None blocking. Two judgement calls made in the plan, cheap to reverse:

- `retrieval_max_distance = 0.75` is a first guess; tune once against a real book if the degrade path
  ever fires.
- Query-error toasts fire only when the query has no cached data, to keep the 2 s document poll
  quiet. If silent background failures prove confusing, promote them to toasts.
