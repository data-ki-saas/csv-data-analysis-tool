import { useMutation } from "@tanstack/react-query";
import { generateInsights, GenerateInsightsInput } from "@/lib/api";

export function useGenerateInsights(datasetId: string) {
  return useMutation({
    mutationFn: (input: GenerateInsightsInput) => generateInsights(datasetId, input),
  });
}
