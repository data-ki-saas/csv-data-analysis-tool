"""LLM-assisted column type review -- a fallback for the rule-based
classifier in profiling.py when a column's stats leave it ambiguous (see
CONFIDENCE_REVIEW_THRESHOLD). Never required for ingestion to succeed; only
invoked when a user asks for a review via POST
/api/datasets/{id}/schema/review, or explicitly overrides a column via
PATCH .../schema/columns/{name} (see src/datasets/service.py).
"""

import json

from src.datasets.profiling import ColumnCategory
from src.llm.providers.base import LLMProvider

_VALID_CATEGORIES = {category.value for category in ColumnCategory}

SYSTEM_PROMPT = (
    "You are a data profiling assistant. For each column described below, "
    "decide which single category best fits it: datetime, "
    "continuous_numerical (e.g. age, marks, revenue -- a real measured "
    "range), categorical (a small, repeated set of labels or codes, even if "
    "stored as numbers -- e.g. a rating or a ZIP code), or free_text "
    "(comments, descriptions, names -- mostly unique values). Judge intent "
    "from the column name and sample values, not just the storage type. "
    "Respond with ONLY a JSON object mapping each column name to "
    '{"category": <one of the four above>, "confidence": <0-100>, '
    '"rationale": "<=15 words"}. No markdown fences, no commentary.'
)


def build_prompt(columns: list[dict]) -> str:
    lines = [
        f"- \"{col['name']}\" (type={col['type']}, current guess={col['category']}, "
        f"distinct={col['distinct_count']}, nulls={col['null_percentage']}%, "
        f"samples={col['samples']})"
        for col in columns
    ]
    return "Columns:\n" + "\n".join(lines)


async def suggest_column_categories(columns: list[dict], provider: LLMProvider) -> dict:
    """columns: [{"name", "type", "category", "distinct_count",
    "null_percentage", "samples"}, ...].

    Returns {name: {"category", "confidence", "rationale"}} for columns the
    model returned a valid suggestion for. A name missing from the result
    (bad category, missing confidence, etc.) should be treated by the caller
    as "no change" rather than an error -- a partially-useful response is
    still useful.
    """
    if not columns:
        return {}

    response = await provider.complete(build_prompt(columns), system=SYSTEM_PROMPT, max_tokens=1024)
    parsed = json.loads(response)

    suggestions = {}
    for col in columns:
        entry = parsed.get(col["name"])
        if not isinstance(entry, dict):
            continue
        category = entry.get("category")
        confidence = entry.get("confidence")
        if category not in _VALID_CATEGORIES or not isinstance(confidence, (int, float)):
            continue
        rationale = entry.get("rationale")
        suggestions[col["name"]] = {
            "category": category,
            "confidence": float(confidence),
            "rationale": rationale if isinstance(rationale, str) else None,
        }
    return suggestions
