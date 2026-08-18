import { useMutation } from "@tanstack/react-query";
import { createChartShare, GenerateInsightsInput, revokeChartShare } from "@/lib/api";

export function useCreateChartShare(datasetId: string) {
  return useMutation({
    mutationFn: (input: GenerateInsightsInput) => createChartShare(datasetId, input),
  });
}

export function useRevokeChartShare(datasetId: string) {
  return useMutation({
    mutationFn: (token: string) => revokeChartShare(datasetId, token),
  });
}
