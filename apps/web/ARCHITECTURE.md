# Frontend Architecture

## Overview

Feature-based architecture with domain-driven DTOs and clean separation of concerns.

## Directory Structure

```
src/
├── features/              # Feature-specific code (domain-focused)
│   ├── documents/         # Document upload & management
│   │   ├── types.ts       # Feature-local types
│   │   ├── hooks/
│   │   │   ├── useDocuments.ts
│   │   │   ├── useUploadDocument.ts
│   │   │   ├── useDeleteDocument.ts
│   │   │   └── useRetryDocument.ts
│   │   ├── components/
│   │   │   ├── DocumentList.tsx
│   │   │   ├── DocumentListItem.tsx
│   │   │   └── UploadDropzone.tsx
│   │   ├── routes/
│   │   │   ├── DocumentsPage.tsx
│   │   │   └── DocumentPage.tsx
│   │   └── index.ts       # Public API
│   ├── chat/              # Chat interface
│   │   ├── types.ts
│   │   ├── hooks/
│   │   │   ├── useChatStream.ts
│   │   │   ├── useConversations.ts
│   │   │   ├── useCreateConversation.ts
│   │   │   ├── useDeleteConversation.ts
│   │   │   ├── useMessages.ts
│   │   │   └── useDocument.ts
│   │   ├── components/
│   │   │   ├── ConversationList.tsx
│   │   │   ├── MessageList.tsx
│   │   │   ├── MessageInput.tsx
│   │   │   ├── MessageBubble.tsx
│   │   │   ├── StreamingMessage.tsx
│   │   │   └── MarkdownAnswer.tsx
│   │   ├── routes/
│   │   │   └── ChatPage.tsx
│   │   └── index.ts
│   └── health/            # Status page
│       ├── routes/
│       │   └── HealthPage.tsx
│       └── index.ts
├── layouts/
│   └── AppLayout.tsx      # Sidebar + outlet
├── libs/                  # Shared code (cross-feature)
│   ├── api/               # API layer (domain-organized)
│   │   ├── client.ts      # HTTP client wrapper
│   │   ├── sse.ts         # Server-sent events parser
│   │   ├── documents/     # Document domain
│   │   │   ├── types.ts   # DTOs
│   │   │   └── api.ts     # Endpoints
│   │   ├── conversations/
│   │   │   ├── types.ts
│   │   │   └── api.ts
│   │   ├── chat/
│   │   │   ├── types.ts
│   │   │   └── api.ts
│   │   └── health/
│   │       ├── types.ts
│   │       └── api.ts
│   ├── components/
│   │   ├── ui/            # Shadcn primitives (button, card, input, etc.)
│   │   └── shared/        # Multi-use components (ConfirmDialog, ErrorBoundary)
│   ├── types/
│   │   ├── shared.ts      # Shared types (ComponentStatus)
│   │   └── index.ts       # Re-exports for convenience
│   └── utils/
│       └── utils.ts       # Helpers (cn function)
├── test/
│   ├── setup.ts           # Vitest + MSW setup
│   └── handlers.ts        # Mock API handlers
├── main.tsx
├── router.tsx
└── index.css
```

## Import Patterns

### API Types & Functions

```typescript
// ✅ Good: import from domain in libs
import type { Document } from "@libs/api/documents/types";
import { listDocuments, uploadDocument } from "@libs/api/documents/api";

// ❌ Avoid: importing from wrong domain
import type { Document } from "@libs/types";  // API types stay in @libs/api
```

### Features

```typescript
// ✅ Good: import public API from feature index
import { DocumentList, useDocuments } from "@/features/documents";
import { useChatStream } from "@/features/chat";

// ❌ Avoid: importing internal hooks/components
import { DocumentListItem } from "@/features/documents/components";
```

### Shared Libraries

```typescript
// ✅ Good: import from libs (shared code)
import { ConfirmDialog, ErrorBoundary } from "@libs/components/shared";
import { Button } from "@libs/components/ui/button";
import { cn } from "@libs/utils/utils";
import type { ComponentStatus } from "@libs/types";

// ❌ Avoid: importing internal lib files
import { MessageInput } from "@/features/chat";  // Not a shared component
```

## Creating a New Feature

1. Create feature folder: `src/features/my-feature/`
2. Add directories: `hooks/`, `components/`, `routes/`
3. Create domain if needed: `src/libs/api/my-domain/types.ts` + `api.ts`
4. Implement hooks in `src/features/my-feature/hooks/`
5. Implement components in `src/features/my-feature/components/`
6. Implement routes in `src/features/my-feature/routes/`
7. Create `src/features/my-feature/types.ts` for feature-local types (if needed)
8. Export public API in `src/features/my-feature/index.ts`
9. Register routes in `src/router.tsx`

Routes belong to features, not top-level `routes/` folder. This keeps all feature code together.

## State Management

**React Query (TanStack Query v5)** for server state:
- Query hooks for read operations (`useDocuments`, `useMessages`)
- Mutation hooks for write operations (`useUploadDocument`, `useDeleteConversation`)
- Cache invalidation on mutations

**No global client state management** — use React hooks + prop drilling for local UI state.

## Type Safety

All API functions fully typed:

```typescript
// libs/api/documents/api.ts
import type { Document, DocumentDetail } from "./types";

export async function listDocuments(): Promise<Document[]> {
  return request<Document[]>("/documents");
}
```

Request → response chain is unbroken. No `any` types in API layer.

Import types from their domain:
```typescript
// ✅ Good: import from the domain's types
import type { Document } from "@libs/api/documents/types";
```

## Testing

- **Unit tests**: Test hooks + components individually (next to implementation)
- **Integration tests**: Test hooks with mock MSW handlers (`test/handlers.ts`)
- **Type checking**: `tsc --noEmit` (run before commit)
- **Linting**: `eslint .` (includes import-linter for circular dependencies)

## DTOs & Sync Strategy

**Current**: Manual sync between backend and frontend DTOs.

Each API domain has a `types.ts` file in `libs/api/{domain}/` with TypeScript interfaces matching the backend API responses.

**Future**: Automate with OpenAPI schema generation when backend has `@fastapi/openapi-generator` or similar.

## Architecture Principles

1. **Features own domain logic**: Hooks, components, local state, routes all live in feature folder
2. **Libs are shared**: API layer, UI components, utilities, types shared across features
3. **Routes in features**: Each feature owns its route pages, router imports from features
4. **No circular imports**: Import-linter enforces: shared ← features ← routes
5. **Type safety**: All API boundaries fully typed, no `any` in API layer

See `specs/frontend-refactor-feature-architecture.md` for full architecture plan.
