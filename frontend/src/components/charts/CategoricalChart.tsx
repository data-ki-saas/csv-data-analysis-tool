"use client";

import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Legend,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { ChartFilter } from "@/lib/chartQueries";
import type { QueryResponse } from "@/lib/api";
import { findColumn, toChartRows } from "@/lib/chartData";

const COLORS = ["var(--accent)", "#8b5cf6", "#16a34a", "#d97706", "#2563eb", "#dc2626", "#0891b2", "#a855f7"];

// Recharts' click payloads are typed as their internal shape descriptors
// (PieSectorDataItem/BarRectangleItem), not the caller's data record, even
// though the original data properties are spread onto the object at runtime.
function fieldOf(entry: unknown, key: string): unknown {
  return (entry as Record<string, unknown>)[key];
}

interface Props {
  result: QueryResponse;
  chartType: "bar" | "pie";
  column: string;
  activeFilter: ChartFilter | null;
  onToggleFilter: (value: string) => void;
}

export function CategoricalChart({ result, chartType, column, activeFilter, onToggleFilter }: Props) {
  const categoryKey = findColumn(result.columns, ["category"]) ?? result.columns[0];
  const countKey = findColumn(result.columns, ["count"]) ?? result.columns[1];
  const rows = toChartRows(result);

  const isSelected = (value: unknown) =>
    activeFilter?.kind === "equals" && activeFilter.column === column && activeFilter.value === String(value);
  const opacityFor = (value: unknown) => (activeFilter && !isSelected(value) ? 0.35 : 1);

  if (chartType === "pie") {
    return (
      <ResponsiveContainer width="100%" height={220}>
        <PieChart>
          <Tooltip />
          <Legend wrapperStyle={{ fontSize: 12 }} />
          <Pie
            data={rows}
            dataKey={countKey}
            nameKey={categoryKey}
            outerRadius={80}
            cursor="pointer"
            onClick={(entry) => onToggleFilter(String(fieldOf(entry, categoryKey)))}
          >
            {rows.map((row, i) => (
              <Cell key={i} fill={COLORS[i % COLORS.length]} opacity={opacityFor(row[categoryKey])} />
            ))}
          </Pie>
        </PieChart>
      </ResponsiveContainer>
    );
  }

  return (
    <ResponsiveContainer width="100%" height={220}>
      <BarChart data={rows}>
        <CartesianGrid strokeOpacity={0.2} />
        <XAxis dataKey={categoryKey} fontSize={11} angle={-15} textAnchor="end" height={45} interval={0} />
        <YAxis fontSize={12} allowDecimals={false} />
        <Tooltip />
        <Bar
          dataKey={countKey}
          cursor="pointer"
          onClick={(entry) => onToggleFilter(String(fieldOf(entry, categoryKey)))}
        >
          {rows.map((row, i) => (
            <Cell key={i} fill="var(--accent)" opacity={opacityFor(row[categoryKey])} />
          ))}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}
