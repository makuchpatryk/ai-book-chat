import { Loader2 } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import type { DocumentStatus } from "@/types";

export function StatusBadge({ status }: { status: DocumentStatus }) {
  const isProcessing = ["PENDING", "PARSING", "EMBEDDING"].includes(status);

  if (status === "READY") {
    return <Badge variant="default">Ready</Badge>;
  }

  if (status === "FAILED") {
    return <Badge variant="destructive">Failed</Badge>;
  }

  if (isProcessing) {
    return (
      <Badge variant="secondary" className="gap-1">
        <Loader2 className="size-3 animate-spin" />
        {status}
      </Badge>
    );
  }

  return <Badge variant="secondary">{status}</Badge>;
}
