"use client";

import { useEffect, useState } from "react";
import { createPortal } from "react-dom";
import { ColumnInfo, ValueMergeRule } from "@/lib/api";
import { cn } from "@/lib/utils";
import {
  useAcceptValueMerge,
  useColumnValues,
  useRevertValueMerge,
  useSuggestValueMerge,
  useUpdateColumn,
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

function RuleRow({ rule, onRevert, disabled }: { rule: ValueMergeRule; onRevert: () => void; disabled: boolean }) {
  return (
    <div className="flex items-center justify-between gap-2 rounded border border-border px-2 py-1.5 text-sm">
      <div className="min-w-0">
        <span className="font-medium">{rule.target}</span>
        <span className="opacity-60"> ← {rule.sources.join(", ")}</span>
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

export function EditColumnDialog({
  datasetId,
  column,
  onClose,
}: {
  datasetId: string;
  column: ColumnInfo;
  onClose: () => void;
}) {
  const canMergeValues = column.category === "categorical";
  const values = useColumnValues(datasetId, column.name, canMergeValues);
  const updateColumn = useUpdateColumn(datasetId);
  const suggest = useSuggestValueMerge(datasetId, column.name);
  const accept = useAcceptValueMerge(datasetId, column.name);
  const revert = useRevertValueMerge(datasetId, column.name);

  const [aliasValue, setAliasValue] = useState(column.alias);
  const [command, setCommand] = useState("");
  const [lastRowsUpdated, setLastRowsUpdated] = useState<number | null>(null);
  const [activeTab, setActiveTab] = useState<"merge" | "rules">("merge");

  function handleRename() {
    const trimmed = aliasValue.trim();
    if (trimmed && trimmed !== column.alias) updateColumn.mutate({ column: column.name, alias: trimmed });
  }

  function handleAsk() {
    if (!command.trim() || suggest.isPending) return;
    setLastRowsUpdated(null);
    suggest.mutate(command.trim(), { onSuccess: () => setCommand("") });
  }

  function handleAccept() {
    if (!suggest.data || suggest.data.groups.length === 0) return;
    accept.mutate(suggest.data.groups, {
      onSuccess: (data) => {
        setLastRowsUpdated(data.rows_updated);
        suggest.reset();
      },
    });
  }

  const proposal = suggest.data && suggest.data.groups.length > 0 ? suggest.data : null;
  const ruleCount = values.data?.rules.length ?? 0;

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

      {!canMergeValues && (
        <p className="border-t border-border pt-4 text-xs opacity-60">
          Value merging is only available for categorical columns.
        </p>
      )}

      {canMergeValues && (
        <>
          <div className="flex gap-1 border-b border-border">
            {(["merge", "rules"] as const).map((tab) => (
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
                {tab === "merge" ? "Merge values" : `Active rules (${ruleCount})`}
              </button>
            ))}
          </div>

          {activeTab === "rules" && (
            <section className="flex flex-col gap-1.5">
              {ruleCount === 0 && <p className="text-xs opacity-60">No values merged yet.</p>}
              <div className="flex max-h-64 flex-col gap-1.5 overflow-y-auto">
                {values.data?.rules.map((rule) => (
                  <RuleRow
                    key={rule.target}
                    rule={rule}
                    disabled={revert.isPending}
                    onRevert={() => {
                      setLastRowsUpdated(null);
                      revert.mutate(rule.target);
                    }}
                  />
                ))}
              </div>
              {revert.isError && <p className="text-xs text-red-600">{(revert.error as Error).message}</p>}
            </section>
          )}

          {activeTab === "merge" && (
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
                <h3 className="text-sm font-medium">Ask AI to merge values</h3>
                <p className="text-xs opacity-60">
                  e.g. &quot;merge all values that contain NY or New York City into New York&quot;
                </p>
                <div className="flex gap-2">
                  <input
                    value={command}
                    onChange={(e) => setCommand(e.target.value)}
                    onKeyDown={(e) => e.key === "Enter" && handleAsk()}
                    placeholder="Describe the merge…"
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
                  <p className="text-xs opacity-60">
                    The AI didn&apos;t find any values to merge for that command.
                  </p>
                )}

                {proposal && (
                  <div className="flex flex-col gap-2 rounded border border-accent/50 bg-accent/5 p-3">
                    <p className="text-sm font-medium">Proposed merge</p>
                    {proposal.groups.map((g) => (
                      <p key={g.target} className="text-xs">
                        <span className="font-medium">{g.target}</span>
                        <span className="opacity-60"> ← {g.sources.join(", ")}</span>
                      </p>
                    ))}
                    <div className="mt-1 flex gap-2">
                      <button
                        type="button"
                        onClick={handleAccept}
                        disabled={accept.isPending}
                        className="rounded bg-accent px-3 py-1 text-xs text-accent-foreground disabled:opacity-50"
                      >
                        {accept.isPending ? "Applying…" : "Accept"}
                      </button>
                      <button
                        type="button"
                        onClick={() => suggest.reset()}
                        disabled={accept.isPending}
                        className="rounded border border-border px-3 py-1 text-xs disabled:opacity-50"
                      >
                        Discard
                      </button>
                    </div>
                    {accept.isError && (
                      <p className="text-xs text-red-600">{(accept.error as Error).message}</p>
                    )}
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
