import { Card } from "@libs/components/ui/card";
import { MarkdownAnswer } from "./MarkdownAnswer";
import { FollowUps } from "./FollowUps";
import { parseAnswer } from "../utils/parseAnswer";
import type { Message } from "@libs/types";

interface MessageBubbleProps {
  message: Message;
  /** Set on the latest answer only, to offer its follow-up questions. */
  onFollowUp?: (question: string) => void;
}

export function MessageBubble({ message, onFollowUp }: MessageBubbleProps) {
  const isUser = message.role === "user";

  if (isUser) {
    return (
      <div className="flex justify-end">
        <Card className="max-w-[80%] bg-primary text-primary-foreground p-3">
          <p className="text-sm whitespace-pre-wrap">{message.content}</p>
        </Card>
      </div>
    );
  }

  const { body, followUps } = parseAnswer(message.content);

  return (
    <div className="flex justify-start">
      <div className="w-full max-w-3xl space-y-2">
        <div className="text-sm text-muted-foreground">
          {message.grounded === false && (
            <p>Not in this document — answered from general knowledge</p>
          )}
          {message.truncated && <p>Stopped early</p>}
        </div>

        <Card className="bg-muted px-4 py-3">
          <MarkdownAnswer content={body} />
        </Card>

        {onFollowUp && <FollowUps questions={followUps} onAsk={onFollowUp} />}
      </div>
    </div>
  );
}
