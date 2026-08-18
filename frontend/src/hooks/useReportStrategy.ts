import { useMutation, useQueryClient } from "@tanstack/react-query";
import { generateReportStrategy } from "@/lib/api";

export function useReportStrategy(datasetId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (force: boolean) => generateReportStrategy(datasetId, force),
    onSuccess: (data) => {
      queryClient.setQueryData(["reportStrategy", datasetId], data);
    },
  });
}
