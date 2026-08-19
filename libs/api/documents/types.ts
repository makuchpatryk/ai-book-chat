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
