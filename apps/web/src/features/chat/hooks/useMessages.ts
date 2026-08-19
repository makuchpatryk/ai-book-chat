import { useQuery } from "@tanstack/react-query";
import { getMessages } from "@/api/conversations/api";

export function useMessages(conversationId: string) {
  return useQuery({
    queryKey: ["messages", conversationId],
    queryFn: () => getMessages(conversationId),
  });
}
