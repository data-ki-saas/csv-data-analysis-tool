import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  acceptColumnValueMerge,
  getColumnValues,
  getDatasetSchema,
  reviewColumnTypes,
  revertColumnValueMerge,
  suggestColumnValueMerge,
  updateColumn,
  UpdateColumnInput,
  ValueMergeRule,
} from "@/lib/api";

export function useDatasetSchema(datasetId: string) {
  return useQuery({
    queryKey: ["datasetSchema", datasetId],
    queryFn: () => getDatasetSchema(datasetId),
  });
}

export function useReviewColumnTypes(datasetId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (columns?: string[]) => reviewColumnTypes(datasetId, columns),
    onSuccess: (data) => {
      queryClient.setQueryData(["datasetSchema", datasetId], data);
    },
  });
}

export function useUpdateColumn(datasetId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ column, ...update }: { column: string } & UpdateColumnInput) =>
      updateColumn(datasetId, column, update),
    onSuccess: (data) => {
      queryClient.setQueryData(["datasetSchema", datasetId], data);
    },
  });
}

export function useColumnValues(datasetId: string, column: string, enabled: boolean) {
  return useQuery({
    queryKey: ["columnValues", datasetId, column],
    queryFn: () => getColumnValues(datasetId, column),
    enabled,
  });
}

export function useSuggestValueMerge(datasetId: string, column: string) {
  return useMutation({
    mutationFn: (command: string) => suggestColumnValueMerge(datasetId, column, command),
  });
}

/** A merge is stored per-dataset but read everywhere (charts, reports, the
 * query API) -- see CLAUDE.md's "merge scope" decision. Accepting or
 * reverting one also clears the dataset's cached report_strategy
 * server-side (see repository.update_dataset_value_remaps), so both queries
 * are invalidated here rather than just patched in place: report_strategy's
 * shape isn't returned by this endpoint, and datasetSchema's
 * has_report_strategy flag needs to reflect that the cache was cleared. */
function onMergeSuccess(
  queryClient: ReturnType<typeof useQueryClient>,
  datasetId: string,
  column: string,
  data: unknown
) {
  queryClient.setQueryData(["columnValues", datasetId, column], data);
  queryClient.invalidateQueries({ queryKey: ["datasetSchema", datasetId] });
  queryClient.invalidateQueries({ queryKey: ["reportStrategy", datasetId] });
}

export function useAcceptValueMerge(datasetId: string, column: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (groups: ValueMergeRule[]) => acceptColumnValueMerge(datasetId, column, groups),
    onSuccess: (data) => onMergeSuccess(queryClient, datasetId, column, data),
  });
}

export function useRevertValueMerge(datasetId: string, column: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (target: string) => revertColumnValueMerge(datasetId, column, target),
    onSuccess: (data) => onMergeSuccess(queryClient, datasetId, column, data),
  });
}
