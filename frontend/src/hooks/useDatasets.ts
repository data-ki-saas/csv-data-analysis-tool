import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { deleteDataset, listDatasets, updateDataset, UpdateDatasetInput } from "@/lib/api";

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

export function useUpdateDataset() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ datasetId, ...input }: { datasetId: string } & UpdateDatasetInput) =>
      updateDataset(datasetId, input),
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: ["datasets"] });
      // The dataset detail query holds the same name/description/notes fields
      // (see DatasetSchema) but a slightly different shape (extra columns/
      // preview) -- patch in just what changed rather than refetching.
      queryClient.setQueryData(["datasetSchema", data.dataset_id], (prev: unknown) =>
        prev && typeof prev === "object"
          ? { ...prev, name: data.name, description: data.description, notes: data.notes }
          : prev
      );
    },
  });
}
