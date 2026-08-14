import { http, HttpResponse } from "msw";
import type { Conversation, Document, DocumentDetail, Message } from "@/types";

// Mock data
const mockDocuments: Document[] = [
  {
    id: "doc-1",
    filename: "test.pdf",
    title: "Test Document",
    status: "READY",
    page_count: 10,
    error_message: null,
    created_at: new Date().toISOString(),
  },
];

const mockConversations: Conversation[] = [
  {
    id: "conv-1",
    title: "First chat",
    created_at: new Date().toISOString(),
  },
];

const mockMessages: Message[] = [
  {
    id: "msg-1",
    role: "user",
    content: "What is this about?",
    grounded: null,
    truncated: false,
    sources: [],
  },
  {
    id: "msg-2",
    role: "assistant",
    content: "This document is about...",
    grounded: true,
    truncated: false,
    sources: [
      {
        chunk_id: "chunk-1",
        page_start: 1,
        page_end: 1,
        score: 0.95,
        section_title: "Introduction",
        snippet: "This document is about...",
      },
    ],
  },
];

export const handlers = [
  // Documents
  http.get("/api/documents", () => HttpResponse.json(mockDocuments)),

  http.get("/api/documents/:id", ({ params }) => {
    const doc = mockDocuments.find((d) => d.id === params.id);
    if (!doc) return HttpResponse.json({ detail: "Not found" }, { status: 404 });

    const detail: DocumentDetail = {
      ...doc,
      sections: [
        {
          id: "sec-1",
          title: "Introduction",
          order_index: 0,
          start_page: 0,
          end_page: 5,
        },
      ],
      chunk_count: 100,
    };
    return HttpResponse.json(detail);
  }),

  http.post("/api/documents", async ({ request }) => {
    const formData = await request.formData();
    const file = formData.get("file") as File;

    if (!file) {
      return HttpResponse.json({ detail: "No file" }, { status: 400 });
    }

    if (file.type !== "application/pdf" && !file.name.endsWith(".pdf")) {
      return HttpResponse.json({ detail: "Invalid file type" }, { status: 415 });
    }

    if (file.size > 50 * 1024 * 1024) {
      return HttpResponse.json({ detail: "File too large" }, { status: 413 });
    }

    const newDoc: Document = {
      id: `doc-${Date.now()}`,
      filename: file.name,
      title: file.name.replace(".pdf", ""),
      status: "PENDING",
      page_count: null,
      error_message: null,
      created_at: new Date().toISOString(),
    };

    return HttpResponse.json(newDoc, { status: 201 });
  }),

  // Conversations
  http.get("/api/documents/:docId/conversations", () => HttpResponse.json(mockConversations)),

  http.post("/api/documents/:docId/conversations", () => {
    const newConv: Conversation = {
      id: `conv-${Date.now()}`,
      title: null,
      created_at: new Date().toISOString(),
    };
    return HttpResponse.json(newConv, { status: 201 });
  }),

  // Messages
  http.get("/api/conversations/:convId/messages", () => HttpResponse.json(mockMessages)),

  http.post("/api/conversations/:convId/messages", () => {
    return handleStreamingMessage();
  }),
];

function handleStreamingMessage(): Response {
  const encoder = new TextEncoder();
  const frames: string[] = [
    `event: sources\ndata: ${JSON.stringify({
      results: [
        {
          chunk_id: "chunk-1",
          page_start: 1,
          page_end: 1,
          score: 0.95,
          section_title: "Introduction",
          snippet: "Introduction text here",
        },
      ],
      pages: [1],
    })}\n\n`,
    `event: token\ndata: ${JSON.stringify({ text: "This " })}\n\n`,
    `event: token\ndata: ${JSON.stringify({ text: "is " })}\n\n`,
    `event: token\ndata: ${JSON.stringify({ text: "the " })}\n\n`,
    `event: token\ndata: ${JSON.stringify({ text: "answer." })}\n\n`,
    `event: done\ndata: ${JSON.stringify({
      message_id: `msg-${Date.now()}`,
      grounded: true,
      truncated: false,
    })}\n\n`,
  ];

  const readable = new ReadableStream<Uint8Array>({
    start(controller) {
      frames.forEach((frame) => {
        controller.enqueue(encoder.encode(frame));
      });
      controller.close();
    },
  });

  return new HttpResponse(readable, {
    headers: {
      "Content-Type": "text/event-stream",
      "Cache-Control": "no-cache",
      Connection: "keep-alive",
      "X-Accel-Buffering": "no",
    },
  });
}
