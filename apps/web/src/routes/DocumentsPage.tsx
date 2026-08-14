import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { DocumentList } from "@/features/documents/DocumentList";
import { UploadDropzone } from "@/features/documents/UploadDropzone";
import { useDocuments } from "@/features/documents/useDocuments";

export function DocumentsPage() {
  const { data: documents } = useDocuments();

  return (
    <div className="max-w-2xl space-y-4">
      <Card>
        <CardHeader>
          <CardTitle>Upload PDF</CardTitle>
          <CardDescription>Add a PDF to start asking questions</CardDescription>
        </CardHeader>
        <CardContent>
          <UploadDropzone />
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Documents</CardTitle>
          <CardDescription>Your uploaded PDFs</CardDescription>
        </CardHeader>
        <CardContent>
          <DocumentList documents={documents} />
        </CardContent>
      </Card>
    </div>
  );
}
