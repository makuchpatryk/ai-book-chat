import { useQuery } from "@tanstack/react-query";
import { listConversations } from "@libs/api/conversations/api";

export function useConversations(documentId: string) {
  return useQuery({
    queryKey: ["conversations", documentId],
    queryFn: () => listConversations(documentId),
    enabled: !!documentId,
  });
}
