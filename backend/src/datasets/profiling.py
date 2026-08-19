"""Pure functions for classifying columns and generating human-readable
aliases -- no DuckDB dependency, so they're cheap to unit test directly.
Used by duckdb_manager.py during ingestion to build each dataset's schema.
"""

import re
from enum import Enum

_NUMERIC_TYPES = {
    "TINYINT",
    "SMALLINT",
    "INTEGER",
    "BIGINT",
    "HUGEINT",
    "UTINYINT",
    "USMALLINT",
    "UINTEGER",
    "UBIGINT",
    "FLOAT",
    "DOUBLE",
    "DECIMAL",
    "REAL",
}
_DATE_TYPES = {"DATE", "TIMESTAMP", "TIMESTAMP WITH TIME ZONE", "TIMESTAMPTZ", "TIME"}
_TEXT_TYPES = {"VARCHAR", "CHAR", "TEXT", "BLOB"}

# Numeric columns with at most this many distinct values are treated as
# categorical (e.g. a 1-5 rating or a region code) rather than continuous.
# This is an absolute cap, not a ratio of row count, because a genuinely
# continuous quantity like age or marks can still have a modest distinct
# count in a small dataset while still being conceptually continuous.
NUMERIC_CATEGORICAL_MAX_DISTINCT = 20
# The text-categorical cap scales with row count (floored at this minimum) --
# a flat cap would flag a low-cardinality column like `job_title` (65 distinct
# values across 5,000 rows, a 1.3% ratio) for needless review just because 65
# exceeds a fixed number that was sized for much smaller datasets.
TEXT_CATEGORICAL_MAX_DISTINCT = 50
TEXT_CATEGORICAL_DISTINCT_RATIO = 0.05
FREE_TEXT_AVG_LENGTH = 40

# Candidate delimiters for a "multi-value" categorical column -- one whose
# cells actually hold a delimited list of several tags packed into one
# string (e.g. a "location" column with values like "Mumbai, Pune"), rather
# than one atomic label per row. Checked in this order since a comma is by
# far the most common real-world delimiter for this pattern; a column
# matching an earlier candidate never gets checked against a later one.
MULTI_VALUE_SEPARATOR_CANDIDATES = [",", ";", "|", "/"]
# Fraction of sampled non-null values that must split into 2+ non-blank
# tokens under a candidate separator for the column to be flagged.
MULTI_VALUE_MATCH_THRESHOLD = 0.5

# A "range" column's cells hold a min-max numeric range, optionally with a
# trailing unit (e.g. "4-10 yrs", "18-25", "2.5-4.0 km") -- text DuckDB's own
# type inference will never treat as numeric, so it never becomes a
# chartable measure on its own. Only non-negative numbers are matched
# (real-world ranges in this shape essentially always are), which also
# sidesteps "-" being ambiguous between range separator and a negative sign.
_RANGE_PATTERN = re.compile(r"^\s*(\d+(?:\.\d+)?)\s*-\s*(\d+(?:\.\d+)?)\s*([A-Za-z]*)\s*$")
RANGE_MATCH_THRESHOLD = 0.5


def detect_range_pattern(values: list[str]) -> tuple[str, str | None] | None:
    """Flags a text column whose cells hold a numeric range like "4-10 yrs"
    rather than one atomic value -- a different shape from both an ordinary
    categorical column and a multi-value/tag column, since a chart over it
    needs a single representative number per row (its midpoint, by default),
    not the whole range string treated as one bar or exploded into tags.
    `values` should be a sample of the column's non-null raw values. Returns
    (separator, unit) -- currently "-" is the only supported separator, and
    `unit` is the most common non-empty trailing token across matches (or
    None if matches never had one) -- or None entirely if the column doesn't
    look like a range column."""
    if not values:
        return None
    matches = 0
    units: dict[str, int] = {}
    for value in values:
        match = _RANGE_PATTERN.match(value)
        if not match:
            continue
        matches += 1
        unit = match.group(3).strip()
        if unit:
            units[unit] = units.get(unit, 0) + 1
    if matches / len(values) < RANGE_MATCH_THRESHOLD:
        return None
    unit = max(units, key=units.get) if units else None
    return "-", unit

# Column-name tokens (after splitting snake_case/camelCase) that suggest an
# identifier/code rather than a genuinely continuous quantity -- cardinality
# alone can't distinguish "thousands of legitimate zip codes" from "a real
# continuous metric like revenue"; only the column name signals that.
_IDENTIFIER_NAME_TOKENS = {
    "id",
    "code",
    "zip",
    "zipcode",
    "postal",
    "postalcode",
    "pin",
    "pincode",
    "phone",
    "phonenumber",
    "ssn",
    "isbn",
    "sku",
    "ein",
    "vin",
}

# Columns whose rule-based confidence falls below this are flagged
# `needs_review` -- surfaced in the type-review page and eligible for the
# AI-assisted review pass (see src/datasets/type_review.py).
CONFIDENCE_REVIEW_THRESHOLD = 70.0


class ColumnCategory(str, Enum):
    DATETIME = "datetime"
    CONTINUOUS_NUMERICAL = "continuous_numerical"
    CATEGORICAL = "categorical"
    FREE_TEXT = "free_text"


def classify_column(
    *,
    duckdb_type: str,
    row_count: int,
    distinct_count: int,
    avg_length: float | None = None,
    column_name: str = "",
) -> ColumnCategory:
    """Categorize a column as Datetime, Continuous Numerical, Categorical, or
    Free Text from its DuckDB type plus cheap summary statistics."""
    return classify_column_with_confidence(
        duckdb_type=duckdb_type,
        row_count=row_count,
        distinct_count=distinct_count,
        avg_length=avg_length,
        column_name=column_name,
    )[0]


def classify_column_with_confidence(
    *,
    duckdb_type: str,
    row_count: int,
    distinct_count: int,
    avg_length: float | None = None,
    column_name: str = "",
) -> tuple[ColumnCategory, float]:
    """Same classification as classify_column(), plus a 0-100 confidence
    score based on how far the column's stats sit from the decision boundary
    -- a column right at a threshold is a coin flip; one far from it is not.
    Confidence below CONFIDENCE_REVIEW_THRESHOLD marks a column as a good
    candidate for AI-assisted or human review."""
    base_type = duckdb_type.split("(")[0].strip().upper()

    if base_type in _DATE_TYPES:
        return ColumnCategory.DATETIME, 99.0

    if base_type == "BOOLEAN":
        return ColumnCategory.CATEGORICAL, 99.0

    if base_type in _NUMERIC_TYPES:
        if distinct_count > NUMERIC_CATEGORICAL_MAX_DISTINCT and _looks_like_identifier_name(column_name):
            # A numeric identifier (zip/phone/SKU/...) can have thousands of
            # legitimate distinct values -- cardinality alone would call that
            # continuous. Confidence is capped below the review threshold
            # since a name-based heuristic is more failure-prone than the
            # type/cardinality checks above it.
            return ColumnCategory.CATEGORICAL, 65.0
        distance_ratio = abs(distinct_count - NUMERIC_CATEGORICAL_MAX_DISTINCT) / max(
            NUMERIC_CATEGORICAL_MAX_DISTINCT, 1
        )
        confidence = round(60.0 + min(distance_ratio, 1.0) * 39.0, 1)
        if distinct_count <= NUMERIC_CATEGORICAL_MAX_DISTINCT:
            return ColumnCategory.CATEGORICAL, confidence
        return ColumnCategory.CONTINUOUS_NUMERICAL, confidence

    # Text-like column (VARCHAR and friends).
    if row_count == 0:
        return ColumnCategory.CATEGORICAL, 50.0

    distinct_ratio = distinct_count / row_count
    # The absolute cap is floored at TEXT_CATEGORICAL_MAX_DISTINCT (so small
    # datasets keep the same protection as before) but scales with row count
    # above that floor, so a bigger dataset isn't penalized for having
    # proportionally the same spread (e.g. 65 distinct job titles across
    # 5,000 rows). The ratio check stays as its own condition -- dropping it
    # in favor of the cap alone would wrongly call an all-unique column
    # categorical whenever distinct_count happens to sit at/under the floor
    # (e.g. 50 distinct values across exactly 50 rows).
    effective_cap = max(TEXT_CATEGORICAL_MAX_DISTINCT, row_count * TEXT_CATEGORICAL_DISTINCT_RATIO)
    if distinct_count <= effective_cap and distinct_ratio <= TEXT_CATEGORICAL_DISTINCT_RATIO:
        headroom = (TEXT_CATEGORICAL_DISTINCT_RATIO - distinct_ratio) / TEXT_CATEGORICAL_DISTINCT_RATIO
        return ColumnCategory.CATEGORICAL, round(60.0 + min(headroom, 1.0) * 39.0, 1)
    if avg_length is not None and avg_length > FREE_TEXT_AVG_LENGTH:
        return ColumnCategory.FREE_TEXT, 85.0
    if distinct_ratio > 0.5:
        excess = (distinct_ratio - 0.5) / 0.5
        return ColumnCategory.FREE_TEXT, round(60.0 + min(excess, 1.0) * 39.0, 1)
    return ColumnCategory.CATEGORICAL, 55.0


def detect_multi_value_separator(values: list[str]) -> str | None:
    """Flags a categorical text column whose cells actually pack several
    tags into one string (e.g. "Mumbai, Pune") rather than holding one
    atomic label per row -- a genuinely different shape from an ordinary
    categorical column, since a chart "by category" on it should count each
    packed tag separately, not treat the whole packed string as one bar.
    `values` should be a sample of the column's non-null raw values. Returns
    the first candidate separator (see MULTI_VALUE_SEPARATOR_CANDIDATES) that
    a large-enough fraction of the sample actually splits on into 2+
    non-blank tokens, or None if the column doesn't look multi-value at all."""
    if not values:
        return None
    for separator in MULTI_VALUE_SEPARATOR_CANDIDATES:
        matches = sum(
            1 for v in values if len([token for token in v.split(separator) if token.strip()]) >= 2
        )
        if matches / len(values) >= MULTI_VALUE_MATCH_THRESHOLD:
            return separator
    return None


def compute_column_health(row_count: int, null_count: int) -> float:
    """Completeness score (0-100): the percentage of non-null values."""
    if row_count == 0:
        return 0.0
    return round((1 - null_count / row_count) * 100, 1)


def compute_dataset_health(column_health_scores: list[float]) -> float:
    """Dataset-level health score: the mean of its columns' completeness."""
    if not column_health_scores:
        return 100.0
    return round(sum(column_health_scores) / len(column_health_scores), 1)


_ABBREVIATIONS = {
    "id": "ID",
    "dob": "Date of Birth",
    "amt": "Amount",
    "qty": "Quantity",
    "num": "Number",
    "no": "Number",
    "desc": "Description",
    "addr": "Address",
    "txn": "Transaction",
    "cust": "Customer",
    "emp": "Employee",
    "dept": "Department",
    "org": "Organization",
    "pct": "Percentage",
    "avg": "Average",
    "min": "Minimum",
    "max": "Maximum",
    "std": "Standard",
    "dt": "Date",
    "yr": "Year",
    "mo": "Month",
    "qtr": "Quarter",
    "rev": "Revenue",
    "nm": "Name",
    "phn": "Phone",
    "tel": "Phone",
}


def _split_words(column_name: str) -> list[str]:
    """Split a raw CSV header into words on snake_case/kebab-case separators
    and camelCase boundaries -- shared by generate_alias() and the
    identifier-name heuristic below."""
    spaced = re.sub(r"[_\-.]+", " ", column_name.strip())
    spaced = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", " ", spaced)  # split camelCase
    return [w for w in spaced.split(" ") if w]


def _looks_like_identifier_name(column_name: str) -> bool:
    tokens = {w.lower() for w in _split_words(column_name)}
    return not tokens.isdisjoint(_IDENTIFIER_NAME_TOKENS)


def generate_alias(column_name: str) -> str:
    """A best-effort human-readable label for a raw CSV column header, e.g.
    "cust_dob" -> "Customer Date of Birth", "txn_amt" -> "Transaction Amount"."""
    words = _split_words(column_name)
    if not words:
        return column_name

    labelled = []
    for word in words:
        lower = word.lower()
        if lower in _ABBREVIATIONS:
            labelled.append(_ABBREVIATIONS[lower])
        elif word.isupper() and len(word) <= 5:
            labelled.append(word)  # keep short acronyms (ID, USA) as-is
        else:
            labelled.append(word[:1].upper() + word[1:])
    return " ".join(labelled)
