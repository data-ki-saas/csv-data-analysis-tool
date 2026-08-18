"use client";

import { useEffect, useRef, useState } from "react";
import { useParams } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { getPublicChartShare } from "@/lib/api";
import { renderBrandedFooterHtml, renderBrandedHeaderHtml } from "@/lib/branding";
import type { ChartFilter } from "@/lib/chartQueries";
import { cn } from "@/lib/utils";
import { IconButton, MaximizeIcon, MinimizeIcon } from "@/components/IconButton";
import { TimeSeriesChart } from "@/components/charts/TimeSeriesChart";
import { HistogramChart } from "@/components/charts/HistogramChart";
import { CategoricalChart } from "@/components/charts/CategoricalChart";

const PARTITION_LABELS: Record<string, string> = {
  datetime: "Time series",
  numerical_bins: "Numerical",
  categorical: "Categorical",
};

export default function SharedChartPage() {
  const { token } = useParams<{ token: string }>();

  // No cross-chart filter concept here -- there's only ever one chart on this
  // page, so bin-select/category-toggle state stays purely local and cosmetic
  // (dimming/highlighting), unlike ChartCard's dataset-wide ChartFilter.
  const [filter, setFilter] = useState<ChartFilter | null>(null);
  const [isFullscreen, setIsFullscreen] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);

  const query = useQuery({
    queryKey: ["publicChartShare", token],
    queryFn: () => getPublicChartShare(token),
  });

  useEffect(() => {
    function handleFullscreenChange() {
      setIsFullscreen(document.fullscreenElement === containerRef.current);
    }
    document.addEventListener("fullscreenchange", handleFullscreenChange);
    return () => document.removeEventListener("fullscreenchange", handleFullscreenChange);
  }, []);

  function handleToggleFullscreen() {
    if (document.fullscreenElement) {
      document.exitFullscreen();
    } else {
      containerRef.current?.requestFullscreen();
    }
  }

  function handleCategoryToggle(value: string) {
    if (!query.data) return;
    if (filter?.kind === "equals" && filter.value === value) {
      setFilter(null);
      return;
    }
    setFilter({ kind: "equals", column: query.data.column, value, label: value });
  }

  function handleBinToggle(range: [number, number] | null) {
    if (!query.data || !range) {
      setFilter(null);
      return;
    }
    setFilter({
      kind: "range",
      column: query.data.column,
      min: range[0],
      max: range[1],
      label: `${range[0].toFixed(1)}–${range[1].toFixed(1)}`,
    });
  }

  const selectedBin: [number, number] | null =
    filter?.kind === "range" ? [filter.min, filter.max] : null;

  return (
    <main className="mx-auto flex w-full max-w-2xl flex-col gap-6 px-4 py-16">
      {query.isLoading && <p className="text-center text-sm opacity-60">Loading…</p>}
      {query.isError && (
        <p className="text-center text-sm text-red-600">
          This share link is invalid or has been revoked.
        </p>
      )}

      {query.data && (
        <div
          ref={containerRef}
          className={cn(
            "flex flex-col gap-3 rounded border border-border bg-surface p-5",
            isFullscreen && "justify-center p-10"
          )}
        >
          <div className="flex items-start justify-between gap-2">
            <div
              className="min-w-0 break-words font-medium"
              dangerouslySetInnerHTML={{
                __html: renderBrandedHeaderHtml(query.data.header_snapshot, query.data.title),
              }}
            />
            <div className="flex shrink-0 items-center gap-2">
              <span className="rounded bg-accent/10 px-2 py-0.5 text-xs text-accent">
                {PARTITION_LABELS[query.data.partition_type] ?? query.data.partition_type}
              </span>
              <IconButton
                label={isFullscreen ? "Exit fullscreen" : "Fullscreen"}
                onClick={handleToggleFullscreen}
              >
                {isFullscreen ? <MinimizeIcon /> : <MaximizeIcon />}
              </IconButton>
            </div>
          </div>

          {query.data.partition_type === "datetime" && <TimeSeriesChart result={query.data.result} />}
          {query.data.partition_type === "numerical_bins" && (
            <HistogramChart
              result={query.data.result}
              chartType={query.data.chart_type === "bell_curve" ? "bell_curve" : "histogram"}
              binCount={query.data.result.rows.length}
              onBinCountChange={() => {}}
              onSelectBin={handleBinToggle}
              selectedBin={selectedBin}
            />
          )}
          {query.data.partition_type === "categorical" && (
            <CategoricalChart
              result={query.data.result}
              chartType={query.data.chart_type === "pie" ? "pie" : "bar"}
              column={query.data.column}
              activeFilter={filter}
              onToggleFilter={handleCategoryToggle}
            />
          )}

          {query.data.footer_snapshot && (
            <div
              className="border-t border-border pt-2 text-center text-xs opacity-80"
              dangerouslySetInnerHTML={{ __html: renderBrandedFooterHtml(query.data.footer_snapshot, "") }}
            />
          )}
        </div>
      )}

      <p className="text-center text-xs opacity-60">
        Powered by{" "}
        <Link href="/" className="underline">
          CSV Data Analysis Tool
        </Link>{" "}
        — try it yourself
      </p>
    </main>
  );
}
