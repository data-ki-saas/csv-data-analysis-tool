import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { deleteDataset, listDatasets } from "@/lib/api";

export function useDatasets() {
  return useQuery({ queryKey: ["datasets"], queryFn: listDatasets });
}

export function useDeleteDataset() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: deleteDataset,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["datasets"] });
    },
  });
}
