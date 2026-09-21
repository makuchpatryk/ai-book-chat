export function EmbeddingProgress({ embedded, total }: { embedded: number; total: number }) {
  const percent = total > 0 ? Math.round((embedded / total) * 100) : 0;

  return (
    <div className="mt-2">
      <div
        role="progressbar"
        aria-label="Embedding progress"
        aria-valuemin={0}
        aria-valuemax={total}
        aria-valuenow={embedded}
        className="h-1.5 w-full overflow-hidden rounded-full bg-secondary"
      >
        <div
          className="h-full bg-primary transition-[width] duration-500"
          style={{ width: `${percent}%` }}
        />
      </div>
      <div className="mt-1 text-xs text-muted-foreground">
        Embedding {embedded} / {total} chunks ({percent}%)
      </div>
    </div>
  );
}
