"""LLM-assisted category-value merging for one categorical column -- e.g.
turning the free-text command "merge NY and New York City into New York"
into a structured merge rule. Never required for anything else in this
codebase to work; only invoked from the Column Types page's "Edit column"
dialog (POST .../schema/columns/{name}/merge/suggest, see
src/datasets/service.py). Follows the same call shape as type_review.py and
strategy_engine.py: a fixed system prompt, one single-turn `complete()` call,
then strict server-side validation of every field before it's ever trusted.
"""

import json

from src.llm.providers.base import LLMProvider

SYSTEM_PROMPT = (
    "You merge similar or duplicate category values within one column, based on a "
    "user's natural-language instruction. You will be given the column's current "
    "distinct values (each with its row count) and a command describing which values "
    "should be merged into which target label. Respond with ONLY a JSON object: "
    '{"groups": [{"target": "<label to keep>", "sources": ["<existing distinct value>", '
    '...]}]}. Every string in "sources" MUST be copied verbatim from the provided '
    "distinct-values list -- never invent one. \"target\" should also be copied verbatim "
    "from the list when the command is merging into an existing value; only use a new "
    "label if the user's command explicitly asks for one that isn't in the list. Only "
    "include groups the command actually affects -- do not propose merges the user "
    "didn't ask for. No markdown fences, no commentary."
)


def build_prompt(column: str, values: list[dict], command: str) -> str:
    values_desc = ", ".join(f"\"{v['value']}\" ({v['count']})" for v in values)
    return f'Column: "{column}"\nCurrent distinct values (value (row count)): {values_desc}\nCommand: {command}'


async def suggest_value_merge(
    column: str, values: list[dict], command: str, provider: LLMProvider
) -> list[dict]:
    """values: [{"value": str, "count": int}, ...] -- the column's current
    distinct values (already reflecting any previously-accepted merges).
    Returns [{"target": str, "sources": [str, ...]}, ...] groups. Every
    `sources` entry is checked against the real distinct-values list before
    being trusted: an LLM-invented value that was never actually in the
    column would otherwise match nothing at merge time (a silent no-op)
    rather than raising anything, so validating up front gives the user an
    honest proposal instead of one that quietly does less than it claims."""
    valid_values = {v["value"] for v in values}
    response = await provider.complete(build_prompt(column, values, command), system=SYSTEM_PROMPT, max_tokens=1024)
    parsed = json.loads(response)

    groups = parsed.get("groups")
    if not isinstance(groups, list):
        return []

    result = []
    for group in groups:
        if not isinstance(group, dict):
            continue
        target = group.get("target")
        sources = group.get("sources")
        if not isinstance(target, str) or not target.strip():
            continue
        if not isinstance(sources, list):
            continue
        valid_sources = [s for s in sources if isinstance(s, str) and s in valid_values]
        if not valid_sources:
            continue
        result.append({"target": target.strip(), "sources": valid_sources})
    return result
