import { useParams } from "react-router";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { ConversationList } from "@/features/chat/ConversationList";
import { useDocument } from "@/features/chat/useDocument";
import { useConversations } from "@/features/chat/useConversations";

export function DocumentPage() {
  const { documentId } = useParams<{ documentId: string }>();
  const { data: document } = useDocument(documentId || "");
  const { data: conversations } = useConversations(documentId || "");

  if (!documentId || !document) {
    return (
      <Card className="max-w-md">
        <CardHeader>
          <CardTitle>Document not found</CardTitle>
        </CardHeader>
      </Card>
    );
  }

  return (
    <div className="max-w-2xl space-y-4">
      <Card>
        <CardHeader>
          <CardTitle>{document.title}</CardTitle>
          <CardDescription>
            {document.page_count ?? "—"} pages • {document.chunk_count} chunks
          </CardDescription>
        </CardHeader>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Conversations</CardTitle>
          <CardDescription>Chat with this document</CardDescription>
        </CardHeader>
        <CardContent>
          <ConversationList documentId={documentId} conversations={conversations} />
        </CardContent>
      </Card>
    </div>
  );
}
