import { ApiError } from "@/api/client";
import { parseSse } from "@/api/sse";

export type ChatEvent =
  | { type: "sources"; results: Array<{
      chunk_id: string;
      page_start: number;
      page_end: number;
      score: number | null;
      section_title: string | null;
      snippet: string;
    }>; pages: number[] }
  | { type: "token"; text: string }
  | { type: "done"; messageId: string; grounded: boolean; truncated: boolean }
  | { type: "error"; detail: string };

export async function* streamMessage(
  conversationId: string,
  content: string,
  signal: AbortSignal
): AsyncGenerator<ChatEvent> {
  const response = await fetch(`/api/conversations/${conversationId}/messages`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ content }),
    signal,
  });

  if (!response.ok) {
    const text = await response.text();
    const body: unknown = text ? JSON.parse(text) : null;
    const detail =
      typeof body === "object" && body !== null && "detail" in body
        ? String((body as { detail: unknown }).detail)
        : response.statusText;
    throw new ApiError(response.status, `${response.status} ${detail}`, body);
  }

  if (!response.body) {
    throw new Error("No response body");
  }

  for await (const frame of parseSse(response.body)) {
    if (frame.event === "sources") {
      const { results, pages } = JSON.parse(frame.data);
      yield {
        type: "sources",
        results,
        pages,
      };
    } else if (frame.event === "token") {
      const { text } = JSON.parse(frame.data);
      yield { type: "token", text };
    } else if (frame.event === "done") {
      const { message_id, grounded, truncated } = JSON.parse(frame.data);
      yield {
        type: "done",
        messageId: message_id,
        grounded,
        truncated,
      };
    } else if (frame.event === "error") {
      const { detail } = JSON.parse(frame.data);
      yield { type: "error", detail };
    }
  }
}
