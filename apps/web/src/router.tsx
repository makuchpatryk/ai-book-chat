import { createBrowserRouter, Navigate } from "react-router";

import { AppLayout } from "@/layouts/AppLayout";
import { DocumentsPage } from "@/routes/DocumentsPage";
import { DocumentPage } from "@/routes/DocumentPage";
import { ChatPage } from "@/routes/ChatPage";
import { HealthPage } from "@/routes/HealthPage";

export const router = createBrowserRouter([
  {
    path: "/",
    element: <AppLayout />,
    children: [
      { index: true, element: <Navigate to="/documents" replace /> },
      { path: "documents", element: <DocumentsPage /> },
      { path: "documents/:documentId", element: <DocumentPage /> },
      { path: "documents/:documentId/c/:conversationId", element: <ChatPage /> },
      { path: "health", element: <HealthPage /> },
    ],
  },
]);
