import { Card } from "@/components/ui/card";
import { MarkdownAnswer } from "@/features/chat/MarkdownAnswer";

export function StreamingMessage({ text }: { text: string }) {
  return (
    <div className="flex gap-3 justify-start">
      <div className="max-w-md">
        <Card className="bg-muted p-3">
          {text && <MarkdownAnswer content={text} />}
          <div className="mt-2 text-xs text-muted-foreground">▌</div>
        </Card>
      </div>
    </div>
  );
}
