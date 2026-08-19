import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import duckdb
import sqlglot
from sqlglot import exp
from starlette.concurrency import run_in_threadpool

from src.core.config import settings
from src.datasets.profiling import (
    CONFIDENCE_REVIEW_THRESHOLD,
    classify_column_with_confidence,
    compute_column_health,
    compute_dataset_health,
    detect_multi_value_separator,
    generate_alias,
)


class UnsafeQueryError(Exception):
    pass


class MalformedCsvError(Exception):
    pass


@dataclass
class ColumnSchema:
    name: str
    type: str
    alias: str
    category: str
    category_source: str  # "rule" | "ai" | "user"
    confidence: float
    needs_review: bool
    rationale: str | None
    null_count: int
    null_percentage: float
    distinct_count: int
    health_score: float
    # Set when a normalization pass (date or numeric-string) converted some of
    # this column's non-null values to NULL because they didn't match the
    # recognized format -- otherwise those losses would silently lower the
    # health score with no indication of why.
    conversion_warning: str | None = None
    # Set when this categorical column's cells look like they pack several
    # delimited tags into one string (see profiling.detect_multi_value_separator)
    # -- surfaced so the Column Types page can flag it and the Edit column
    # dialog can offer tag extraction/vocabulary curation.
    multi_value_separator: str | None = None


@dataclass
class QueryResult:
    columns: list[str]
    rows: list[list]
    row_count: int
    truncated: bool


@dataclass
class IngestResult:
    schema: list[ColumnSchema]
    row_count: int
    preview: QueryResult
    health_score: float


_TEXT_TYPES = {"VARCHAR", "CHAR", "TEXT", "BLOB"}

# Tokens CSV exports commonly use in place of a real value -- normalized to
# SQL NULL at ingest time so null counts/health scores reflect actual missing
# data instead of being masked by inconsistent sentinel strings.
_NULL_TOKENS = [
    "",
    "NA",
    "N/A",
    "n/a",
    "null",
    "NULL",
    "None",
    "none",
    "-",
    "--",
    "?",
    "unknown",
    "Unknown",
    "N.A.",
]
# Embedded directly as a SQL literal (not a bound parameter) since DuckDB's CSV
# reader takes `nullstr` as a table-function argument, not a query parameter;
# safe because the list is a fixed constant, never derived from user input.
_NULLSTR_LITERAL = "[" + ", ".join("'" + tok.replace("'", "''") + "'" for tok in _NULL_TOKENS) + "]"

# Candidate strptime formats tried, in order, against sampled column values to
# detect inconsistently-formatted date/datetime columns (see _looks_like_date_column).
_DATE_FORMAT_CANDIDATES = [
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%d",
    "%Y/%m/%d",
    "%m/%d/%Y",
    "%d/%m/%Y",
    "%m-%d-%Y",
    "%d-%m-%Y",
    "%B %d, %Y",
    "%b %d, %Y",
]
_DATE_FORMAT_MATCH_THRESHOLD = 0.8
_DATE_FORMAT_SAMPLE_SIZE = 500

# Matches currency/percentage-formatted numbers DuckDB's own auto-detection
# doesn't recognize (e.g. "$1,037.50", "1,037.50", "0%") -- these land as
# VARCHAR instead of a numeric type, so the whole numeric pipeline (health
# stats, histograms, bell curves) never sees them as numbers at all.
_NUMERIC_STRING_PATTERN = re.compile(r"^\s*-?\$?\s?(\d{1,3}(,\d{3})*|\d+)(\.\d+)?\s?%?\s*$")
_NUMERIC_FORMAT_MATCH_THRESHOLD = 0.8
_NUMERIC_FORMAT_SAMPLE_SIZE = 500

_MULTI_VALUE_SAMPLE_SIZE = 500


def _assert_readonly_select(sql: str) -> None:
    """Only a single SELECT/WITH statement is allowed — this SQL may come from an LLM."""
    try:
        statements = sqlglot.parse(sql, dialect="duckdb")
    except sqlglot.ParseError as exc:
        # SQL that doesn't even parse is exactly as unsafe as SQL that parses
        # into something other than a SELECT -- and LLM-generated SQL is far
        # more likely to be outright malformed than hand-typed SQL is.
        raise UnsafeQueryError(f"Could not parse SQL: {exc}") from exc
    if len(statements) != 1 or statements[0] is None:
        raise UnsafeQueryError("Exactly one SQL statement is allowed")
    if not isinstance(statements[0], (exp.Select, exp.With)):
        raise UnsafeQueryError("Only SELECT queries are allowed")


def _quote_ident(name: str) -> str:
    """Safely quote a DuckDB identifier. Column names come from uploaded CSV
    headers, so they're untrusted wherever they get interpolated into SQL text."""
    return '"' + name.replace('"', '""') + '"'


def _sql_string_literal(value: str) -> str:
    """Safely quote an untrusted string as a SQL literal (source/target
    values in a merge rule come from CSV data and/or LLM output)."""
    return "'" + value.replace("'", "''") + "'"


def _column_transform_expr(
    ident: str,
    replacements: list[dict] | None,
    merge_rules: list[dict] | None,
) -> str | None:
    """The read-time expression for one column, or None if it has neither
    replacement nor merge rules (the common case). Replacements are chained
    first -- each either a literal substring REPLACE or, when the rule's
    `is_regex` is set, a global regexp_replace (DuckDB's RE2 dialect, 'g'
    flag so every occurrence is replaced, not just the first) -- applied in
    rule order, and merge rules are matched against the *result* of that
    chain, so a merge added after a replacement sees already-replaced text,
    not the original. Always text: once a column has any rule, both branches
    of the resulting CASE (and every REPLACE/regexp_replace) operate on
    VARCHAR, so it reads as text everywhere from then on, even for values no
    rule touches."""
    text_expr = f"CAST({ident} AS VARCHAR)"
    for rule in replacements or []:
        find_lit = _sql_string_literal(rule["find"])
        replace_lit = _sql_string_literal(rule["replace"])
        if rule.get("is_regex"):
            text_expr = f"regexp_replace({text_expr}, {find_lit}, {replace_lit}, 'g')"
        else:
            text_expr = f"REPLACE({text_expr}, {find_lit}, {replace_lit})"

    when_clauses = []
    for rule in merge_rules or []:
        sources = rule.get("sources") or []
        if not sources:
            continue
        in_list = ", ".join(_sql_string_literal(s) for s in sources)
        when_clauses.append(f"WHEN {text_expr} IN ({in_list}) THEN {_sql_string_literal(rule['target'])}")

    if when_clauses:
        return f"CASE {' '.join(when_clauses)} ELSE {text_expr} END"
    if replacements:
        return text_expr
    return None


def _scope_to_column(
    rules: dict[str, list[dict]] | None, column: str
) -> dict[str, list[dict]] | None:
    """Narrows a dataset-wide rules dict down to just one column's own rules
    -- avoids building a REPLACE clause for every edited column when only one
    is actually being read (column_value_counts, count_replacement_effect)."""
    return {column: rules[column]} if rules and column in rules else None


def _column_transform_replace_clause(
    value_remaps: dict[str, list[dict]] | None,
    value_replacements: dict[str, list[dict]] | None,
) -> str:
    """Builds the `REPLACE (...)` clause of a `SELECT * REPLACE (...)` that
    applies every column's accepted merge and substring-replacement rules at
    read time -- the Parquet file itself is never rewritten (see CLAUDE.md),
    so an edit can only ever be layered on as a view-time expression, never
    an in-place write. Returns "" (no REPLACE clause at all) when there's
    nothing to transform, so callers can build a plain `SELECT * FROM ...`
    for the overwhelmingly common case of a dataset with no edits."""
    columns = set(value_remaps or {}) | set(value_replacements or {})
    if not columns:
        return ""

    parts = []
    for column in columns:
        ident = _quote_ident(column)
        expr = _column_transform_expr(
            ident, (value_replacements or {}).get(column), (value_remaps or {}).get(column)
        )
        if expr is not None:
            parts.append(f"{expr} AS {ident}")

    return f" REPLACE ({', '.join(parts)})" if parts else ""


def _tag_source_expr(ident: str, prefix_separator: str | None) -> str:
    """The text a multi-value column's cell should be split into tags from --
    already reflecting any value_remaps/value_replacements (the caller passes
    an `ident` that's read from the transformed view, not the raw column),
    plus this feature's own prefix-stripping: if `prefix_separator` occurs in
    the cell (e.g. "-" in "Hybrid - Pune, Noida"), only the text AFTER its
    first occurrence is kept -- the prefix itself (a work-mode label, not a
    tag) is discarded, not exploded into a bogus tag alongside the real ones."""
    text_expr = f"CAST({ident} AS VARCHAR)"
    if not prefix_separator:
        return text_expr
    sep_lit = _sql_string_literal(prefix_separator)
    return (
        f"CASE WHEN position({sep_lit} IN {text_expr}) > 0 "
        f"THEN substr({text_expr}, position({sep_lit} IN {text_expr}) + length({sep_lit})) "
        f"ELSE {text_expr} END"
    )


def build_tag_chart_sql(column: str, config: dict) -> str:
    """Deterministic (no LLM involved) SQL for a "count of rows per tag"
    chart on a multi-value column -- e.g. "location" holding "Mumbai, Pune"
    becomes one count each for Mumbai and Pune, not one bar for the whole
    packed string. `config`: {"prefix_separator", "tag_separator",
    "vocabulary", "include_other"} (see schemas.TagConfig). Executed via the
    same duckdb_manager.execute_query() every other chart uses, against the
    "data" view that already has value_remaps/value_replacements applied --
    so a tag chart reflects any merges/replacements made on this column too.

    No vocabulary yet: every exploded tag counts, uncurated -- lets the
    "Tags" panel show live candidates before the user has picked a vocabulary.
    A curated vocabulary without "include_other": only vocabulary tags count
    (everything else is silently excluded -- e.g. a stray "Remote" entry
    with no city at all). With "include_other": every non-vocabulary tag is
    folded into one "Other" bucket instead of being dropped, so the chart's
    total still accounts for every row."""
    ident = _quote_ident(column)
    text_expr = _tag_source_expr(ident, config.get("prefix_separator"))
    tag_sep_lit = _sql_string_literal(config.get("tag_separator") or ",")
    vocabulary = config.get("vocabulary") or []
    vocab_list = ", ".join(_sql_string_literal(v) for v in vocabulary)

    predicates = ["tag != ''"]
    if vocabulary and not config.get("include_other"):
        predicates.append(f"tag IN ({vocab_list})")
    label_expr = (
        f"CASE WHEN tag IN ({vocab_list}) THEN tag ELSE 'Other' END"
        if vocabulary and config.get("include_other")
        else "tag"
    )

    return (
        f"WITH exploded AS ("
        f"SELECT trim(unnest(string_split({text_expr}, {tag_sep_lit}))) AS tag "
        f"FROM data WHERE {ident} IS NOT NULL"
        f") "
        f"SELECT {label_expr} AS category, count(*) AS count "
        f"FROM exploded WHERE {' AND '.join(predicates)} "
        f"GROUP BY 1 ORDER BY 2 DESC"
    )


def _new_r2_connection() -> duckdb.DuckDBPyConnection:
    """A fresh connection configured to read/write R2 (S3-compatible) objects.

    A new connection per operation keeps concurrent requests isolated — DuckDB
    connections aren't safe to share across threads.
    """
    endpoint_url = settings.r2_endpoint_url
    use_ssl = endpoint_url.startswith("https://")
    endpoint_host = endpoint_url.split("://", 1)[-1]

    conn = duckdb.connect(":memory:")
    conn.execute("INSTALL httpfs")
    conn.execute("LOAD httpfs")
    conn.execute("SET s3_endpoint=?", [endpoint_host])
    conn.execute("SET s3_access_key_id=?", [settings.r2_access_key_id])
    conn.execute("SET s3_secret_access_key=?", [settings.r2_secret_access_key])
    conn.execute("SET s3_region='auto'")
    conn.execute("SET s3_url_style='path'")
    conn.execute(f"SET s3_use_ssl={'true' if use_ssl else 'false'}")
    return conn


def _s3_uri(key: str) -> str:
    return f"s3://{settings.r2_bucket_name}/{key}"


def _parses_as_date(value: str) -> bool:
    return any(_try_strptime(value, fmt) for fmt in _DATE_FORMAT_CANDIDATES)


def _try_strptime(value: str, fmt: str) -> bool:
    try:
        datetime.strptime(value, fmt)
        return True
    except ValueError:
        return False


def _sample_non_null_values(
    conn: duckdb.DuckDBPyConnection, table: str, column: str, sample_size: int
) -> list[str]:
    ident = _quote_ident(column)
    rows = conn.execute(
        f"SELECT {ident} FROM {table} WHERE {ident} IS NOT NULL LIMIT {sample_size}"
    ).fetchall()
    return [str(row[0]) for row in rows]


def _looks_like_date_column(conn: duckdb.DuckDBPyConnection, table: str, column: str) -> bool:
    """Sample a text column's non-null values and check whether most of them
    parse under *some* candidate format. Checked per-value against the whole
    candidate list (rather than requiring one format to fit the entire
    column) because a real-world export can mix formats row by row."""
    values = _sample_non_null_values(conn, table, column, _DATE_FORMAT_SAMPLE_SIZE)
    if not values:
        return False
    matched = sum(1 for value in values if _parses_as_date(value))
    return (matched / len(values)) >= _DATE_FORMAT_MATCH_THRESHOLD


def _looks_like_numeric_string_column(conn: duckdb.DuckDBPyConnection, table: str, column: str) -> bool:
    """Same sampling approach as _looks_like_date_column, but for
    currency/percentage-formatted numbers DuckDB's own type detection
    doesn't recognize."""
    values = _sample_non_null_values(conn, table, column, _NUMERIC_FORMAT_SAMPLE_SIZE)
    if not values:
        return False
    matched = sum(1 for value in values if _NUMERIC_STRING_PATTERN.match(value))
    return (matched / len(values)) >= _NUMERIC_FORMAT_MATCH_THRESHOLD


def _date_parse_expr(ident: str) -> str:
    """COALESCE across every candidate format, tried in order, so each row is
    parsed under whichever format it actually matches — this is what lets a
    column with genuinely mixed per-row formats normalize to one type."""
    attempts = ", ".join(f"try_strptime({ident}, '{fmt}')" for fmt in _DATE_FORMAT_CANDIDATES)
    return f"COALESCE({attempts})"


def _numeric_strip_expr(ident: str) -> str:
    """Strip the currency/percentage/thousands-separator characters DuckDB's
    numeric parser doesn't tolerate, then cast -- a value that still doesn't
    parse (e.g. genuinely non-numeric text) becomes NULL rather than erroring."""
    stripped = ident
    for token in ("$", ",", "%"):
        stripped = f"REPLACE({stripped}, '{token}', '')"
    return f"TRY_CAST(TRIM({stripped}) AS DOUBLE)"


def _count_conversion_losses(
    conn: duckdb.DuckDBPyConnection, table: str, column: str, parse_expr: str
) -> tuple[int, int]:
    """Returns (non_null_before, newly_null_after) for a column about to be
    rewritten via parse_expr -- lets normalization passes warn when they
    silently drop some values to NULL instead of converting them."""
    ident = _quote_ident(column)
    non_null_before, newly_null = conn.execute(
        f"SELECT count(*) FILTER (WHERE {ident} IS NOT NULL), "
        f"count(*) FILTER (WHERE {ident} IS NOT NULL AND {parse_expr} IS NULL) FROM {table}"
    ).fetchone()
    return non_null_before, newly_null


def _normalize_dates(conn: duckdb.DuckDBPyConnection, table: str) -> dict[str, str]:
    """Detect free-text columns holding dates in inconsistent (possibly
    mixed, row-by-row) formats and rewrite them as native DATE columns with
    one canonical representation. Returns a column-name -> warning message
    for any column where some non-null values didn't match a recognized
    format and were converted to NULL."""
    columns = conn.execute(f"DESCRIBE {table}").fetchall()
    date_columns = [
        name
        for name, duckdb_type, *_ in columns
        if duckdb_type.split("(")[0].strip().upper() in _TEXT_TYPES
        and _looks_like_date_column(conn, table, name)
    ]
    if not date_columns:
        return {}

    warnings: dict[str, str] = {}
    replace_clauses = []
    for col in date_columns:
        ident = _quote_ident(col)
        parse_expr = _date_parse_expr(ident)
        non_null_before, newly_null = _count_conversion_losses(conn, table, col, parse_expr)
        if newly_null:
            warnings[col] = (
                f"{newly_null} of {non_null_before} non-null values did not match a "
                "recognized date format and were set to NULL."
            )
        replace_clauses.append(f"{parse_expr}::DATE AS {ident}")

    conn.execute(
        f"CREATE OR REPLACE TABLE {table} AS SELECT * REPLACE ({', '.join(replace_clauses)}) FROM {table}"
    )
    return warnings


def _normalize_numeric_strings(conn: duckdb.DuckDBPyConnection, table: str) -> dict[str, str]:
    """Detect text columns holding currency/percentage-formatted numbers
    (e.g. "$1,037.50", "0%") and rewrite them as native DOUBLE columns so the
    numeric pipeline (health stats, histograms, bell curves) can see them.
    Returns a column-name -> warning message for any column where some
    non-null values weren't recognized as numbers and were set to NULL."""
    columns = conn.execute(f"DESCRIBE {table}").fetchall()
    numeric_columns = [
        name
        for name, duckdb_type, *_ in columns
        if duckdb_type.split("(")[0].strip().upper() in _TEXT_TYPES
        and _looks_like_numeric_string_column(conn, table, name)
    ]
    if not numeric_columns:
        return {}

    warnings: dict[str, str] = {}
    replace_clauses = []
    for col in numeric_columns:
        ident = _quote_ident(col)
        parse_expr = _numeric_strip_expr(ident)
        non_null_before, newly_null = _count_conversion_losses(conn, table, col, parse_expr)
        if newly_null:
            warnings[col] = (
                f"{newly_null} of {non_null_before} non-null values were not recognized as "
                "numbers (after stripping $/,/%) and were set to NULL."
            )
        replace_clauses.append(f"{parse_expr} AS {ident}")

    conn.execute(
        f"CREATE OR REPLACE TABLE {table} AS SELECT * REPLACE ({', '.join(replace_clauses)}) FROM {table}"
    )
    return warnings


_GENERIC_COLUMN_NAME = re.compile(r"column\d+")


def _assert_csv_parsed_cleanly(conn: duckdb.DuckDBPyConnection, table: str) -> None:
    """DuckDB's CSV sniffer can silently recover from a malformed file in
    ways that produce a technically-valid but nonsense schema instead of
    raising anything -- this would otherwise sail through as a "successful"
    upload. Two known shapes, both reproduced from a real ragged/quoting bug:
    1. A row whose field count doesn't match the header's (e.g. an unquoted
       value that embeds the delimiter) makes DuckDB discard the header
       entirely and fall back to generic `column0, column1, ...` names.
    2. Rarer: the whole file collapses into one text column whose "name" is
       the unsplit header line itself (still contains a comma)."""
    columns = conn.execute(f"DESCRIBE {table}").fetchall()
    names = [name for name, *_ in columns]
    if len(names) == 1 and "," in names[0]:
        raise MalformedCsvError(
            "Could not parse this CSV into columns -- check for inconsistent quoting, "
            "delimiters, or unescaped commas in the source file."
        )
    if names and all(_GENERIC_COLUMN_NAME.fullmatch(name) for name in names):
        raise MalformedCsvError(
            "CSV rows don't consistently match the header's column count -- check for "
            "unescaped delimiters or inconsistent quoting in the source file."
        )


def _profile_columns(
    conn: duckdb.DuckDBPyConnection,
    table: str,
    row_count: int,
    conversion_warnings: dict[str, str] | None = None,
) -> list[ColumnSchema]:
    conversion_warnings = conversion_warnings or {}
    columns = conn.execute(f"DESCRIBE {table}").fetchall()
    profiles = []
    for name, duckdb_type, *_ in columns:
        ident = _quote_ident(name)
        null_count, distinct_count = conn.execute(
            f"SELECT count(*) FILTER (WHERE {ident} IS NULL), count(DISTINCT {ident}) FROM {table}"
        ).fetchone()

        base_type = duckdb_type.split("(")[0].strip().upper()
        avg_length = None
        if base_type in _TEXT_TYPES:
            avg_length = conn.execute(
                f"SELECT avg(length({ident})) FROM {table} WHERE {ident} IS NOT NULL"
            ).fetchone()[0]

        category, confidence = classify_column_with_confidence(
            duckdb_type=duckdb_type,
            row_count=row_count,
            distinct_count=distinct_count,
            avg_length=avg_length,
            column_name=name,
        )
        null_percentage = round((null_count / row_count) * 100, 1) if row_count else 0.0

        multi_value_separator = None
        if category.value == "categorical" and base_type in _TEXT_TYPES:
            sample = _sample_non_null_values(conn, table, name, _MULTI_VALUE_SAMPLE_SIZE)
            multi_value_separator = detect_multi_value_separator(sample)

        profiles.append(
            ColumnSchema(
                name=name,
                type=duckdb_type,
                alias=generate_alias(name),
                category=category.value,
                category_source="rule",
                confidence=confidence,
                needs_review=confidence < CONFIDENCE_REVIEW_THRESHOLD,
                rationale=None,
                null_count=null_count,
                null_percentage=null_percentage,
                distinct_count=distinct_count,
                health_score=compute_column_health(row_count, null_count),
                conversion_warning=conversion_warnings.get(name),
                multi_value_separator=multi_value_separator,
            )
        )
    return profiles


def _preview(
    conn: duckdb.DuckDBPyConnection, from_clause: str, limit: int, replace_clause: str = ""
) -> QueryResult:
    cursor = conn.execute(f"SELECT *{replace_clause} FROM {from_clause} LIMIT {limit}")
    columns = [d[0] for d in cursor.description]
    rows = [list(row) for row in cursor.fetchall()]
    return QueryResult(columns=columns, rows=rows, row_count=len(rows), truncated=False)


class DuckDBManager:
    """Ingests CSVs into Parquet-on-R2 and serves SQL directly against R2 — no
    per-dataset state is kept locally, so the service can restart or scale
    freely (Render's free tier spins down when idle).
    """

    def ingest_and_export(self, csv_path: Path, parquet_key: str) -> IngestResult:
        conn = _new_r2_connection()
        try:
            # DuckDB's own CSV reader streams the file directly from disk —
            # the rows never pass through a Python object. `nullstr` folds
            # common null sentinels into real SQL NULLs during the same pass.
            conn.execute(
                "CREATE TABLE data AS SELECT * FROM "
                f"read_csv(?, auto_detect=true, nullstr={_NULLSTR_LITERAL})",
                [str(csv_path)],
            )
            _assert_csv_parsed_cleanly(conn, "data")

            conversion_warnings = _normalize_dates(conn, "data")
            conversion_warnings.update(_normalize_numeric_strings(conn, "data"))

            row_count = conn.execute("SELECT count(*) FROM data").fetchone()[0]
            profiles = _profile_columns(conn, "data", row_count, conversion_warnings)
            preview = _preview(conn, "data", limit=20)
            health_score = compute_dataset_health([p.health_score for p in profiles])

            conn.execute("COPY data TO ? (FORMAT PARQUET)", [_s3_uri(parquet_key)])

            return IngestResult(
                schema=profiles, row_count=row_count, preview=preview, health_score=health_score
            )
        finally:
            conn.close()

    async def execute_query(
        self,
        parquet_key: str,
        sql: str,
        max_rows: int | None = None,
        value_remaps: dict[str, list[dict]] | None = None,
        value_replacements: dict[str, list[dict]] | None = None,
    ) -> QueryResult:
        max_rows = max_rows or settings.query_max_rows
        _assert_readonly_select(sql)
        return await run_in_threadpool(
            self._execute_sync, parquet_key, sql, max_rows, value_remaps, value_replacements
        )

    def _execute_sync(
        self,
        parquet_key: str,
        sql: str,
        max_rows: int,
        value_remaps: dict[str, list[dict]] | None,
        value_replacements: dict[str, list[dict]] | None,
    ) -> QueryResult:
        # DuckDB doesn't support prepared parameters in CREATE VIEW, so the URI is
        # interpolated directly — safe here because parquet_key is always a
        # server-generated "{uuid4}.parquet" key, never derived from user input.
        if "'" in parquet_key or ";" in parquet_key:
            raise UnsafeQueryError("Invalid dataset storage key")

        conn = _new_r2_connection()
        try:
            replace_clause = _column_transform_replace_clause(value_remaps, value_replacements)
            conn.execute(
                f"CREATE VIEW data AS SELECT *{replace_clause} FROM read_parquet('{_s3_uri(parquet_key)}')"
            )
            cursor = conn.execute(sql)
            columns = [description[0] for description in cursor.description]
            rows = cursor.fetchmany(max_rows + 1)
            truncated = len(rows) > max_rows
            return QueryResult(
                columns=columns,
                rows=[list(row) for row in rows[:max_rows]],
                row_count=min(len(rows), max_rows),
                truncated=truncated,
            )
        finally:
            conn.close()

    async def preview_dataset(
        self,
        parquet_key: str,
        limit: int = 20,
        value_remaps: dict[str, list[dict]] | None = None,
        value_replacements: dict[str, list[dict]] | None = None,
    ) -> QueryResult:
        """A fixed, non-user-supplied `SELECT * LIMIT n` against the stored
        Parquet — used by the schema API to serve a fresh preview without
        needing the readonly-SQL guard that arbitrary query SQL requires."""
        return await run_in_threadpool(
            self._preview_sync, parquet_key, limit, value_remaps, value_replacements
        )

    def _preview_sync(
        self,
        parquet_key: str,
        limit: int,
        value_remaps: dict[str, list[dict]] | None,
        value_replacements: dict[str, list[dict]] | None,
    ) -> QueryResult:
        if "'" in parquet_key or ";" in parquet_key:
            raise UnsafeQueryError("Invalid dataset storage key")

        conn = _new_r2_connection()
        try:
            replace_clause = _column_transform_replace_clause(value_remaps, value_replacements)
            return _preview(
                conn, f"read_parquet('{_s3_uri(parquet_key)}')", int(limit), replace_clause
            )
        finally:
            conn.close()

    async def column_value_counts(
        self,
        parquet_key: str,
        column: str,
        limit: int = 200,
        value_remaps: dict[str, list[dict]] | None = None,
        value_replacements: dict[str, list[dict]] | None = None,
    ) -> list[tuple[str, int]]:
        """Distinct values (as their string representation, post-edit) and
        row counts for one column, most frequent first -- backs the "Edit
        column" dialog's value list. Capped at `limit` distinct values; a
        column with more distinct values than that only shows its most
        common ones, since this is a UI aid, not an exhaustive export."""
        return await run_in_threadpool(
            self._column_value_counts_sync, parquet_key, column, limit, value_remaps, value_replacements
        )

    def _column_value_counts_sync(
        self,
        parquet_key: str,
        column: str,
        limit: int,
        value_remaps: dict[str, list[dict]] | None,
        value_replacements: dict[str, list[dict]] | None,
    ) -> list[tuple[str, int]]:
        if "'" in parquet_key or ";" in parquet_key:
            raise UnsafeQueryError("Invalid dataset storage key")

        conn = _new_r2_connection()
        try:
            # Only this column's own rules matter for its value list -- no
            # need to build a REPLACE clause for every edited column in the
            # dataset just to read one of them.
            replace_clause = _column_transform_replace_clause(
                _scope_to_column(value_remaps, column), _scope_to_column(value_replacements, column)
            )
            conn.execute(
                f"CREATE VIEW data AS SELECT *{replace_clause} FROM read_parquet('{_s3_uri(parquet_key)}')"
            )
            ident = _quote_ident(column)
            rows = conn.execute(
                f"SELECT CAST({ident} AS VARCHAR), count(*) FROM data "
                f"WHERE {ident} IS NOT NULL GROUP BY 1 ORDER BY 2 DESC LIMIT {int(limit)}"
            ).fetchall()
            return [(row[0], row[1]) for row in rows]
        finally:
            conn.close()

    async def count_replacement_effect(
        self,
        parquet_key: str,
        column: str,
        find: str,
        replace: str,
        is_regex: bool = False,
        value_remaps: dict[str, list[dict]] | None = None,
        value_replacements: dict[str, list[dict]] | None = None,
    ) -> int:
        """How many rows' current text for `column` (after whatever rules
        already apply, via value_remaps/value_replacements) would actually
        CHANGE if this find/replace were applied -- used to report how many
        rows a *new* replacement rule is about to affect, before it's
        persisted. Deliberately checks the post-replace result differs from
        the current value, not just whether `find` matches: a regex like
        "New York.*" matches the value "New York" too, but replacing it with
        "New York" is a no-op for that row -- counting matches instead of
        actual changes would overcount."""
        return await run_in_threadpool(
            self._count_replacement_effect_sync,
            parquet_key,
            column,
            find,
            replace,
            is_regex,
            value_remaps,
            value_replacements,
        )

    def _count_replacement_effect_sync(
        self,
        parquet_key: str,
        column: str,
        find: str,
        replace: str,
        is_regex: bool,
        value_remaps: dict[str, list[dict]] | None,
        value_replacements: dict[str, list[dict]] | None,
    ) -> int:
        if "'" in parquet_key or ";" in parquet_key:
            raise UnsafeQueryError("Invalid dataset storage key")

        conn = _new_r2_connection()
        try:
            replace_clause = _column_transform_replace_clause(
                _scope_to_column(value_remaps, column), _scope_to_column(value_replacements, column)
            )
            conn.execute(
                f"CREATE VIEW data AS SELECT *{replace_clause} FROM read_parquet('{_s3_uri(parquet_key)}')"
            )
            ident = _quote_ident(column)
            text_expr = f"CAST({ident} AS VARCHAR)"
            find_lit = _sql_string_literal(find)
            replace_lit = _sql_string_literal(replace)
            after_expr = (
                f"regexp_replace({text_expr}, {find_lit}, {replace_lit}, 'g')"
                if is_regex
                else f"REPLACE({text_expr}, {find_lit}, {replace_lit})"
            )
            row = conn.execute(
                f"SELECT count(*) FROM data WHERE {text_expr} IS DISTINCT FROM {after_expr}"
            ).fetchone()
            return row[0]
        finally:
            conn.close()

    async def column_distinct_count(
        self,
        parquet_key: str,
        column: str,
        value_remaps: dict[str, list[dict]] | None = None,
        value_replacements: dict[str, list[dict]] | None = None,
    ) -> int:
        """The column's true distinct-value count after whatever rules
        already apply -- NOT capped like column_value_counts' returned list,
        so it stays accurate even if the column has more distinct values
        than that list shows. Backs the "N categories" figure shown in the
        Column Types listing and the Edit column dialog, so a user can see
        how much a proposed merge/replace would shrink that number by."""
        return await run_in_threadpool(
            self._column_distinct_count_sync, parquet_key, column, value_remaps, value_replacements
        )

    def _column_distinct_count_sync(
        self,
        parquet_key: str,
        column: str,
        value_remaps: dict[str, list[dict]] | None,
        value_replacements: dict[str, list[dict]] | None,
    ) -> int:
        if "'" in parquet_key or ";" in parquet_key:
            raise UnsafeQueryError("Invalid dataset storage key")

        conn = _new_r2_connection()
        try:
            replace_clause = _column_transform_replace_clause(
                _scope_to_column(value_remaps, column), _scope_to_column(value_replacements, column)
            )
            conn.execute(
                f"CREATE VIEW data AS SELECT *{replace_clause} FROM read_parquet('{_s3_uri(parquet_key)}')"
            )
            ident = _quote_ident(column)
            row = conn.execute(f"SELECT count(DISTINCT {ident}) FROM data").fetchone()
            return row[0]
        finally:
            conn.close()

    async def tag_candidates(
        self,
        parquet_key: str,
        column: str,
        prefix_separator: str | None,
        tag_separator: str,
        limit: int = 200,
        value_remaps: dict[str, list[dict]] | None = None,
        value_replacements: dict[str, list[dict]] | None = None,
    ) -> list[tuple[str, int]]:
        """Every distinct tag a multi-value column's cells explode into under
        the given separators, with row counts, most frequent first -- backs
        the "Tags" panel's candidate list a user curates into a vocabulary.
        Uncurated (no vocabulary filter) by design: this is what lets the
        panel show what's actually in the data before any vocabulary exists."""
        return await run_in_threadpool(
            self._tag_candidates_sync,
            parquet_key,
            column,
            prefix_separator,
            tag_separator,
            limit,
            value_remaps,
            value_replacements,
        )

    def _tag_candidates_sync(
        self,
        parquet_key: str,
        column: str,
        prefix_separator: str | None,
        tag_separator: str,
        limit: int,
        value_remaps: dict[str, list[dict]] | None,
        value_replacements: dict[str, list[dict]] | None,
    ) -> list[tuple[str, int]]:
        if "'" in parquet_key or ";" in parquet_key:
            raise UnsafeQueryError("Invalid dataset storage key")

        conn = _new_r2_connection()
        try:
            replace_clause = _column_transform_replace_clause(
                _scope_to_column(value_remaps, column), _scope_to_column(value_replacements, column)
            )
            conn.execute(
                f"CREATE VIEW data AS SELECT *{replace_clause} FROM read_parquet('{_s3_uri(parquet_key)}')"
            )
            ident = _quote_ident(column)
            text_expr = _tag_source_expr(ident, prefix_separator)
            tag_sep_lit = _sql_string_literal(tag_separator)
            rows = conn.execute(
                f"SELECT trim(tag) AS t, count(*) FROM ("
                f"SELECT unnest(string_split({text_expr}, {tag_sep_lit})) AS tag "
                f"FROM data WHERE {ident} IS NOT NULL"
                f") WHERE trim(tag) != '' GROUP BY 1 ORDER BY 2 DESC LIMIT {int(limit)}"
            ).fetchall()
            return [(row[0], row[1]) for row in rows]
        finally:
            conn.close()

    async def tag_distinct_count(
        self,
        parquet_key: str,
        column: str,
        prefix_separator: str | None,
        tag_separator: str,
        value_remaps: dict[str, list[dict]] | None = None,
        value_replacements: dict[str, list[dict]] | None = None,
    ) -> int:
        """The true, uncapped count of distinct tags under the given
        separators -- NOT capped like tag_candidates' returned list, so the
        "Tags" panel can tell whether its (capped) candidate list is showing
        everything or whether there's more to page through."""
        return await run_in_threadpool(
            self._tag_distinct_count_sync,
            parquet_key,
            column,
            prefix_separator,
            tag_separator,
            value_remaps,
            value_replacements,
        )

    def _tag_distinct_count_sync(
        self,
        parquet_key: str,
        column: str,
        prefix_separator: str | None,
        tag_separator: str,
        value_remaps: dict[str, list[dict]] | None,
        value_replacements: dict[str, list[dict]] | None,
    ) -> int:
        if "'" in parquet_key or ";" in parquet_key:
            raise UnsafeQueryError("Invalid dataset storage key")

        conn = _new_r2_connection()
        try:
            replace_clause = _column_transform_replace_clause(
                _scope_to_column(value_remaps, column), _scope_to_column(value_replacements, column)
            )
            conn.execute(
                f"CREATE VIEW data AS SELECT *{replace_clause} FROM read_parquet('{_s3_uri(parquet_key)}')"
            )
            ident = _quote_ident(column)
            text_expr = _tag_source_expr(ident, prefix_separator)
            tag_sep_lit = _sql_string_literal(tag_separator)
            row = conn.execute(
                f"SELECT count(DISTINCT trim(tag)) FROM ("
                f"SELECT unnest(string_split({text_expr}, {tag_sep_lit})) AS tag "
                f"FROM data WHERE {ident} IS NOT NULL"
                f") WHERE trim(tag) != ''"
            ).fetchone()
            return row[0]
        finally:
            conn.close()


duckdb_manager = DuckDBManager()
