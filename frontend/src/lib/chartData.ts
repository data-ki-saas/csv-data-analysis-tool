import type { QueryResponse } from "@/lib/api";

/** Finds a result column by name, case-insensitively, trying each candidate
 * in order. Chart components use this instead of hardcoded indices because
 * the SQL producing a result may be LLM-generated (initial recommendation)
 * or client-built (filter/bin-size re-aggregation) -- column order isn't
 * guaranteed to match between the two. */
export function findColumn(columns: string[], candidates: string[]): string | undefined {
  const lower = columns.map((c) => c.toLowerCase());
  for (const candidate of candidates) {
    const idx = lower.indexOf(candidate.toLowerCase());
    if (idx !== -1) return columns[idx];
  }
  return undefined;
}

/** Converts the {columns, rows} wire format into Recharts' preferred
 * array-of-objects shape, keyed by the actual column names. */
export function toChartRows(result: QueryResponse): Record<string, unknown>[] {
  return result.rows.map((row) => {
    const record: Record<string, unknown> = {};
    result.columns.forEach((col, i) => {
      record[col] = row[i];
    });
    return record;
  });
}

/** DuckDB DATE/TIMESTAMP values arrive as ISO strings; trims to the date part. */
export function formatDateLabel(value: unknown): string {
  return String(value).slice(0, 10);
}
