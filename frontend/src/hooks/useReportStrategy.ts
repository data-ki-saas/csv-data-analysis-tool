import { useMutation, useQueryClient } from "@tanstack/react-query";
import {
  addCustomChart,
  deleteChart,
  generateReportStrategy,
  reorderCharts,
  updateChart,
  UpdateChartInput,
  type ChartRecommendation,
  type ReportStrategy,
} from "@/lib/api";

export function useReportStrategy(datasetId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (force: boolean) => generateReportStrategy(datasetId, force),
    onSuccess: (data) => {
      queryClient.setQueryData(["reportStrategy", datasetId], data);
    },
  });
}

function appendChart(datasetId: string, chart: ChartRecommendation, prev: ReportStrategy | undefined) {
  return prev
    ? { ...prev, recommendations: [...prev.recommendations, chart] }
    : { dataset_id: datasetId, filename: "", recommendations: [chart] };
}

export function useAddCustomChart(datasetId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (prompt: string) => addCustomChart(datasetId, prompt),
    onSuccess: (chart) => {
      queryClient.setQueryData<ReportStrategy | undefined>(["reportStrategy", datasetId], (prev) =>
        appendChart(datasetId, chart, prev)
      );
    },
  });
}

export function useDeleteChart(datasetId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (chartId: string) => deleteChart(datasetId, chartId),
    onSuccess: (data) => {
      queryClient.setQueryData(["reportStrategy", datasetId], data);
    },
  });
}

export function useUpdateChart(datasetId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ chartId, ...input }: { chartId: string } & UpdateChartInput) =>
      updateChart(datasetId, chartId, input),
    onSuccess: (updated) => {
      queryClient.setQueryData<ReportStrategy | undefined>(["reportStrategy", datasetId], (prev) =>
        prev
          ? {
              ...prev,
              recommendations: prev.recommendations.map((r) => (r.id === updated.id ? updated : r)),
            }
          : prev
      );
    },
  });
}

export function useReorderCharts(datasetId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (chartIds: string[]) => reorderCharts(datasetId, chartIds),
    onSuccess: (data) => {
      queryClient.setQueryData(["reportStrategy", datasetId], data);
    },
  });
}
