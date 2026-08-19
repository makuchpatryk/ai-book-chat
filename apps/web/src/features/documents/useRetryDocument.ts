import { useMutation, useQueryClient } from "@tanstack/react-query";
import { retryDocument } from "@/api/documents/api";

export function useRetryDocument() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: retryDocument,
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ["documents"] });
      queryClient.invalidateQueries({ queryKey: ["document", data.id] });
    },
  });
}
