import pytest

from src.datasets.duckdb_manager import UnsafeQueryError, _assert_readonly_select, duckdb_manager


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
