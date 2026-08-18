import { useMutation, useQueryClient } from "@tanstack/react-query";
import { generateReportStrategy } from "@/lib/api";

export function useReportStrategy(datasetId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => generateReportStrategy(datasetId),
    onSuccess: (data) => {
      queryClient.setQueryData(["reportStrategy", datasetId], data);
    },
  });
}
