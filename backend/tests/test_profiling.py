import pytest

from src.datasets.profiling import (
    CONFIDENCE_REVIEW_THRESHOLD,
    ColumnCategory,
    classify_column,
    classify_column_with_confidence,
    compute_column_health,
    compute_dataset_health,
    detect_multi_value_separator,
    detect_range_pattern,
    generate_alias,
)


def test_classify_date_type_is_datetime():
    assert (
        classify_column(duckdb_type="DATE", row_count=100, distinct_count=90)
        == ColumnCategory.DATETIME
    )
    assert (
        classify_column(duckdb_type="TIMESTAMP", row_count=100, distinct_count=100)
        == ColumnCategory.DATETIME
    )


def test_classify_boolean_is_always_categorical():
    assert (
        classify_column(duckdb_type="BOOLEAN", row_count=1000, distinct_count=2)
        == ColumnCategory.CATEGORICAL
    )


def test_classify_low_cardinality_numeric_is_categorical():
    # e.g. a 1-5 star rating across many rows
    assert (
        classify_column(duckdb_type="INTEGER", row_count=1000, distinct_count=5)
        == ColumnCategory.CATEGORICAL
    )


def test_classify_high_cardinality_numeric_is_continuous():
    # e.g. age, marks, revenue -- a real range of values, not a small code set
    assert (
        classify_column(duckdb_type="DOUBLE", row_count=1000, distinct_count=340)
        == ColumnCategory.CONTINUOUS_NUMERICAL
    )


def test_classify_decimal_with_precision_is_treated_as_numeric():
    assert (
        classify_column(duckdb_type="DECIMAL(10,2)", row_count=1000, distinct_count=500)
        == ColumnCategory.CONTINUOUS_NUMERICAL
    )


def test_classify_low_cardinality_text_is_categorical():
    # e.g. a "status" column with a handful of repeated values
    assert (
        classify_column(
            duckdb_type="VARCHAR", row_count=1000, distinct_count=4, avg_length=6
        )
        == ColumnCategory.CATEGORICAL
    )


def test_classify_high_cardinality_long_text_is_free_text():
    # e.g. a free-form comments/description column
    assert (
        classify_column(
            duckdb_type="VARCHAR", row_count=1000, distinct_count=980, avg_length=120
        )
        == ColumnCategory.FREE_TEXT
    )


def test_classify_near_unique_short_text_is_free_text():
    # e.g. names/emails -- short strings, but essentially unique per row
    assert (
        classify_column(
            duckdb_type="VARCHAR", row_count=1000, distinct_count=995, avg_length=12
        )
        == ColumnCategory.FREE_TEXT
    )


def test_classify_empty_table_defaults_to_categorical():
    assert (
        classify_column(duckdb_type="VARCHAR", row_count=0, distinct_count=0)
        == ColumnCategory.CATEGORICAL
    )


@pytest.mark.parametrize(
    "row_count,null_count,expected",
    [(100, 0, 100.0), (100, 25, 75.0), (0, 0, 0.0), (4, 1, 75.0)],
)
def test_compute_column_health(row_count, null_count, expected):
    assert compute_column_health(row_count, null_count) == expected


def test_compute_dataset_health_averages_column_scores():
    assert compute_dataset_health([100.0, 50.0]) == 75.0


def test_compute_dataset_health_with_no_columns_defaults_to_full():
    assert compute_dataset_health([]) == 100.0


@pytest.mark.parametrize(
    "column_name,expected",
    [
        ("cust_dob", "Customer Date of Birth"),
        ("txn_amt", "Transaction Amount"),
        ("revenue", "Revenue"),
        ("user_id", "User ID"),
        ("camelCaseColumn", "Camel Case Column"),
        ("region_pct", "Region Percentage"),
    ],
)
def test_generate_alias(column_name, expected):
    assert generate_alias(column_name) == expected


@pytest.mark.parametrize("column_name", ["zip_code", "postal_code", "phone_number", "customer_id", "sku"])
def test_classify_high_cardinality_numeric_identifier_is_categorical(column_name):
    # Real zip/phone/ID columns can have thousands of legitimate distinct
    # values -- cardinality alone would call this continuous_numerical, but
    # the column name signals it's actually an identifier/code.
    category, confidence = classify_column_with_confidence(
        duckdb_type="BIGINT", row_count=5000, distinct_count=3000, column_name=column_name
    )
    assert category == ColumnCategory.CATEGORICAL
    assert confidence < CONFIDENCE_REVIEW_THRESHOLD  # a name-based heuristic, so still flagged for review


def test_classify_high_cardinality_numeric_without_identifier_name_stays_continuous():
    # Without an identifier-shaped name, the same stats should still read as
    # a genuine continuous quantity (e.g. revenue) -- the heuristic must not
    # over-fire on every high-cardinality numeric column.
    assert (
        classify_column(
            duckdb_type="BIGINT", row_count=5000, distinct_count=3000, column_name="revenue"
        )
        == ColumnCategory.CONTINUOUS_NUMERICAL
    )


def test_classify_text_categorical_cap_scales_with_row_count():
    # job_title: 65 distinct values across 5,000 rows (1.3% ratio) -- a flat
    # 50-value cap would flag this for needless review even though it's an
    # obviously low-cardinality dimension at this dataset size.
    category, confidence = classify_column_with_confidence(
        duckdb_type="VARCHAR", row_count=5000, distinct_count=65, avg_length=15
    )
    assert category == ColumnCategory.CATEGORICAL
    assert confidence >= CONFIDENCE_REVIEW_THRESHOLD


def test_classify_text_categorical_cap_still_floored_for_small_datasets():
    # The same 65-distinct-value column on a much smaller dataset (a 32.5%
    # ratio) should fall outside the confident-categorical cap and still get
    # flagged for review, rather than the scaling silently applying everywhere.
    category, confidence = classify_column_with_confidence(
        duckdb_type="VARCHAR", row_count=200, distinct_count=65, avg_length=15
    )
    assert category == ColumnCategory.CATEGORICAL
    assert confidence < CONFIDENCE_REVIEW_THRESHOLD


def test_detect_multi_value_separator_finds_comma_packed_tags():
    values = ["Mumbai, Pune", "Hyderabad, Gurugram, Bengaluru", "Chennai", "Delhi, Pune"]
    assert detect_multi_value_separator(values) == ","


def test_detect_multi_value_separator_prefers_earlier_candidate():
    # Every value here also splits on "/" as a side effect of splitting on
    # ",", but comma is checked first and already clears the threshold.
    values = ["Mumbai, Pune", "Hyderabad/Gurugram, Bengaluru", "Chennai, Delhi"]
    assert detect_multi_value_separator(values) == ","


def test_detect_multi_value_separator_returns_none_for_atomic_values():
    values = ["Mumbai", "Pune", "Hyderabad", "Chennai", "Delhi"]
    assert detect_multi_value_separator(values) is None


def test_detect_multi_value_separator_returns_none_below_threshold():
    # Only 1 of 4 values actually packs multiple tags -- below the 50% match
    # threshold, so this is treated as an ordinary (if slightly messy)
    # categorical column, not flagged as multi-value.
    values = ["Mumbai, Pune", "Hyderabad", "Chennai", "Delhi"]
    assert detect_multi_value_separator(values) is None


def test_detect_multi_value_separator_with_no_values_returns_none():
    assert detect_multi_value_separator([]) is None


def test_detect_range_pattern_finds_unit_suffixed_ranges():
    values = ["4-10 yrs", "2-5 yrs", "10-15 yrs", "0-2 yrs"]
    assert detect_range_pattern(values) == ("-", "yrs")


def test_detect_range_pattern_handles_decimals_and_no_unit():
    values = ["2.5-4.0", "1-3", "0.5-1.5"]
    assert detect_range_pattern(values) == ("-", None)


def test_detect_range_pattern_returns_none_for_atomic_numbers():
    values = ["5", "10", "15", "20"]
    assert detect_range_pattern(values) is None


def test_detect_range_pattern_returns_none_below_threshold():
    values = ["4-10 yrs", "Senior", "Manager", "Contractor"]
    assert detect_range_pattern(values) is None


def test_detect_range_pattern_with_no_values_returns_none():
    assert detect_range_pattern([]) is None
