import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { RouterProvider } from "react-router";
import { toast } from "sonner";

import { router } from "@/router";

import "./index.css";

const queryClient = new QueryClient({
  defaultOptions: {
    queries: { retry: 1, refetchOnWindowFocus: false },
  },
});

queryClient.getQueryCache().config.onError = (error, query) => {
  if (query.state.dataUpdatedAt === 0) {
    const message = error instanceof Error ? error.message : "Failed to load data";
    toast.error(message);
  }
};

queryClient.getMutationCache().config.onError = (error) => {
  const message = error instanceof Error ? error.message : "Operation failed";
  toast.error(message);
};

const rootElement = document.getElementById("root");
if (!rootElement) {
  throw new Error("#root element not found");
}

createRoot(rootElement).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <RouterProvider router={router} />
    </QueryClientProvider>
  </StrictMode>,
);
