import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  getPresentation,
  pinBlock,
  PresentationPageData,
  updatePresentation,
} from "@/lib/api";

export function usePresentation(datasetId: string) {
  return useQuery({
    queryKey: ["presentation", datasetId],
    queryFn: () => getPresentation(datasetId),
  });
}

export function useUpdatePresentation(datasetId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (input: { title: string; pages: PresentationPageData[] }) =>
      updatePresentation(datasetId, input),
    onSuccess: (data) => {
      queryClient.setQueryData(["presentation", datasetId], data);
    },
  });
}

export function usePinBlock(datasetId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (input: Parameters<typeof pinBlock>[1]) => pinBlock(datasetId, input),
    onSuccess: (data) => {
      queryClient.setQueryData(["presentation", datasetId], data);
    },
  });
}
