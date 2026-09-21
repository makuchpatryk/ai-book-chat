import { Card } from "@libs/components/ui/card";
import { MarkdownAnswer } from "./MarkdownAnswer";
import { parseAnswer } from "../utils/parseAnswer";

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
  // Follow-up questions appear on the saved message, once streaming ends.
  const { body } = parseAnswer(text);

  return (
    <div className="flex justify-start">
      <div className="w-full max-w-3xl">
        <Card className="bg-muted px-4 py-3">
          {body ? (
            <>
              <MarkdownAnswer content={body} />
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
