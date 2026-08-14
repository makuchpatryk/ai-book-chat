/**
 * App-local API types. Deliberately NOT shared with the backend package —
 * each app owns its own types (see specs/basic-structure.md).
 */

export type ComponentStatus = "ok" | "error";

export interface HealthResponse {
  status: ComponentStatus;
  database: ComponentStatus;
  redis: ComponentStatus;
}

export type DocumentStatus = "PENDING" | "PARSING" | "EMBEDDING" | "READY" | "FAILED";

export interface Section {
  id: string;
  title: string;
  order_index: number;
  start_page: number;
  end_page: number;
}

export interface Document {
  id: string;
  filename: string;
  title: string;
  status: DocumentStatus;
  page_count: number | null;
  error_message: string | null;
  created_at: string;
}

export interface DocumentDetail extends Document {
  sections: Section[];
  chunk_count: number;
}

export interface Conversation {
  id: string;
  title: string | null;
  created_at: string;
}

export interface Source {
  chunk_id: string;
  page_start: number;
  page_end: number;
  score: number | null;
  section_title: string | null;
  snippet: string;
}

export interface Message {
  id: string;
  role: string;
  content: string;
  grounded: boolean | null;
  truncated: boolean;
  sources: Source[];
}
