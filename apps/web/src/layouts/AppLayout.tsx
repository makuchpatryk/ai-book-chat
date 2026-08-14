import { HeartPulse } from "lucide-react";
import { NavLink, Outlet, useParams } from "react-router";

import { cn } from "@/lib/utils";
import { ConversationList } from "@/features/chat/ConversationList";
import { DocumentList } from "@/features/documents/DocumentList";
import { useDocuments } from "@/features/documents/useDocuments";
import { useConversations } from "@/features/chat/useConversations";

const FOOTER_NAV = [{ to: "/health", label: "Status", icon: HeartPulse }];

/** Sidebar (documents -> conversations) + main panel, per PRD §7. */
export function AppLayout() {
  const { documentId } = useParams<{ documentId?: string }>();
  const { data: documents } = useDocuments();
  const { data: conversations } = useConversations(documentId || "");

  return (
    <div className="flex h-screen">
      <aside className="flex w-80 shrink-0 flex-col border-r border-border bg-card">
        <div className="border-b border-border px-4 py-4">
          <h1 className="text-sm font-semibold">PDF RAG Chat</h1>
        </div>

        <div className="flex-1 overflow-y-auto">
          <div className="border-b border-border">
            <div className="p-3">
              <NavLink
                to="/documents"
                className={({ isActive }) =>
                  cn(
                    "text-xs font-semibold uppercase tracking-wider block px-2 py-1",
                    isActive ? "text-foreground" : "text-muted-foreground"
                  )
                }
              >
                Documents
              </NavLink>
            </div>
            <div className="px-2 pb-3">
              <DocumentList documents={documents} />
            </div>
          </div>

          {documentId && (
            <div className="border-b border-border">
              <div className="p-3">
                <div className="text-xs font-semibold uppercase tracking-wider text-muted-foreground px-2 py-1">
                  Conversations
                </div>
              </div>
              <div className="px-2 pb-3">
                <ConversationList documentId={documentId} conversations={conversations} />
              </div>
            </div>
          )}
        </div>

        <nav className="border-t border-border flex flex-col gap-1 p-2">
          {FOOTER_NAV.map(({ to, label, icon: Icon }) => (
            <NavLink
              key={to}
              to={to}
              end
              className={({ isActive }) =>
                cn(
                  "flex items-center gap-2 rounded-md px-3 py-2 text-sm",
                  isActive ? "bg-accent text-accent-foreground" : "text-muted-foreground"
                )
              }
            >
              <Icon className="size-4" />
              {label}
            </NavLink>
          ))}
        </nav>
      </aside>

      <main className="flex-1 overflow-y-auto p-8">
        <Outlet />
      </main>
    </div>
  );
}
