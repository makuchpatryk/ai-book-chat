# Per-Document Quiz Generation — Implementation Plan

## Summary
Add a "Prepare Quiz" action per document that becomes available once ingestion/embedding completes (`DocumentStatus.READY`). It generates a 10-question multiple-choice (A/B/C/D) quiz from the document's embedded chunks via the existing chat LLM, caches it, and displays it in a modal that cannot be dismissed by clicking outside or pressing Escape — only an explicit X button closes it. Grading is done client-side and is ephemeral (no attempt history persisted).

## Success Criteria
- Quiz button appears/enables only when `document.status == READY`.
- First click generates and caches exactly 10 MCQs (4 options each) grounded in the document's chunks (not full raw text).
- Second click on the same document reopens the cached quiz without a new LLM call.
- A separate "Regenerate" action forces a fresh quiz, replacing the cached one.
- Modal cannot be dismissed via backdrop click or Escape; only the X button closes it.
- After submitting all 10 answers, user sees total score + per-question correct/incorrect + correct answer, with nothing persisted to the DB as attempt history.
- New unit/API tests pass; import-linter continues to enforce clean-architecture layering.

## Scope & Constraints
- In scope: quiz generation (async via existing Celery worker), caching per document, explicit regenerate, modal UI, client-side grading.
- Out of scope: configurable question count, difficulty levels, non-MCQ question types, attempt history/analytics, timed quizzes, multi-user scoping (app has no auth).
- Hard constraint: reuse existing Celery worker infra and chunk-sampling helper — no new async mechanism.
- Trade-off: grading is client-side (correct answers ship with the quiz payload) rather than a server-side submit endpoint — acceptable because attempts aren't persisted and this is a single-user tool with no anti-cheat requirement.
- Trade-off: quiz questions are stored as a single JSON blob per document (matches the existing `document.description_sections` JSON-column precedent) rather than a normalized per-question table — simpler, and per-question querying isn't needed anywhere.

## Architecture & Design

### High-Level Flow
```
Frontend button (DocumentListItem, enabled when status===READY)
  -> POST /documents/{id}/quiz          (get-or-create; 202 if generating, 200 if cached ready)
  -> poll GET /documents/{id}/quiz while status=PENDING
  -> status=READY: open modal; questions (incl. correct_option) already loaded client-side
  -> user answers all 10 -> Submit -> client-side grade -> render per-question review + score
  -> "Regenerate" -> POST /documents/{id}/quiz/regenerate -> resume polling
```
Backend generation mirrors the existing overview feature: an HTTP route enqueues a Celery task; the task loads chunks, samples them evenly, calls an LLM adapter, persists the result as JSON, flips status.

### Key Changes

**Domain** (`apps/api/src/app/domain/`)
- `values/quiz.py` (new): `QuizStatus(StrEnum)` {PENDING, READY, FAILED}; `QuizQuestion` dataclass (position, question, option_a, option_b, option_c, option_d, correct_option: Literal["A","B","C","D"]).
- `Quiz` entity (id, document_id, status, questions: list[QuizQuestion], error_message, created_at/updated_at) with `mark_pending()`, `apply_questions(questions: list[QuizQuestion])` (validates exactly 10, each with a valid `correct_option`), `mark_failed(msg)` — mirrors `Document.mark_overview_pending/apply_overview/mark_overview_failed`.
- `errors.py`: reuse `DocumentNotFound`/`DocumentNotReady` for gating on document status; add `QuizAlreadyPending` only if needed for the dedupe window (see `RequestQuiz` below — likely handled without raising).
- `ports/llm.py`: add `QuizGenerator(Protocol): async def generate(self, title: str, chunks: list[str]) -> list[QuizQuestion]` (must return exactly 10).
- `ports/storage.py` (`IngestionQueue`): add `enqueue_quiz(document_id)`.
- `ports/repositories.py`: add `QuizRepository(Protocol)`: `get_for_document(document_id) -> Quiz | None`, `save(quiz) -> None`.

**Application** (`apps/api/src/app/application/usecases/documents/`)
- `request_quiz.py` — `RequestQuiz.execute(document_id)`: load document (404 if missing), require `status == READY` else raise `DocumentNotReady`. Load existing quiz: if `READY`, return as-is (cache hit, no LLM call); if `PENDING` and within a 10-min dedupe window (same pattern as overview's `PENDING_TIMEOUT`), return current state as-is; if none or `FAILED` (or `PENDING` past the timeout), create/reset `Quiz(status=PENDING)`, save, enqueue `enqueue_quiz`.
- `regenerate_quiz.py` — `RegenerateQuiz.execute(document_id)`: require document READY; reset existing quiz row to PENDING (clear questions), save, enqueue unconditionally (bypasses the cache-hit check, always forces a new LLM call).
- `generate_quiz.py` — `GenerateQuiz.execute(document_id) -> bool` (worker-side, "never raises" like `GenerateDocumentOverview`): loads document + chunks via `uow.chunks.list_for_document`, samples them with the existing `sample_chunks(chunks, max_input_tokens)` helper (the same one `GenerateDocumentOverview` uses for evenly-spaced coverage), calls `QuizGenerator.generate` with retry (2 attempts, matching `DESCRIBE_ATTEMPTS`), validates exactly 10 well-formed questions, persists via `quiz.apply_questions(...)` + `uow.quizzes.save(quiz)`, or `quiz.mark_failed(...)` if all attempts fail.
- `get_quiz.py` — `GetQuiz.execute(document_id) -> Quiz | None` (for the GET polling route).

**Infrastructure**
- `infrastructure/llm/adapters.py`: add `OpenAIQuizGenerator` implementing `QuizGenerator` — one prompt requesting a JSON array of 10 objects `{question, option_a, option_b, option_c, option_d, correct_option}` via the OpenAI-compatible client's JSON-mode/response_format, parsed and validated with a Pydantic model (parse failures count against the use case's retry budget). `build_quiz_generator(settings)` factory alongside `build_describer`.
- `infrastructure/queue/celery_queue.py`: `enqueue_quiz(document_id)` → `generate_quiz.delay(str(document_id))`.
- `infrastructure/db/models/quiz.py` (new): single SQLAlchemy `Quiz` model — `id` (UUID pk), `document_id` (FK to `documents`, unique — one quiz per document, `ON DELETE CASCADE`), `status` (native enum, same pattern as `DocumentStatus`), `questions` (`sqlalchemy.JSON`, list of question dicts — same pattern as `Document.description_sections`), `error_message` (Text, nullable), `created_at`/`updated_at`.
- `infrastructure/db/repositories/quiz_repository.py`: implements `QuizRepository`, upserting the single row per document.

**Interfaces**
- `interfaces/worker/tasks.py`: `@shared_task(name=..., acks_late=True, time_limit=300) def generate_quiz(document_id: str)` mirroring `generate_overview`.
- `interfaces/worker/composition.py`: `get_generate_quiz()`.
- `interfaces/http/routers/documents.py`:
  - `POST /documents/{id}/quiz` → `RequestQuiz.execute` → `QuizRead` (200 if READY/already-PENDING, 202 if newly enqueued).
  - `POST /documents/{id}/quiz/regenerate` → `RegenerateQuiz.execute` → 202 `QuizRead`.
  - `GET /documents/{id}/quiz` → `GetQuiz.execute` → `QuizRead` or 404 (used for polling).
- `interfaces/http/schemas/documents.py`: `QuizQuestionRead` (position, question, option_a..d, correct_option), `QuizRead` (id, document_id, status, questions: list[QuizQuestionRead], error_message).
- `interfaces/http/composition.py`: DI factories `get_request_quiz`, `get_regenerate_quiz`, `get_get_quiz`.

**DB Migration**: `apps/api/alembic/versions/0008_quiz_table.py` — `op.create_table("quizzes", ...)` with a unique index on `document_id` and `ON DELETE CASCADE` FK to `documents`, modeled on the existing migration style (see `0002_ingestion_tables.py`).

**Frontend** (`apps/web/src/features/documents/`)
- `libs/api/documents/api.ts`: `prepareQuiz(id)`, `regenerateQuiz(id)`, `getQuiz(id)`.
- `hooks/useQuiz.ts`: `useQuery(["quiz", id], getQuiz, { enabled: doc.status==="READY", refetchInterval: (data) => data?.status==="PENDING" ? 2000 : false })`.
- `hooks/usePrepareQuiz.ts` / `hooks/useRegenerateQuiz.ts`: `useMutation` invalidating `["quiz", id]`.
- `components/DocumentListItem.tsx`: add "Prepare Quiz" button (disabled unless `status===READY`), opens `QuizModal` once quiz data is READY.
- `components/QuizModal.tsx` (new): built on Radix `Dialog` primitives directly (the existing `alert-dialog.tsx` wrapper is AlertDialog-specific and doesn't expose outside-click override) with `onInteractOutside={(e) => e.preventDefault()}` and `onEscapeKeyDown={(e) => e.preventDefault()}`, an explicit X close button in the header, following the Tailwind/`cn`/`forwardRef` conventions already used in `alert-dialog.tsx`. Internal state: 10 nullable answer slots + `submitted` boolean. On submit, grade client-side against `correct_option` already present in the fetched quiz payload; render per-question review (question, selected answer, correct answer, right/wrong marker) plus total score (e.g. "7/10").

### Alternative Approaches Considered
- **Synchronous generation** vs **async Celery + polling (chosen)**: sync is simpler but ties up an HTTP worker for the full LLM round-trip and risks request timeouts on slower models; async matches the existing overview-generation pattern exactly (same worker, same client polling shape), so it was chosen for consistency and reliability.
- **Top-K retrieval via `RetrieveContext`** vs **even-spaced `sample_chunks` (chosen)**: retrieval-based sampling could target the most "important" content via a synthetic query, but adds extra embedding/rerank calls and complexity for one LLM prompt; the even-spaced helper is already proven (used by overview generation) and gives simple, predictable coverage across the whole document.
- **Normalized `quiz_questions` table** vs **single JSON column on `quizzes` (chosen)**: a per-question table would make individual questions queryable, but nothing in this feature needs that (no analytics, no attempt history); a JSON column matches the existing `document.description_sections` precedent and keeps the schema/entity code simpler.
- **Server-side submit/grade endpoint** vs **client-side grading (chosen)**: a submit endpoint would keep correct answers off the wire until submission, but since attempts aren't persisted and there's no multi-user cheating concern, shipping `correct_option` with the quiz and grading in the browser avoids an entire extra endpoint and request schema.

## Implementation Steps
1. Alembic migration `0008_quiz_table.py` creating the `quizzes` table (JSON `questions` column, unique `document_id`, cascade delete).
2. Domain: `values/quiz.py`, `Quiz` entity + methods, port protocols (`QuizGenerator`, `QuizRepository`, `IngestionQueue.enqueue_quiz`).
3. Infrastructure: SQLAlchemy `Quiz` model + `QuizRepository` impl; `OpenAIQuizGenerator` + `build_quiz_generator`; `CeleryIngestionQueue.enqueue_quiz`.
4. Application use cases: `RequestQuiz`, `RegenerateQuiz`, `GenerateQuiz`, `GetQuiz`.
5. Worker: `generate_quiz` Celery task + composition wiring.
6. HTTP: schemas, routes, composition DI.
7. Unit tests (domain entity, use cases with fakes) — see Test Strategy.
8. Frontend: API functions, hooks, `QuizModal.tsx`, wire button into `DocumentListItem.tsx`.
9. Manual end-to-end verification (see Test Strategy).

### Risks & Mitigations
- **LLM returns malformed JSON or wrong question count**: mitigate with Pydantic validation + retry (2 attempts, same as describer); mark quiz FAILED with a surfaced error and let the user hit Regenerate.
- **Long documents produce too many chunks for one prompt**: reuse the existing `max_input_tokens`-bounded `sample_chunks` helper already proven for overview generation.
- **User clicks Prepare Quiz twice quickly**: guarded by the PENDING-timeout dedupe pattern already used for overview requests.
- **Correct answers visible in the network response before submission**: explicitly accepted trade-off (client-side grading), not a bug — no multi-user/anti-cheat requirement exists in this app.
- **Document deleted while a quiz exists**: `ON DELETE CASCADE` FK from `quizzes.document_id` → `documents.id`.

## Test Strategy
- Unit (domain): `test_quiz_entity.py` — status transitions, `apply_questions` validation (exactly 10, valid `correct_option` per question).
- Unit (application): `test_quiz_usecases.py` — `RequestQuiz` cache-hit / cache-miss / pending-dedupe, `RegenerateQuiz` force-reset, `GenerateQuiz` success/failure/retry — using `fakes.py` (`FakeUowFactory`, a new `ScriptedQuizGenerator`, `make_document`, `make_quiz`).
- API-level: `test_quiz_api.py` mirroring `test_overview_api.py` — route status codes (200/202/404).
- Manual: generate a quiz on a real ingested PDF, verify 10 questions render, answer all, submit, confirm score + per-question review, click Regenerate and confirm new questions differ, verify backdrop click and Escape do not close the modal, confirm the X button does.

## Success Checklist
- [ ] All success criteria met and manually verified
- [ ] New unit + API tests passing, import-linter still clean
- [ ] Migration applied cleanly on a fresh DB
- [ ] Frontend build/typecheck passes
- [ ] Manual E2E pass (see above)
- [ ] No regressions to existing document list/detail actions

## Timeline & Estimates
- Backend (domain/app/infra/worker/routes/migration): ~4-5h
- Frontend (hooks/modal/button wiring): ~2-3h
- Tests (unit + API): ~2h
- Manual verification + polish: ~1h
- **Total**: ~9-11h (rough estimate, plus buffer)

## Open Questions
None — all decisions confirmed with the user: fixed 10 questions, async generation via Celery, even-spaced chunk sampling, single-JSON-column storage, client-side ephemeral grading with per-question review, cache + explicit regenerate, X-only modal close (no backdrop/Escape dismiss), button on the document list/detail item.
