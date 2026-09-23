import { useMutation, useQueryClient } from "@tanstack/react-query";
import { prepareQuiz } from "@libs/api/documents/api";

export function usePrepareQuiz() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: prepareQuiz,
    onSuccess: (quiz) => {
      queryClient.setQueryData(["quiz", quiz.document_id], quiz);
    },
  });
}
