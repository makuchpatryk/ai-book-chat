import { useMutation, useQueryClient } from "@tanstack/react-query";
import { regenerateQuiz } from "@libs/api/documents/api";

export function useRegenerateQuiz() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: regenerateQuiz,
    onSuccess: (quiz) => {
      queryClient.setQueryData(["quiz", quiz.document_id], quiz);
    },
  });
}
