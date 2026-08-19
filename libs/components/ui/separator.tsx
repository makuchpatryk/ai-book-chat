import { cn } from "@/lib/utils";

interface SeparatorProps extends React.ComponentProps<"div"> {
  orientation?: "horizontal" | "vertical";
  decorative?: boolean;
}

const Separator = ({
  className,
  orientation = "horizontal",
  decorative = true,
  ...props
}: SeparatorProps) => (
  <div
    role={decorative ? "none" : "separator"}
    aria-orientation={orientation === "vertical" ? "vertical" : "horizontal"}
    className={cn(
      "shrink-0 bg-border",
      orientation === "horizontal" ? "h-px w-full" : "h-full w-px",
      className
    )}
    {...props}
  />
);

Separator.displayName = "Separator";

export { Separator };
export type { SeparatorProps };
