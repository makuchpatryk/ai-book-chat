# Frontend Refactor: Feature-Based Architecture with Shared DTOs

## Summary

Reorganize frontend from flat type/API structure into a clean feature-based architecture with domain-driven DTOs, centralized API service layer, and systematic UI component reuse. This eliminates type safety gaps, reduces duplication, and makes onboarding new devs fast.

## Success Criteria

- [ ] DTOs split by domain (documents, conversations, chat, health) instead of single types file
- [ ] Each feature folder has: `api.ts`, `hooks/`, `components/`, `types.ts`
- [ ] All API functions have full TS typing from request → response (zero `any` types)
- [ ] New feature scaffoldable in <1 day by copying feature template
- [ ] Shared UI components documented with usage patterns
- [ ] Zero circular imports; clear dependency graph (shared → features → pages)
- [ ] All DTOs match backend DTO structure (manual sync or codegen-ready)

## Scope & Constraints

**In scope:**
- Reorganize folder structure (feature-based directories)
- Split types.ts into domain-specific DTO files
- Consolidate API service layer (already mostly organized, needs cleaner structure)
- Move/organize custom hooks per feature
- Clarify shared component boundaries (ui/ vs feature-specific)
- Update import paths across codebase
- Document feature template and API layer pattern

**Out of scope:**
- Migrate from React Query to different state management
- Change styling/Tailwind setup
- Rewrite existing components (only move/refactor)
- Add new features (only organize existing ones)
- Backend DTO generation tooling (prep for future codegen)

**Hard constraints:**
- Solo dev, flexible timeline
- No breaking changes to routing (React Router structure stays)
- React app (not Vue — clarify "composables" = custom hooks)
- Must maintain working dev server during refactor

**Trade-offs:**
- Prioritizing organization & type safety over incremental refactoring — full greenfield-style rewrite at once (safer, cleaner)
- Separate DTOs per domain over single types file (better scalability, slight duplication)
- Opinionated folder structure over flexible nesting (faster onboarding, consistent discovery)

## Architecture & Design

### High-Level Structure (Target)

```
/apps/web/src/
├── types/
│   ├── shared.ts          # Shared types (ApiError, etc.)
│   └── index.ts           # Re-exports for convenience
├── api/
│   ├── client.ts          # HTTP client wrapper (unchanged)
│   ├── documents/
│   │   ├── types.ts       # Document DTOs (Document, DocumentStatus, Section, etc.)
│   │   └── api.ts         # Document endpoints (listDocuments, uploadDocument, etc.)
│   ├── conversations/
│   │   ├── types.ts       # Conversation, Message, Source DTOs
│   │   └── api.ts         # Conversation endpoints
│   ├── chat/
│   │   ├── types.ts       # ChatEvent, streaming types
│   │   └── api.ts         # Chat streaming (streamMessage)
│   ├── health/
│   │   ├── types.ts       # HealthResponse
│   │   └── api.ts         # Health check
│   └── sse.ts             # SSE parser (unchanged)
├── components/
│   ├── ui/                # Shared UI primitives (shadcn + custom)
│   │   ├── button.tsx
│   │   ├── input.tsx
│   │   ├── card.tsx
│   │   └── ... (existing)
│   └── shared/            # Shared complex components
│       ├── ConfirmDialog.tsx
│       ├── ErrorBoundary.tsx
│       └── StatusBadge.tsx
├── features/
│   ├── documents/
│   │   ├── types.ts       # Feature-local types (if any)
│   │   ├── api.ts         # or: import from /api/documents
│   │   ├── hooks/
│   │   │   ├── useDocuments.ts
│   │   │   ├── useUploadDocument.ts
│   │   │   └── useDeleteDocument.ts
│   │   ├── components/
│   │   │   ├── DocumentList.tsx
│   │   │   ├── DocumentListItem.tsx
│   │   │   ├── UploadDropzone.tsx
│   │   │   └── index.ts   # Re-export (internal use only)
│   │   └── index.ts       # Public feature API (exports hooks + main component)
│   ├── chat/
│   │   ├── types.ts       # Chat-specific local state types (if any)
│   │   ├── api.ts         # or: import from /api/chat
│   │   ├── hooks/
│   │   │   ├── useChatStream.ts
│   │   │   ├── useConversations.ts
│   │   │   ├── useCreateConversation.ts
│   │   │   └── useDeleteConversation.ts
│   │   ├── components/
│   │   │   ├── ConversationList.tsx
│   │   │   ├── MessageList.tsx
│   │   │   ├── MessageInput.tsx
│   │   │   ├── MessageBubble.tsx
│   │   │   ├── StreamingMessage.tsx
│   │   │   ├── MarkdownAnswer.tsx
│   │   │   └── index.ts
│   │   └── index.ts
│   ├── health/
│   │   ├── hooks/
│   │   │   └── useHealth.ts
│   │   ├── components/
│   │   │   └── HealthStatus.tsx
│   │   └── index.ts
│   └── _template/         # Template for new features (reference)
│       ├── types.ts
│       ├── api.ts
│       ├── hooks/
│       │   └── use[Feature].ts
│       ├── components/
│       │   └── [Feature]View.tsx
│       └── index.ts
├── layouts/
│   └── AppLayout.tsx
├── routes/
│   ├── ChatPage.tsx       # Uses features/chat/index
│   ├── DocumentsPage.tsx  # Uses features/documents/index
│   ├── DocumentPage.tsx
│   └── HealthPage.tsx
├── lib/
│   └── utils.ts
├── test/
│   ├── setup.ts
│   └── handlers.ts
├── router.tsx
├── main.tsx
└── index.css
```

### Key Changes

#### 1. **Domain-Driven DTOs** (`/api/{domain}/types.ts`)

Split `/src/types/index.ts` into `/src/api/{domain}/types.ts`:

```typescript
// /src/api/documents/types.ts
export interface Document {
  id: string;
  name: string;
  status: DocumentStatus;
  created_at: string;
  error_message: string | null;
}

export type DocumentStatus = "PENDING" | "PARSING" | "EMBEDDING" | "READY" | "FAILED";

export interface DocumentDetail extends Document {
  sections: Section[];
}

export interface Section {
  id: string;
  title: string;
  content: string;
  embeddings: number[];
}

// /src/api/conversations/types.ts
export interface Conversation {
  id: string;
  document_id: string;
  created_at: string;
  title: string;
}

export interface Message {
  id: string;
  conversation_id: string;
  role: "user" | "assistant";
  content: string;
  created_at: string;
  sources: Source[];
}

export interface Source {
  document_id: string;
  section_id: string;
  title: string;
  score: number;
}

// /src/api/chat/types.ts
export type ChatEvent = ChatEventToken | ChatEventSources | ChatEventDone | ChatEventError;

export interface ChatEventToken {
  event: "token";
  token: string;
}

export interface ChatEventSources {
  event: "sources";
  sources: Source[];
}

export interface ChatEventDone {
  event: "done";
}

export interface ChatEventError {
  event: "error";
  error: string;
}

// /src/types/shared.ts
export class ApiError extends Error {
  constructor(public status: number, public body: unknown) {
    super(`API Error: ${status}`);
  }
}
```

#### 2. **API Service Layer** (`/src/api/{domain}/api.ts`)

Keep current pattern, add types import:

```typescript
// /src/api/documents/api.ts
import type { Document, DocumentDetail, DocumentStatus } from "./types";
import { request, upload } from "../client";

export async function listDocuments(): Promise<Document[]> {
  return request<Document[]>("/documents");
}

export async function uploadDocument(file: File): Promise<Document> {
  return upload<Document>("/documents/upload", file);
}

export async function getDocument(id: string): Promise<DocumentDetail> {
  return request<DocumentDetail>(`/documents/${id}`);
}

export async function deleteDocument(id: string): Promise<void> {
  return request<void>(`/documents/${id}`, { method: "DELETE" });
}

export async function retryDocument(id: string): Promise<Document> {
  return request<Document>(`/documents/${id}/retry`, { method: "POST" });
}
```

#### 3. **Feature Folder Structure** (`/src/features/{feature}/`)

Each feature encapsulates related code:

```typescript
// /src/features/documents/types.ts
// Feature-local types only (e.g., UI state, filters)
export interface DocumentFilter {
  status?: DocumentStatus;
  sortBy?: "date" | "name";
}

// /src/features/documents/hooks/useDocuments.ts
import { useQuery } from "@tanstack/react-query";
import { listDocuments } from "@/api/documents";

export function useDocuments() {
  return useQuery({
    queryKey: ["documents"],
    queryFn: listDocuments,
  });
}

// /src/features/documents/components/DocumentList.tsx
import { useDocuments } from "../hooks/useDocuments";
import { DocumentListItem } from "./DocumentListItem";

export function DocumentList() {
  const { data = [] } = useDocuments();
  return (
    <div>
      {data.map(doc => <DocumentListItem key={doc.id} document={doc} />)}
    </div>
  );
}

// /src/features/documents/index.ts
// Public API: what other features/pages can import
export { DocumentList } from "./components/DocumentList";
export { useDocuments, useUploadDocument, useDeleteDocument } from "./hooks";
export type { DocumentFilter } from "./types";
```

#### 4. **Shared Component Organization** (`/src/components/`)

**Before:**
- `/components/ui/` — Shadcn primitives
- `/components/ConfirmDialog.tsx` — Shared complex component (orphaned)

**After:**
```
/components/
├── ui/                     # Shadcn + CVA primitives
│   ├── button.tsx
│   ├── input.tsx
│   ├── card.tsx
│   └── ...
└── shared/                 # Shared complex components (reused across features)
    ├── ConfirmDialog.tsx
    ├── ErrorBoundary.tsx
    ├── StatusBadge.tsx     # Moved from features/documents
    └── index.ts            # Re-exports
```

Rule: Component goes to `shared/` only if used by 2+ features. Otherwise stays in feature folder.

#### 5. **Import Paths** (Path alias clarity)

Keep `@/` alias; structure imports:

```typescript
// ✅ Good
import { useDocuments } from "@/features/documents/hooks";
import { DocumentList } from "@/features/documents";
import { Button } from "@/components/ui/button";
import { ConfirmDialog } from "@/components/shared/ConfirmDialog";
import type { Document } from "@/api/documents/types";

// ❌ Avoid
import useDocuments from "@/features/documents/hooks/useDocuments";
import { DocumentListItem } from "@/features/documents/components";
import anything from "@/api/documents/api";  // Use domain types, not API functions in other features
```

---

### Alternative Approaches Considered

| Approach | Pros | Cons | Decision |
|----------|------|------|----------|
| **Single types file** (current) | No duplication | Hard to find right type, scales poorly | ❌ Rejected |
| **Domain-driven DTOs** (proposed) | Clear ownership, scalable, matches BE structure | Slight type duplication across domains | ✅ Chosen |
| **One mega feature folder** | Simplicity | No organization for large codebases | ❌ Rejected |
| **Feature folders + co-locate types** (proposed) | Keeps feature code together, easy discoverability | Types live in api/ not feature/ (cleaner boundary) | ✅ Chosen |
| **Pinia for state** (vs React Query) | Can match user expectation | Already using React Query, no need to change | ❌ Rejected (user was mistaken about frontend being Vue) |

---

## Implementation Steps

1. **Create API domain structure** — mkdir for `/api/documents`, `/api/conversations`, `/api/chat`, `/api/health`

2. **Split types.ts into domain files** — Move DTOs from `/types/index.ts` to `/api/{domain}/types.ts`; create `/types/shared.ts` for ApiError; update `/types/index.ts` to re-export

3. **Reorganize API functions** — Move existing functions from `/api/{domain}.ts` to `/api/{domain}/api.ts`; add typed imports

4. **Update all API imports** — Grep for `import { listDocuments } from "@/api/documents"` → `import { listDocuments } from "@/api/documents/api"`

5. **Reorganize features** — Create `/features/documents/hooks/`, `/features/chat/hooks/`, etc.; move custom hooks into these folders

6. **Create feature index files** — Each `features/{feature}/index.ts` exports public hooks + main component

7. **Move shared components** — Move `components/ConfirmDialog.tsx` and `StatusBadge.tsx` to `components/shared/`; create `components/shared/index.ts`

8. **Update all imports** — Global search/replace for import paths (use IDE's rename refactor where possible)

9. **Create feature template** — Write `/features/_template/` as reference documentation

10. **Test app** — Run dev server, verify no console errors, check all pages load and features work

11. **Update documentation** — Add README to features/ with architecture overview and onboarding guide

---

## Risks & Mitigations

| Risk | Impact | Mitigation |
|------|--------|-----------|
| **Circular imports** when reorganizing | App won't build or tree-shake | Enforce rule: shared → features → pages. Use linter (import-linter already set up in clean arch). Add pre-commit check. |
| **Import path confusion** across team | Devs use wrong paths, defeats organization | Document path conventions clearly in README. Create template. Add ESLint rule (no absolute paths to internal modules). |
| **Type duplication** (same DTO across domains) | Maintenance burden if BE changes | Accept as intentional boundary. Types are cheap; shared boundary types are fragile. If dup becomes problematic later, codegen solves it. |
| **Stale types** (FE types diverge from BE) | Type safety false positive | Maintain manual sync discipline or set up codegen pipeline. Document DTO source in each file. |
| **Lost during refactor** (hooks forgotten, components orphaned) | Silent bugs in unused code | Lint rule: no unused exports. Run tests after each step. Type-check entire codebase (`tsc --noEmit`). |

---

## Test Strategy

- **Unit tests**: No new unit tests needed; existing tests stay (test hooks/components where they live)
- **Integration tests**: Verify each feature's hooks call correct API endpoints (already in MSW mocks)
- **Manual testing**: 
  - [ ] Upload document → verify parsing flow
  - [ ] Create conversation → verify chat streaming works
  - [ ] Delete document → verify cache invalidation
  - [ ] Navigate between features (sidebar + routing)
  - [ ] No console errors in dev tools
- **Type checking**: `tsc --noEmit` passes (strict mode)
- **Linting**: ESLint + import-linter pass (no circular deps)

---

## Success Checklist

At completion:
- [ ] All DTOs split by domain in `/api/{domain}/types.ts`
- [ ] All features have `/features/{feature}/hooks/`, `/components/` folders
- [ ] All features export public API via `/features/{feature}/index.ts`
- [ ] No `any` types in API functions (full TS chain: request → response)
- [ ] Shared components in `/components/shared/`; feature-specific in `/features/{feature}/components/`
- [ ] All imports use `@/` alias with correct path structure
- [ ] Zero linter/type errors: `eslint .` + `tsc --noEmit` + `import-linter` pass
- [ ] Dev server runs without errors: `npm run dev`
- [ ] All manual tests pass (upload, chat, delete flows)
- [ ] Feature template documented in `/features/_template/`

---

## Timeline & Estimates

- Step 1-3 (setup + types split): ~2-3 hours
- Step 4-6 (reorganize + imports): ~4-5 hours (bulk of refactor; most time is find/replace)
- Step 7-8 (shared components + final imports): ~1-2 hours
- Step 9-11 (template + docs + testing): ~1-2 hours
- **Total**: ~8-12 hours solo dev (spread over 2-3 days if doing incrementally)

Estimates assume no major complications; adjust if circular import issues or edge cases arise.

---

## Open Questions

- [ ] **DTO sync strategy**: Manual sync from BE or codegen later? (Can use OpenAPI → TS tools like `openapi-typescript` when BE has OpenAPI spec)
- [ ] **Feature-local types**: Do features need local types (e.g., UI state like `DocumentFilter`), or keep types purely at API layer? (Recommend keeping feature-local types minimal; use hooks for complex state)
- [ ] **Re-export strategy**: Should feature index re-export hooks + components, or only main component? (Recommend exporting hooks + main component so caller imports from one place: `import { DocumentList, useDocuments } from "@/features/documents"`)

---

## Notes for Implementation

- **Ref files for patterns**: Current code already follows most of these patterns; refactor is mainly about organization
- **Type safety wins**: Splitting types by domain makes it harder to accidentally mix documents/conversations DTOs
- **Onboarding**: New dev copy `/features/_template/` → rename → follow structure. Clear path to contribution.
- **Future proofing**: Structure supports codegen (OpenAPI → `/api/{domain}/types.ts`) when ready
