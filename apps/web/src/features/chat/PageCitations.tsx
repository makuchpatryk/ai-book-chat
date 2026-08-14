import { useState } from "react";
import { Badge } from "@/components/ui/badge";
import { SourcesPanel } from "@/features/chat/SourcesPanel";
import type { Source } from "@/types";

export function PageCitations({
  sources,
  pages,
}: {
  sources: Source[];
  pages: number[];
}) {
  const [showSources, setShowSources] = useState(false);

  if (pages.length === 0) {
    return null;
  }

  return (
    <>
      <div className="flex flex-wrap gap-1 mt-3">
        {pages.map((page) => (
          <Badge
            key={page}
            variant="outline"
            className="cursor-pointer hover:bg-accent"
            onClick={() => setShowSources(true)}
          >
            p.{page}
          </Badge>
        ))}
      </div>

      {showSources && <SourcesPanel sources={sources} onClose={() => setShowSources(false)} />}
    </>
  );
}
