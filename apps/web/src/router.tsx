import { createBrowserRouter, Navigate } from "react-router";

import { AppLayout } from "@/layouts/AppLayout";
import { DocumentsPage } from "@/features/documents/routes/DocumentsPage";
import { DocumentPage } from "@/features/documents/routes/DocumentPage";
import { ChatPage } from "@/features/chat/routes/ChatPage";
import { HealthPage } from "@/features/health/routes/HealthPage";

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
