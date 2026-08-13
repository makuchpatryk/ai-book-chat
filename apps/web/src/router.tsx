import { createBrowserRouter } from "react-router";

import { AppLayout } from "@/layouts/AppLayout";
import { DocumentsPage } from "@/routes/DocumentsPage";
import { HealthPage } from "@/routes/HealthPage";

export const router = createBrowserRouter([
  {
    path: "/",
    element: <AppLayout />,
    children: [
      { index: true, element: <HealthPage /> },
      { path: "documents", element: <DocumentsPage /> },
    ],
  },
]);
