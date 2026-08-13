import { FileText, HeartPulse } from "lucide-react";
import { NavLink, Outlet } from "react-router";

import { cn } from "@/lib/utils";

const NAV = [
  { to: "/", label: "Status", icon: HeartPulse },
  { to: "/documents", label: "Documents", icon: FileText },
];

/** Sidebar (documents -> conversations) + main panel, per PRD §7. */
export function AppLayout() {
  return (
    <div className="flex h-screen">
      <aside className="flex w-64 shrink-0 flex-col border-r border-border bg-card">
        <div className="border-b border-border px-4 py-4">
          <h1 className="text-sm font-semibold">PDF RAG Chat</h1>
        </div>
        <nav className="flex flex-col gap-1 p-2">
          {NAV.map(({ to, label, icon: Icon }) => (
            <NavLink
              key={to}
              to={to}
              end
              className={({ isActive }) =>
                cn(
                  "flex items-center gap-2 rounded-md px-3 py-2 text-sm",
                  isActive ? "bg-accent text-accent-foreground" : "text-muted-foreground",
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
