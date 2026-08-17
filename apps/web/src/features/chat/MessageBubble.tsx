import { cn } from "@/lib/utils";
import { Card } from "@/components/ui/card";
import { MarkdownAnswer } from "@/features/chat/MarkdownAnswer";
import type { Message } from "@/types";

export function MessageBubble({ message }: { message: Message }) {
  const isUser = message.role === "user";

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
            </Card>
          </div>
        )}
      </div>
    </div>
  );
}
