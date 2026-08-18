"use client";

import { useState } from "react";
import {
  Area,
  AreaChart,
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { QueryResponse } from "@/lib/api";
import { findColumn, formatDateLabel, toChartRows } from "@/lib/chartData";
import { cn } from "@/lib/utils";

export function TimeSeriesChart({ result }: { result: QueryResponse }) {
  const [mode, setMode] = useState<"area" | "line">("area");

  const xKey = findColumn(result.columns, ["period"]) ?? result.columns[0];
  const yKey = findColumn(result.columns, ["count"]) ?? result.columns[1];
  const rows = toChartRows(result).map((row) => ({ ...row, [xKey]: formatDateLabel(row[xKey]) }));

  return (
    <div className="flex flex-col gap-2">
      <div className="flex justify-end gap-3 text-xs">
        <button
          type="button"
          onClick={() => setMode("area")}
          className={cn("opacity-60", mode === "area" && "underline opacity-100")}
        >
          Area
        </button>
        <button
          type="button"
          onClick={() => setMode("line")}
          className={cn("opacity-60", mode === "line" && "underline opacity-100")}
        >
          Line
        </button>
      </div>
      <ResponsiveContainer width="100%" height={220}>
        {mode === "area" ? (
          <AreaChart data={rows}>
            <CartesianGrid strokeOpacity={0.2} />
            <XAxis dataKey={xKey} fontSize={11} />
            <YAxis fontSize={12} allowDecimals={false} />
            <Tooltip />
            <Area type="monotone" dataKey={yKey} stroke="var(--accent)" fill="var(--accent)" fillOpacity={0.3} />
          </AreaChart>
        ) : (
          <LineChart data={rows}>
            <CartesianGrid strokeOpacity={0.2} />
            <XAxis dataKey={xKey} fontSize={11} />
            <YAxis fontSize={12} allowDecimals={false} />
            <Tooltip />
            <Line type="monotone" dataKey={yKey} stroke="var(--accent)" dot={false} strokeWidth={2} />
          </LineChart>
        )}
      </ResponsiveContainer>
    </div>
  );
}
