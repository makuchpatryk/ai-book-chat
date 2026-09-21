import { useMutation, useQueryClient } from "@tanstack/react-query";
import { regenerateOverview } from "@libs/api/documents/api";

export function useRegenerateOverview() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: regenerateOverview,
    onSuccess: () => {
      // Prefix match covers the list and every document detail query.
      queryClient.invalidateQueries({ queryKey: ["documents"] });
    },
  });
}
