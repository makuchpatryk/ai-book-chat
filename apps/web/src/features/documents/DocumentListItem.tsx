import { formatDistanceToNow } from "date-fns";
import { NavLink, useNavigate } from "react-router";
import { Trash2, RotateCcw } from "lucide-react";
import { useState } from "react";
import { cn } from "@/lib/utils";
import { StatusBadge } from "@/features/documents/StatusBadge";
import { ConfirmDialog } from "@/components/ConfirmDialog";
import { useDeleteDocument } from "@/features/documents/useDeleteDocument";
import { useRetryDocument } from "@/features/documents/useRetryDocument";
import { Button } from "@/components/ui/button";
import { toast } from "sonner";
import type { Document } from "@/types";

export function DocumentListItem({ document }: { document: Document }) {
  const navigate = useNavigate();
  const uploadedAgo = formatDistanceToNow(new Date(document.created_at), { addSuffix: true });
  const [showDeleteDialog, setShowDeleteDialog] = useState(false);
  const [showRetryDialog, setShowRetryDialog] = useState(false);

  const deleteDoc = useDeleteDocument();
  const retryDoc = useRetryDocument();

  const handleDelete = async () => {
    await deleteDoc.mutateAsync(document.id);
    navigate("/documents");
  };

  const handleRetry = async () => {
    await retryDoc.mutateAsync(document.id);
    toast.success("Document re-processing started");
  };

  return (
    <>
      <div className="relative group">
        <NavLink
          to={`/documents/${document.id}`}
          className={({ isActive }) =>
            cn(
              "block p-3 rounded-md text-sm hover:bg-accent transition-colors text-left",
              isActive && "bg-accent"
            )
          }
        >
          <div className="flex items-start justify-between gap-2 mb-1">
            <div className="min-w-0 flex-1">
              <div className="font-medium truncate">{document.title}</div>
              <div className="text-xs text-muted-foreground">
                {document.page_count ?? "—"} pages • {uploadedAgo}
              </div>
            </div>
            <StatusBadge status={document.status} />
          </div>
          {document.status === "FAILED" && document.error_message && (
            <div className="text-xs text-destructive mt-2">{document.error_message}</div>
          )}
        </NavLink>

        <div className="absolute right-2 top-2 hidden gap-1 group-hover:flex">
          {document.status === "FAILED" && (
            <Button
              size="sm"
              variant="ghost"
              onClick={(e) => {
                e.preventDefault();
                setShowRetryDialog(true);
              }}
              disabled={retryDoc.isPending}
              title="Retry processing"
            >
              <RotateCcw className="h-4 w-4" />
            </Button>
          )}
          <Button
            size="sm"
            variant="ghost"
            onClick={(e) => {
              e.preventDefault();
              setShowDeleteDialog(true);
            }}
            disabled={deleteDoc.isPending}
            title="Delete document"
          >
            <Trash2 className="h-4 w-4" />
          </Button>
        </div>
      </div>

      <ConfirmDialog
        open={showDeleteDialog}
        onOpenChange={setShowDeleteDialog}
        title="Delete document"
        description="This will permanently delete the document and all associated conversations. This action cannot be undone."
        confirmLabel="Delete"
        isDestructive
        isLoading={deleteDoc.isPending}
        onConfirm={handleDelete}
      />

      <ConfirmDialog
        open={showRetryDialog}
        onOpenChange={setShowRetryDialog}
        title="Retry processing"
        description="This will re-process the document, which may take a while and will use credits."
        confirmLabel="Retry"
        isLoading={retryDoc.isPending}
        onConfirm={handleRetry}
      />
    </>
  );
}
