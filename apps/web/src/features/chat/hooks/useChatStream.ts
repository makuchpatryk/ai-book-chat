import { useRef, useState, useCallback, useEffect } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { streamMessage } from "@libs/api/chat/api";
import type { ChatStreamState } from "../types";

export function useChatStream(conversationId: string) {
  const [state, setState] = useState<ChatStreamState>({
    status: "idle",
    liveText: "",
    error: null,
    pendingUserText: null,
  });

  const abortControllerRef = useRef<AbortController | null>(null);
  const textBufferRef = useRef<string>("");
  const timerRef = useRef<NodeJS.Timeout | null>(null);
  const queryClient = useQueryClient();

  const flushBuffer = useCallback(() => {
    // Capture before clearing: React may run the updater later, after the reset.
    const buffered = textBufferRef.current;
    if (buffered) {
      textBufferRef.current = "";
      setState((prev) => ({
        ...prev,
        liveText: prev.liveText + buffered,
      }));
    }
  }, []);

  /**
   * Refetch persisted messages, then drop the optimistic user bubble only once
   * the server copy has arrived — otherwise it flickers out and back in.
   */
  const syncMessages = useCallback(async () => {
    await queryClient.invalidateQueries({
      queryKey: ["messages", conversationId],
    });
    setState((prev) => ({ ...prev, pendingUserText: null }));
  }, [queryClient, conversationId]);

  const startStream = useCallback(
    async (content: string) => {
      if (state.status === "streaming") return;

      setState({
        status: "streaming",
        liveText: "",
        error: null,
        pendingUserText: content,
      });
      abortControllerRef.current = new AbortController();
      textBufferRef.current = "";

      try {
        for await (const event of streamMessage(conversationId, content, abortControllerRef.current.signal)) {
          if (event.type === "token") {
            textBufferRef.current += event.text;

            if (timerRef.current) clearTimeout(timerRef.current);
            timerRef.current = setTimeout(flushBuffer, 60);
          } else if (event.type === "done") {
            if (timerRef.current) clearTimeout(timerRef.current);
            flushBuffer();

            setState((prev) => ({ ...prev, status: "idle" }));
            syncMessages();
          } else if (event.type === "error") {
            if (timerRef.current) clearTimeout(timerRef.current);
            flushBuffer();

            setState((prev) => ({
              ...prev,
              status: "error",
              error: event.detail,
            }));
            syncMessages();
          }
        }

        // Stream closed without a done/error frame — don't leave the input locked.
        setState((prev) =>
          prev.status === "streaming"
            ? { ...prev, status: "error", error: "Stream ended unexpectedly" }
            : prev
        );
      } catch (err) {
        if ((err as Error).name !== "AbortError") {
          if (timerRef.current) clearTimeout(timerRef.current);
          flushBuffer();

          setState((prev) => ({
            ...prev,
            status: "error",
            error: (err as Error).message || "Stream error",
          }));
          syncMessages();
        } else {
          if (timerRef.current) clearTimeout(timerRef.current);
          flushBuffer();
        }
      }
    },
    [conversationId, state.status, flushBuffer, syncMessages]
  );

  const abort = useCallback(() => {
    if (abortControllerRef.current && state.status === "streaming") {
      abortControllerRef.current.abort();
      if (timerRef.current) clearTimeout(timerRef.current);
      flushBuffer();
      setState((prev) => ({ ...prev, status: "idle" }));
      syncMessages();
    }
  }, [state.status, flushBuffer, syncMessages]);

  // The route reuses this component across conversations: start each one clean,
  // and stop the previous stream on switch or unmount so it can't write into it.
  useEffect(() => {
    setState({ status: "idle", liveText: "", error: null, pendingUserText: null });
    return () => {
      textBufferRef.current = "";
      abortControllerRef.current?.abort();
      if (timerRef.current) clearTimeout(timerRef.current);
    };
  }, [conversationId]);

  return {
    ...state,
    startStream,
    abort,
    isStreaming: state.status === "streaming",
  };
}
