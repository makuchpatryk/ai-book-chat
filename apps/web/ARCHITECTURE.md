# Frontend Architecture

## Overview

Feature-based architecture with domain-driven DTOs and clean separation of concerns.

## Directory Structure

```
src/
├── api/                    # API layer (domain-organized)
│   ├── client.ts          # HTTP client wrapper
│   ├── sse.ts             # Server-sent events parser
│   ├── documents/         # Document domain
│   │   ├── types.ts       # DTOs
│   │   └── api.ts         # Endpoints
│   ├── conversations/     # Conversation domain
│   │   ├── types.ts
│   │   └── api.ts
│   ├── chat/              # Chat streaming
│   │   ├── types.ts
│   │   └── api.ts
│   └── health/            # Health checks
│       ├── types.ts
│       └── api.ts
├── types/
│   ├── shared.ts          # Shared types (ComponentStatus)
│   └── index.ts           # Re-exports for convenience
├── components/
│   ├── ui/                # Shadcn primitives (button, card, input, etc.)
│   └── shared/            # Multi-use components (ConfirmDialog, ErrorBoundary)
├── features/              # Feature-specific code
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
│   │   └── index.ts
│   ├── health/            # Status page
│   └── _template/         # Template for new features
├── routes/                # Page components (route-level)
│   ├── DocumentsPage.tsx
│   ├── DocumentPage.tsx
│   ├── ChatPage.tsx
│   └── HealthPage.tsx
├── layouts/
│   └── AppLayout.tsx      # Sidebar + outlet
├── lib/
│   └── utils.ts           # Helpers (cn function)
└── test/
    ├── setup.ts           # Vitest + MSW setup
    └── handlers.ts        # Mock API handlers
```

## Import Patterns

### API Types & Functions

```typescript
// ✅ Good: import from domain
import type { Document } from "@/api/documents/types";
import { listDocuments, uploadDocument } from "@/api/documents/api";

// ❌ Avoid: importing from wrong domain
import type { Document } from "@/types";  // Not for API types
```

### Features

```typescript
// ✅ Good: import public API from feature index
import { DocumentList, useDocuments } from "@/features/documents";
import { useChatStream } from "@/features/chat";

// ❌ Avoid: importing internal hooks/components
import { DocumentListItem } from "@/features/documents/components";
```

### Shared Components

```typescript
// ✅ Good: import from shared
import { ConfirmDialog, ErrorBoundary } from "@/components/shared";

// ✅ Good: import UI primitives
import { Button } from "@/components/ui/button";

// ❌ Avoid: importing from features
import { StatusBadge } from "@/features/documents";  // Now shared
```

## Creating a New Feature

1. Copy `/features/_template/` → `/features/my-feature/`
2. Replace `Template` with your feature name
3. Create domain if needed: `/api/my-domain/types.ts` + `/api/my-domain/api.ts`
4. Implement hooks in `/features/my-feature/hooks/`
5. Implement components in `/features/my-feature/components/`
6. Export public API in `/features/my-feature/index.ts`
7. Use in routes via feature index: `import { MyView } from "@/features/my-feature"`

## State Management

**React Query (TanStack Query v5)** for server state:
- Query hooks for read operations (`useDocuments`, `useMessages`)
- Mutation hooks for write operations (`useUploadDocument`, `useDeleteConversation`)
- Cache invalidation on mutations

**No global client state management** — use React hooks + prop drilling for local UI state.

## Type Safety

All API functions fully typed:

```typescript
// api/documents/api.ts
import type { Document, DocumentDetail } from "./types";

export async function listDocuments(): Promise<Document[]> {
  return request<Document[]>("/documents");
}
```

Request → response chain is unbroken. No `any` types in API layer.

## Testing

- **Unit tests**: Test hooks + components individually (next to implementation)
- **Integration tests**: Test hooks with mock MSW handlers (`test/handlers.ts`)
- **Type checking**: `tsc --noEmit` (run before commit)
- **Linting**: `eslint .` (includes import-linter for circular dependencies)

## DTOs & Sync Strategy

**Current**: Manual sync between backend and frontend DTOs.

Each API domain has a `types.ts` file with TypeScript interfaces matching the backend API responses.

**Future**: Automate with OpenAPI schema generation when backend has `@fastapi/openapi-generator` or similar.

See `specs/frontend-refactor-feature-architecture.md` for full architecture plan.
