import { DocumentListItem } from "@/features/documents/DocumentListItem";
import type { Document } from "@/types";

export function DocumentList({ documents }: { documents: Document[] | undefined }) {
  if (!documents || documents.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center py-8 text-center">
        <p className="text-sm text-muted-foreground">No documents yet. Upload one to get started.</p>
      </div>
    );
  }

  return (
    <div className="space-y-1">
      {documents.map((doc) => (
        <DocumentListItem key={doc.id} document={doc} />
      ))}
    </div>
  );
}
