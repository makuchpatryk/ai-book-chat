import type * as React from "react";

import { cn } from "@/lib/utils";

type TextareaProps = React.ComponentProps<"textarea">;

const Textarea = ({ className, ...props }: TextareaProps) => (
  <textarea
    className={cn(
      "flex min-h-[60px] w-full rounded-md border border-border bg-transparent px-3 py-2 text-base shadow-sm transition-colors placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:cursor-not-allowed disabled:opacity-50",
      className
    )}
    {...props}
  />
);

Textarea.displayName = "Textarea";

export { Textarea };
export type { TextareaProps };
