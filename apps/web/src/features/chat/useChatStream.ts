import { useRef, useState, useCallback, useEffect } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { streamMessage } from "@/api/chat";

interface ChatStreamState {
  status: "idle" | "streaming" | "error";
  liveText: string;
  error: string | null;
}

export function useChatStream(conversationId: string) {
  const [state, setState] = useState<ChatStreamState>({
    status: "idle",
    liveText: "",
    error: null,
  });

  const abortControllerRef = useRef<AbortController | null>(null);
  const textBufferRef = useRef<string>("");
  const timerRef = useRef<NodeJS.Timeout | null>(null);
  const queryClient = useQueryClient();

  const flushBuffer = useCallback(() => {
    if (textBufferRef.current) {
      setState((prev) => ({
        ...prev,
        liveText: prev.liveText + textBufferRef.current,
      }));
      textBufferRef.current = "";
    }
  }, []);

  const startStream = useCallback(
    async (content: string) => {
      if (state.status === "streaming") return;

      setState({ status: "streaming", liveText: "", error: null });
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
            queryClient.invalidateQueries({ queryKey: ["messages", conversationId] });
          } else if (event.type === "error") {
            if (timerRef.current) clearTimeout(timerRef.current);
            flushBuffer();

            setState((prev) => ({
              ...prev,
              status: "error",
              error: event.detail,
            }));
            queryClient.invalidateQueries({ queryKey: ["messages", conversationId] });
          }
        }
      } catch (err) {
        if ((err as Error).name !== "AbortError") {
          if (timerRef.current) clearTimeout(timerRef.current);
          flushBuffer();

          setState((prev) => ({
            ...prev,
            status: "error",
            error: (err as Error).message || "Stream error",
          }));
          queryClient.invalidateQueries({ queryKey: ["messages", conversationId] });
        } else {
          if (timerRef.current) clearTimeout(timerRef.current);
          flushBuffer();
        }
      }
    },
    [conversationId, state.status, queryClient, flushBuffer]
  );

  const abort = useCallback(() => {
    if (abortControllerRef.current && state.status === "streaming") {
      abortControllerRef.current.abort();
      if (timerRef.current) clearTimeout(timerRef.current);
      flushBuffer();
      setState((prev) => ({ ...prev, status: "idle" }));
      queryClient.invalidateQueries({ queryKey: ["messages", conversationId] });
    }
  }, [state.status, queryClient, conversationId, flushBuffer]);

  useEffect(() => {
    return () => {
      if (timerRef.current) clearTimeout(timerRef.current);
    };
  }, []);

  return {
    ...state,
    startStream,
    abort,
    isStreaming: state.status === "streaming",
  };
}
