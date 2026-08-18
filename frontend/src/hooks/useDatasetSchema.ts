import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { getDatasetSchema, reviewColumnTypes, updateColumn, UpdateColumnInput } from "@/lib/api";

export function useDatasetSchema(datasetId: string) {
  return useQuery({
    queryKey: ["datasetSchema", datasetId],
    queryFn: () => getDatasetSchema(datasetId),
  });
}

export function useReviewColumnTypes(datasetId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (columns?: string[]) => reviewColumnTypes(datasetId, columns),
    onSuccess: (data) => {
      queryClient.setQueryData(["datasetSchema", datasetId], data);
    },
  });
}

export function useUpdateColumn(datasetId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ column, ...update }: { column: string } & UpdateColumnInput) =>
      updateColumn(datasetId, column, update),
    onSuccess: (data) => {
      queryClient.setQueryData(["datasetSchema", datasetId], data);
    },
  });
}
