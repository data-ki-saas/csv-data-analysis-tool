"use client";

import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import { ChartCard } from "@/components/charts/ChartCard";
import { useDatasetSchema } from "@/hooks/useDatasetSchema";
import { useUpdateDataset } from "@/hooks/useDatasets";
import {
  useAddCustomChart,
  useDeleteChart,
  useReorderCharts,
  useReportStrategy,
  useReportStrategyData,
} from "@/hooks/useReportStrategy";
import type { ChartFilter } from "@/lib/chartQueries";

function NameEditor({
  name,
  onSave,
  disabled,
}: {
  name: string;
  onSave: (name: string) => void;
  disabled: boolean;
}) {
  const [editing, setEditing] = useState(false);
  const [value, setValue] = useState(name);

  function commit() {
    setEditing(false);
    const trimmed = value.trim();
    if (trimmed && trimmed !== name) onSave(trimmed);
    else setValue(name);
  }

  if (!editing) {
    return (
      <button
        type="button"
        onClick={() => setEditing(true)}
        title="Click to rename"
        className="break-words text-left font-semibold underline decoration-dotted underline-offset-2"
      >
        {name}
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
          setValue(name);
          setEditing(false);
        }
      }}
      className="w-full rounded border border-border bg-surface px-1 py-0.5 font-semibold"
    />
  );
}

function DescriptionEditor({
  description,
  onSave,
  disabled,
}: {
  description: string | null;
  onSave: (description: string) => void;
  disabled: boolean;
}) {
  const [editing, setEditing] = useState(false);
  const [value, setValue] = useState(description ?? "");

  function commit() {
    setEditing(false);
    const trimmed = value.trim();
    if (trimmed !== (description ?? "")) onSave(trimmed);
  }

  if (editing) {
    return (
      <input
        autoFocus
        value={value}
        disabled={disabled}
        maxLength={200}
        onChange={(e) => setValue(e.target.value)}
        onBlur={commit}
        onKeyDown={(e) => {
          if (e.key === "Enter") {
            e.preventDefault();
            commit();
          }
          if (e.key === "Escape") {
            setValue(description ?? "");
            setEditing(false);
          }
        }}
        placeholder="Add a short description…"
        className="w-full rounded border border-border bg-surface px-1 py-0.5 text-sm italic"
      />
    );
  }

  return (
    <button
      type="button"
      onClick={() => setEditing(true)}
      title="Click to edit description"
      className="text-left text-sm italic opacity-80 hover:opacity-100"
    >
      {description || <span className="opacity-60">Add a short description…</span>}
    </button>
  );
}

export default function ReportsPage() {
  const { datasetId } = useParams<{ datasetId: string }>();

  const schema = useDatasetSchema(datasetId);
  const strategy = useReportStrategy(datasetId);
  const strategyData = useReportStrategyData(datasetId);
  const addCustomChart = useAddCustomChart(datasetId);
  const deleteChart = useDeleteChart(datasetId);
  const reorderCharts = useReorderCharts(datasetId);
  const updateDataset = useUpdateDataset();
  const [filter, setFilter] = useState<ChartFilter | null>(null);
  const [customPrompt, setCustomPrompt] = useState("");

  // Reads the query cache directly (see useReportStrategyData's doc comment)
  // so a delete/reorder/custom-add/rename from any of the mutations below
  // re-renders this list immediately -- `strategy.data` only reflects
  // `strategy`'s own mutate() calls, not writes made by the others.
  const recommendations = strategyData.data?.recommendations ?? [];

  // A report already generated on a previous visit is cached server-side
  // (report_strategy on the datasets row) -- force=false below is a free
  // cache hit, no LLM call. Only auto-load when has_report_strategy says a
  // report already exists; a dataset that's never been analyzed still waits
  // for an explicit "Generate visual report" click (see useReportStrategy /
  // strategy.isIdle guard: this only ever fires once per mount).
  useEffect(() => {
    if (schema.data?.has_report_strategy && strategy.isIdle) {
      strategy.mutate(false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [schema.data?.has_report_strategy]);

  function handleAddCustomChart(e: React.FormEvent) {
    e.preventDefault();
    const prompt = customPrompt.trim();
    if (!prompt) return;
    addCustomChart.mutate(prompt, { onSuccess: () => setCustomPrompt("") });
  }

  function handleMove(index: number, direction: -1 | 1) {
    const target = index + direction;
    if (target < 0 || target >= recommendations.length) return;
    const reordered = [...recommendations];
    [reordered[index], reordered[target]] = [reordered[target], reordered[index]];
    reorderCharts.mutate(reordered.map((r) => r.id));
  }

  function handleDeleteChart(chartId: string, title: string) {
    if (window.confirm(`Delete the chart "${title}"? This can't be undone.`)) {
      deleteChart.mutate(chartId);
    }
  }

  return (
    <main className="mx-auto flex w-full max-w-5xl flex-col gap-6 px-4 py-12">
      <h1 className="text-2xl font-semibold">Visual Reports</h1>

      {schema.data && (
        <div className="flex flex-wrap items-start justify-between gap-3 rounded border border-border p-4">
          <div className="min-w-0 flex-1">
            <NameEditor
              name={schema.data.name}
              disabled={updateDataset.isPending}
              onSave={(name) => updateDataset.mutate({ datasetId, name })}
            />
            <DescriptionEditor
              description={schema.data.description}
              disabled={updateDataset.isPending}
              onSave={(description) => updateDataset.mutate({ datasetId, description })}
            />
            {schema.data.notes && (
              <p className="line-clamp-3 text-sm opacity-70">{schema.data.notes}</p>
            )}
            <p className="text-xs opacity-60">{schema.data.row_count.toLocaleString()} rows</p>
          </div>
          <button
            type="button"
            onClick={() => strategy.mutate(recommendations.length > 0)}
            disabled={strategy.isPending}
            className="rounded bg-accent px-4 py-2 text-sm text-accent-foreground disabled:opacity-50"
          >
            {strategy.isPending
              ? "Analyzing dataset…"
              : recommendations.length > 0
                ? "Regenerate report"
                : "Generate visual report"}
          </button>
        </div>
      )}

      {strategy.isError && (
        <p className="text-sm text-red-600">
          Couldn&apos;t generate a report: {(strategy.error as Error).message}
        </p>
      )}
      {updateDataset.isError && (
        <p className="text-sm text-red-600">
          Couldn&apos;t save that change: {(updateDataset.error as Error).message}
        </p>
      )}

      <form onSubmit={handleAddCustomChart} className="flex flex-wrap items-center gap-2">
        <input
          value={customPrompt}
          onChange={(e) => setCustomPrompt(e.target.value)}
          placeholder="Describe a chart, e.g. &quot;distribution of annual income city wise&quot;"
          disabled={addCustomChart.isPending}
          className="min-w-0 flex-1 rounded border border-border bg-surface px-3 py-2 text-sm"
        />
        <button
          type="submit"
          disabled={addCustomChart.isPending || !customPrompt.trim()}
          className="rounded bg-accent px-4 py-2 text-sm text-accent-foreground disabled:opacity-50"
        >
          {addCustomChart.isPending ? "Adding chart…" : "Add chart"}
        </button>
      </form>
      {addCustomChart.isError && (
        <p className="text-sm text-red-600">
          Couldn&apos;t add that chart: {(addCustomChart.error as Error).message}
        </p>
      )}
      {deleteChart.isError && (
        <p className="text-sm text-red-600">
          Couldn&apos;t delete that chart: {(deleteChart.error as Error).message}
        </p>
      )}
      {reorderCharts.isError && (
        <p className="text-sm text-red-600">
          Couldn&apos;t reorder charts: {(reorderCharts.error as Error).message}
        </p>
      )}

      {filter && (
        <div className="flex items-center gap-2 self-start rounded border border-accent bg-accent/10 px-3 py-1.5 text-sm">
          <span>Filter: {filter.label}</span>
          <button type="button" onClick={() => setFilter(null)} className="underline" aria-label="Clear filter">
            ✕
          </button>
        </div>
      )}

      {strategy.isPending && (
        <p className="py-10 text-center text-sm opacity-60">
          Asking the AI to analyze your schema and suggest charts…
        </p>
      )}

      {!strategy.isPending &&
        recommendations.length === 0 &&
        !strategy.isError &&
        strategy.isIdle &&
        schema.data &&
        !schema.data.has_report_strategy && (
          <p className="py-10 text-center text-sm opacity-60">
            No report yet — click &quot;Generate visual report&quot; to get AI-recommended charts for this dataset,
            or describe one above.
          </p>
        )}

      {!strategy.isPending && strategy.isSuccess && recommendations.length === 0 && (
        <p className="py-10 text-center text-sm opacity-60">
          Nothing chartable was found (only free-text columns, or the model returned no usable recommendations).
        </p>
      )}

      <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
        {recommendations.map((recommendation, index) => (
          <ChartCard
            key={recommendation.id}
            datasetId={datasetId}
            recommendation={recommendation}
            filter={filter}
            onFilterChange={setFilter}
            onMoveUp={() => handleMove(index, -1)}
            onMoveDown={() => handleMove(index, 1)}
            canMoveUp={index > 0}
            canMoveDown={index < recommendations.length - 1}
            onDelete={() => handleDeleteChart(recommendation.id, recommendation.title)}
            deleting={deleteChart.isPending && deleteChart.variables === recommendation.id}
          />
        ))}
      </div>
    </main>
  );
}
