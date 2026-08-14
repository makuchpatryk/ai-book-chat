import { useMemo } from "react";
import { cn } from "@/lib/utils";
import { Card } from "@/components/ui/card";
import { MarkdownAnswer } from "@/features/chat/MarkdownAnswer";
import { PageCitations } from "@/features/chat/PageCitations";
import type { Message } from "@/types";

export function MessageBubble({ message }: { message: Message }) {
  const isUser = message.role === "user";

  const pages = useMemo(() => {
    if (message.sources.length === 0) return [];
    return Array.from(
      new Set(
        message.sources.flatMap((s) => {
          const pageList = [];
          for (let i = s.page_start; i <= s.page_end; i++) {
            pageList.push(i);
          }
          return pageList;
        })
      )
    ).sort((a, b) => a - b);
  }, [message.sources]);

  return (
    <div className={cn("flex gap-3", isUser ? "justify-end" : "justify-start")}>
      <div className={cn("max-w-md", isUser ? "order-2" : "order-1")}>
        {isUser ? (
          <Card className="bg-primary text-primary-foreground p-3">
            <p className="text-sm whitespace-pre-wrap">{message.content}</p>
          </Card>
        ) : (
          <div className="space-y-2">
            <div className="text-sm text-muted-foreground">
              {message.grounded === false && <p>Not found in this document</p>}
              {message.truncated && <p>Stopped early</p>}
            </div>

            <Card className="bg-muted p-3">
              <MarkdownAnswer content={message.content} />
              <PageCitations sources={message.sources} pages={pages} />
            </Card>
          </div>
        )}
      </div>
    </div>
  );
}
