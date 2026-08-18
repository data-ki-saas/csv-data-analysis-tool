"use client";

import { Bar, CartesianGrid, Cell, ComposedChart, Line, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import type { QueryResponse } from "@/lib/api";
import { findColumn, toChartRows } from "@/lib/chartData";

const BIN_OPTIONS = [5, 8, 10, 15, 20];

interface Props {
  result: QueryResponse;
  chartType: "histogram" | "bell_curve";
  binCount: number;
  onBinCountChange: (count: number) => void;
  onSelectBin: (range: [number, number] | null) => void;
  selectedBin: [number, number] | null;
}

/** Bell-curve height at `x`, scaled so its peak matches `maxCount` -- this is
 * a visual overlay against a categorical (per-bucket) axis, not a normalized
 * probability density, so it deliberately skips the 1/(σ√2π) normalization
 * constant in favor of something that visually lines up with the bars. */
function gaussianHeight(x: number, mean: number, stddev: number, maxCount: number): number {
  const z = (x - mean) / stddev;
  return maxCount * Math.exp(-0.5 * z * z);
}

function formatBound(value: number): string {
  return Number.isInteger(value) ? String(value) : value.toFixed(1);
}

export function HistogramChart({
  result,
  chartType,
  binCount,
  onBinCountChange,
  onSelectBin,
  selectedBin,
}: Props) {
  const bucketKey = findColumn(result.columns, ["bucket"]) ?? result.columns[0];
  const countKey = findColumn(result.columns, ["count"]) ?? result.columns[1];
  const meanKey = findColumn(result.columns, ["mean"]);
  const stddevKey = findColumn(result.columns, ["stddev"]);
  const minKey = findColumn(result.columns, ["min_val"]);
  const maxKey = findColumn(result.columns, ["max_val"]);

  const rows = toChartRows(result);
  const hasRange = Boolean(minKey && maxKey && rows.length > 0);
  const minVal = hasRange ? Number(rows[0][minKey!]) : null;
  const maxVal = hasRange ? Number(rows[0][maxKey!]) : null;
  const mean = meanKey && rows.length > 0 ? Number(rows[0][meanKey]) : null;
  const stddev = stddevKey && rows.length > 0 ? Number(rows[0][stddevKey]) : null;
  const binWidth = hasRange && minVal !== null && maxVal !== null ? (maxVal - minVal) / binCount : null;

  const maxCount = Math.max(...rows.map((row) => Number(row[countKey])), 1);
  const showCurve = chartType === "bell_curve" && mean !== null && stddev !== null && stddev > 0;

  const chartRows = rows.map((row) => {
    const bucket = Number(row[bucketKey]);
    const binStart = binWidth !== null && minVal !== null ? minVal + bucket * binWidth : null;
    const binEnd = binStart !== null ? binStart + (binWidth ?? 0) : null;
    const center = binStart !== null && binEnd !== null ? (binStart + binEnd) / 2 : null;
    return {
      __label: binStart !== null && binEnd !== null ? `${formatBound(binStart)}–${formatBound(binEnd)}` : String(bucket),
      __binStart: binStart,
      __binEnd: binEnd,
      __count: Number(row[countKey]),
      __curve: showCurve && center !== null ? gaussianHeight(center, mean!, stddev!, maxCount) : undefined,
    };
  });

  function handleBarClick(_: unknown, index: number) {
    const row = chartRows[index];
    if (row.__binStart === null || row.__binEnd === null) return;
    const isSame = selectedBin && selectedBin[0] === row.__binStart && selectedBin[1] === row.__binEnd;
    onSelectBin(isSame ? null : [row.__binStart, row.__binEnd]);
  }

  return (
    <div className="flex flex-col gap-2">
      <div className="flex items-center justify-end gap-2 text-xs">
        <label htmlFor="bin-count" className="opacity-60">
          Bins
        </label>
        <select
          id="bin-count"
          value={binCount}
          onChange={(e) => onBinCountChange(Number(e.target.value))}
          className="rounded border border-border bg-surface px-1 py-0.5"
        >
          {BIN_OPTIONS.map((n) => (
            <option key={n} value={n}>
              {n}
            </option>
          ))}
        </select>
      </div>
      <ResponsiveContainer width="100%" height={220}>
        <ComposedChart data={chartRows}>
          <CartesianGrid strokeOpacity={0.2} />
          <XAxis dataKey="__label" fontSize={10} angle={-20} textAnchor="end" height={45} interval={0} />
          <YAxis fontSize={12} allowDecimals={false} />
          <Tooltip />
          <Bar dataKey="__count" name="Count" cursor={hasRange ? "pointer" : undefined} onClick={handleBarClick}>
            {chartRows.map((row, i) => (
              <Cell
                key={i}
                fill="var(--accent)"
                opacity={
                  selectedBin && !(row.__binStart === selectedBin[0] && row.__binEnd === selectedBin[1]) ? 0.35 : 1
                }
              />
            ))}
          </Bar>
          {showCurve && (
            <Line type="monotone" dataKey="__curve" name="Normal fit" stroke="var(--foreground)" dot={false} strokeWidth={2} />
          )}
        </ComposedChart>
      </ResponsiveContainer>
    </div>
  );
}
