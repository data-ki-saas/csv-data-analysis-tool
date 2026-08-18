"""LLM-driven visualization strategy: given a dataset's already-inferred
schema (src/datasets/profiling.py), ask the configured LLM provider
(Anthropic by default -- see src/llm/client.py) to recommend a prioritized
set of charts and the DuckDB SQL to compute each one.

Every returned SQL string is untrusted LLM output. It is re-validated by
duckdb_manager's readonly guard at execution time (see
service.generate_report_strategy()) -- this module only does structural
validation of the JSON shape, never treats "syntactically plausible SQL" as
"safe to run".
"""

import json

from src.llm.providers.base import LLMProvider

_VALID_PARTITION_TYPES = {"datetime", "numerical_bins", "categorical"}
_VALID_CHART_TYPES = {"line", "bar", "pie", "histogram", "bell_curve"}

# Enforced server-side after the LLM responds (see service.py) -- an
# instruction in the prompt is a strong hint, not a guarantee, so priority
# order is a property we compute, not one we trust the model to have applied.
PARTITION_PRIORITY = {"datetime": 0, "numerical_bins": 1, "categorical": 2}

SYSTEM_PROMPT = """You are a data visualization strategist for a CSV analysis tool. \
Given a dataset's columns (with their inferred category, cardinality, null rate, and \
sample values), recommend a prioritized set of charts that would make a good default \
report for this dataset, plus the exact DuckDB SQL to compute each one.

PRIORITIZATION (always in this order -- put datetime columns first in your output, \
then numerical, then categorical):
1. Datetime columns first -- these drive time-series partitioning (e.g. trend by month).
2. Numerical columns next -- bucket them into meaningful ranges (e.g. age ranges, \
score brackets), don't just report the raw column.
3. Categorical columns last -- one chart per column showing the distribution across \
its category values.
Skip a column if it has no meaningful chart (e.g. entirely null, or a categorical \
column so high-cardinality it's really an identifier).

CHART MATCHING (pick exactly one per recommendation):
- datetime -> "line": a trend over time, bucketed with date_trunc (choose a sensible \
grain -- day/week/month/year -- from the date range and row count).
- numerical_bins -> "histogram" (plain distribution) or "bell_curve" (distribution \
plus the mean/stddev needed to overlay a normal curve) -- prefer "bell_curve" when the \
data plausibly clusters around a center (age, scores, measurements); prefer \
"histogram" for skewed or bounded-at-zero data (counts, amounts).
- categorical -> "pie" when the column has at most 6 distinct values, otherwise "bar".

SQL RULES (violating any of these makes the query unusable):
- The table is always named `data`. Query it directly, e.g. `FROM data`.
- Always double-quote column identifiers exactly as given, e.g. `"signup_date"`.
- Exactly ONE statement: a single SELECT, or a single WITH ... SELECT. No semicolons, \
no DDL/DML, no multiple statements.
- DuckDB dialect: use `date_trunc('month', "col")` for time buckets, `stddev("col")` \
for standard deviation. There is no `width_bucket` in DuckDB -- for numeric binning, \
compute bucket = `LEAST(CAST(floor(("col" - min_val) / NULLIF(max_val - min_val, 0) * \
N) AS INTEGER), N - 1)` against a `stats` CTE holding `min_val`/`max_val`, as in the \
example below.
- Filter out NULLs from the column being charted (`WHERE "col" IS NOT NULL`).
- For numerical_bins charts, always include `min_val` and `max_val` (the bucketing range) as columns \
in the final SELECT, alongside `bucket`/`count` (and `mean`/`stddev` for bell_curve) -- the frontend \
uses them to label bin edges and can't recompute the intended range from bucket counts alone.

EXAMPLES (follow this shape):

Time series (datetime, chart_type "line"):
SELECT date_trunc('month', "signup_date") AS period, count(*) AS count
FROM data GROUP BY 1 ORDER BY 1

Numeric distribution with bell-curve stats (numerical_bins, chart_type "bell_curve"):
WITH stats AS (
  SELECT avg("age") AS mean, stddev("age") AS stddev, min("age") AS min_val, max("age") AS max_val FROM data
),
binned AS (
  SELECT LEAST(CAST(floor(("age" - stats.min_val) / NULLIF(stats.max_val - stats.min_val, 0) * 5) AS INTEGER), 4) AS bucket
  FROM data, stats WHERE "age" IS NOT NULL
)
SELECT binned.bucket, count(*) AS count, stats.mean, stats.stddev, stats.min_val, stats.max_val
FROM binned CROSS JOIN stats GROUP BY binned.bucket, stats.mean, stats.stddev, stats.min_val, stats.max_val
ORDER BY binned.bucket

Categorical (categorical, chart_type "pie" or "bar"):
SELECT "plan" AS category, count(*) AS count FROM data GROUP BY 1 ORDER BY 2 DESC

RESPONSE FORMAT: respond with ONLY a JSON array (no markdown fences, no commentary), \
ordered datetime-first/numerical-next/categorical-last, one object per recommendation:
[{"column": <name>, "partition_type": "datetime"|"numerical_bins"|"categorical", \
"chart_type": "line"|"bar"|"pie"|"histogram"|"bell_curve", "title": "<short chart title>", \
"rationale": "<=20 words", "sql": "<single DuckDB SELECT/WITH statement>"}]
"""


def build_prompt(columns: list[dict]) -> str:
    lines = [
        f"- \"{col['name']}\" (alias=\"{col['alias']}\", type={col['type']}, "
        f"category={col['category']}, distinct={col['distinct_count']}, "
        f"nulls={col['null_percentage']}%, samples={col['samples']})"
        for col in columns
    ]
    return "Columns:\n" + "\n".join(lines)


async def suggest_visual_strategy(columns: list[dict], provider: LLMProvider) -> list[dict]:
    """columns: [{"name", "alias", "type", "category", "distinct_count",
    "null_percentage", "samples"}, ...] -- pass only chartable columns (the
    caller excludes free_text; see service.generate_report_strategy()).

    Returns a list of recommendation dicts: {"column", "partition_type",
    "chart_type", "title", "rationale", "sql"}, sorted by PARTITION_PRIORITY.
    Malformed entries (unknown column, invalid enum value, missing SQL/title)
    are dropped rather than raising -- a partially-useful response is still
    useful, and the caller re-validates every "sql" value before running it.
    """
    if not columns:
        return []

    response = await provider.complete(build_prompt(columns), system=SYSTEM_PROMPT, max_tokens=4096)
    parsed = json.loads(response)
    if not isinstance(parsed, list):
        raise ValueError("Expected a JSON array of chart recommendations")

    valid_columns = {col["name"] for col in columns}
    suggestions = []
    for entry in parsed:
        if not isinstance(entry, dict):
            continue
        column = entry.get("column")
        partition_type = entry.get("partition_type")
        chart_type = entry.get("chart_type")
        title = entry.get("title")
        sql = entry.get("sql")
        if (
            column not in valid_columns
            or partition_type not in _VALID_PARTITION_TYPES
            or chart_type not in _VALID_CHART_TYPES
            or not isinstance(title, str)
            or not title.strip()
            or not isinstance(sql, str)
            or not sql.strip()
        ):
            continue
        rationale = entry.get("rationale")
        suggestions.append(
            {
                "column": column,
                "partition_type": partition_type,
                "chart_type": chart_type,
                "title": title,
                "rationale": rationale if isinstance(rationale, str) else "",
                "sql": sql,
            }
        )

    suggestions.sort(key=lambda s: PARTITION_PRIORITY[s["partition_type"]])
    return suggestions
