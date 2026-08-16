import { useMutation, useQueryClient } from "@tanstack/react-query";
import { deleteDocument } from "@/api/documents";

export function useDeleteDocument() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: deleteDocument,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["documents"] });
    },
  });
}
