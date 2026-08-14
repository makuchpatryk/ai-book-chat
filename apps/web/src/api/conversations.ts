import { request } from "@/api/client";
import type { Conversation, Message } from "@/types";

export async function listConversations(documentId: string): Promise<Conversation[]> {
  return request<Conversation[]>(`/documents/${documentId}/conversations`);
}

export async function createConversation(documentId: string): Promise<Conversation> {
  return request<Conversation>(`/documents/${documentId}/conversations`, {
    method: "POST",
  });
}

export async function getMessages(conversationId: string): Promise<Message[]> {
  return request<Message[]>(`/conversations/${conversationId}/messages`);
}
