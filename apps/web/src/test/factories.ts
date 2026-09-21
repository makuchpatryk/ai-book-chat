import type { Document, DocumentDetail } from "@libs/types";

export function makeDocument(overrides: Partial<Document> = {}): Document {
  return {
    id: "doc-1",
    filename: "book.pdf",
    title: "A Book",
    status: "READY",
    page_count: 12,
    error_message: null,
    created_at: "2026-09-01T10:00:00Z",
    author: null,
    summary: null,
    language: null,
    doc_type: null,
    topics: [],
    overview_status: null,
    has_cover: false,
    embedded_chunks: null,
    total_chunks: null,
    ...overrides,
  };
}

export function makeDetail(overrides: Partial<DocumentDetail> = {}): DocumentDetail {
  return {
    ...makeDocument(),
    sections: [],
    description_sections: [],
    chunk_count: 30,
    ...overrides,
  };
}
