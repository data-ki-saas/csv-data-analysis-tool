import logging
import uuid
from dataclasses import asdict
from pathlib import Path

import aiofiles
import duckdb
from fastapi import HTTPException, UploadFile

from src.core.auth import CurrentUser
from src.core.config import settings
from src.datasets import repository
from src.datasets.duckdb_manager import MalformedCsvError, QueryResult, UnsafeQueryError, duckdb_manager
from src.datasets.profiling import CONFIDENCE_REVIEW_THRESHOLD
from src.datasets.insights import generate_insights
from src.datasets.schemas import (
    ChartRecommendation,
    ColumnInfo,
    DatasetInfo,
    DatasetPreview,
    DatasetSchemaResponse,
    GenerateInsightsRequest,
    InsightsResponse,
    ReportStrategyResponse,
    UploadResponse,
)
from src.datasets.strategy_engine import suggest_visual_strategy
from src.datasets.type_review import suggest_column_categories
from src.llm.client import get_llm_provider
from src.query.schemas import QueryResponse
from src.storage import r2_client

logger = logging.getLogger(__name__)

_SAMPLE_VALUES_PER_COLUMN = 5

_UPLOAD_CHUNK_SIZE = 1024 * 1024  # 1 MiB


def _cleanup_orphaned_objects(*keys: str) -> None:
    """Best-effort delete for R2 objects written before a later upload stage
    failed -- swallows its own errors (logged) so a cleanup failure doesn't
    mask the original error being raised to the client."""
    for key in keys:
        try:
            r2_client.delete_object(key)
        except Exception:
            logger.exception("failed to clean up orphaned R2 object %r after a failed upload", key)


async def _stream_upload_to_disk(file: UploadFile, destination: Path) -> None:
    written = 0
    async with aiofiles.open(destination, "wb") as out:
        while chunk := await file.read(_UPLOAD_CHUNK_SIZE):
            written += len(chunk)
            if written > settings.max_upload_size_bytes:
                raise HTTPException(
                    status_code=413,
                    detail=f"File exceeds the {settings.max_upload_size_mb} MB upload limit",
                )
            await out.write(chunk)
    if written == 0:
        raise HTTPException(status_code=400, detail="Uploaded file is empty")


async def ingest_csv_upload(file: UploadFile, user: CurrentUser) -> UploadResponse:
    if not file.filename or not file.filename.lower().endswith(".csv"):
        raise HTTPException(status_code=400, detail="Only .csv files are supported")

    dataset_id = uuid.uuid4().hex
    tmp_csv_path = settings.scratch_dir / f"{dataset_id}.upload.csv"
    raw_key = f"raw/{dataset_id}.csv"
    parquet_key = f"processed/{dataset_id}.parquet"

    logger.info("upload start: user=%s filename=%r", user.id, file.filename)

    try:
        await _stream_upload_to_disk(file, tmp_csv_path)

        try:
            result = duckdb_manager.ingest_and_export(tmp_csv_path, parquet_key)
        except (duckdb.Error, MalformedCsvError) as exc:
            logger.warning(
                "upload failed to parse: user=%s filename=%r error=%s", user.id, file.filename, exc
            )
            raise HTTPException(status_code=400, detail=f"Failed to parse CSV: {exc}") from exc

        logger.info(
            "upload parsed: user=%s filename=%r row_count=%d columns=%d",
            user.id,
            file.filename,
            result.row_count,
            len(result.schema),
        )

        try:
            r2_client.upload_raw_file(tmp_csv_path, raw_key)
        except Exception as exc:
            # The Parquet export above already reached R2 successfully -- this
            # is specifically the raw-CSV-archive upload failing (bad R2
            # credentials, network blip, wrong bucket), not a CSV problem, so
            # it gets its own error rather than being folded into "Failed to
            # parse CSV" above.
            logger.exception(
                "upload failed to store raw CSV in R2: user=%s filename=%r raw_key=%s",
                user.id,
                file.filename,
                raw_key,
            )
            _cleanup_orphaned_objects(parquet_key)
            raise HTTPException(
                status_code=502, detail="Failed to store the uploaded file. Please try again."
            ) from exc
    finally:
        tmp_csv_path.unlink(missing_ok=True)

    schema_dicts = [asdict(col) for col in result.schema]
    try:
        record = repository.create_dataset(
            owner_id=user.id,
            filename=file.filename,
            row_count=result.row_count,
            schema=schema_dicts,
            raw_key=raw_key,
            parquet_key=parquet_key,
            health_score=result.health_score,
        )
    except Exception as exc:
        logger.exception(
            "upload failed to save dataset metadata: user=%s filename=%r", user.id, file.filename
        )
        _cleanup_orphaned_objects(parquet_key, raw_key)
        raise HTTPException(
            status_code=502,
            detail="Your file was processed but we couldn't save it. Please try again.",
        ) from exc

    logger.info(
        "upload complete: user=%s dataset_id=%s filename=%r row_count=%d",
        user.id,
        record.id,
        file.filename,
        record.row_count,
    )

    return UploadResponse(
        dataset_id=record.id,
        filename=record.filename,
        row_count=record.row_count,
        health_score=record.health_score,
        schema=[ColumnInfo(**col) for col in record.schema],
        preview=DatasetPreview(columns=result.preview.columns, rows=result.preview.rows),
    )


def get_dataset_info(dataset_id: str, user: CurrentUser) -> DatasetInfo:
    record = repository.get_dataset(dataset_id, user.id)
    if record is None:
        raise HTTPException(status_code=404, detail="Dataset not found")

    return DatasetInfo(
        dataset_id=record.id,
        filename=record.filename,
        row_count=record.row_count,
        health_score=record.health_score,
        schema=[ColumnInfo(**col) for col in record.schema],
    )


def list_datasets(user: CurrentUser) -> list[DatasetInfo]:
    return [
        DatasetInfo(
            dataset_id=record.id,
            filename=record.filename,
            row_count=record.row_count,
            health_score=record.health_score,
            schema=[ColumnInfo(**col) for col in record.schema],
        )
        for record in repository.list_datasets(user.id)
    ]


def delete_dataset(dataset_id: str, user: CurrentUser) -> None:
    record = repository.get_dataset(dataset_id, user.id)
    if record is None:
        raise HTTPException(status_code=404, detail="Dataset not found")

    r2_client.delete_object(record.raw_key)
    r2_client.delete_object(record.parquet_key)
    repository.delete_dataset(dataset_id, user.id)


def _to_schema_response(
    record: repository.DatasetRecord, preview: QueryResult
) -> DatasetSchemaResponse:
    return DatasetSchemaResponse(
        dataset_id=record.id,
        filename=record.filename,
        row_count=record.row_count,
        created_at=record.created_at,
        health_score=record.health_score,
        columns=[ColumnInfo(**col) for col in record.schema],
        preview=DatasetPreview(columns=preview.columns, rows=preview.rows),
    )


def _sample_values(preview: QueryResult) -> dict[str, list]:
    """Cheap, non-exhaustive sample values per column, pulled from the
    already-fetched preview rows rather than an extra DuckDB query per
    column -- good enough context for the AI reviewer, not a statistical sample."""
    samples: dict[str, list] = {name: [] for name in preview.columns}
    for row in preview.rows:
        for name, value in zip(preview.columns, row):
            if value is None or len(samples[name]) >= _SAMPLE_VALUES_PER_COLUMN:
                continue
            if value not in samples[name]:
                samples[name].append(value)
    return samples


async def get_dataset_schema(dataset_id: str, user: CurrentUser) -> DatasetSchemaResponse:
    record = repository.get_dataset(dataset_id, user.id)
    if record is None:
        raise HTTPException(status_code=404, detail="Dataset not found")

    preview = await duckdb_manager.preview_dataset(record.parquet_key)
    return _to_schema_response(record, preview)


async def ai_review_column_types(
    dataset_id: str, column_names: list[str] | None, user: CurrentUser
) -> DatasetSchemaResponse:
    """Ask the configured LLM provider to weigh in on columns the rule-based
    classifier is unsure about (or, if `column_names` is given, exactly those
    columns). Columns a user has already explicitly set are left alone
    unless named explicitly — a bulk review should never silently overwrite
    a human decision."""
    record = repository.get_dataset(dataset_id, user.id)
    if record is None:
        raise HTTPException(status_code=404, detail="Dataset not found")

    preview = await duckdb_manager.preview_dataset(record.parquet_key)
    samples = _sample_values(preview)

    columns = [ColumnInfo(**col) for col in record.schema]
    if column_names is not None:
        target_names = set(column_names)
    else:
        target_names = {col.name for col in columns if col.needs_review and col.category_source != "user"}

    to_review = [col for col in columns if col.name in target_names]
    if not to_review:
        return _to_schema_response(record, preview)

    payload = [
        {
            "name": col.name,
            "type": col.type,
            "category": col.category,
            "distinct_count": col.distinct_count,
            "null_percentage": col.null_percentage,
            "samples": samples.get(col.name, []),
        }
        for col in to_review
    ]

    try:
        suggestions = await suggest_column_categories(payload, get_llm_provider())
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"AI type review failed: {exc}") from exc

    updated_columns = []
    for col in columns:
        suggestion = suggestions.get(col.name)
        if suggestion is None:
            updated_columns.append(col)
            continue
        updated_columns.append(
            col.model_copy(
                update={
                    "category": suggestion["category"],
                    "category_source": "ai",
                    "confidence": suggestion["confidence"],
                    "needs_review": suggestion["confidence"] < CONFIDENCE_REVIEW_THRESHOLD,
                    "rationale": suggestion["rationale"],
                }
            )
        )

    schema_dicts = [col.model_dump() for col in updated_columns]
    updated_record = repository.update_dataset_schema(dataset_id, user.id, schema_dicts)
    if updated_record is None:
        raise HTTPException(status_code=404, detail="Dataset not found")

    return _to_schema_response(updated_record, preview)


async def update_column(
    dataset_id: str,
    column_name: str,
    *,
    category: str | None,
    alias: str | None,
    user: CurrentUser,
) -> DatasetSchemaResponse:
    """A human override always wins: a category override sets full
    confidence, clears `needs_review`, and drops any stale AI rationale. An
    alias rename only touches the display label -- it doesn't affect
    category/confidence/source at all."""
    record = repository.get_dataset(dataset_id, user.id)
    if record is None:
        raise HTTPException(status_code=404, detail="Dataset not found")

    columns = [ColumnInfo(**col) for col in record.schema]
    if not any(col.name == column_name for col in columns):
        raise HTTPException(status_code=404, detail=f"Column {column_name!r} not found")

    def apply(col: ColumnInfo) -> ColumnInfo:
        if col.name != column_name:
            return col
        updates: dict = {}
        if alias is not None:
            updates["alias"] = alias
        if category is not None:
            updates.update(
                {
                    "category": category,
                    "category_source": "user",
                    "confidence": 100.0,
                    "needs_review": False,
                    "rationale": None,
                }
            )
        return col.model_copy(update=updates)

    updated_columns = [apply(col) for col in columns]

    schema_dicts = [col.model_dump() for col in updated_columns]
    updated_record = repository.update_dataset_schema(dataset_id, user.id, schema_dicts)
    if updated_record is None:
        raise HTTPException(status_code=404, detail="Dataset not found")

    preview = await duckdb_manager.preview_dataset(updated_record.parquet_key)
    return _to_schema_response(updated_record, preview)


async def generate_report_strategy(dataset_id: str, user: CurrentUser) -> ReportStrategyResponse:
    """Ask the configured LLM provider for a prioritized set of chart
    recommendations (see strategy_engine.SYSTEM_PROMPT for the datetime ->
    numerical -> categorical ordering and chart-matching rules), then execute
    each recommendation's SQL for real before returning it.

    Free-text columns are excluded before the prompt is even built — there's
    no meaningful aggregate chart for a comments/description column, so
    there's no reason to spend tokens describing one. Every recommendation's
    SQL runs through duckdb_manager.execute_query(), which enforces the same
    single-statement/readonly guard as the query API — a query that fails
    that guard or fails to execute is reported per-recommendation via
    `error`, not raised, so one bad suggestion doesn't sink the rest.
    """
    record = repository.get_dataset(dataset_id, user.id)
    if record is None:
        raise HTTPException(status_code=404, detail="Dataset not found")

    columns = [ColumnInfo(**col) for col in record.schema]
    chartable = [col for col in columns if col.category != "free_text"]

    if not chartable:
        return ReportStrategyResponse(dataset_id=record.id, filename=record.filename, recommendations=[])

    preview = await duckdb_manager.preview_dataset(record.parquet_key)
    samples = _sample_values(preview)

    payload = [
        {
            "name": col.name,
            "alias": col.alias,
            "type": col.type,
            "category": col.category,
            "distinct_count": col.distinct_count,
            "null_percentage": col.null_percentage,
            "samples": samples.get(col.name, []),
        }
        for col in chartable
    ]

    try:
        suggestions = await suggest_visual_strategy(payload, get_llm_provider())
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Report strategy generation failed: {exc}") from exc

    recommendations = []
    for suggestion in suggestions:
        result = None
        error = None
        try:
            query_result = await duckdb_manager.execute_query(record.parquet_key, suggestion["sql"])
            result = QueryResponse(
                columns=query_result.columns,
                rows=query_result.rows,
                row_count=query_result.row_count,
                truncated=query_result.truncated,
            )
        except (UnsafeQueryError, duckdb.Error) as exc:
            error = str(exc)

        recommendations.append(
            ChartRecommendation(
                column=suggestion["column"],
                partition_type=suggestion["partition_type"],
                chart_type=suggestion["chart_type"],
                title=suggestion["title"],
                rationale=suggestion["rationale"],
                sql=suggestion["sql"],
                result=result,
                error=error,
            )
        )

    return ReportStrategyResponse(
        dataset_id=record.id, filename=record.filename, recommendations=recommendations
    )


async def generate_chart_insights(
    dataset_id: str, request: GenerateInsightsRequest, user: CurrentUser
) -> InsightsResponse:
    """The chart's aggregated data comes straight from the request body (the
    frontend already has it, whether from the original report-strategy
    result or a client-rebuilt fast-aggregation query) -- this only checks
    dataset ownership, it never re-runs SQL itself."""
    record = repository.get_dataset(dataset_id, user.id)
    if record is None:
        raise HTTPException(status_code=404, detail="Dataset not found")

    try:
        insights = await generate_insights(request.model_dump(), get_llm_provider())
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Insight generation failed: {exc}") from exc

    return InsightsResponse(insights=insights)
