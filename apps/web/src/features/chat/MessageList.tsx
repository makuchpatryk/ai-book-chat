import { useRef, useEffect } from "react";
import { MessageBubble } from "@/features/chat/MessageBubble";
import { StreamingMessage } from "@/features/chat/StreamingMessage";
import type { Message } from "@/types";

interface MessageListProps {
  messages: Message[];
  streaming: boolean;
  liveText: string;
}

export function MessageList({
  messages,
  streaming,
  liveText,
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
  }, [messages, liveText]);

  return (
    <div
      ref={containerRef}
      className="flex-1 overflow-y-auto p-4 space-y-4"
    >
      {messages.length === 0 && !streaming ? (
        <div className="flex items-center justify-center h-full">
          <p className="text-muted-foreground text-sm">Start a conversation</p>
        </div>
      ) : (
        <>
          {messages.map((msg) => (
            <MessageBubble key={msg.id} message={msg} />
          ))}
          {streaming && (
            <StreamingMessage text={liveText} />
          )}
          <div ref={endRef} />
        </>
      )}
    </div>
  );
}
