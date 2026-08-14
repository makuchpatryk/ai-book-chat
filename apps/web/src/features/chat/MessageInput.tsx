import { useRef, useState } from "react";
import { Send, Square } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Alert, AlertDescription } from "@/components/ui/alert";

interface MessageInputProps {
  onSend: (content: string) => void;
  isStreaming: boolean;
  onStop: () => void;
  disabled?: boolean;
  disabledReason?: string;
}

const MAX_LENGTH = 4000;

export function MessageInput({
  onSend,
  isStreaming,
  onStop,
  disabled,
  disabledReason,
}: MessageInputProps) {
  const [content, setContent] = useState("");
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      if (content.trim() && !isStreaming && !disabled) {
        handleSend();
      }
    }
  };

  const handleSend = () => {
    if (content.trim()) {
      onSend(content);
      setContent("");
      textareaRef.current?.focus();
    }
  };

  return (
    <div className="border-t border-border p-4 space-y-3">
      {disabled && disabledReason && (
        <Alert variant="destructive">
          <AlertDescription className="text-xs">{disabledReason}</AlertDescription>
        </Alert>
      )}

      <div className="flex gap-2">
        <Textarea
          ref={textareaRef}
          placeholder="Ask a question..."
          value={content}
          onChange={(e) => setContent(e.target.value.slice(0, MAX_LENGTH))}
          onKeyDown={handleKeyDown}
          disabled={isStreaming || disabled}
          className="min-h-12 max-h-32 resize-none"
        />

        {isStreaming ? (
          <Button
            onClick={onStop}
            variant="destructive"
            size="icon"
            className="h-12 w-12 shrink-0"
          >
            <Square className="size-4" />
          </Button>
        ) : (
          <Button
            onClick={handleSend}
            disabled={!content.trim() || disabled}
            size="icon"
            className="h-12 w-12 shrink-0"
          >
            <Send className="size-4" />
          </Button>
        )}
      </div>

      {content.length > 0 && (
        <div className="text-xs text-muted-foreground text-right">
          {content.length} / {MAX_LENGTH}
        </div>
      )}
    </div>
  );
}
