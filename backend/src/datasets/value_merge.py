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
import re

from src.llm.providers.base import LLMProvider

# Matches a literal "replace 'X' with 'Y'" command (straight or curly quotes,
# case-insensitive) -- deliberately NOT sent to the LLM: unlike a merge
# ("which values are duplicates of each other?", a judgment call), a literal
# substring replacement is fully specified by the command itself, so parsing
# it with a regex is both cheaper and more reliable than an LLM round trip.
# Only commands matching this exact shape skip the LLM; anything else (e.g.
# "merge NY and New York into New York") falls through to suggest_value_merge.
_REPLACE_COMMAND = re.compile(
    r"""^\s*replace\s+['"“”](?P<find>.+?)['"“”]\s+with\s+['"“”](?P<replace>.*?)['"“”]\s*$""",
    re.IGNORECASE,
)

# Same shape, marked with an explicit "regex" keyword -- e.g.
# `replace regex 'Kolkata\(.*\)' with 'Kolkata'` to strip any parenthetical
# qualifier. Checked BEFORE _REPLACE_COMMAND since it's the more specific of
# the two shapes (a plain "replace 'X' with 'Y'" should never itself be
# treated as a regex, since a literal find like "Delhi / NCR" or "St. Louis"
# contains regex metacharacters that aren't meant to be interpreted as such).
_REPLACE_REGEX_COMMAND = re.compile(
    r"""^\s*replace\s+regex\s+['"“”](?P<find>.+?)['"“”]\s+with\s+['"“”](?P<replace>.*?)['"“”]\s*$""",
    re.IGNORECASE,
)


class InvalidRegexError(Exception):
    pass


def parse_replace_command(command: str) -> tuple[str, str, bool] | None:
    """Returns (find, replace, is_regex) if `command` is a literal or regex
    replace instruction, else None (the caller should fall back to the
    LLM-based merge flow). Raises InvalidRegexError if a "replace regex ..."
    command's pattern doesn't even compile -- a clear, immediate error beats
    a confusing DuckDB failure much later at accept time. This is only a
    sanity check (Python's `re`, not DuckDB's actual RE2 engine), so it
    catches outright typos, not every RE2/Python syntax difference."""
    match = _REPLACE_REGEX_COMMAND.match(command)
    if match is not None:
        find = match.group("find").strip()
        if not find:
            return None
        try:
            re.compile(find)
        except re.error as exc:
            raise InvalidRegexError(f"{find!r} is not a valid regular expression: {exc}") from exc
        return find, match.group("replace").strip(), True

    match = _REPLACE_COMMAND.match(command)
    if match is None:
        return None
    find = match.group("find").strip()
    if not find:
        return None
    return find, match.group("replace").strip(), False

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
