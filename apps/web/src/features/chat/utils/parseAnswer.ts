export interface ParsedAnswer {
  body: string;
  followUps: string[];
}

/** The line the model is told to write before its suggested questions. */
const FOLLOW_UPS_MARKER = /^[ \t>#*_]*follow[- ]?ups?(?: questions?)?[*_ \t]*:?[*_ \t]*$/im;
const LIST_ITEM = /^\s*(?:[-*+]|\d+[.)])\s+(.+?)\s*$/;

/**
 * Split an assistant answer into its Markdown body and the follow-up questions
 * listed after the FOLLOW-UPS marker. Works on partial (streaming) text too:
 * everything from the marker on is kept out of the body.
 */
export function parseAnswer(content: string): ParsedAnswer {
  const match = FOLLOW_UPS_MARKER.exec(content);
  if (!match) return { body: content, followUps: [] };

  const body = content
    .slice(0, match.index)
    .replace(/\s*(?:-{3,}|\*{3,})\s*$/, "")
    .trimEnd();
  const followUps = content
    .slice(match.index + match[0].length)
    .split("\n")
    .map((line) => LIST_ITEM.exec(line)?.[1].replace(/^\*\*(.+)\*\*$/, "$1"))
    .filter((q): q is string => !!q)
    .slice(0, 3);

  return { body, followUps };
}
