import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { expect, it } from "vitest";

import { makeDocument } from "@/test/factories";
import { DocumentListItem } from "./DocumentListItem";

function renderItem(document = makeDocument()) {
  const queryClient = new QueryClient();
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <DocumentListItem document={document} />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

it("shows the summary clamped to two lines under the title", () => {
  renderItem(makeDocument({ summary: "A concise summary of the book." }));

  const summary = screen.getByText("A concise summary of the book.");
  expect(summary).toHaveClass("line-clamp-2");
  expect(screen.getByText("A Book")).toBeInTheDocument();
});

it("omits the summary line when the document has none", () => {
  renderItem(makeDocument({ summary: null }));

  expect(document.querySelector(".line-clamp-2")).toBeNull();
});

it("shows the cover thumbnail when the document has one", () => {
  renderItem(makeDocument({ has_cover: true }));

  expect(screen.getByAltText("Cover of A Book")).toBeInTheDocument();
});

it("shows the placeholder when the document has no cover", () => {
  renderItem(makeDocument({ has_cover: false }));

  expect(screen.getByLabelText("No cover")).toBeInTheDocument();
});

it("shows embedding progress while the document is embedding", () => {
  renderItem(makeDocument({ status: "EMBEDDING", embedded_chunks: 48, total_chunks: 200 }));

  const bar = screen.getByRole("progressbar", { name: "Embedding progress" });
  expect(bar).toHaveAttribute("aria-valuenow", "48");
  expect(bar).toHaveAttribute("aria-valuemax", "200");
  expect(screen.getByText("Embedding 48 / 200 chunks (24%)")).toBeInTheDocument();
});

it("hides the progress bar once the document is ready", () => {
  renderItem(makeDocument({ status: "READY", embedded_chunks: 200, total_chunks: 200 }));

  expect(screen.queryByRole("progressbar")).toBeNull();
});
