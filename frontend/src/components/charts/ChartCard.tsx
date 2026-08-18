"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import type { ChartRecommendation, ChartShare, QueryResponse } from "@/lib/api";
import { queryDataset } from "@/lib/api";
import { buildEffectiveSql, ChartFilter, DEFAULT_BIN_COUNT } from "@/lib/chartQueries";
import { cn } from "@/lib/utils";
import { downloadChartAsJpg } from "@/lib/exportChartImage";
import { printChartAsPdf } from "@/lib/exportChartPdf";
import { useCreateChartShare, useRevokeChartShare } from "@/hooks/useChartShare";
import { useGenerateInsights } from "@/hooks/useGenerateInsights";
import { usePinBlock } from "@/hooks/usePresentation";
import {
  CopyIcon,
  IconButton,
  InsightsIcon,
  JpgIcon,
  MaximizeIcon,
  MinimizeIcon,
  PdfIcon,
  PinIcon,
  RevokeIcon,
  ShareIcon,
} from "@/components/IconButton";
import { TimeSeriesChart } from "./TimeSeriesChart";
import { HistogramChart } from "./HistogramChart";
import { CategoricalChart } from "./CategoricalChart";

const PARTITION_LABELS: Record<string, string> = {
  datetime: "Time series",
  numerical_bins: "Numerical",
  categorical: "Categorical",
};

interface Props {
  datasetId: string;
  recommendation: ChartRecommendation;
  filter: ChartFilter | null;
  onFilterChange: (filter: ChartFilter | null) => void;
}

export function ChartCard({ datasetId, recommendation, filter, onFilterChange }: Props) {
  const [binCount, setBinCount] = useState<number | null>(null);
  const [insights, setInsights] = useState<string[] | null>(null);
  const [share, setShare] = useState<ChartShare | null>(null);
  const [isFullscreen, setIsFullscreen] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);

  const generateInsights = useGenerateInsights(datasetId);
  const pin = usePinBlock(datasetId);
  const createShare = useCreateChartShare(datasetId);
  const revokeShare = useRevokeChartShare(datasetId);

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

  const sql = useMemo(
    () => buildEffectiveSql(recommendation, filter, binCount),
    [recommendation, filter, binCount]
  );
  // Nothing's been touched -> use the strategy response's own result, no
  // extra request. The moment a filter or bin-size override changes the SQL,
  // this fires a real query against /api/datasets/{id}/query ("fast aggregation").
  const isCustomized = sql !== recommendation.sql;

  const query = useQuery({
    queryKey: ["chartQuery", datasetId, sql],
    queryFn: () => queryDataset(datasetId, sql),
    enabled: isCustomized,
  });

  const result = isCustomized ? query.data : (recommendation.result ?? undefined);
  const error = isCustomized ? (query.error as Error | undefined)?.message : (recommendation.error ?? undefined);
  const loading = isCustomized && query.isFetching;

  function handleCategoryToggle(value: string) {
    if (filter?.kind === "equals" && filter.column === recommendation.column && filter.value === value) {
      onFilterChange(null);
      return;
    }
    onFilterChange({
      kind: "equals",
      column: recommendation.column,
      value,
      label: `${recommendation.title}: ${value}`,
    });
  }

  function handleBinToggle(range: [number, number] | null) {
    if (!range) {
      onFilterChange(null);
      return;
    }
    onFilterChange({
      kind: "range",
      column: recommendation.column,
      min: range[0],
      max: range[1],
      label: `${recommendation.title}: ${range[0].toFixed(1)}–${range[1].toFixed(1)}`,
    });
  }

  const selectedBin: [number, number] | null =
    filter?.kind === "range" && filter.column === recommendation.column ? [filter.min, filter.max] : null;

  function handleGenerateInsights(currentResult: QueryResponse) {
    generateInsights.mutate(
      {
        title: recommendation.title,
        chart_type: recommendation.chart_type,
        partition_type: recommendation.partition_type,
        column: recommendation.column,
        result: currentResult,
      },
      { onSuccess: (data) => setInsights(data.insights) }
    );
  }

  function toChartBlock(currentResult: QueryResponse) {
    return {
      type: "chart" as const,
      id: recommendation.column,
      title: recommendation.title,
      chart_type: recommendation.chart_type,
      partition_type: recommendation.partition_type,
      column: recommendation.column,
      result: currentResult,
    };
  }

  function handleDownloadJpg(currentResult: QueryResponse) {
    downloadChartAsJpg(toChartBlock(currentResult));
  }

  function handleDownloadPdf(currentResult: QueryResponse) {
    printChartAsPdf(toChartBlock(currentResult));
  }

  function handleShare(currentResult: QueryResponse) {
    createShare.mutate(
      {
        title: recommendation.title,
        chart_type: recommendation.chart_type,
        partition_type: recommendation.partition_type,
        column: recommendation.column,
        result: currentResult,
      },
      { onSuccess: (data) => setShare(data) }
    );
  }

  function handleRevokeShare() {
    if (!share) return;
    revokeShare.mutate(share.token, { onSuccess: () => setShare(null) });
  }

  function handleCopyShareLink() {
    if (!share) return;
    navigator.clipboard.writeText(`${window.location.origin}/share/${share.token}`);
  }

  function handlePin(currentResult: QueryResponse) {
    pin.mutate(
      {
        chart: {
          id: crypto.randomUUID(),
          title: recommendation.title,
          chart_type: recommendation.chart_type,
          partition_type: recommendation.partition_type,
          column: recommendation.column,
          result: currentResult,
        },
        insights,
      },
      { onSuccess: () => setTimeout(() => pin.reset(), 2000) }
    );
  }

  return (
    <div
      ref={containerRef}
      className={cn(
        "flex flex-col gap-3 rounded border border-border bg-surface p-4",
        isFullscreen && "justify-center p-10"
      )}
    >
      <div className="flex items-start justify-between gap-2">
        <div>
          <h3 className="font-medium">{recommendation.title}</h3>
          {recommendation.rationale && <p className="text-xs opacity-60">{recommendation.rationale}</p>}
        </div>
        <div className="flex shrink-0 items-center gap-2">
          <span className="rounded bg-accent/10 px-2 py-0.5 text-xs text-accent">
            {PARTITION_LABELS[recommendation.partition_type] ?? recommendation.partition_type}
          </span>
          <IconButton
            label={isFullscreen ? "Exit fullscreen" : "Fullscreen"}
            onClick={handleToggleFullscreen}
          >
            {isFullscreen ? <MinimizeIcon /> : <MaximizeIcon />}
          </IconButton>
        </div>
      </div>

      {loading && <p className="py-10 text-center text-sm opacity-60">Updating…</p>}
      {!loading && error && (
        <p className="py-10 text-center text-sm text-red-600">Couldn&apos;t render this chart: {error}</p>
      )}
      {!loading && !error && result && (
        <>
          {recommendation.partition_type === "datetime" && <TimeSeriesChart result={result} />}
          {recommendation.partition_type === "numerical_bins" && (
            <HistogramChart
              result={result}
              chartType={recommendation.chart_type === "bell_curve" ? "bell_curve" : "histogram"}
              binCount={binCount ?? DEFAULT_BIN_COUNT}
              onBinCountChange={setBinCount}
              onSelectBin={handleBinToggle}
              selectedBin={selectedBin}
            />
          )}
          {recommendation.partition_type === "categorical" && (
            <CategoricalChart
              result={result}
              chartType={recommendation.chart_type === "pie" ? "pie" : "bar"}
              column={recommendation.column}
              activeFilter={filter}
              onToggleFilter={handleCategoryToggle}
            />
          )}

          {insights && (
            <ul className="flex list-disc flex-col gap-1 rounded bg-accent/5 p-3 pl-6 text-xs">
              {insights.map((bullet, i) => (
                <li key={i}>{bullet}</li>
              ))}
            </ul>
          )}
          {generateInsights.isError && (
            <p className="text-xs text-red-600">
              Couldn&apos;t generate insights: {(generateInsights.error as Error).message}
            </p>
          )}
          {pin.isError && (
            <p className="text-xs text-red-600">Couldn&apos;t pin this chart: {(pin.error as Error).message}</p>
          )}
          {(createShare.isError || revokeShare.isError) && (
            <p className="text-xs text-red-600">
              Couldn&apos;t update sharing: {((createShare.error ?? revokeShare.error) as Error).message}
            </p>
          )}

          <div className="flex flex-wrap items-center gap-1 border-t border-border pt-2">
            <IconButton
              label={generateInsights.isPending ? "Generating…" : insights ? "Regenerate insights" : "Generate insights"}
              onClick={() => handleGenerateInsights(result)}
              disabled={generateInsights.isPending}
            >
              <InsightsIcon />
            </IconButton>
            <IconButton
              label={pin.isPending ? "Pinning…" : pin.isSuccess ? "Pinned" : "Pin to presentation"}
              onClick={() => handlePin(result)}
              disabled={pin.isPending}
            >
              <PinIcon />
            </IconButton>
            <IconButton label="Download JPG" onClick={() => handleDownloadJpg(result)}>
              <JpgIcon />
            </IconButton>
            <IconButton label="Download PDF" onClick={() => handleDownloadPdf(result)}>
              <PdfIcon />
            </IconButton>
            {!share ? (
              <IconButton
                label={createShare.isPending ? "Creating link…" : "Share"}
                onClick={() => handleShare(result)}
                disabled={createShare.isPending}
              >
                <ShareIcon />
              </IconButton>
            ) : (
              <>
                <IconButton label="Copy share link" onClick={handleCopyShareLink}>
                  <CopyIcon />
                </IconButton>
                <IconButton
                  label={revokeShare.isPending ? "Revoking…" : "Revoke share link"}
                  onClick={handleRevokeShare}
                  disabled={revokeShare.isPending}
                >
                  <RevokeIcon />
                </IconButton>
              </>
            )}
          </div>
        </>
      )}
    </div>
  );
}
