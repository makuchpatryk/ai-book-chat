import { X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import type { Source } from "@/types";

export function SourcesPanel({
  sources,
  onClose,
}: {
  sources: Source[];
  onClose: () => void;
}) {
  if (sources.length === 0) {
    return null;
  }

  return (
    <div className="fixed inset-0 bg-black/50 z-50 flex items-center justify-center p-4">
      <div className="bg-background rounded-lg shadow-lg max-w-md w-full max-h-96 overflow-y-auto">
        <div className="sticky top-0 bg-background border-b border-border p-4 flex items-center justify-between">
          <h3 className="font-semibold text-sm">Sources</h3>
          <Button variant="ghost" size="sm" onClick={onClose}>
            <X className="size-4" />
          </Button>
        </div>

        <div className="divide-y divide-border">
          {sources.map((source, idx) => (
            <div key={idx} className="p-4 space-y-2">
              <div className="flex items-center justify-between">
                <div className="font-mono text-xs text-muted-foreground">
                  p.{source.page_start}
                  {source.page_start !== source.page_end ? `–${source.page_end}` : ""}
                </div>
                {source.score !== null && (
                  <Badge variant="secondary" className="text-xs">
                    {(source.score * 100).toFixed(0)}%
                  </Badge>
                )}
              </div>

              {source.section_title && (
                <div className="text-sm font-medium text-foreground">{source.section_title}</div>
              )}

              <div className="text-sm text-muted-foreground line-clamp-3">{source.snippet}</div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
