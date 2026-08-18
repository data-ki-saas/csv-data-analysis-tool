import type { ChartRecommendation } from "@/lib/api";

// Interactive filter/bin-size adjustments never round-trip through the LLM —
// they build fresh, deterministic DuckDB SQL client-side and re-run it via
// the existing /api/datasets/{id}/query endpoint, which re-validates every
// query with the same readonly guard regardless of where the SQL came from.
export type ChartFilter =
  | { kind: "equals"; column: string; value: string; label: string }
  | { kind: "range"; column: string; min: number; max: number; label: string };

export const DEFAULT_BIN_COUNT = 10;

export function quoteIdent(name: string): string {
  return `"${name.replace(/"/g, '""')}"`;
}

function buildWhereClause(filter: ChartFilter): string {
  const ident = quoteIdent(filter.column);
  if (filter.kind === "equals") {
    return `${ident} = '${filter.value.replace(/'/g, "''")}'`;
  }
  return `${ident} >= ${filter.min} AND ${ident} < ${filter.max}`;
}

export function buildTimeSeriesSql(column: string, grain: string, whereClause: string | null): string {
  const ident = quoteIdent(column);
  const where = whereClause ? `WHERE ${whereClause} AND ${ident} IS NOT NULL` : `WHERE ${ident} IS NOT NULL`;
  return `SELECT date_trunc('${grain}', ${ident}) AS period, count(*) AS count FROM data ${where} GROUP BY 1 ORDER BY 1`;
}

export function buildCategoricalSql(column: string, whereClause: string | null): string {
  const ident = quoteIdent(column);
  const where = whereClause ? `WHERE ${whereClause} AND ${ident} IS NOT NULL` : `WHERE ${ident} IS NOT NULL`;
  return `SELECT ${ident} AS category, count(*) AS count FROM data ${where} GROUP BY 1 ORDER BY 2 DESC`;
}

export function buildHistogramSql(column: string, binCount: number, whereClause: string | null): string {
  const ident = quoteIdent(column);
  const extra = whereClause ? ` AND ${whereClause}` : "";
  return `WITH stats AS (
  SELECT avg(${ident}) AS mean, stddev(${ident}) AS stddev, min(${ident}) AS min_val, max(${ident}) AS max_val
  FROM data WHERE ${ident} IS NOT NULL${extra}
),
binned AS (
  SELECT LEAST(CAST(floor((${ident} - stats.min_val) / NULLIF(stats.max_val - stats.min_val, 0) * ${binCount}) AS INTEGER), ${binCount - 1}) AS bucket
  FROM data, stats WHERE ${ident} IS NOT NULL${extra}
)
SELECT binned.bucket AS bucket, count(*) AS count, stats.mean AS mean, stats.stddev AS stddev,
       stats.min_val AS min_val, stats.max_val AS max_val
FROM binned CROSS JOIN stats
GROUP BY binned.bucket, stats.mean, stats.stddev, stats.min_val, stats.max_val
ORDER BY binned.bucket`;
}

/** The SQL a chart should actually run: the LLM's original recommendation
 * when nothing's been touched, or a freshly-built query the moment a filter
 * or bin-size override applies. A cross-filter set by clicking this chart's
 * own column is skipped (there's nothing useful to filter a chart by itself). */
export function buildEffectiveSql(
  recommendation: ChartRecommendation,
  filter: ChartFilter | null,
  binCountOverride: number | null
): string {
  const applicableFilter = filter && filter.column !== recommendation.column ? filter : null;
  const whereClause = applicableFilter ? buildWhereClause(applicableFilter) : null;

  const needsRebuild =
    whereClause !== null ||
    (recommendation.partition_type === "numerical_bins" && binCountOverride !== null);
  if (!needsRebuild) return recommendation.sql;

  switch (recommendation.partition_type) {
    case "numerical_bins":
      return buildHistogramSql(recommendation.column, binCountOverride ?? DEFAULT_BIN_COUNT, whereClause);
    case "categorical":
      return buildCategoricalSql(recommendation.column, whereClause);
    case "datetime":
      return buildTimeSeriesSql(recommendation.column, "month", whereClause);
    default:
      return recommendation.sql;
  }
}
