import { useQuery } from "@tanstack/react-query";
import { listDocuments } from "@/api/documents";
import type { Document, DocumentStatus } from "@/types";

export function hasProcessing(data: Document[] | undefined): boolean {
  return !!data?.some((doc) => {
    const status: DocumentStatus = doc.status;
    return ["PENDING", "PARSING", "EMBEDDING"].includes(status);
  });
}

export function useDocuments() {
  return useQuery({
    queryKey: ["documents"],
    queryFn: listDocuments,
    refetchInterval: (query) => (hasProcessing(query.state.data) ? 2000 : false),
  });
}
