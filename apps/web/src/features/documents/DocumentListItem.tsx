import { formatDistanceToNow } from "date-fns";
import { NavLink } from "react-router";
import { cn } from "@/lib/utils";
import { StatusBadge } from "@/features/documents/StatusBadge";
import type { Document } from "@/types";

export function DocumentListItem({ document }: { document: Document }) {
  const uploadedAgo = formatDistanceToNow(new Date(document.created_at), { addSuffix: true });

  return (
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
  );
}
