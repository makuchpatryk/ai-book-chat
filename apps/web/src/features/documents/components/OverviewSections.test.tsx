import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, expect, it, vi } from "vitest";

import { regenerateOverview } from "@libs/api/documents/api";
import { makeDetail } from "@/test/factories";
import { OverviewSections } from "./OverviewSections";

vi.mock("@libs/api/documents/api", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@libs/api/documents/api")>()),
  regenerateOverview: vi.fn(),
}));

beforeEach(() => {
  vi.mocked(regenerateOverview).mockResolvedValue(makeDetail());
});

function renderSections(overrides: Parameters<typeof makeDetail>[0]) {
  const queryClient = new QueryClient();
  return render(
    <QueryClientProvider client={queryClient}>
      <OverviewSections document={makeDetail(overrides)} />
    </QueryClientProvider>,
  );
}

it("renders each description section with its heading and body", () => {
  renderSections({
    overview_status: "ready",
    description_sections: [
      { heading: "Overview", body: "What it covers." },
      { heading: "Audience", body: "Who reads it." },
    ],
  });

  expect(screen.getByRole("heading", { name: "Overview" })).toBeInTheDocument();
  expect(screen.getByText("What it covers.")).toBeInTheDocument();
  expect(screen.getByRole("heading", { name: "Audience" })).toBeInTheDocument();
});

it("renders LLM text as plain text, never as HTML", () => {
  renderSections({
    overview_status: "ready",
    description_sections: [{ heading: "<img src=x onerror=alert(1)>", body: "<b>bold</b>" }],
  });

  expect(screen.getByText("<b>bold</b>")).toBeInTheDocument();
  expect(document.querySelector("img")).toBeNull();
});

it("shows a skeleton while the overview is pending", () => {
  renderSections({ overview_status: "pending" });

  expect(screen.getByText("Generating description…")).toBeInTheDocument();
  expect(screen.queryByRole("button")).not.toBeInTheDocument();
});

it("offers Regenerate when generation failed, and calls the API", async () => {
  renderSections({ overview_status: "failed" });

  expect(screen.getByText("Description generation failed")).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Regenerate" }));

  await waitFor(() => expect(regenerateOverview).toHaveBeenCalled());
  expect(vi.mocked(regenerateOverview).mock.calls[0]?.[0]).toBe("doc-1");
});

it("offers Generate description for documents that never had an overview", async () => {
  renderSections({ overview_status: null });

  fireEvent.click(screen.getByRole("button", { name: "Generate description" }));

  await waitFor(() => expect(regenerateOverview).toHaveBeenCalled());
  expect(vi.mocked(regenerateOverview).mock.calls[0]?.[0]).toBe("doc-1");
});

it("renders nothing for a document that is not READY", () => {
  const { container } = renderSections({ status: "EMBEDDING", overview_status: null });

  expect(container).toBeEmptyDOMElement();
});
