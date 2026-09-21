import { Children, type ReactNode } from "react";
import ReactMarkdown, { type Components } from "react-markdown";
import remarkGfm from "remark-gfm";

/** Inline page citations the model writes, e.g. [p.12], [p. 26-29], [p. 15-16, 31-33]. */
const CITATION = /(\[p\.\s?\d+(?:\s?[-–]\s?\d+)?(?:,\s?\d+(?:\s?[-–]\s?\d+)?)*\])/g;

function withCitations(children: ReactNode): ReactNode {
  return Children.map(children, (child) => {
    if (typeof child !== "string") return child;
    return child.split(CITATION).map((part, i) =>
      i % 2 === 1 ? (
        <span
          key={i}
          className="mx-0.5 inline-block rounded bg-primary/10 px-1.5 py-px align-baseline text-[0.7rem] font-medium whitespace-nowrap text-primary"
        >
          {part.slice(1, -1)}
        </span>
      ) : (
        part
      ),
    );
  });
}

const components: Components = {
  h1: ({ children }) => <h3 className="mt-5 mb-2 text-base font-semibold first:mt-0">{children}</h3>,
  h2: ({ children }) => (
    <h3 className="mt-5 mb-2 border-b border-border pb-1 text-base font-semibold first:mt-0">
      {children}
    </h3>
  ),
  h3: ({ children }) => <h4 className="mt-4 mb-1.5 text-sm font-semibold first:mt-0">{children}</h4>,
  p: ({ children }) => <p className="my-2 leading-relaxed first:mt-0 last:mb-0">{withCitations(children)}</p>,
  ul: ({ children }) => <ul className="my-2 list-disc space-y-1.5 pl-5 marker:text-muted-foreground">{children}</ul>,
  ol: ({ children }) => <ol className="my-2 list-decimal space-y-1.5 pl-5 marker:text-muted-foreground">{children}</ol>,
  li: ({ children }) => <li className="leading-relaxed pl-0.5">{withCitations(children)}</li>,
  strong: ({ children }) => <strong className="font-semibold text-foreground">{withCitations(children)}</strong>,
  em: ({ children }) => <em>{withCitations(children)}</em>,
  blockquote: ({ children }) => (
    <blockquote className="my-3 border-l-2 border-primary/40 pl-3 italic text-muted-foreground">
      {children}
    </blockquote>
  ),
  hr: () => <hr className="my-4 border-border" />,
  a: ({ children, href }) => (
    <a href={href} target="_blank" rel="noreferrer" className="text-primary underline underline-offset-2">
      {children}
    </a>
  ),
  code: ({ children }) => (
    <code className="rounded bg-background/70 px-1 py-0.5 font-mono text-[0.8em]">{children}</code>
  ),
  pre: ({ children }) => (
    <pre className="my-3 overflow-x-auto rounded-md bg-background/70 p-3 text-xs [&_code]:bg-transparent [&_code]:p-0">
      {children}
    </pre>
  ),
  table: ({ children }) => (
    <div className="my-3 overflow-x-auto">
      <table className="w-full border-collapse text-xs">{children}</table>
    </div>
  ),
  th: ({ children }) => <th className="border-b border-border px-2 py-1 text-left font-semibold">{children}</th>,
  td: ({ children }) => <td className="border-b border-border/60 px-2 py-1 align-top">{withCitations(children)}</td>,
};

export function MarkdownAnswer({ content }: { content: string }) {
  return (
    <div className="text-sm break-words">
      <ReactMarkdown remarkPlugins={[remarkGfm]} components={components}>
        {content}
      </ReactMarkdown>
    </div>
  );
}
