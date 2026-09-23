import { formatDistanceToNow } from "date-fns";
import { Pencil, Plus, Trash2 } from "lucide-react";
import { NavLink, useNavigate } from "react-router";
import { useRef, useState } from "react";
import { cn } from "@libs/utils/utils";
import { Button } from "@libs/components/ui/button";
import { Input } from "@libs/components/ui/input";
import { ConfirmDialog } from "@libs/components/shared";
import { useCreateConversation } from "../hooks/useCreateConversation";
import { useDeleteConversation } from "../hooks/useDeleteConversation";
import { useRenameConversation } from "../hooks/useRenameConversation";
import type { Conversation } from "@libs/types";

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
  const renameConv = useRenameConversation(documentId);
  const [showDeleteDialog, setShowDeleteDialog] = useState<string | null>(null);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [draft, setDraft] = useState("");
  // Enter/Esc unmount the input, which can also fire blur — settle only once per edit.
  const settledRef = useRef(true);

  const startEditing = (conv: Conversation) => {
    settledRef.current = false;
    setDraft(conv.title ?? "");
    setEditingId(conv.id);
  };

  const finishEditing = (conv: Conversation, save: boolean) => {
    if (settledRef.current) return;
    settledRef.current = true;
    setEditingId(null);
    const title = draft.trim();
    if (save && title && title !== conv.title) {
      renameConv.mutate({ conversationId: conv.id, title });
    }
  };

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
              {editingId === conv.id ? (
                <div className="p-2">
                  <Input
                    autoFocus
                    aria-label="Conversation title"
                    className="h-7 px-2 text-xs"
                    maxLength={100}
                    value={draft}
                    onChange={(e) => setDraft(e.target.value)}
                    onFocus={(e) => e.currentTarget.select()}
                    onBlur={() => finishEditing(conv, true)}
                    onKeyDown={(e) => {
                      if (e.key === "Enter") finishEditing(conv, true);
                      if (e.key === "Escape") finishEditing(conv, false);
                    }}
                  />
                </div>
              ) : (
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
              )}

              {editingId !== conv.id && (
                <div className="absolute right-1 top-1 hidden group-hover:flex group-focus-within:flex">
                  <Button
                    size="sm"
                    variant="ghost"
                    onClick={(e) => {
                      e.preventDefault();
                      startEditing(conv);
                    }}
                    title="Rename conversation"
                    aria-label="Rename conversation"
                  >
                    <Pencil className="h-3 w-3" />
                  </Button>
                  <Button
                    size="sm"
                    variant="ghost"
                    onClick={(e) => {
                      e.preventDefault();
                      setShowDeleteDialog(conv.id);
                    }}
                    disabled={deleteConv.isPending}
                    title="Delete conversation"
                    aria-label="Delete conversation"
                  >
                    <Trash2 className="h-3 w-3" />
                  </Button>
                </div>
              )}

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
