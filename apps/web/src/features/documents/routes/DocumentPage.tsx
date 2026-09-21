import { useParams } from "react-router";
import { format } from "date-fns";
import { Badge } from "@libs/components/ui/badge";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@libs/components/ui/card";
import { ConversationList, useDocument, useConversations } from "@/features/chat";
import { DocumentCover } from "../components/DocumentCover";
import { OverviewSections } from "../components/OverviewSections";

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

  const meta = [
    document.author,
    `${document.page_count ?? "—"} pages`,
    `${document.chunk_count} chunks`,
    `uploaded ${format(new Date(document.created_at), "PP")}`,
  ].filter(Boolean);

  return (
    <div className="max-w-2xl space-y-4">
      <Card>
        <CardContent className="flex gap-4 pt-6">
          <DocumentCover
            documentId={document.id}
            hasCover={document.has_cover}
            alt={`Cover of ${document.title}`}
            className="w-28"
          />
          <div className="min-w-0 flex-1 space-y-2">
            <h1 className="text-xl font-semibold leading-tight">{document.title}</h1>
            {(document.doc_type || document.language) && (
              <div className="flex flex-wrap gap-2">
                {document.doc_type && <Badge variant="secondary">{document.doc_type}</Badge>}
                {document.language && <Badge variant="outline">{document.language}</Badge>}
              </div>
            )}
            <p className="text-sm text-muted-foreground">{meta.join(" · ")}</p>
            {document.topics.length > 0 && (
              <div className="flex flex-wrap gap-1">
                {document.topics.map((topic) => (
                  <Badge key={topic} variant="outline">
                    {topic}
                  </Badge>
                ))}
              </div>
            )}
            {document.summary && <p className="text-sm">{document.summary}</p>}
          </div>
        </CardContent>
      </Card>

      <OverviewSections document={document} />

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
