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
  /** Whether the view was pinned to the bottom before the latest render. */
  const anchoredRef = useRef(true);
  /** Set while we scroll ourselves, so the resulting events don't unpin. */
  const selfScrollRef = useRef(false);
  const selfScrollTimer = useRef<number | null>(null);

  const scrollToBottom = (behavior: ScrollBehavior) => {
    anchoredRef.current = true;
    selfScrollRef.current = true;
    if (selfScrollTimer.current !== null) {
      window.clearTimeout(selfScrollTimer.current);
    }
    // Smooth scrolling emits intermediate events; release the guard once it settles.
    selfScrollTimer.current = window.setTimeout(() => {
      selfScrollRef.current = false;
      selfScrollTimer.current = null;
    }, behavior === "smooth" ? 700 : 100);
    endRef.current?.scrollIntoView({ behavior });
  };

  const handleScroll = () => {
    if (selfScrollRef.current || !containerRef.current) return;
    const { scrollHeight, scrollTop, clientHeight } = containerRef.current;
    anchoredRef.current = scrollHeight - scrollTop - clientHeight < 80;
  };

  useEffect(
    () => () => {
      if (selfScrollTimer.current !== null) {
        window.clearTimeout(selfScrollTimer.current);
      }
    },
    [],
  );

  // Sending a message always jumps to the bottom, even if scrolled away.
  useEffect(() => {
    if (pendingUserText) {
      scrollToBottom("smooth");
    }
  }, [pendingUserText]);

  // Incoming content only follows along when already pinned to the bottom.
  useEffect(() => {
    if (anchoredRef.current) {
      scrollToBottom("smooth");
    }
  }, [messages, liveText]);

  // The refetched list lands one render before the optimistic copy is cleared;
  // skip the placeholder once the server echoes the same message back.
  const last = messages[messages.length - 1];
  const showPending =
    !!pendingUserText &&
    !(last?.role === "user" && last.content === pendingUserText);

  return (
    <div
      ref={containerRef}
      onScroll={handleScroll}
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
