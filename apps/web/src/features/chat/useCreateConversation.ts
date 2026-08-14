import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "react-router";
import { createConversation } from "@/api/conversations";

export function useCreateConversation(documentId: string) {
  const queryClient = useQueryClient();
  const navigate = useNavigate();

  return useMutation({
    mutationFn: () => createConversation(documentId),
    onSuccess: (conversation) => {
      queryClient.invalidateQueries({ queryKey: ["conversations", documentId] });
      navigate(`/documents/${documentId}/c/${conversation.id}`);
    },
  });
}
