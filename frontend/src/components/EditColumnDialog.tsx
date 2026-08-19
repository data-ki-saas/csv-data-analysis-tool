"use client";

import { useEffect, useState } from "react";
import { createPortal } from "react-dom";
import { ColumnInfo, ReplacementRule, TagConfig, ValueMergeRule } from "@/lib/api";
import { cn } from "@/lib/utils";
import {
  useAcceptValueMerge,
  useAcceptValueReplacement,
  useAddTagChart,
  useColumnValues,
  useRevertValueMerge,
  useRevertValueReplacement,
  useSuggestValueMerge,
  useTagCandidates,
  useUpdateColumn,
  useUpdateTagConfig,
} from "@/hooks/useDatasetSchema";
import { CloseIcon, IconButton } from "@/components/IconButton";

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
  const values = useColumnValues(datasetId, column.name, canEditValues);
  const updateColumn = useUpdateColumn(datasetId);
  const suggest = useSuggestValueMerge(datasetId, column.name);
  const acceptMerge = useAcceptValueMerge(datasetId, column.name);
  const acceptReplacement = useAcceptValueReplacement(datasetId, column.name);
  const revertMerge = useRevertValueMerge(datasetId, column.name);
  const revertReplacement = useRevertValueReplacement(datasetId, column.name);

  const [aliasValue, setAliasValue] = useState(column.alias);
  const [command, setCommand] = useState("");
  const [lastRowsUpdated, setLastRowsUpdated] = useState<number | null>(null);
  const [activeTab, setActiveTab] = useState<"edit" | "rules" | "tags">("edit");

  const tagCandidates = useTagCandidates(datasetId, column.name, activeTab === "tags" && isCategorical);
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
      const { find, replace } = suggest.data.replacement;
      acceptReplacement.mutate(
        { find, replace },
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
            <div className="flex gap-1">
              {(isCategorical ? (["edit", "rules", "tags"] as const) : (["edit", "rules"] as const)).map(
                (tab) => (
                  <button
                    key={tab}
                    type="button"
                    onClick={() => setActiveTab(tab)}
                    className={cn(
                      "-mb-px border-b-2 px-3 py-1.5 text-sm capitalize",
                      activeTab === tab
                        ? "border-accent font-medium"
                        : "border-transparent opacity-60 hover:opacity-100"
                    )}
                  >
                    {tab === "edit" ? "Edit values" : tab === "rules" ? `Active rules (${ruleCount})` : "Tags"}
                  </button>
                )
              )}
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
                    Prefix separator (optional)
                    <input
                      value={tagConfig.prefix_separator ?? ""}
                      onChange={(e) => updateLocalTagConfig({ prefix_separator: e.target.value || null })}
                      placeholder={`e.g. - (strips "Hybrid - " before splitting)`}
                      className="w-64 rounded border border-border bg-surface px-2 py-1 text-sm"
                    />
                  </label>
                  <label className="flex flex-col gap-1 text-xs">
                    Tag separator
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
                  <h3 className="text-sm font-medium">
                    Vocabulary ({tagConfig.vocabulary.length} selected)
                  </h3>
                </div>
                <p className="text-xs opacity-60">
                  Check the tags that should count as their own bar in a chart -- this controls the size of
                  the resulting chart. Leave everything unchecked to count every tag found.
                </p>
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

          {activeTab === "edit" && (
            <>
              {lastRowsUpdated !== null && (
                <p className="rounded border border-accent/50 bg-accent/5 px-3 py-1.5 text-xs">
                  {lastRowsUpdated.toLocaleString()} row{lastRowsUpdated === 1 ? "" : "s"} updated.
                </p>
              )}

              <section className="flex flex-col gap-1.5">
                <h3 className="text-sm font-medium">Current values</h3>
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
              </section>

              <section className="flex flex-col gap-1.5 border-t border-border pt-4">
                <h3 className="text-sm font-medium">Ask AI to merge values, or replace text</h3>
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
