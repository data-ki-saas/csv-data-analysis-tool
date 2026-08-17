import { useMutation, useQueryClient } from "@tanstack/react-query";
import { uploadDataset } from "@/lib/api";

export function useUploadDataset() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: uploadDataset,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["datasets"] });
    },
  });
}
