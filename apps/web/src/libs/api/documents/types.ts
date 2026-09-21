export type DocumentStatus = "PENDING" | "PARSING" | "EMBEDDING" | "READY" | "FAILED";

export interface Section {
  id: string;
  title: string;
  order_index: number;
  start_page: number;
  end_page: number;
}

export type OverviewStatus = "pending" | "ready" | "failed";

export interface DescriptionSection {
  heading: string;
  body: string;
}

export interface Document {
  id: string;
  filename: string;
  title: string;
  status: DocumentStatus;
  page_count: number | null;
  error_message: string | null;
  created_at: string;
  author: string | null;
  summary: string | null;
  language: string | null;
  doc_type: string | null;
  topics: string[];
  overview_status: OverviewStatus | null;
  has_cover: boolean;
  /** Embedding progress; null until ingestion reaches EMBEDDING. */
  embedded_chunks: number | null;
  total_chunks: number | null;
}

export interface DocumentDetail extends Document {
  sections: Section[];
  description_sections: DescriptionSection[];
  chunk_count: number;
}
