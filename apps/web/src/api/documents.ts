import { request, upload } from "@/api/client";
import type { Document, DocumentDetail } from "@/types";

export async function listDocuments(): Promise<Document[]> {
  return request<Document[]>("/documents");
}

export async function getDocument(id: string): Promise<DocumentDetail> {
  return request<DocumentDetail>(`/documents/${id}`);
}

export async function uploadDocument(file: File): Promise<Document> {
  const formData = new FormData();
  formData.append("file", file);
  return upload<Document>("/documents", formData);
}

export async function deleteDocument(id: string): Promise<void> {
  return request<void>(`/documents/${id}`, { method: "DELETE" });
}

export async function retryDocument(id: string): Promise<Document> {
  return request<Document>(`/documents/${id}/retry`, { method: "POST" });
}
