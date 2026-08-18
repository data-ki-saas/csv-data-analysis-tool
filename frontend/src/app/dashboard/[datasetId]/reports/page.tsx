"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useState } from "react";
import { ChartCard } from "@/components/charts/ChartCard";
import { useDatasetSchema } from "@/hooks/useDatasetSchema";
import { useReportStrategy } from "@/hooks/useReportStrategy";
import type { ChartFilter } from "@/lib/chartQueries";

export default function ReportsPage() {
  const { datasetId } = useParams<{ datasetId: string }>();

  const schema = useDatasetSchema(datasetId);
  const strategy = useReportStrategy(datasetId);
  const [filter, setFilter] = useState<ChartFilter | null>(null);

  const recommendations = strategy.data?.recommendations ?? [];

  return (
    <main className="mx-auto flex w-full max-w-5xl flex-col gap-6 px-4 py-12">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold">Visual Reports</h1>
        <Link href="/dashboard" className="text-sm underline">
          Back to dashboard
        </Link>
      </div>

      {schema.data && (
        <div className="flex flex-wrap items-center justify-between gap-3 rounded border border-border p-4">
          <div>
            <p className="font-medium">{schema.data.filename}</p>
            <p className="text-sm opacity-70">{schema.data.row_count.toLocaleString()} rows</p>
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

      {!strategy.isPending && recommendations.length === 0 && !strategy.isError && strategy.isIdle && (
        <p className="py-10 text-center text-sm opacity-60">
          No report yet — click &quot;Generate visual report&quot; to get AI-recommended charts for this dataset.
        </p>
      )}

      {!strategy.isPending && strategy.isSuccess && recommendations.length === 0 && (
        <p className="py-10 text-center text-sm opacity-60">
          Nothing chartable was found (only free-text columns, or the model returned no usable recommendations).
        </p>
      )}

      <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
        {recommendations.map((recommendation) => (
          <ChartCard
            key={recommendation.column + recommendation.chart_type}
            datasetId={datasetId}
            recommendation={recommendation}
            filter={filter}
            onFilterChange={setFilter}
          />
        ))}
      </div>
    </main>
  );
}
