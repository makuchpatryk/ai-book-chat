import { useQuery } from "@tanstack/react-query";
import { getMessages } from "@/api/conversations";

export function useMessages(conversationId: string) {
  return useQuery({
    queryKey: ["messages", conversationId],
    queryFn: () => getMessages(conversationId),
  });
}
