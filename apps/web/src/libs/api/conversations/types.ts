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
