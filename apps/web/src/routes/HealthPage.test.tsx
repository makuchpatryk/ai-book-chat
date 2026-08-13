import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import type { ReactElement } from "react";
import { afterEach, expect, it, vi } from "vitest";

import { HealthPage } from "@/routes/HealthPage";

afterEach(() => {
  vi.unstubAllGlobals();
});

function renderWithQuery(ui: ReactElement) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={queryClient}>{ui}</QueryClientProvider>);
}

it("renders each dependency status once loaded", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      statusText: "OK",
      text: () => Promise.resolve(JSON.stringify({ status: "ok", database: "ok", redis: "ok" })),
    }),
  );

  renderWithQuery(<HealthPage />);

  expect(screen.getByText("Checking…")).toBeInTheDocument();
  expect(await screen.findAllByText("ok")).toHaveLength(3);
  expect(screen.getByText("Database")).toBeInTheDocument();
});
