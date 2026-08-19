/**
 * App-local API types. Deliberately NOT shared with the backend package —
 * each app owns its own types (see specs/basic-structure.md).
 *
 * Exported from domain-specific locations for organization; re-exported here for convenience.
 */

export type { ComponentStatus } from "./shared";
export type { DocumentStatus, Section, Document, DocumentDetail } from "@/api/documents/types";
export type { Conversation, Message, Source } from "@/api/conversations/types";
export type { ChatEvent } from "@/api/chat/types";
export type { HealthResponse } from "@/api/health/types";
