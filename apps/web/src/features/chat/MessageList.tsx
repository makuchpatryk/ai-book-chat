import { useRef, useEffect } from "react";
import { MessageBubble } from "@/features/chat/MessageBubble";
import { StreamingMessage } from "@/features/chat/StreamingMessage";
import type { Message } from "@/types";

interface MessageListProps {
  messages: Message[];
  streaming: boolean;
  liveText: string;
  /** Optimistic user message, shown until the persisted copy is refetched. */
  pendingUserText?: string | null;
}

export function MessageList({
  messages,
  streaming,
  liveText,
  pendingUserText,
}: MessageListProps) {
  const endRef = useRef<HTMLDivElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (containerRef.current) {
      const { scrollHeight, scrollTop, clientHeight } = containerRef.current;
      const isNearBottom = scrollHeight - scrollTop - clientHeight < 80;

      if (isNearBottom) {
        endRef.current?.scrollIntoView({ behavior: "smooth" });
      }
    }
  }, [messages, liveText, pendingUserText]);

  // The refetched list lands one render before the optimistic copy is cleared;
  // skip the placeholder once the server echoes the same message back.
  const last = messages[messages.length - 1];
  const showPending =
    !!pendingUserText &&
    !(last?.role === "user" && last.content === pendingUserText);

  return (
    <div
      ref={containerRef}
      className="flex-1 overflow-y-auto p-4 space-y-4"
    >
      {messages.length === 0 && !streaming && !showPending ? (
        <div className="flex items-center justify-center h-full">
          <p className="text-muted-foreground text-sm">Start a conversation</p>
        </div>
      ) : (
        <>
          {messages.map((msg) => (
            <MessageBubble key={msg.id} message={msg} />
          ))}
          {showPending && (
            <MessageBubble
              message={{
                id: "pending-user",
                role: "user",
                content: pendingUserText,
                grounded: null,
                truncated: false,
                sources: [],
              }}
            />
          )}
          {streaming && (
            <StreamingMessage text={liveText} />
          )}
          <div ref={endRef} />
        </>
      )}
    </div>
  );
}
