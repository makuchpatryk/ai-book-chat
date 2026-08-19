export type ChatEvent =
  | { type: "sources"; results: Array<{
      chunk_id: string;
      page_start: number;
      page_end: number;
      score: number | null;
      section_title: string | null;
      snippet: string;
    }>; pages: number[] }
  | { type: "token"; text: string }
  | { type: "done"; messageId: string; grounded: boolean; truncated: boolean }
  | { type: "error"; detail: string };
