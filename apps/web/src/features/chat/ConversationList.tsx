import { formatDistanceToNow } from "date-fns";
import { Plus, Trash2 } from "lucide-react";
import { NavLink, useNavigate } from "react-router";
import { useState } from "react";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { ConfirmDialog } from "@/components/ConfirmDialog";
import { useCreateConversation } from "@/features/chat/useCreateConversation";
import { useDeleteConversation } from "@/features/chat/useDeleteConversation";
import type { Conversation } from "@/types";

export function ConversationList({
  documentId,
  conversations,
}: {
  documentId: string;
  conversations: Conversation[] | undefined;
}) {
  const navigate = useNavigate();
  const { mutate: createNew, isPending } = useCreateConversation(documentId);
  const deleteConv = useDeleteConversation(documentId);
  const [showDeleteDialog, setShowDeleteDialog] = useState<string | null>(null);

  const handleDelete = async (conversationId: string) => {
    await deleteConv.mutateAsync(conversationId);
    navigate(`/documents/${documentId}`);
  };

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
            <div key={conv.id} className="relative group">
              <NavLink
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

              <Button
                size="sm"
                variant="ghost"
                className="absolute right-1 top-1 hidden group-hover:block"
                onClick={(e) => {
                  e.preventDefault();
                  setShowDeleteDialog(conv.id);
                }}
                disabled={deleteConv.isPending}
                title="Delete conversation"
              >
                <Trash2 className="h-3 w-3" />
              </Button>

              <ConfirmDialog
                open={showDeleteDialog === conv.id}
                onOpenChange={(open) => setShowDeleteDialog(open ? conv.id : null)}
                title="Delete conversation"
                description="This will permanently delete the conversation and all its messages."
                confirmLabel="Delete"
                isDestructive
                isLoading={deleteConv.isPending}
                onConfirm={() => handleDelete(conv.id)}
              />
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
