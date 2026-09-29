import { useMutation, useQueryClient } from "@tanstack/react-query";
import { deleteDocument } from "@libs/api/documents/api";

export function useDeleteDocument() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: deleteDocument,
    onSuccess: () => {
      // Refresh only the list. A prefix match would also refetch ["documents", id],
      // and purging the deleted document's cached queries while its page is still
      // mounted makes them refetch: the API cascade already removed them, so they 404.
      queryClient.invalidateQueries({ queryKey: ["documents"], exact: true });
    },
  });
}
