import { useQuery } from "@tanstack/react-query";
import { getDocument } from "@/api/documents";

export function useDocument(documentId: string) {
  return useQuery({
    queryKey: ["documents", documentId],
    queryFn: () => getDocument(documentId),
    enabled: !!documentId,
  });
}
