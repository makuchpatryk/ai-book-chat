# Rename Conversation — Implementation Plan

## Summary
Users can't rename a chat. Sidebar shows `conv.title || "New chat"`, and `title` is never set today (see Findings), so every chat reads "New chat". Add `PATCH /conversations/{id}` + inline edit in the sidebar list.

## Findings from code exploration
- `Conversation.title: str | None` exists (entity, ORM `String(200)`, `ConversationRead`, TS type). No migration needed.
- `Conversation.derive_title` exists and is tested, but **nothing calls it** — `ask_question.py` never sets the title. Titles are always `null` right now. Out of scope here (see Open Questions), but rename makes the "only derive when null" rule trivially safe whenever auto-title is wired.
- Port `ConversationRepository` has `get/list_for_document/add/delete` only — no update.
- Clean Architecture enforced by import-linter: domain pure, use cases take `UnitOfWorkFactory`, routers thin, deps in `interfaces/http/composition.py`.
- Frontend: `libs/api/conversations/api.ts` → hook in `features/chat/hooks/` → `ConversationList.tsx`. Query key `["conversations", documentId]`.

## Success Criteria
- `PATCH /conversations/{id}` `{"title": "  My chat "}` → 200, returns `{id, title: "My chat", created_at}`; persisted.
- Empty / whitespace-only / >100 chars → 422. Unknown id → 404.
- Sidebar: hover pencil → inline input prefilled with current title; Enter saves, Esc/blur-empty cancels; list updates without reload.
- Renaming never triggers navigation; NavLink click doesn't fire while editing.
- New unit + integration tests pass; import-linter still green.

## Scope & Constraints
- In scope: backend endpoint, use case, repo method; sidebar inline edit; tests.
- Out of scope: chat page header rename, auto-title wiring in `AskQuestion`, "reset to default" (empty rejected), migration.
- Decisions (user-confirmed): inline sidebar edit; trim + 1–100 chars; manual title never overwritten by auto-derive (derive only when `title is None`); sidebar only.
- Trade-off: validate at HTTP boundary (pydantic) rather than entity — matches `SendMessageRequest` pattern, least code. 100 < column 200, safe.

## Architecture & Design

### High-Level Flow
```
ConversationList (pencil) -> inline <input> -> useRenameConversation
  -> PATCH /conversations/{id} {title}
  -> router -> RenameConversation.execute(id, title)
  -> uow.conversations.rename(id, title)  (sets title, updated_at)
  -> commit -> ConversationRead
  -> invalidate ["conversations", documentId]
```

### Key Changes
- `apps/api/src/app/domain/ports/repositories.py`: add `ConversationRepository.rename(conversation_id, title) -> Conversation | None`.
- `apps/api/src/app/infrastructure/db/repositories.py`: `SqlConversationRepository.rename` — select row, set `title`, `updated_at = datetime.utcnow()`, flush, return `orm_conversation_to_entity(row)`; `None` if missing.
- `apps/api/src/app/application/usecases/chat/rename_conversation.py` (new): `RenameConversation(uow_factory).execute(conversation_id, title) -> Conversation | None`; commit only on success (mirrors `DeleteConversation`).
- `apps/api/src/app/interfaces/http/schemas/chat.py`: `RenameConversationRequest` with `title: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]`.
- `apps/api/src/app/interfaces/http/composition.py`: `get_rename_conversation`.
- `apps/api/src/app/interfaces/http/routers/conversations.py`: `@router.patch("/conversations/{conversation_id}", response_model=ConversationRead)`; 404 "conversation not found".
- `apps/web/src/libs/api/conversations/api.ts`: `renameConversation({conversationId, title})` → `request<Conversation>(..., {method:"PATCH", body: JSON.stringify({title}), headers JSON})` — match how `libs/api/chat/api.ts` sends JSON.
- `apps/web/src/features/chat/hooks/useRenameConversation.ts` (new): mutation, `onSuccess` invalidates `["conversations", documentId]`.
- `apps/web/src/features/chat/components/ConversationList.tsx`: `editingId` + `draft` state; pencil `Button` (lucide `Pencil`) beside trash; when editing render `<input maxLength={100} autoFocus>` instead of NavLink content. Enter → submit if trimmed non-empty and changed; Esc → cancel; blur → submit (same rule). `onClick`/`onKeyDown` `stopPropagation` + no NavLink wrapping while editing.

### Alternative Approaches Considered
- **PUT/POST `/rename`**: not RESTful; PATCH on the resource fits partial update.
- **Generic `update` on repo taking entity**: more flexible, but port has no update pattern and only title mutates; `rename` is explicit and minimal.
- **Modal dialog**: reuses ConfirmDialog style but heavier UX; user chose inline.
- **Optimistic update**: nicer feel; skipped — invalidate is enough for a local single-user app, add later if laggy.

## Implementation Steps
1. Add `rename` to `ConversationRepository` port; implement in `SqlConversationRepository`; add to any fake UoW/repo in `tests/fakes.py` if conversations are faked there.
2. Add `RenameConversation` use case + unit test with fake UoW (renames, returns None on missing, no commit on missing).
3. Add request schema, composition dep, PATCH route.
4. Integration test (`tests/test_rename_conversation.py`, `pytest.mark.integration`, `client` fixture): create doc + conversation, PATCH ok / trims / 422 empty / 422 too long / 404 unknown; list reflects new title.
5. Frontend: `renameConversation` api fn, `useRenameConversation` hook.
6. `ConversationList` inline edit UI.
7. Manual check in browser (see below). Run `pytest`, import-linter, `tsc`/lint, web tests.

## Risks & Mitigations
- Risk: click on pencil/input triggers NavLink navigation.
  - Mitigation: render input outside `<NavLink>` while editing; `preventDefault` + `stopPropagation` on pencil.
- Risk: blur + Enter double-submit (Enter causes unmount/blur).
  - Mitigation: `submittedRef` guard, or clear `editingId` before mutate.
- Risk: whitespace title passes client, fails 422 → silent.
  - Mitigation: client trims and skips empty; on mutation error keep input open + show toast/inline error (use existing error pattern if any).
- Risk: title vs. future auto-title race overwrite.
  - Mitigation: when wired, derive only if `conversation.title is None`, re-read inside same UoW.
- Risk: hidden-until-hover pencil unreachable on touch/keyboard.
  - Mitigation: also `group-focus-within:block`; same as existing trash button behaviour (accepted).

## Test Strategy
- Unit: `RenameConversation` (success, not found → None, no commit on miss).
- Integration: PATCH happy path, trim, 422 ×2, 404, persisted in list.
- Frontend: hook/component test if `ConversationList` has none yet — at minimum, test Enter submits trimmed title and Esc cancels (Vitest + Testing Library, matching `useChatStream.test.tsx` setup).
- Manual: rename, reload page → persists; rename active chat → still selected; rename to 100 chars; Esc; rename while streaming an answer.

## Success Checklist
- [ ] All success criteria met
- [ ] Backend tests + import-linter pass
- [ ] Web typecheck, lint, tests pass
- [ ] No regression in delete / new chat / navigation
- [ ] Committed directly to main, one-line subject, no trailer (per memory)

## Timeline & Estimates
- Backend: ~1 h
- Frontend: ~1 h
- Tests + manual: ~1 h
- **Total**: ~3 h

## Open Questions
- [ ] Titles are never auto-derived today (`derive_title` unused). Wire it into `AskQuestion` (set on first user message when `title is None`) as a follow-up? Separate spec/commit suggested.
