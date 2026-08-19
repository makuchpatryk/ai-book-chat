import { useQuery } from "@tanstack/react-query";
// import { getSomething } from "@/api/domain/api";

/**
 * Example custom hook for this feature.
 *
 * Patterns:
 * - Query hooks: wrap React Query useQuery()
 * - Mutation hooks: wrap useMutation() with cache invalidation
 * - Colocate with component that uses it (or in hooks/ if multi-use)
 *
 * Example:
 *   export function useSomething(id: string) {
 *     return useQuery({
 *       queryKey: ["something", id],
 *       queryFn: () => getSomething(id),
 *       enabled: !!id,
 *     });
 *   }
 */
export function useTemplateExample() {
  return useQuery({
    queryKey: ["template"],
    queryFn: async () => {
      // Replace with real API call
      return { example: "data" };
    },
  });
}
