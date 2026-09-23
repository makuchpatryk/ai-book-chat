import { useQuery } from "@tanstack/react-query";
import { getQuiz } from "@libs/api/documents/api";

/** Polls the quiz while generation is pending. `enabled` lets the caller defer the
 * first fetch until a quiz has actually been requested (GET 404s before then). */
export function useQuiz(documentId: string, enabled: boolean) {
  return useQuery({
    queryKey: ["quiz", documentId],
    queryFn: () => getQuiz(documentId),
    enabled,
    refetchInterval: (query) => (query.state.data?.status === "pending" ? 2000 : false),
  });
}
