import { useMutation, useQueryClient } from "@tanstack/react-query";
import { deleteDocument } from "@/api/documents";

export function useDeleteDocument() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: deleteDocument,
    onSuccess: (_data, documentId) => {
      queryClient.invalidateQueries({ queryKey: ["documents"] });
      // The API cascades the document's conversations away with it; drop their
      // cached lists so a re-upload does not show the deleted threads.
      queryClient.removeQueries({ queryKey: ["conversations", documentId] });
    },
  });
}
