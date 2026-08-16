import { useMutation, useQueryClient } from "@tanstack/react-query";
import { deleteConversation } from "@/api/conversations";

export function useDeleteConversation(documentId: string) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: deleteConversation,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["conversations", documentId] });
    },
  });
}
