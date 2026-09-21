import { Loader2 } from "lucide-react";
import { Alert, AlertDescription, AlertTitle } from "@libs/components/ui/alert";
import { Button } from "@libs/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@libs/components/ui/card";
import { Skeleton } from "@libs/components/ui/skeleton";
import type { DocumentDetail } from "@libs/types";
import { useRegenerateOverview } from "../hooks/useRegenerateOverview";

/** Description card: sections when ready, skeleton while pending, action otherwise. */
export function OverviewSections({ document }: { document: DocumentDetail }) {
  const regenerate = useRegenerateOverview();

  if (document.status !== "READY") return null;

  const { overview_status: status, description_sections: sections } = document;

  if (status === "pending") {
    return (
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-base">
            <Loader2 className="size-4 animate-spin" />
            Generating description…
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <Skeleton className="h-4 w-full" />
          <Skeleton className="h-4 w-5/6" />
          <Skeleton className="h-4 w-2/3" />
        </CardContent>
      </Card>
    );
  }

  if (status === "ready" && sections.length > 0) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>Description</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          {sections.map((section) => (
            <section key={section.heading}>
              <h3 className="font-semibold">{section.heading}</h3>
              <p className="text-sm text-muted-foreground whitespace-pre-line">{section.body}</p>
            </section>
          ))}
        </CardContent>
      </Card>
    );
  }

  const failed = status === "failed";

  return (
    <Alert variant={failed ? "destructive" : "default"}>
      <AlertTitle>{failed ? "Description generation failed" : "No description yet"}</AlertTitle>
      <AlertDescription className="flex items-center justify-between gap-2">
        <span>
          {failed
            ? "Chat still works. You can try generating the description again."
            : "Generate a summary, topics and a cover for this document."}
        </span>
        <Button
          size="sm"
          variant="outline"
          disabled={regenerate.isPending}
          onClick={() => regenerate.mutate(document.id)}
        >
          {failed ? "Regenerate" : "Generate description"}
        </Button>
      </AlertDescription>
    </Alert>
  );
}
