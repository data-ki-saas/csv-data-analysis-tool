"""LLM-generated executive-summary bullet points for a chart's aggregated
data. Given the already-computed {columns, rows} result of a chart (from
either the report-strategy engine or a client-rebuilt fast-aggregation
query), asks the configured LLM provider for a handful of concrete,
number-citing bullets -- never raw SQL or chart-rendering concerns, just the
same aggregate data a human would be looking at on screen.
"""

import json

from src.llm.providers.base import LLMProvider

MAX_INSIGHTS = 5

SYSTEM_PROMPT = """You are a data analyst writing executive-summary bullet points for a \
business intelligence report. Given a chart's title, type, and its already-aggregated \
result data (counts, distributions, or a time series -- computed via SQL, not raw rows), \
write 3-5 short, concrete bullets a busy executive could skim in five seconds.

Rules:
- Cite actual numbers/categories from the data (the largest category and its share, a \
clear trend direction, a notable skew or outlier) -- never generic filler like "this \
chart shows the distribution of X".
- Do not restate the chart title verbatim.
- Each bullet under 25 words.
- If the data is too sparse or flat to say anything meaningful, say so in one bullet \
rather than inventing a pattern that isn't there.

Respond with ONLY a JSON array of 3-5 strings (no markdown fences, no commentary)."""


def build_prompt(chart_context: dict) -> str:
    return (
        f"Chart: \"{chart_context['title']}\" "
        f"({chart_context['chart_type']} chart, {chart_context['partition_type']} "
        f"partition on column \"{chart_context['column']}\")\n"
        f"Result columns: {chart_context['result']['columns']}\n"
        f"Result rows: {chart_context['result']['rows']}"
    )


async def generate_insights(chart_context: dict, provider: LLMProvider) -> list[str]:
    """chart_context: {"title", "chart_type", "partition_type", "column",
    "result": {"columns", "rows"}}. Returns up to MAX_INSIGHTS bullet strings.

    Raises (rather than degrading silently) on a non-JSON or non-list
    response -- unlike the type-review/strategy modules, there's no partial
    per-item structure to salvage here, so the caller treats any parse
    failure as a hard error (see service.generate_chart_insights()).
    """
    response = await provider.complete(build_prompt(chart_context), system=SYSTEM_PROMPT, max_tokens=512)
    parsed = json.loads(response)
    if not isinstance(parsed, list):
        raise ValueError("Expected a JSON array of insight strings")

    bullets = [item.strip() for item in parsed if isinstance(item, str) and item.strip()]
    return bullets[:MAX_INSIGHTS]
