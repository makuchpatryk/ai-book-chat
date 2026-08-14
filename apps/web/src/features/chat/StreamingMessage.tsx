import { Card } from "@/components/ui/card";
import { MarkdownAnswer } from "@/features/chat/MarkdownAnswer";
import { PageCitations } from "@/features/chat/PageCitations";

interface Source {
  chunk_id: string;
  page_start: number;
  page_end: number;
  score: number | null;
  section_title: string | null;
  snippet: string;
}

export function StreamingMessage({ text, sources }: { text: string; sources: Source[] }) {
  const pages = Array.from(
    new Set(
      sources.flatMap((s) => {
        const pages = [];
        for (let i = s.page_start; i <= s.page_end; i++) {
          pages.push(i);
        }
        return pages;
      })
    )
  ).sort((a, b) => a - b);

  return (
    <div className="flex gap-3 justify-start">
      <div className="max-w-md">
        <Card className="bg-muted p-3">
          {sources.length > 0 && (
            <div className="mb-2 text-xs text-muted-foreground">
              Found in document...
            </div>
          )}
          {text && <MarkdownAnswer content={text} />}
          <div className="mt-2 text-xs text-muted-foreground">▌</div>
          <PageCitations sources={sources} pages={pages} />
        </Card>
      </div>
    </div>
  );
}
