import { CornerDownRight } from "lucide-react";

interface FollowUpsProps {
  questions: string[];
  onAsk: (question: string) => void;
}

export function FollowUps({ questions, onAsk }: FollowUpsProps) {
  if (questions.length === 0) return null;

  return (
    <div className="space-y-1.5">
      <p className="text-xs font-medium text-muted-foreground">Ask next</p>
      <div className="flex flex-col items-start gap-1.5">
        {questions.map((question) => (
          <button
            key={question}
            type="button"
            onClick={() => onAsk(question)}
            className="flex items-start gap-2 rounded-lg border border-border bg-background px-3 py-1.5 text-left text-sm transition-colors hover:border-primary/50 hover:bg-primary/5"
          >
            <CornerDownRight className="mt-0.5 size-3.5 shrink-0 text-muted-foreground" />
            {question}
          </button>
        ))}
      </div>
    </div>
  );
}
