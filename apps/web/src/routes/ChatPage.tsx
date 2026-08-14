import { useParams } from "react-router";
import { Card } from "@/components/ui/card";
import { MessageList } from "@/features/chat/MessageList";
import { MessageInput } from "@/features/chat/MessageInput";
import { useMessages } from "@/features/chat/useMessages";
import { useChatStream } from "@/features/chat/useChatStream";
import { useDocument } from "@/features/chat/useDocument";

export function ChatPage() {
  const { conversationId, documentId } = useParams<{
    conversationId: string;
    documentId: string;
  }>();

  const { data: messages, isLoading } = useMessages(conversationId || "");
  const { data: document } = useDocument(documentId || "");
  const { liveText, liveSources, isStreaming, error, startStream, abort } = useChatStream(
    conversationId || ""
  );

  if (!conversationId || !documentId) {
    return (
      <Card className="max-w-md p-6">
        <p className="text-sm text-destructive">Invalid conversation or document</p>
      </Card>
    );
  }

  const isDocumentReady = document?.status === "READY";
  const disabledReason: string | undefined = !isDocumentReady
    ? document
      ? `Document is ${document.status.toLowerCase()}. Cannot chat yet.`
      : "Loading document..."
    : undefined;

  return (
    <Card className="h-full flex flex-col overflow-hidden">
      {isLoading ? (
        <div className="flex items-center justify-center h-full">
          <p className="text-sm text-muted-foreground">Loading conversation...</p>
        </div>
      ) : (
        <>
          <MessageList
            messages={messages || []}
            streaming={isStreaming}
            liveText={liveText}
            liveSources={liveSources}
          />
          {error && (
            <div className="px-4 py-2 bg-destructive/10 text-destructive text-sm border-t border-border">
              {error}
            </div>
          )}
          <MessageInput
            onSend={startStream}
            isStreaming={isStreaming}
            onStop={abort}
            disabled={!isDocumentReady}
            disabledReason={disabledReason}
          />
        </>
      )}
    </Card>
  );
}
