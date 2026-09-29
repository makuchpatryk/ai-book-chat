import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { createMemoryRouter, RouterProvider } from "react-router";
import { beforeEach, expect, it, vi } from "vitest";

import { AppLayout } from "@/layouts/AppLayout";
import { ChatPage } from "@/features/chat/routes/ChatPage";
import { DocumentPage } from "./DocumentPage";
import { DocumentsPage } from "./DocumentsPage";
import { makeDocument } from "@/test/factories";
import { toast } from "sonner";

vi.mock("sonner", async (orig) => ({ ...(await orig<object>()), toast: { error: vi.fn(), success: vi.fn() } }));

let deleted = false;
const requests: string[] = [];

beforeEach(() => {
  window.matchMedia ??= (() => ({ matches: false, addEventListener() {}, removeEventListener() {}, addListener() {}, removeListener() {} })) as never;
  deleted = false;
  requests.length = 0;
  vi.clearAllMocks();
});

async function setup(path: string) {
  const doc = makeDocument({ id: "doc-1", status: "READY" });
  const json = (body: unknown, status = 200) =>
    new Response(status === 204 ? null : JSON.stringify(body), { status });
  vi.stubGlobal("fetch", async (url: string, init?: RequestInit) => {
    const method = init?.method ?? "GET";
    requests.push(`${method} ${url}`);
    if (method === "DELETE") {
      deleted = true;
      return json(null, 204);
    }
    if (url === "/api/documents") return json(deleted ? [] : [doc]);
    if (/^\/api\/documents\/[^/]+$/.test(url))
      return deleted
        ? json({ detail: "document not found" }, 404)
        : json({ ...doc, sections: [], description_sections: [], chunk_count: 1 });
    if (url.endsWith("/conversations"))
      return deleted
        ? json({ detail: "document not found" }, 404)
        : json([{ id: "conv-1", title: "chat", created_at: new Date().toISOString() }]);
    if (url.endsWith("/messages"))
      return deleted ? json({ detail: "conversation not found" }, 404) : json([]);
    return json({ detail: "unhandled " + url }, 500);
  });

  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: 1, refetchOnWindowFocus: false } } });
  queryClient.getQueryCache().config.onError = (error, query) => {
    if (query.state.dataUpdatedAt === 0) toast.error(error instanceof Error ? error.message : "x");
  };
  const router = createMemoryRouter(
    [
      {
        path: "/",
        element: <AppLayout />,
        children: [
          { path: "documents", element: <DocumentsPage /> },
          { path: "documents/:documentId", element: <DocumentPage /> },
          { path: "documents/:documentId/c/:conversationId", element: <ChatPage /> },
        ],
      },
    ],
    { initialEntries: [path] },
  );
  render(
    <QueryClientProvider client={queryClient}>
      <RouterProvider router={router} />
    </QueryClientProvider>,
  );
  return router;
}

for (const path of ["/documents/doc-1", "/documents/doc-1/c/conv-1"]) {
  it(`no 404 after deleting the open document (${path})`, async () => {
    const router = await setup(path);
    await screen.findByTitle("Delete document", {}, { timeout: 3000 });
    fireEvent.click(screen.getByTitle("Delete document"));
    fireEvent.click(await screen.findByRole("button", { name: "Delete" }));
    await waitFor(() => expect(router.state.location.pathname).toBe("/documents"));
    await new Promise((r) => setTimeout(r, 2500)); // let retries (1s) fire
    expect(toast.error).not.toHaveBeenCalled();
  });
}
