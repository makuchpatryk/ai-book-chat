import { readResponse } from "@libs/api/client";
import { parseSse } from "@libs/api/sse";
import type { ChatEvent } from "./types";

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
    await readResponse(response); // throws ApiError
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
