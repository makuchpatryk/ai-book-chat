import { formatDistanceToNow } from "date-fns";
import { Plus } from "lucide-react";
import { NavLink } from "react-router";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { useCreateConversation } from "@/features/chat/useCreateConversation";
import type { Conversation } from "@/types";

export function ConversationList({
  documentId,
  conversations,
}: {
  documentId: string;
  conversations: Conversation[] | undefined;
}) {
  const { mutate: createNew, isPending } = useCreateConversation(documentId);

  return (
    <div className="space-y-2">
      <Button
        onClick={() => createNew()}
        disabled={isPending}
        size="sm"
        className="w-full gap-1"
        variant="outline"
      >
        <Plus className="size-3" />
        New chat
      </Button>

      {conversations && conversations.length > 0 && (
        <div className="space-y-1">
          {conversations.map((conv) => (
            <NavLink
              key={conv.id}
              to={`/documents/${documentId}/c/${conv.id}`}
              className={({ isActive }) =>
                cn(
                  "block p-2 rounded-md text-xs hover:bg-accent transition-colors text-left truncate",
                  isActive && "bg-accent"
                )
              }
            >
              <div className="font-medium truncate">{conv.title || "New chat"}</div>
              <div className="text-muted-foreground text-xs">
                {formatDistanceToNow(new Date(conv.created_at), { addSuffix: true })}
              </div>
            </NavLink>
          ))}
        </div>
      )}
    </div>
  );
}
