import type { ChartBlock } from "@/lib/api";
import { findColumn, formatDateLabel, toChartRows } from "@/lib/chartData";

// Dependency-free SVG chart rendering for the standalone HTML export -- no
// React, no Recharts. The exported file has to open in any browser with
// zero JS framework and zero network requests, so charts are plain inline
// <svg> markup built from strings, not a rendered component tree.

const PADDING = { top: 20, right: 16, bottom: 46, left: 36 };
const COLORS = ["#2563eb", "#8b5cf6", "#16a34a", "#d97706", "#dc2626", "#0891b2", "#a855f7", "#64748b"];

function escapeXml(value: string): string {
  return value.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
}

function truncate(value: string, max: number): string {
  return value.length > max ? `${value.slice(0, max - 1)}…` : value;
}

function scale(value: number, domainMin: number, domainMax: number, rangeMin: number, rangeMax: number): number {
  if (domainMax === domainMin) return (rangeMin + rangeMax) / 2;
  return rangeMin + ((value - domainMin) / (domainMax - domainMin)) * (rangeMax - rangeMin);
}

function svgWrap(width: number, height: number, body: string): string {
  return `<svg viewBox="0 0 ${width} ${height}" xmlns="http://www.w3.org/2000/svg" font-family="Arial, Helvetica, sans-serif">${body}</svg>`;
}

function renderBarChart(
  labels: string[],
  values: number[],
  width: number,
  height: number,
  curve?: number[]
): string {
  const innerWidth = width - PADDING.left - PADDING.right;
  const innerHeight = height - PADDING.top - PADDING.bottom;
  const maxValue = Math.max(...values, ...(curve ?? []), 1);
  const gap = 6;
  const barWidth = Math.max((innerWidth - gap * (values.length - 1)) / Math.max(values.length, 1), 1);
  const baseline = PADDING.top + innerHeight;

  const centers: number[] = [];
  const bars = values
    .map((v, i) => {
      const barHeight = scale(v, 0, maxValue, 0, innerHeight);
      const x = PADDING.left + i * (barWidth + gap);
      const y = baseline - barHeight;
      centers.push(x + barWidth / 2);
      return (
        `<rect x="${x.toFixed(1)}" y="${y.toFixed(1)}" width="${barWidth.toFixed(1)}" height="${barHeight.toFixed(1)}" fill="#2563eb" />` +
        `<text x="${(x + barWidth / 2).toFixed(1)}" y="${(y - 4).toFixed(1)}" font-size="9" text-anchor="middle">${v}</text>` +
        `<text x="${(x + barWidth / 2).toFixed(1)}" y="${(baseline + 14).toFixed(1)}" font-size="8" text-anchor="middle" transform="rotate(-25 ${(x + barWidth / 2).toFixed(1)} ${(baseline + 14).toFixed(1)})">${escapeXml(truncate(labels[i], 10))}</text>`
      );
    })
    .join("");

  const curveLine =
    curve && curve.length === values.length
      ? `<polyline points="${curve.map((v, i) => `${centers[i].toFixed(1)},${(baseline - scale(v, 0, maxValue, 0, innerHeight)).toFixed(1)}`).join(" ")}" fill="none" stroke="#111827" stroke-width="2" />`
      : "";

  return svgWrap(
    width,
    height,
    `<line x1="${PADDING.left}" y1="${baseline}" x2="${width - PADDING.right}" y2="${baseline}" stroke="#94a3b8" />${bars}${curveLine}`
  );
}

function renderPieChart(labels: string[], values: number[], width: number, height: number): string {
  const total = values.reduce((a, b) => a + b, 0) || 1;
  const cx = width * 0.32;
  const cy = height / 2;
  const r = Math.min(cx, cy) - 12;
  let angle = -Math.PI / 2;

  const slices = values
    .map((v, i) => {
      const fraction = v / total;
      const nextAngle = angle + fraction * Math.PI * 2;
      const x1 = cx + r * Math.cos(angle);
      const y1 = cy + r * Math.sin(angle);
      const x2 = cx + r * Math.cos(nextAngle);
      const y2 = cy + r * Math.sin(nextAngle);
      const largeArc = fraction > 0.5 ? 1 : 0;
      const path =
        fraction >= 0.999
          ? `M ${cx - r} ${cy} A ${r} ${r} 0 1 1 ${cx + r} ${cy} A ${r} ${r} 0 1 1 ${cx - r} ${cy} Z`
          : `M ${cx} ${cy} L ${x1.toFixed(2)} ${y1.toFixed(2)} A ${r} ${r} 0 ${largeArc} 1 ${x2.toFixed(2)} ${y2.toFixed(2)} Z`;
      angle = nextAngle;
      return `<path d="${path}" fill="${COLORS[i % COLORS.length]}" stroke="var(--surface, #fff)" stroke-width="1" />`;
    })
    .join("");

  const legend = labels
    .map((label, i) => {
      const y = 16 + i * 16;
      const pct = ((values[i] / total) * 100).toFixed(1);
      return (
        `<rect x="${width * 0.62}" y="${y - 9}" width="10" height="10" fill="${COLORS[i % COLORS.length]}" />` +
        `<text x="${width * 0.62 + 14}" y="${y}" font-size="10">${escapeXml(truncate(label, 18))} (${pct}%)</text>`
      );
    })
    .join("");

  return svgWrap(width, height, slices + legend);
}

function renderLineChart(labels: string[], values: number[], width: number, height: number): string {
  const innerWidth = width - PADDING.left - PADDING.right;
  const innerHeight = height - PADDING.top - PADDING.bottom;
  const maxValue = Math.max(...values, 1);
  const minValue = Math.min(...values, 0);
  const baseline = PADDING.top + innerHeight;

  const points = values.map((v, i) => {
    const x = PADDING.left + (values.length <= 1 ? innerWidth / 2 : (i / (values.length - 1)) * innerWidth);
    const y = baseline - scale(v, minValue, maxValue, 0, innerHeight);
    return [x, y] as const;
  });
  const pointsAttr = points.map(([x, y]) => `${x.toFixed(1)},${y.toFixed(1)}`).join(" ");
  const areaPath =
    points.length > 0
      ? `M ${points[0][0].toFixed(1)},${baseline.toFixed(1)} L ${pointsAttr} L ${points[points.length - 1][0].toFixed(1)},${baseline.toFixed(1)} Z`
      : "";

  const step = Math.max(Math.ceil(labels.length / 8), 1);
  const labelEls = labels
    .map((label, i) => (i % step === 0 ? [i, label] : null))
    .filter((entry): entry is [number, string] => entry !== null)
    .map(
      ([i, label]) =>
        `<text x="${points[i][0].toFixed(1)}" y="${(baseline + 14).toFixed(1)}" font-size="8" text-anchor="middle">${escapeXml(label)}</text>`
    )
    .join("");

  return svgWrap(
    width,
    height,
    `<path d="${areaPath}" fill="#2563eb" fill-opacity="0.25" />` +
      `<polyline points="${pointsAttr}" fill="none" stroke="#2563eb" stroke-width="2" />` +
      `<line x1="${PADDING.left}" y1="${baseline}" x2="${width - PADDING.right}" y2="${baseline}" stroke="#94a3b8" />` +
      labelEls
  );
}

function gaussianHeight(x: number, mean: number, stddev: number, maxCount: number): number {
  const z = (x - mean) / stddev;
  return maxCount * Math.exp(-0.5 * z * z);
}

export function renderStaticChart(block: ChartBlock, width = 480, height = 240): string {
  const rows = toChartRows(block.result);

  if (block.partition_type === "datetime") {
    const xKey = findColumn(block.result.columns, ["period"]) ?? block.result.columns[0];
    const yKey = findColumn(block.result.columns, ["count"]) ?? block.result.columns[1];
    const labels = rows.map((row) => formatDateLabel(row[xKey]));
    const values = rows.map((row) => Number(row[yKey]) || 0);
    return renderLineChart(labels, values, width, height);
  }

  if (block.partition_type === "numerical_bins") {
    const bucketKey = findColumn(block.result.columns, ["bucket"]) ?? block.result.columns[0];
    const countKey = findColumn(block.result.columns, ["count"]) ?? block.result.columns[1];
    const meanKey = findColumn(block.result.columns, ["mean"]);
    const stddevKey = findColumn(block.result.columns, ["stddev"]);
    const minKey = findColumn(block.result.columns, ["min_val"]);
    const maxKey = findColumn(block.result.columns, ["max_val"]);

    const values = rows.map((row) => Number(row[countKey]) || 0);
    const hasRange = Boolean(minKey && maxKey && rows.length > 0);
    const minVal = hasRange ? Number(rows[0][minKey!]) : null;
    const maxVal = hasRange ? Number(rows[0][maxKey!]) : null;
    const binWidth = hasRange && minVal !== null && maxVal !== null ? (maxVal - minVal) / values.length : null;
    const labels = rows.map((row) => {
      const bucket = Number(row[bucketKey]);
      if (binWidth === null || minVal === null) return String(bucket);
      const start = minVal + bucket * binWidth;
      return `${start.toFixed(1)}–${(start + binWidth).toFixed(1)}`;
    });

    let curve: number[] | undefined;
    if (block.chart_type === "bell_curve" && meanKey && stddevKey && binWidth !== null && minVal !== null) {
      const mean = Number(rows[0][meanKey]);
      const stddev = Number(rows[0][stddevKey]);
      const maxCount = Math.max(...values, 1);
      if (stddev > 0) {
        curve = rows.map((row) => {
          const bucket = Number(row[bucketKey]);
          const center = minVal + (bucket + 0.5) * binWidth;
          return gaussianHeight(center, mean, stddev, maxCount);
        });
      }
    }

    return renderBarChart(labels, values, width, height, curve);
  }

  // categorical
  const categoryKey = findColumn(block.result.columns, ["category"]) ?? block.result.columns[0];
  const countKey = findColumn(block.result.columns, ["count"]) ?? block.result.columns[1];
  const labels = rows.map((row) => String(row[categoryKey]));
  const values = rows.map((row) => Number(row[countKey]) || 0);
  return block.chart_type === "pie"
    ? renderPieChart(labels, values, width, height)
    : renderBarChart(labels, values, width, height);
}
