import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router";
import { beforeEach, expect, it, vi } from "vitest";

import { useDocument } from "@/features/chat";
import { makeDetail } from "@/test/factories";
import { DocumentPage } from "./DocumentPage";

vi.mock("@/features/chat", () => ({
  useDocument: vi.fn(),
  useConversations: vi.fn(() => ({ data: [] })),
  ConversationList: () => <div>conversations</div>,
}));

function renderPage(detail: ReturnType<typeof makeDetail> | undefined) {
  vi.mocked(useDocument).mockReturnValue({ data: detail } as ReturnType<typeof useDocument>);
  return render(
    <QueryClientProvider client={new QueryClient()}>
      <MemoryRouter initialEntries={["/documents/doc-1"]}>
        <Routes>
          <Route path="/documents/:documentId" element={<DocumentPage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.mocked(useDocument).mockReset();
});

it("shows title, badges, meta row, topics and summary next to the cover", () => {
  renderPage(
    makeDetail({
      title: "Deep Work",
      author: "Cal Newport",
      doc_type: "Non-fiction",
      language: "en",
      topics: ["focus", "productivity"],
      summary: "Rules for focused success.",
      has_cover: true,
      overview_status: "ready",
      description_sections: [{ heading: "Core idea", body: "Depth beats shallowness." }],
    }),
  );

  expect(screen.getByRole("heading", { level: 1, name: "Deep Work" })).toBeInTheDocument();
  expect(screen.getByText("Non-fiction")).toBeInTheDocument();
  expect(screen.getByText("en")).toBeInTheDocument();
  expect(screen.getByText(/Cal Newport · 12 pages · 30 chunks · uploaded/)).toBeInTheDocument();
  expect(screen.getByText("focus")).toBeInTheDocument();
  expect(screen.getByText("productivity")).toBeInTheDocument();
  expect(screen.getByText("Rules for focused success.")).toBeInTheDocument();
  expect(screen.getByAltText("Cover of Deep Work")).toBeInTheDocument();
  expect(screen.getByRole("heading", { name: "Core idea" })).toBeInTheDocument();
});

it("drops the author and empty overview parts when the document has none", () => {
  renderPage(makeDetail({ overview_status: "pending" }));

  expect(screen.getByText(/^12 pages · 30 chunks · uploaded/)).toBeInTheDocument();
  expect(screen.getByText("Generating description…")).toBeInTheDocument();
  expect(screen.getByLabelText("No cover")).toBeInTheDocument();
});

it("shows not-found when the document is missing", () => {
  renderPage(undefined);

  expect(screen.getByText("Document not found")).toBeInTheDocument();
});
