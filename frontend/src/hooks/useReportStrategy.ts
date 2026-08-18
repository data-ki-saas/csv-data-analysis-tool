import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
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

/** Reads the ["reportStrategy", datasetId] cache entry reactively.
 *
 * `useReportStrategy` below (and every other mutation in this file) is a
 * `useMutation`, not a `useQuery` -- a mutation's own `.data` only updates
 * when *that specific hook instance's* `mutate()` resolves, it is not a
 * subscription to the query cache. `queryClient.setQueryData(["reportStrategy",
 * ...])` from useDeleteChart/useReorderCharts/useAddCustomChart/useUpdateChart
 * writes into the cache correctly, but nothing was ever subscribed to that
 * cache entry, so a delete/reorder/custom-add/rename appeared to do nothing
 * until the next full page load's auto-generate effect called
 * `strategy.mutate(false)` again and repopulated the mutation's own `.data`
 * from the (already-updated) cache. This hook is the fix: an always-enabled
 * subscriber with no fetcher of its own (every write to this cache key comes
 * from a mutation's onSuccess, never from this hook fetching) -- reading
 * through it means every one of those writes re-renders the page immediately. */
export function useReportStrategyData(datasetId: string) {
  return useQuery<ReportStrategy>({
    queryKey: ["reportStrategy", datasetId],
    queryFn: () => {
      throw new Error("reportStrategy has no fetcher of its own -- only populated via mutations");
    },
    enabled: false,
    staleTime: Infinity,
  });
}

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
