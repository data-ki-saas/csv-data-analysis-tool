"use client";

import { useEffect, useState } from "react";
import { createPortal } from "react-dom";
import { ColumnInfo, RangeConfig, ReplacementRule, TagConfig, ValueMergeRule } from "@/lib/api";
import { cn } from "@/lib/utils";
import {
  useAcceptValueMerge,
  useAcceptValueReplacement,
  useAddRangeChart,
  useAddTagChart,
  useColumnValues,
  useRangePreview,
  useRevertValueMerge,
  useRevertValueReplacement,
  useSuggestValueMerge,
  useTagCandidates,
  useUpdateColumn,
  useUpdateRangeConfig,
  useUpdateTagConfig,
} from "@/hooks/useDatasetSchema";
import { CloseIcon, HelpTooltip, IconButton } from "@/components/IconButton";
import { EDIT_COLUMN_VALUES_PAGE_SIZE } from "@/lib/limits";

/** Hand-rolled modal (no existing Modal/Dialog primitive in this codebase --
 * see CLAUDE.md) -- a portal to <body> for correct stacking, a backdrop that
 * closes on click, and Escape-to-close, matching this codebase's existing
 * aversion to new deps for presentational concerns. */
function DialogShell({ onClose, children }: { onClose: () => void; children: React.ReactNode }) {
  useEffect(() => {
    function handleKey(e: KeyboardEvent) {
      if (e.key === "Escape") onClose();
    }
    document.addEventListener("keydown", handleKey);
    return () => document.removeEventListener("keydown", handleKey);
  }, [onClose]);

  if (typeof document === "undefined") return null;

  return createPortal(
    <div
      role="dialog"
      aria-modal="true"
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4"
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div className="flex max-h-[85vh] w-full max-w-2xl flex-col gap-4 overflow-y-auto rounded border border-border bg-surface p-6 shadow-xl">
        {children}
      </div>
    </div>,
    document.body
  );
}

function RowsAffectedBadge({ rows }: { rows: number | null }) {
  if (rows == null) return null;
  return (
    <span className="ml-2 shrink-0 rounded bg-border px-1.5 py-0.5 text-[10px] opacity-70">
      {rows.toLocaleString()} row{rows === 1 ? "" : "s"}
    </span>
  );
}

function MergeRuleRow({ rule, onRevert, disabled }: { rule: ValueMergeRule; onRevert: () => void; disabled: boolean }) {
  return (
    <div className="flex items-center justify-between gap-2 rounded border border-border px-2 py-1.5 text-sm">
      <div className="flex min-w-0 items-center">
        <div className="min-w-0">
          <span className="font-medium">{rule.target}</span>
          <span className="opacity-60"> ← {rule.sources.join(", ")}</span>
        </div>
        <RowsAffectedBadge rows={rule.rows_affected} />
      </div>
      <button
        type="button"
        onClick={onRevert}
        disabled={disabled}
        className="shrink-0 text-xs underline opacity-70 hover:opacity-100 disabled:opacity-30"
      >
        Revert
      </button>
    </div>
  );
}

function ReplacementRuleRow({
  rule,
  onRevert,
  disabled,
}: {
  rule: ReplacementRule;
  onRevert: () => void;
  disabled: boolean;
}) {
  return (
    <div className="flex items-center justify-between gap-2 rounded border border-border px-2 py-1.5 text-sm">
      <div className="flex min-w-0 items-center">
        <div className="min-w-0">
          <span className="font-medium">&quot;{rule.find}&quot;</span>
          <span className="opacity-60"> → &quot;{rule.replace}&quot;</span>
        </div>
        {rule.is_regex && (
          <span className="ml-2 shrink-0 rounded bg-border px-1.5 py-0.5 text-[10px] opacity-70">regex</span>
        )}
        <RowsAffectedBadge rows={rule.rows_affected} />
      </div>
      <button
        type="button"
        onClick={onRevert}
        disabled={disabled}
        className="shrink-0 text-xs underline opacity-70 hover:opacity-100 disabled:opacity-30"
      >
        Revert
      </button>
    </div>
  );
}

const DEFAULT_TAG_CONFIG: TagConfig = {
  prefix_separator: null,
  tag_separator: ",",
  vocabulary: [],
  include_other: false,
};

const DEFAULT_RANGE_CONFIG: RangeConfig = {
  separator: "-",
  unit: null,
  value_type: "midpoint",
};

const RANGE_VALUE_TYPE_OPTIONS: { value: RangeConfig["value_type"]; label: string }[] = [
  { value: "midpoint", label: "Midpoint" },
  { value: "min", label: "Minimum" },
  { value: "max", label: "Maximum" },
];

function TagCandidateRow({
  tag,
  count,
  checked,
  onToggle,
}: {
  tag: string;
  count: number;
  checked: boolean;
  onToggle: () => void;
}) {
  return (
    <label className="flex items-center justify-between gap-2 rounded border border-border px-2 py-1.5 text-sm">
      <span className="flex min-w-0 items-center gap-2">
        <input type="checkbox" checked={checked} onChange={onToggle} className="shrink-0" />
        <span className="truncate">{tag}</span>
      </span>
      <span className="shrink-0 text-xs opacity-60">{count.toLocaleString()}</span>
    </label>
  );
}

export function EditColumnDialog({
  datasetId,
  column,
  onClose,
}: {
  datasetId: string;
  column: ColumnInfo;
  onClose: () => void;
}) {
  const isCategorical = column.category === "categorical";
  const canEditValues = isCategorical || column.category === "free_text";
  const [valuesLimit, setValuesLimit] = useState(EDIT_COLUMN_VALUES_PAGE_SIZE);
  const values = useColumnValues(datasetId, column.name, canEditValues, valuesLimit);
  const updateColumn = useUpdateColumn(datasetId);
  const suggest = useSuggestValueMerge(datasetId, column.name);
  const acceptMerge = useAcceptValueMerge(datasetId, column.name);
  const acceptReplacement = useAcceptValueReplacement(datasetId, column.name);
  const revertMerge = useRevertValueMerge(datasetId, column.name);
  const revertReplacement = useRevertValueReplacement(datasetId, column.name);

  const [aliasValue, setAliasValue] = useState(column.alias);
  const [command, setCommand] = useState("");
  const [lastRowsUpdated, setLastRowsUpdated] = useState<number | null>(null);
  const [activeTab, setActiveTab] = useState<"edit" | "rules" | "tags" | "range">("edit");

  const [tagsLimit, setTagsLimit] = useState(EDIT_COLUMN_VALUES_PAGE_SIZE);
  const tagCandidates = useTagCandidates(
    datasetId,
    column.name,
    activeTab === "tags" && isCategorical,
    tagsLimit
  );
  const updateTagConfig = useUpdateTagConfig(datasetId, column.name);
  const addTagChart = useAddTagChart(datasetId, column.name);
  // null = "no local edits yet, defer to the query result" -- same
  // local-state-forks-from-query pattern as AliasEditor/notes elsewhere in
  // this codebase. Once touched, this is the only source of truth for the
  // form until Save persists it (after which it already matches the query).
  const [localTagConfig, setLocalTagConfig] = useState<TagConfig | null>(null);
  const [tagChartTitle, setTagChartTitle] = useState("");
  const [tagChartAdded, setTagChartAdded] = useState(false);

  const tagConfig = localTagConfig ?? tagCandidates.data?.config ?? DEFAULT_TAG_CONFIG;

  function updateLocalTagConfig(patch: Partial<TagConfig>) {
    setLocalTagConfig({ ...tagConfig, ...patch });
  }

  function toggleVocabularyTag(tag: string) {
    const vocabulary = tagConfig.vocabulary.includes(tag)
      ? tagConfig.vocabulary.filter((t) => t !== tag)
      : [...tagConfig.vocabulary, tag];
    updateLocalTagConfig({ vocabulary });
  }

  function handleSaveTagConfig() {
    updateTagConfig.mutate(tagConfig);
  }

  function handleAddTagChart() {
    setTagChartAdded(false);
    addTagChart.mutate(tagChartTitle.trim() || undefined, { onSuccess: () => setTagChartAdded(true) });
  }

  const rangePreview = useRangePreview(datasetId, column.name, activeTab === "range" && canEditValues);
  const updateRangeConfig = useUpdateRangeConfig(datasetId, column.name);
  const addRangeChart = useAddRangeChart(datasetId, column.name);
  const [localRangeConfig, setLocalRangeConfig] = useState<RangeConfig | null>(null);
  const [rangeChartTitle, setRangeChartTitle] = useState("");
  const [rangeChartAdded, setRangeChartAdded] = useState(false);

  const rangeConfig = localRangeConfig ?? rangePreview.data?.config ?? DEFAULT_RANGE_CONFIG;

  function updateLocalRangeConfig(patch: Partial<RangeConfig>) {
    setLocalRangeConfig({ ...rangeConfig, ...patch });
  }

  function handleSaveRangeConfig() {
    updateRangeConfig.mutate(rangeConfig);
  }

  function handleAddRangeChart() {
    setRangeChartAdded(false);
    addRangeChart.mutate(rangeChartTitle.trim() || undefined, { onSuccess: () => setRangeChartAdded(true) });
  }

  function handleRename() {
    const trimmed = aliasValue.trim();
    if (trimmed && trimmed !== column.alias) updateColumn.mutate({ column: column.name, alias: trimmed });
  }

  function handleAsk() {
    if (!command.trim() || suggest.isPending) return;
    setLastRowsUpdated(null);
    suggest.mutate(command.trim(), { onSuccess: () => setCommand("") });
  }

  function clearProposal() {
    suggest.reset();
  }

  function handleAccept() {
    if (!suggest.data) return;
    if (suggest.data.kind === "merge") {
      if (suggest.data.groups.length === 0) return;
      acceptMerge.mutate(suggest.data.groups, {
        onSuccess: (data) => {
          setLastRowsUpdated(data.rows_updated);
          clearProposal();
        },
      });
    } else if (suggest.data.replacement) {
      const { find, replace, is_regex } = suggest.data.replacement;
      acceptReplacement.mutate(
        { find, replace, isRegex: is_regex },
        {
          onSuccess: (data) => {
            setLastRowsUpdated(data.rows_updated);
            clearProposal();
          },
        }
      );
    }
  }

  const proposal =
    suggest.data && (suggest.data.kind === "replace" || suggest.data.groups.length > 0) ? suggest.data : null;
  const isAccepting = acceptMerge.isPending || acceptReplacement.isPending;
  const acceptErrorMessage = ((acceptMerge.error ?? acceptReplacement.error) as Error | null)?.message;

  const mergeRuleCount = values.data?.rules.length ?? 0;
  const replacementRuleCount = values.data?.replacements.length ?? 0;
  const ruleCount = mergeRuleCount + replacementRuleCount;

  return (
    <DialogShell onClose={onClose}>
      <div className="flex items-start justify-between gap-4">
        <div className="min-w-0">
          <h2 className="text-lg font-semibold">Edit column</h2>
          <p className="truncate text-xs opacity-60">{column.name}</p>
        </div>
        <IconButton label="Close" onClick={onClose}>
          <CloseIcon />
        </IconButton>
      </div>

      <section className="flex flex-col gap-1.5">
        <label className="text-sm font-medium" htmlFor="edit-column-alias">
          Display name
        </label>
        <div className="flex gap-2">
          <input
            id="edit-column-alias"
            value={aliasValue}
            onChange={(e) => setAliasValue(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && handleRename()}
            className="w-full rounded border border-border bg-surface px-2 py-1 text-sm"
          />
          <button
            type="button"
            onClick={handleRename}
            disabled={updateColumn.isPending || aliasValue.trim() === column.alias}
            className="shrink-0 rounded border border-border px-3 py-1 text-sm disabled:opacity-50"
          >
            Save
          </button>
        </div>
        {updateColumn.isError && (
          <p className="text-xs text-red-600">{(updateColumn.error as Error).message}</p>
        )}
      </section>

      {!canEditValues && (
        <p className="border-t border-border pt-4 text-xs opacity-60">
          Value editing is only available for categorical or free-text columns.
        </p>
      )}

      {canEditValues && (
        <>
          <div className="flex items-center justify-between gap-4 border-b border-border">
            <div className="flex flex-wrap gap-1">
              {[
                "edit",
                "rules",
                ...(isCategorical ? (["tags"] as const) : []),
                "range",
              ].map((tab) => (
                <button
                  key={tab}
                  type="button"
                  onClick={() => setActiveTab(tab as typeof activeTab)}
                  className={cn(
                    "-mb-px border-b-2 px-3 py-1.5 text-sm capitalize",
                    activeTab === tab
                      ? "border-accent font-medium"
                      : "border-transparent opacity-60 hover:opacity-100"
                  )}
                >
                  {tab === "edit"
                    ? "Edit values"
                    : tab === "rules"
                      ? `Active rules (${ruleCount})`
                      : tab === "tags"
                        ? "Tags"
                        : "Range"}
                </button>
              ))}
            </div>
            {isCategorical && values.data && (
              <span className="shrink-0 pb-1.5 text-xs opacity-60">
                {values.data.distinct_count.toLocaleString()} categories
              </span>
            )}
          </div>

          {activeTab === "rules" && (
            <section className="flex flex-col gap-1.5">
              {ruleCount === 0 && <p className="text-xs opacity-60">No values edited yet.</p>}
              <div className="flex max-h-64 flex-col gap-1.5 overflow-y-auto">
                {values.data?.rules.map((rule) => (
                  <MergeRuleRow
                    key={`merge-${rule.target}`}
                    rule={rule}
                    disabled={revertMerge.isPending}
                    onRevert={() => {
                      setLastRowsUpdated(null);
                      revertMerge.mutate(rule.target);
                    }}
                  />
                ))}
                {values.data?.replacements.map((rule) => (
                  <ReplacementRuleRow
                    key={`replace-${rule.find}`}
                    rule={rule}
                    disabled={revertReplacement.isPending}
                    onRevert={() => {
                      setLastRowsUpdated(null);
                      revertReplacement.mutate(rule.find);
                    }}
                  />
                ))}
              </div>
              {(revertMerge.isError || revertReplacement.isError) && (
                <p className="text-xs text-red-600">
                  {((revertMerge.error ?? revertReplacement.error) as Error).message}
                </p>
              )}
            </section>
          )}

          {activeTab === "tags" && (
            <>
              <section className="flex flex-col gap-1.5">
                <h3 className="text-sm font-medium">Split cells into tags</h3>
                <p className="text-xs opacity-60">
                  {column.multi_value_separator
                    ? `This column's cells look like they pack several values together, separated by "${column.multi_value_separator}".`
                    : "Configure how this column's cells should be split into individual tags."}
                </p>
                <div className="flex flex-wrap gap-3">
                  <label className="flex flex-col gap-1 text-xs">
                    <span className="flex items-center gap-1">
                      Prefix separator (optional)
                      <HelpTooltip label="Prefix separator help">
                        Splits off a leading label before extracting tags. e.g. &quot;-&quot; turns &quot;Hybrid
                        - Pune, Noida&quot; into tags &quot;Pune&quot; and &quot;Noida&quot; -- the
                        &quot;Hybrid&quot; part is dropped.
                      </HelpTooltip>
                    </span>
                    <input
                      value={tagConfig.prefix_separator ?? ""}
                      onChange={(e) => updateLocalTagConfig({ prefix_separator: e.target.value || null })}
                      placeholder={`Just the marker, e.g. "-" (splits "Hybrid - Pune" into "Hybrid" + "Pune")`}
                      className="w-64 rounded border border-border bg-surface px-2 py-1 text-sm"
                    />
                  </label>
                  <label className="flex flex-col gap-1 text-xs">
                    <span className="flex items-center gap-1">
                      Tag separator
                      <HelpTooltip label="Tag separator help">
                        The character that separates multiple tags within one cell. Usually a comma --
                        change it if your data uses &quot;;&quot; or &quot;/&quot; instead.
                      </HelpTooltip>
                    </span>
                    <input
                      value={tagConfig.tag_separator}
                      onChange={(e) => updateLocalTagConfig({ tag_separator: e.target.value || "," })}
                      className="w-24 rounded border border-border bg-surface px-2 py-1 text-sm"
                    />
                  </label>
                </div>
              </section>

              <section className="flex flex-col gap-1.5">
                <div className="flex items-center justify-between">
                  <h3 className="flex items-center gap-1 text-sm font-medium">
                    Vocabulary ({tagConfig.vocabulary.length} selected)
                    <HelpTooltip label="Vocabulary help">
                      Check the tags that should get their own bar in a chart -- this controls how many bars
                      the chart has. Leave everything unchecked to count every tag found.
                    </HelpTooltip>
                  </h3>
                </div>
                {tagCandidates.data && (
                  <p className="text-xs opacity-60">
                    Showing {tagCandidates.data.candidates.length.toLocaleString()} of{" "}
                    {tagCandidates.data.total_tags.toLocaleString()} tags
                  </p>
                )}
                {tagCandidates.isLoading && <p className="text-xs opacity-60">Loading…</p>}
                {tagCandidates.isError && (
                  <p className="text-xs text-red-600">{(tagCandidates.error as Error).message}</p>
                )}
                <div className="flex max-h-56 flex-col gap-1.5 overflow-y-auto">
                  {tagCandidates.data?.candidates.map((c) => (
                    <TagCandidateRow
                      key={c.tag}
                      tag={c.tag}
                      count={c.count}
                      checked={tagConfig.vocabulary.includes(c.tag)}
                      onToggle={() => toggleVocabularyTag(c.tag)}
                    />
                  ))}
                </div>
                {tagCandidates.data && tagCandidates.data.candidates.length < tagCandidates.data.total_tags && (
                  <button
                    type="button"
                    onClick={() => setTagsLimit((l) => l + EDIT_COLUMN_VALUES_PAGE_SIZE)}
                    disabled={tagCandidates.isFetching}
                    className="self-start text-xs underline opacity-70 hover:opacity-100 disabled:opacity-30"
                  >
                    {tagCandidates.isFetching ? "Loading…" : "Load more"}
                  </button>
                )}
                <label className="flex items-center gap-2 text-xs">
                  <input
                    type="checkbox"
                    checked={tagConfig.include_other}
                    onChange={(e) => updateLocalTagConfig({ include_other: e.target.checked })}
                    disabled={tagConfig.vocabulary.length === 0}
                  />
                  Include an &quot;Other&quot; bucket for tags not in the vocabulary
                </label>
                <div>
                  <button
                    type="button"
                    onClick={handleSaveTagConfig}
                    disabled={updateTagConfig.isPending}
                    className="rounded bg-accent px-3 py-1 text-xs text-accent-foreground disabled:opacity-50"
                  >
                    {updateTagConfig.isPending ? "Saving…" : "Save configuration"}
                  </button>
                </div>
                {updateTagConfig.isError && (
                  <p className="text-xs text-red-600">{(updateTagConfig.error as Error).message}</p>
                )}
              </section>

              <section className="flex flex-col gap-1.5 border-t border-border pt-4">
                <h3 className="text-sm font-medium">Add to Visual Reports</h3>
                <p className="text-xs opacity-60">
                  Adds a &quot;count of rows per tag&quot; chart using the saved configuration above -- one
                  packed cell can count toward more than one bar.
                </p>
                <div className="flex gap-2">
                  <input
                    value={tagChartTitle}
                    onChange={(e) => setTagChartTitle(e.target.value)}
                    placeholder={`${column.alias} by tag`}
                    className="w-full rounded border border-border bg-surface px-2 py-1 text-sm"
                  />
                  <button
                    type="button"
                    onClick={handleAddTagChart}
                    disabled={addTagChart.isPending}
                    className="shrink-0 rounded bg-accent px-3 py-1 text-sm text-accent-foreground disabled:opacity-50"
                  >
                    {addTagChart.isPending ? "Adding…" : "Add chart"}
                  </button>
                </div>
                {tagChartAdded && (
                  <p className="text-xs opacity-70">Chart added -- view it on the Visual Reports page.</p>
                )}
                {addTagChart.isError && (
                  <p className="text-xs text-red-600">{(addTagChart.error as Error).message}</p>
                )}
              </section>
            </>
          )}

          {activeTab === "range" && (
            <>
              <section className="flex flex-col gap-1.5">
                <h3 className="flex items-center gap-1 text-sm font-medium">
                  Parse cells into a number
                  <HelpTooltip label="Range parsing help">
                    Splits a cell like &quot;4-10 yrs&quot; into two numbers and picks one representative
                    value per row -- the midpoint (the average of the two), or just the minimum or maximum.
                    That value is then chartable as a normal numeric distribution.
                  </HelpTooltip>
                </h3>
                <p className="text-xs opacity-60">
                  {column.range_separator
                    ? `This column's cells look like a numeric range, e.g. "min${column.range_separator}max${
                        column.range_unit ? ` ${column.range_unit}` : ""
                      }".`
                    : "Configure how this column's cells should be parsed as a numeric range."}
                </p>
                <div className="flex flex-wrap gap-3">
                  <label className="flex flex-col gap-1 text-xs">
                    Separator
                    <input
                      value={rangeConfig.separator}
                      onChange={(e) => updateLocalRangeConfig({ separator: e.target.value || "-" })}
                      className="w-16 rounded border border-border bg-surface px-2 py-1 text-sm"
                    />
                  </label>
                  <label className="flex flex-col gap-1 text-xs">
                    Unit (optional)
                    <input
                      value={rangeConfig.unit ?? ""}
                      onChange={(e) => updateLocalRangeConfig({ unit: e.target.value || null })}
                      placeholder='e.g. "yrs"'
                      className="w-32 rounded border border-border bg-surface px-2 py-1 text-sm"
                    />
                  </label>
                  <label className="flex flex-col gap-1 text-xs">
                    Value
                    <select
                      value={rangeConfig.value_type}
                      onChange={(e) =>
                        updateLocalRangeConfig({ value_type: e.target.value as RangeConfig["value_type"] })
                      }
                      className="rounded border border-border bg-surface px-2 py-1 text-sm"
                    >
                      {RANGE_VALUE_TYPE_OPTIONS.map((opt) => (
                        <option key={opt.value} value={opt.value}>
                          {opt.label}
                        </option>
                      ))}
                    </select>
                  </label>
                </div>
              </section>

              <section className="flex flex-col gap-1.5">
                <h3 className="text-sm font-medium">Preview</h3>
                {rangePreview.data && (
                  <p className="text-xs opacity-60">
                    {rangePreview.data.parsed_count.toLocaleString()} of{" "}
                    {rangePreview.data.total_count.toLocaleString()} rows parsed
                  </p>
                )}
                {rangePreview.isLoading && <p className="text-xs opacity-60">Loading…</p>}
                {rangePreview.isError && (
                  <p className="text-xs text-red-600">{(rangePreview.error as Error).message}</p>
                )}
                <div className="max-h-40 overflow-y-auto rounded border border-border">
                  <table className="min-w-full text-left text-xs">
                    <tbody>
                      {rangePreview.data?.sample.map((row, i) => (
                        <tr key={i} className="border-b border-border last:border-b-0">
                          <td className="px-2 py-1">{row.raw_value}</td>
                          <td className="px-2 py-1 text-right opacity-60">
                            {row.parsed_value === null ? (
                              <span className="italic">unparsed</span>
                            ) : (
                              row.parsed_value.toLocaleString()
                            )}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                <div>
                  <button
                    type="button"
                    onClick={handleSaveRangeConfig}
                    disabled={updateRangeConfig.isPending}
                    className="rounded bg-accent px-3 py-1 text-xs text-accent-foreground disabled:opacity-50"
                  >
                    {updateRangeConfig.isPending ? "Saving…" : "Save configuration"}
                  </button>
                </div>
                {updateRangeConfig.isError && (
                  <p className="text-xs text-red-600">{(updateRangeConfig.error as Error).message}</p>
                )}
              </section>

              <section className="flex flex-col gap-1.5 border-t border-border pt-4">
                <h3 className="text-sm font-medium">Add to Visual Reports</h3>
                <p className="text-xs opacity-60">
                  Adds a distribution chart using the saved configuration above.
                </p>
                <div className="flex gap-2">
                  <input
                    value={rangeChartTitle}
                    onChange={(e) => setRangeChartTitle(e.target.value)}
                    placeholder={`${column.alias} distribution`}
                    className="w-full rounded border border-border bg-surface px-2 py-1 text-sm"
                  />
                  <button
                    type="button"
                    onClick={handleAddRangeChart}
                    disabled={addRangeChart.isPending}
                    className="shrink-0 rounded bg-accent px-3 py-1 text-sm text-accent-foreground disabled:opacity-50"
                  >
                    {addRangeChart.isPending ? "Adding…" : "Add chart"}
                  </button>
                </div>
                {rangeChartAdded && (
                  <p className="text-xs opacity-70">Chart added -- view it on the Visual Reports page.</p>
                )}
                {addRangeChart.isError && (
                  <p className="text-xs text-red-600">{(addRangeChart.error as Error).message}</p>
                )}
              </section>
            </>
          )}

          {activeTab === "edit" && (
            <>
              {lastRowsUpdated !== null && (
                <p className="rounded border border-accent/50 bg-accent/5 px-3 py-1.5 text-xs">
                  {lastRowsUpdated.toLocaleString()} row{lastRowsUpdated === 1 ? "" : "s"} updated.
                </p>
              )}

              <section className="flex flex-col gap-1.5">
                <h3 className="text-sm font-medium">
                  Current values
                  {values.data && (
                    <span className="ml-1 font-normal opacity-60">
                      ({values.data.values.length.toLocaleString()} of{" "}
                      {values.data.distinct_count.toLocaleString()})
                    </span>
                  )}
                </h3>
                {values.isLoading && <p className="text-xs opacity-60">Loading…</p>}
                {values.isError && (
                  <p className="text-xs text-red-600">{(values.error as Error).message}</p>
                )}
                <div className="max-h-40 overflow-y-auto rounded border border-border">
                  <table className="min-w-full text-left text-xs">
                    <tbody>
                      {values.data?.values.map((v) => (
                        <tr key={v.value} className="border-b border-border last:border-b-0">
                          <td className="px-2 py-1">{v.value}</td>
                          <td className="px-2 py-1 text-right opacity-60">{v.count.toLocaleString()}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                {values.data && values.data.values.length < values.data.distinct_count && (
                  <button
                    type="button"
                    onClick={() => setValuesLimit((l) => l + EDIT_COLUMN_VALUES_PAGE_SIZE)}
                    disabled={values.isFetching}
                    className="self-start text-xs underline opacity-70 hover:opacity-100 disabled:opacity-30"
                  >
                    {values.isFetching ? "Loading…" : "Load more"}
                  </button>
                )}
              </section>

              <section className="flex flex-col gap-1.5 border-t border-border pt-4">
                <h3 className="flex items-center gap-1 text-sm font-medium">
                  Ask AI to merge values, or replace text
                  <HelpTooltip label="Command syntax help">
                    Two kinds of command:
                    <br />• Merge (AI-judged): &quot;merge NY and New York into New York&quot;
                    <br />• Replace (literal): Replace &apos;X&apos; with &apos;Y&apos;
                    <br />
                    Each acts on the column&apos;s current values.
                  </HelpTooltip>
                  <HelpTooltip label="Regex replace guide">
                    For pattern-based replacing:
                    <br />
                    <code>Replace regex &apos;PATTERN&apos; with &apos;TEXT&apos;</code>
                    <br />
                    <code>.</code> any character, <code>.*</code> any sequence
                    <br />
                    <code>\( \)</code> literal parentheses
                    <br />
                    <code>^ $</code> start / end, <code>|</code> or
                    <br />
                    e.g. <code>Kolkata\(.*\)</code> → <code>Kolkata</code>
                  </HelpTooltip>
                </h3>
                <p className="text-xs opacity-60">
                  e.g. &quot;merge all values that contain NY or New York City into New York&quot;, or a literal{" "}
                  <code>Replace &apos;Delhi / NCR&apos; with &apos;Delhi&apos;</code>
                </p>
                <div className="flex gap-2">
                  <input
                    value={command}
                    onChange={(e) => setCommand(e.target.value)}
                    onKeyDown={(e) => e.key === "Enter" && handleAsk()}
                    placeholder="Describe the edit…"
                    className="w-full rounded border border-border bg-surface px-2 py-1 text-sm"
                  />
                  <button
                    type="button"
                    onClick={handleAsk}
                    disabled={suggest.isPending || !command.trim()}
                    className="shrink-0 rounded bg-accent px-3 py-1 text-sm text-accent-foreground disabled:opacity-50"
                  >
                    {suggest.isPending ? "Asking…" : "Ask"}
                  </button>
                </div>
                {suggest.isError && (
                  <p className="text-xs text-red-600">{(suggest.error as Error).message}</p>
                )}
                {suggest.isSuccess && !proposal && (
                  <p className="text-xs opacity-60">The AI didn&apos;t find any values to change for that command.</p>
                )}

                {proposal && (
                  <div className="flex flex-col gap-2 rounded border border-accent/50 bg-accent/5 p-3">
                    <p className="text-sm font-medium">
                      {proposal.kind === "merge" ? "Proposed merge" : "Proposed replacement"}
                    </p>
                    {proposal.kind === "merge" &&
                      proposal.groups.map((g) => (
                        <p key={g.target} className="text-xs">
                          <span className="font-medium">{g.target}</span>
                          <span className="opacity-60"> ← {g.sources.join(", ")}</span>
                        </p>
                      ))}
                    {proposal.kind === "replace" && proposal.replacement && (
                      <p className="text-xs">
                        <span className="font-medium">&quot;{proposal.replacement.find}&quot;</span>
                        <span className="opacity-60"> → &quot;{proposal.replacement.replace}&quot;</span>
                        {proposal.replacement.is_regex && (
                          <span className="ml-2 rounded bg-border px-1.5 py-0.5 text-[10px] opacity-70">
                            regex
                          </span>
                        )}
                      </p>
                    )}
                    {isCategorical && values.data && (
                      <p className="text-xs opacity-60">
                        {values.data.distinct_count.toLocaleString()} → {proposal.preview_distinct_count.toLocaleString()}{" "}
                        categories
                      </p>
                    )}
                    <div className="mt-1 flex gap-2">
                      <button
                        type="button"
                        onClick={handleAccept}
                        disabled={isAccepting}
                        className="rounded bg-accent px-3 py-1 text-xs text-accent-foreground disabled:opacity-50"
                      >
                        {isAccepting ? "Applying…" : "Accept"}
                      </button>
                      <button
                        type="button"
                        onClick={clearProposal}
                        disabled={isAccepting}
                        className="rounded border border-border px-3 py-1 text-xs disabled:opacity-50"
                      >
                        Discard
                      </button>
                    </div>
                    {acceptErrorMessage && <p className="text-xs text-red-600">{acceptErrorMessage}</p>}
                  </div>
                )}
              </section>
            </>
          )}
        </>
      )}
    </DialogShell>
  );
}
