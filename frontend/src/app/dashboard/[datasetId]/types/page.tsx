"use client";

import { useParams } from "next/navigation";
import { useState } from "react";
import { ColumnCategory, ColumnInfo } from "@/lib/api";
import { useDatasetSchema, useReviewColumnTypes, useUpdateColumn } from "@/hooks/useDatasetSchema";
import { cn } from "@/lib/utils";

const CATEGORY_OPTIONS: { value: ColumnCategory; label: string }[] = [
  { value: "datetime", label: "Datetime" },
  { value: "continuous_numerical", label: "Continuous Numerical" },
  { value: "categorical", label: "Categorical" },
  { value: "free_text", label: "Free Text" },
];

function sampleValues(preview: { columns: string[]; rows: unknown[][] }, column: string, max = 3): string[] {
  const index = preview.columns.indexOf(column);
  if (index === -1) return [];
  const seen: string[] = [];
  for (const row of preview.rows) {
    const value = row[index];
    if (value === null || value === undefined) continue;
    const text = String(value);
    if (!seen.includes(text)) seen.push(text);
    if (seen.length >= max) break;
  }
  return seen;
}

function AliasEditor({
  column,
  onSave,
  disabled,
}: {
  column: ColumnInfo;
  onSave: (alias: string) => void;
  disabled: boolean;
}) {
  const [editing, setEditing] = useState(false);
  // No effect syncing this from column.alias on change: only this editor
  // ever changes an alias, and it already sets `value` to the saved alias
  // at commit time -- there's no external-update case to reconcile.
  const [value, setValue] = useState(column.alias);

  function commit() {
    setEditing(false);
    const trimmed = value.trim();
    if (trimmed && trimmed !== column.alias) onSave(trimmed);
    else setValue(column.alias);
  }

  if (!editing) {
    return (
      <button
        type="button"
        onClick={() => setEditing(true)}
        title="Click to rename this column"
        className="text-left font-medium underline decoration-dotted underline-offset-2"
      >
        {column.alias}
      </button>
    );
  }

  return (
    <input
      autoFocus
      value={value}
      disabled={disabled}
      onChange={(e) => setValue(e.target.value)}
      onBlur={commit}
      onKeyDown={(e) => {
        if (e.key === "Enter") {
          e.preventDefault();
          commit();
        }
        if (e.key === "Escape") {
          setValue(column.alias);
          setEditing(false);
        }
      }}
      className="w-full rounded border border-border bg-surface px-1 py-0.5 font-medium"
    />
  );
}

export default function ColumnTypesPage() {
  const { datasetId } = useParams<{ datasetId: string }>();

  const schema = useDatasetSchema(datasetId);
  const review = useReviewColumnTypes(datasetId);
  const updateColumn = useUpdateColumn(datasetId);

  const data = schema.data;
  const flagged = data?.columns.filter((col) => col.needs_review) ?? [];

  function handleReviewColumn(column: ColumnInfo) {
    review.mutate([column.name]);
  }

  return (
    <main className="mx-auto flex w-full max-w-4xl flex-col gap-6 px-4 py-12">
      <h1 className="text-2xl font-semibold">Column Types</h1>

      {schema.isLoading && <p className="text-sm opacity-70">Loading…</p>}
      {schema.isError && (
        <p className="text-sm text-red-600">Couldn&apos;t load this dataset&apos;s schema.</p>
      )}

      {data && (
        <>
          <div className="flex flex-wrap items-center justify-between gap-3 rounded border border-border p-4">
            <div>
              <p className="font-medium">{data.filename}</p>
              <p className="text-sm opacity-70">
                {data.row_count.toLocaleString()} rows · Health score {data.health_score}%
                {flagged.length > 0 &&
                  ` · ${flagged.length} column${flagged.length === 1 ? "" : "s"} flagged for review`}
              </p>
            </div>
            <button
              type="button"
              onClick={() => review.mutate(undefined)}
              disabled={review.isPending || flagged.length === 0}
              className="rounded bg-accent px-4 py-2 text-sm text-accent-foreground disabled:opacity-50"
            >
              {review.isPending ? "Asking AI…" : "Ask AI to review flagged columns"}
            </button>
          </div>

          {review.isError && (
            <p className="text-sm text-red-600">AI review failed: {(review.error as Error).message}</p>
          )}
          {updateColumn.isError && (
            <p className="text-sm text-red-600">
              Couldn&apos;t save that change: {(updateColumn.error as Error).message}
            </p>
          )}

          <section className="flex flex-col gap-3">
            <h2 className="text-lg font-medium">Columns</h2>
            <div className="overflow-x-auto rounded border border-border">
              <table className="min-w-full text-left text-sm">
                <thead>
                  <tr className="border-b border-border">
                    <th className="px-3 py-2 font-medium">Column</th>
                    <th className="px-3 py-2 font-medium">Sample values</th>
                    <th className="px-3 py-2 font-medium">Category</th>
                    <th className="px-3 py-2 font-medium">Confidence</th>
                    <th className="px-3 py-2 font-medium">Source</th>
                    <th className="px-3 py-2 font-medium">Nulls</th>
                  </tr>
                </thead>
                <tbody>
                  {data.columns.map((col) => (
                    <tr
                      key={col.name}
                      className={cn("border-b border-border align-top", col.needs_review && "bg-accent/10")}
                    >
                      <td className="px-3 py-2">
                        <AliasEditor
                          column={col}
                          disabled={updateColumn.isPending}
                          onSave={(alias) => updateColumn.mutate({ column: col.name, alias })}
                        />
                        <div className="text-xs opacity-60">{col.name}</div>
                      </td>
                      <td className="px-3 py-2 text-xs opacity-70">
                        {sampleValues(data.preview, col.name).join(", ") || "—"}
                      </td>
                      <td className="px-3 py-2">
                        <select
                          value={col.category}
                          onChange={(e) =>
                            updateColumn.mutate({
                              column: col.name,
                              category: e.target.value as ColumnCategory,
                            })
                          }
                          className="rounded border border-border bg-surface px-2 py-1"
                        >
                          {CATEGORY_OPTIONS.map((opt) => (
                            <option key={opt.value} value={opt.value}>
                              {opt.label}
                            </option>
                          ))}
                        </select>
                        {col.rationale && <p className="mt-1 max-w-xs text-xs opacity-60">{col.rationale}</p>}
                        {col.needs_review && (
                          <button
                            type="button"
                            onClick={() => handleReviewColumn(col)}
                            disabled={review.isPending}
                            className="mt-1 block text-xs underline disabled:opacity-50"
                          >
                            Ask AI about this column
                          </button>
                        )}
                      </td>
                      <td className="px-3 py-2">
                        {col.needs_review && (
                          <span className="mr-1 rounded bg-accent px-1.5 py-0.5 text-xs text-accent-foreground">
                            Review
                          </span>
                        )}
                        {col.confidence}%
                      </td>
                      <td className="px-3 py-2 capitalize">{col.category_source}</td>
                      <td className="px-3 py-2">
                        {col.null_percentage}%
                        {col.conversion_warning && (
                          <p className="mt-1 max-w-xs text-xs text-amber-600 dark:text-amber-400">
                            {col.conversion_warning}
                          </p>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>

          <section className="flex flex-col gap-3">
            <h2 className="text-lg font-medium">Cleaned data preview</h2>
            <p className="text-xs opacity-60">
              Nulls normalized and dates reformatted at upload time — this is what queries and charts see, not
              the raw CSV.
            </p>
            <div className="overflow-x-auto rounded border border-border">
              <table className="min-w-full text-left text-sm">
                <thead>
                  <tr className="border-b border-border">
                    {data.preview.columns.map((columnName) => {
                      const column = data.columns.find((c) => c.name === columnName);
                      return (
                        <th key={columnName} className="whitespace-nowrap px-3 py-2 font-medium">
                          <div>{column?.alias ?? columnName}</div>
                          <div className="text-xs font-normal opacity-60">{columnName}</div>
                        </th>
                      );
                    })}
                  </tr>
                </thead>
                <tbody>
                  {data.preview.rows.map((row, i) => (
                    <tr key={i} className="border-b border-border">
                      {row.map((cell, j) => (
                        <td key={j} className="whitespace-nowrap px-3 py-2">
                          {cell === null || cell === undefined ? (
                            <span className="opacity-40">null</span>
                          ) : (
                            String(cell)
                          )}
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>
        </>
      )}
    </main>
  );
}
