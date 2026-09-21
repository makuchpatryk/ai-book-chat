import type { ReactNode } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, renderHook, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { streamMessage } from "@libs/api/chat/api";
import type { ChatEvent } from "@libs/api/chat/types";
import { useChatStream } from "./useChatStream";

vi.mock("@libs/api/chat/api", () => ({ streamMessage: vi.fn() }));

function wrapper({ children }: { children: ReactNode }) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>;
}

/** Yields one token, then waits until the request is aborted. */
async function* tokenThenHang(signal: AbortSignal): AsyncGenerator<ChatEvent> {
  yield { type: "token", text: "partial" };
  await new Promise((_, reject) =>
    signal.addEventListener("abort", () => reject(new DOMException("aborted", "AbortError")))
  );
}

describe("useChatStream", () => {
  it("aborts the stream and starts clean when the conversation changes", async () => {
    let signal: AbortSignal | undefined;
    vi.mocked(streamMessage).mockImplementation((_id, _content, s) => {
      signal = s;
      return tokenThenHang(s);
    });
    const { result, rerender } = renderHook(({ id }) => useChatStream(id), {
      wrapper,
      initialProps: { id: "conv-1" },
    });

    act(() => {
      void result.current.startStream("question");
    });
    await waitFor(() => expect(result.current.liveText).toBe("partial"));

    rerender({ id: "conv-2" });

    expect(signal?.aborted).toBe(true);
    await waitFor(() => expect(result.current.isStreaming).toBe(false));
    expect(result.current.liveText).toBe("");
    expect(result.current.pendingUserText).toBeNull();
  });

  it("unlocks the input when the stream ends without done or error", async () => {
    vi.mocked(streamMessage).mockImplementation(async function* () {
      yield { type: "token", text: "cut off" } as ChatEvent;
    });
    const { result } = renderHook(() => useChatStream("conv-1"), { wrapper });

    await act(() => result.current.startStream("question"));

    expect(result.current.isStreaming).toBe(false);
    expect(result.current.error).toBe("Stream ended unexpectedly");
  });
});
