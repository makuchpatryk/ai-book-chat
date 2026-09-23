import { API_BASE, request, upload } from "@libs/api/client";
import type { Document, DocumentDetail, Quiz } from "./types";

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

export async function regenerateOverview(id: string): Promise<Document> {
  return request<Document>(`/documents/${id}/overview/regenerate`, { method: "POST" });
}

export function documentCoverUrl(id: string): string {
  return `${API_BASE}/documents/${id}/cover`;
}

export async function prepareQuiz(id: string): Promise<Quiz> {
  return request<Quiz>(`/documents/${id}/quiz`, { method: "POST" });
}

export async function regenerateQuiz(id: string): Promise<Quiz> {
  return request<Quiz>(`/documents/${id}/quiz/regenerate`, { method: "POST" });
}

export async function getQuiz(id: string): Promise<Quiz> {
  return request<Quiz>(`/documents/${id}/quiz`);
}
