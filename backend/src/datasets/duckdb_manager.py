from dataclasses import dataclass
from pathlib import Path

import duckdb
import sqlglot
from sqlglot import exp
from starlette.concurrency import run_in_threadpool

from src.core.config import settings


class UnsafeQueryError(Exception):
    pass


@dataclass
class ColumnSchema:
    name: str
    type: str


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


def _assert_readonly_select(sql: str) -> None:
    """Only a single SELECT/WITH statement is allowed — this SQL may come from an LLM."""
    statements = sqlglot.parse(sql, dialect="duckdb")
    if len(statements) != 1 or statements[0] is None:
        raise UnsafeQueryError("Exactly one SQL statement is allowed")
    if not isinstance(statements[0], (exp.Select, exp.With)):
        raise UnsafeQueryError("Only SELECT queries are allowed")


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


def _describe_and_preview(
    conn: duckdb.DuckDBPyConnection, table: str, preview_rows: int
) -> tuple[list[ColumnSchema], int, QueryResult]:
    schema = [
        ColumnSchema(name=row[0], type=row[1])
        for row in conn.execute(f"DESCRIBE {table}").fetchall()
    ]
    row_count = conn.execute(f"SELECT count(*) FROM {table}").fetchone()[0]
    preview_cursor = conn.execute(f"SELECT * FROM {table} LIMIT {preview_rows}")
    preview_columns = [d[0] for d in preview_cursor.description]
    preview_rows_data = [list(row) for row in preview_cursor.fetchall()]
    preview = QueryResult(
        columns=preview_columns,
        rows=preview_rows_data,
        row_count=len(preview_rows_data),
        truncated=False,
    )
    return schema, row_count, preview


class DuckDBManager:
    """Ingests CSVs into Parquet-on-R2 and serves SQL directly against R2 — no
    per-dataset state is kept locally, so the service can restart or scale
    freely (Render's free tier spins down when idle).
    """

    def ingest_and_export(self, csv_path: Path, parquet_key: str) -> IngestResult:
        conn = _new_r2_connection()
        try:
            # DuckDB's own CSV reader streams the file directly from disk —
            # the rows never pass through a Python object.
            conn.execute("CREATE TABLE data AS SELECT * FROM read_csv_auto(?)", [str(csv_path)])
            conn.execute("COPY data TO ? (FORMAT PARQUET)", [_s3_uri(parquet_key)])
            schema, row_count, preview = _describe_and_preview(conn, "data", preview_rows=20)
            return IngestResult(schema=schema, row_count=row_count, preview=preview)
        finally:
            conn.close()

    async def execute_query(
        self, parquet_key: str, sql: str, max_rows: int | None = None
    ) -> QueryResult:
        max_rows = max_rows or settings.query_max_rows
        _assert_readonly_select(sql)
        return await run_in_threadpool(self._execute_sync, parquet_key, sql, max_rows)

    def _execute_sync(self, parquet_key: str, sql: str, max_rows: int) -> QueryResult:
        # DuckDB doesn't support prepared parameters in CREATE VIEW, so the URI is
        # interpolated directly — safe here because parquet_key is always a
        # server-generated "{uuid4}.parquet" key, never derived from user input.
        if "'" in parquet_key or ";" in parquet_key:
            raise UnsafeQueryError("Invalid dataset storage key")

        conn = _new_r2_connection()
        try:
            conn.execute(f"CREATE VIEW data AS SELECT * FROM read_parquet('{_s3_uri(parquet_key)}')")
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


duckdb_manager = DuckDBManager()
