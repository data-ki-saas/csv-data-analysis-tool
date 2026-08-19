import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  acceptColumnValueMerge,
  acceptColumnValueReplacement,
  addTagChart,
  getColumnValues,
  getDatasetSchema,
  getTagCandidates,
  reviewColumnTypes,
  revertColumnValueMerge,
  revertColumnValueReplacement,
  suggestColumnValueMerge,
  TagConfig,
  updateColumn,
  UpdateColumnInput,
  updateTagConfig,
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

export function useColumnValues(datasetId: string, column: string, enabled: boolean, limit?: number) {
  return useQuery({
    queryKey: ["columnValues", datasetId, column, limit],
    queryFn: () => getColumnValues(datasetId, column, limit),
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
 * has_report_strategy flag needs to reflect that the cache was cleared.
 *
 * columnValues is invalidated by its key *prefix* (["columnValues",
 * datasetId, column], no trailing limit) rather than overwritten with this
 * response's own (default-sized) data -- an accept/revert response is
 * always capped at the backend's default page size, so patching it in
 * directly would silently discard however many extra rows a "Load more"
 * click had already fetched. Invalidating lets each mounted useColumnValues
 * instance refetch under its own current limit instead. */
function onMergeSuccess(queryClient: ReturnType<typeof useQueryClient>, datasetId: string, column: string) {
  queryClient.invalidateQueries({ queryKey: ["columnValues", datasetId, column] });
  queryClient.invalidateQueries({ queryKey: ["datasetSchema", datasetId] });
  queryClient.invalidateQueries({ queryKey: ["reportStrategy", datasetId] });
}

export function useAcceptValueMerge(datasetId: string, column: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (groups: ValueMergeRule[]) => acceptColumnValueMerge(datasetId, column, groups),
    onSuccess: () => onMergeSuccess(queryClient, datasetId, column),
  });
}

export function useRevertValueMerge(datasetId: string, column: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (target: string) => revertColumnValueMerge(datasetId, column, target),
    onSuccess: () => onMergeSuccess(queryClient, datasetId, column),
  });
}

export function useAcceptValueReplacement(datasetId: string, column: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ find, replace, isRegex }: { find: string; replace: string; isRegex?: boolean }) =>
      acceptColumnValueReplacement(datasetId, column, find, replace, isRegex),
    onSuccess: () => onMergeSuccess(queryClient, datasetId, column),
  });
}

export function useRevertValueReplacement(datasetId: string, column: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (find: string) => revertColumnValueReplacement(datasetId, column, find),
    onSuccess: () => onMergeSuccess(queryClient, datasetId, column),
  });
}

export function useTagCandidates(datasetId: string, column: string, enabled: boolean, limit?: number) {
  return useQuery({
    queryKey: ["tagCandidates", datasetId, column, limit],
    queryFn: () => getTagCandidates(datasetId, column, limit),
    enabled,
  });
}

/** Saving a new config (separators/vocabulary) changes what candidates mean
 * for every page size, so this invalidates by key prefix (see
 * onMergeSuccess's columnValues note above for the same reasoning) rather
 * than overwriting with this response's own single-page result. */
export function useUpdateTagConfig(datasetId: string, column: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (config: TagConfig) => updateTagConfig(datasetId, column, config),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["tagCandidates", datasetId, column] });
    },
  });
}

/** Adding a tag chart appends to the dataset's persisted report_strategy --
 * same reasoning as onMergeSuccess above, but this endpoint doesn't return
 * the dataset's columnValues/tagCandidates, only the new chart, so there's
 * nothing to patch in place; both affected caches are just invalidated. */
export function useAddTagChart(datasetId: string, column: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (title?: string) => addTagChart(datasetId, column, title),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["datasetSchema", datasetId] });
      queryClient.invalidateQueries({ queryKey: ["reportStrategy", datasetId] });
    },
  });
}
