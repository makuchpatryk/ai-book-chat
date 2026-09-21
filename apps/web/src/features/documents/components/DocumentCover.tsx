import { useState } from "react";
import { FileText } from "lucide-react";
import { cn } from "@libs/utils/utils";
import { documentCoverUrl } from "@libs/api/documents/api";

interface DocumentCoverProps {
  documentId: string;
  hasCover: boolean;
  alt: string;
  className?: string;
}

export function DocumentCover({ documentId, hasCover, alt, className }: DocumentCoverProps) {
  const [failed, setFailed] = useState(false);
  const frame = cn("aspect-[3/4] shrink-0 overflow-hidden rounded border bg-muted", className);

  if (!hasCover || failed) {
    return (
      <div className={cn(frame, "flex items-center justify-center text-muted-foreground")}>
        <FileText className="size-1/3" aria-label="No cover" />
      </div>
    );
  }

  return (
    <div className={frame}>
      <img
        src={documentCoverUrl(documentId)}
        alt={alt}
        loading="lazy"
        className="h-full w-full object-cover"
        onError={() => setFailed(true)}
      />
    </div>
  );
}
