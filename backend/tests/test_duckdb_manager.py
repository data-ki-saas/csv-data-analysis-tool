import pytest

from src.datasets.duckdb_manager import (
    MalformedCsvError,
    UnsafeQueryError,
    _assert_readonly_select,
    _column_transform_replace_clause,
    duckdb_manager,
)


def test_transform_clause_is_empty_with_no_rules():
    assert _column_transform_replace_clause(None, None) == ""
    assert _column_transform_replace_clause({}, {}) == ""


def test_transform_clause_builds_merge_case():
    clause = _column_transform_replace_clause({"city": [{"target": "NY", "sources": ["ny", "New York"]}]}, None)
    assert clause.startswith(" REPLACE (")
    assert "CASE WHEN CAST(\"city\" AS VARCHAR) IN ('ny', 'New York') THEN 'NY'" in clause
    assert clause.count('AS "city"') == 1


def test_transform_clause_chains_replacements_before_merge_case():
    clause = _column_transform_replace_clause(
        {"city": [{"target": "Delhi", "sources": ["Old Delhi"]}]},
        {"city": [{"find": "Delhi / NCR", "replace": "Delhi"}]},
    )
    # The WHEN's own comparison must test against the *replaced* text, not
    # the raw column -- i.e. REPLACE(...) nested directly inside CASE WHEN.
    assert (
        "CASE WHEN REPLACE(CAST(\"city\" AS VARCHAR), 'Delhi / NCR', 'Delhi') IN ('Old Delhi') THEN 'Delhi'"
        in clause
    )


def test_transform_clause_escapes_single_quotes():
    clause = _column_transform_replace_clause(None, {"city": [{"find": "O'Brien", "replace": "Obrien"}]})
    assert "O''Brien" in clause


def test_transform_clause_replacement_only_column_has_no_case():
    clause = _column_transform_replace_clause(None, {"notes": [{"find": "foo", "replace": "bar"}]})
    assert "CASE" not in clause
    assert "REPLACE(CAST(\"notes\" AS VARCHAR), 'foo', 'bar') AS \"notes\"" in clause


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT * FROM data",
        "WITH t AS (SELECT * FROM data) SELECT * FROM t",
    ],
)
def test_readonly_guard_allows_select(sql):
    _assert_readonly_select(sql)  # should not raise


@pytest.mark.parametrize(
    "sql",
    [
        "DROP TABLE data",
        "DELETE FROM data",
        "SELECT * FROM data; DROP TABLE data",
        "INSERT INTO data VALUES (1)",
    ],
)
def test_readonly_guard_rejects_unsafe_sql(sql):
    with pytest.raises(UnsafeQueryError):
        _assert_readonly_select(sql)


def test_readonly_guard_rejects_sql_that_fails_to_parse():
    # Genuinely malformed SQL (as opposed to well-formed-but-disallowed SQL)
    # must still surface as UnsafeQueryError, not an uncaught sqlglot
    # ParseError -- this matters more once query SQL can come from an LLM.
    with pytest.raises(UnsafeQueryError):
        _assert_readonly_select('SELECT "plan" AS FROM GROUP BY nonsense(')


def test_ingest_and_query_round_trip(sample_csv_path):
    result = duckdb_manager.ingest_and_export(sample_csv_path, "processed/test.parquet")

    assert result.row_count == 3
    assert {col.name for col in result.schema} == {"id", "name", "amount"}
    assert len(result.preview.rows) == 3


async def test_query_remote_parquet(sample_csv_path):
    duckdb_manager.ingest_and_export(sample_csv_path, "processed/test-query.parquet")

    result = await duckdb_manager.execute_query(
        "processed/test-query.parquet", "SELECT count(*) AS n FROM data"
    )

    assert result.columns == ["n"]
    assert result.rows == [[3]]


async def test_query_remote_respects_row_cap(sample_csv_path):
    duckdb_manager.ingest_and_export(sample_csv_path, "processed/test-cap.parquet")

    result = await duckdb_manager.execute_query(
        "processed/test-cap.parquet", "SELECT * FROM data", max_rows=2
    )

    assert result.row_count == 2
    assert result.truncated is True


def test_ingest_normalizes_null_sentinels_and_reports_health(tmp_path):
    csv_path = tmp_path / "nulls.csv"
    csv_path.write_text(
        "id,status,note\n"
        "1,active,fine\n"
        "2,NA,\n"
        "3,active,n/a\n"
        "4,inactive,-\n"
    )

    result = duckdb_manager.ingest_and_export(csv_path, "processed/test-nulls.parquet")

    by_name = {col.name: col for col in result.schema}
    assert by_name["status"].null_count == 1  # only the "NA" row
    assert by_name["note"].null_count == 3  # "", "n/a", "-" all normalized to NULL
    assert by_name["note"].null_percentage == 75.0
    assert by_name["id"].null_count == 0
    assert result.health_score < 100.0


def test_ingest_normalizes_inconsistent_date_formats(tmp_path):
    csv_path = tmp_path / "dates.csv"
    csv_path.write_text(
        "id,signup_date\n"
        "1,2024-01-05\n"
        "2,01/15/2024\n"
        '3,"March 3, 2024"\n'
        "4,2024-02-20\n"
        "5,04/10/2024\n"
    )

    result = duckdb_manager.ingest_and_export(csv_path, "processed/test-dates.parquet")

    signup_date = next(col for col in result.schema if col.name == "signup_date")
    assert signup_date.type == "DATE"
    assert signup_date.category == "datetime"


async def test_normalized_dates_are_queryable_after_export(tmp_path):
    csv_path = tmp_path / "dates2.csv"
    csv_path.write_text(
        "id,signup_date\n"
        "1,2024-01-05\n"
        "2,01/15/2024\n"
        '3,"March 3, 2024"\n'
        "4,2024-02-20\n"
        "5,04/10/2024\n"
    )

    duckdb_manager.ingest_and_export(csv_path, "processed/test-dates-query.parquet")

    result = await duckdb_manager.execute_query(
        "processed/test-dates-query.parquet",
        "SELECT signup_date FROM data ORDER BY signup_date",
    )

    assert result.rows[0][0].isoformat() == "2024-01-05"


def test_ingest_classifies_and_aliases_columns(tmp_path):
    csv_path = tmp_path / "profile.csv"
    rows = "\n".join(f"{i},active,revenue {i}" for i in range(1, 31))
    csv_path.write_text("cust_id,status,notes\n" + rows + "\n")

    result = duckdb_manager.ingest_and_export(csv_path, "processed/test-profile.parquet")

    by_name = {col.name: col for col in result.schema}
    assert by_name["cust_id"].alias == "Customer ID"
    # 30 distinct ids -- would be continuous_numerical by cardinality alone,
    # but the "id" in the column name marks it as an identifier instead.
    assert by_name["cust_id"].category == "categorical"
    assert by_name["cust_id"].needs_review is True
    assert by_name["status"].alias == "Status"
    assert by_name["status"].category == "categorical"  # a single repeated value


async def test_preview_dataset_reads_fresh_from_parquet(sample_csv_path):
    duckdb_manager.ingest_and_export(sample_csv_path, "processed/test-preview.parquet")

    preview = await duckdb_manager.preview_dataset("processed/test-preview.parquet", limit=2)

    assert preview.row_count == 2
    assert set(preview.columns) == {"id", "name", "amount"}


def test_ingest_normalizes_currency_and_percentage_strings(tmp_path):
    csv_path = tmp_path / "money.csv"
    # 25 distinct revenue values -- enough to clear NUMERIC_CATEGORICAL_MAX_DISTINCT
    # so a successful conversion reads as continuous_numerical, not a coincidental
    # low-cardinality "categorical" numeric.
    rows = "\n".join(f'{i},"${1000 + i * 37.5:.2f}","{i}%"' for i in range(1, 26))
    csv_path.write_text("id,revenue,discount_pct\n" + rows + "\n")

    result = duckdb_manager.ingest_and_export(csv_path, "processed/test-money.parquet")

    by_name = {col.name: col for col in result.schema}
    assert by_name["revenue"].type == "DOUBLE"
    assert by_name["revenue"].category == "continuous_numerical"
    assert by_name["discount_pct"].type == "DOUBLE"


async def test_normalized_numeric_strings_are_queryable_after_export(tmp_path):
    csv_path = tmp_path / "money2.csv"
    csv_path.write_text(
        "id,revenue\n"
        '1,"$1,000.00"\n'
        '2,"$2,000.50"\n'
    )

    duckdb_manager.ingest_and_export(csv_path, "processed/test-money-query.parquet")

    result = await duckdb_manager.execute_query(
        "processed/test-money-query.parquet", "SELECT sum(revenue) AS total FROM data"
    )

    assert result.rows[0][0] == pytest.approx(3000.50)


def test_ingest_warns_when_date_normalization_drops_values_to_null(tmp_path):
    csv_path = tmp_path / "dates_partial.csv"
    csv_path.write_text(
        "id,signup_date\n"
        "1,2024-01-05\n"
        "2,2024-02-20\n"
        "3,2024-03-10\n"
        "4,2024-04-15\n"
        "5,5-Apr-2024\n"  # not in _DATE_FORMAT_CANDIDATES -- becomes NULL
    )

    result = duckdb_manager.ingest_and_export(csv_path, "processed/test-dates-warn.parquet")

    signup_date = next(col for col in result.schema if col.name == "signup_date")
    assert signup_date.category == "datetime"
    assert signup_date.conversion_warning is not None
    assert "1 of 5" in signup_date.conversion_warning


def test_ingest_raises_on_malformed_ragged_csv(tmp_path):
    csv_path = tmp_path / "malformed.csv"
    # An unquoted date value ("Jan 5, 2024") embeds an extra delimiter, so
    # every data row has one more field than the 3-column header. DuckDB
    # doesn't error on this -- it silently discards the header and falls
    # back to generic column0/column1/... names instead.
    csv_path.write_text(
        "order_id,signup_date,revenue\n"
        "1,Jan 5, 2024,100\n"
        "2,Jan 6, 2024,200\n"
        "3,Jan 7, 2024,300\n"
    )

    with pytest.raises(MalformedCsvError):
        duckdb_manager.ingest_and_export(csv_path, "processed/test-malformed.parquet")
