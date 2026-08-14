import { useQuery } from "@tanstack/react-query";
import { listConversations } from "@/api/conversations";

export function useConversations(documentId: string) {
  return useQuery({
    queryKey: ["conversations", documentId],
    queryFn: () => listConversations(documentId),
    enabled: !!documentId,
  });
}
