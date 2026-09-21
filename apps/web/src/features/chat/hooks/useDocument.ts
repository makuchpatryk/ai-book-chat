import { useQuery } from "@tanstack/react-query";
import { getDocument } from "@libs/api/documents/api";

const PROCESSING = ["PENDING", "PARSING", "EMBEDDING"];

export function useDocument(documentId: string) {
  return useQuery({
    queryKey: ["documents", documentId],
    queryFn: () => getDocument(documentId),
    enabled: !!documentId,
    refetchInterval: (query) => {
      const doc = query.state.data;
      const busy = !!doc && (PROCESSING.includes(doc.status) || doc.overview_status === "pending");
      return busy ? 2000 : false;
    },
  });
}
