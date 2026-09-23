import { useMutation, useQueryClient } from "@tanstack/react-query";
import { renameConversation } from "@libs/api/conversations/api";

export function useRenameConversation(documentId: string) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ conversationId, title }: { conversationId: string; title: string }) =>
      renameConversation(conversationId, title),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["conversations", documentId] });
    },
  });
}
