import { Card } from "@/components/ui/card";
import { MarkdownAnswer } from "@/features/chat/MarkdownAnswer";

function TypingDots() {
  return (
    <div className="flex items-center gap-1 py-1" role="status" aria-label="Assistant is thinking">
      <span className="size-2 rounded-full bg-muted-foreground/60 animate-bounce [animation-delay:-300ms]" />
      <span className="size-2 rounded-full bg-muted-foreground/60 animate-bounce [animation-delay:-150ms]" />
      <span className="size-2 rounded-full bg-muted-foreground/60 animate-bounce" />
    </div>
  );
}

export function StreamingMessage({ text }: { text: string }) {
  return (
    <div className="flex gap-3 justify-start">
      <div className="max-w-md">
        <Card className="bg-muted p-3">
          {text ? (
            <>
              <MarkdownAnswer content={text} />
              <div className="mt-2 text-xs text-muted-foreground">▌</div>
            </>
          ) : (
            <TypingDots />
          )}
        </Card>
      </div>
    </div>
  );
}
