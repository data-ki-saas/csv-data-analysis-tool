import hashlib
import json
import logging
import uuid
from dataclasses import asdict
from pathlib import Path

import aiofiles
import duckdb
from fastapi import HTTPException, UploadFile

from src.core.auth import CurrentUser
from src.core.config import settings
from src.datasets import insights_cache_repository, repository
from src.datasets.duckdb_manager import MalformedCsvError, QueryResult, UnsafeQueryError, duckdb_manager
from src.datasets.profiling import CONFIDENCE_REVIEW_THRESHOLD
from src.datasets.insights import generate_insights
from src.datasets.schemas import (
    ChartRecommendation,
    ColumnInfo,
    ColumnValueCount,
    ColumnValuesResponse,
    DatasetInfo,
    DatasetPreview,
    DatasetSchemaResponse,
    GenerateInsightsRequest,
    InsightsResponse,
    ReportStrategyResponse,
    UpdateChartRequest,
    UpdateDatasetRequest,
    UploadResponse,
    ValueMergeRule,
    ValueMergeSuggestion,
)
from src.datasets.strategy_engine import suggest_custom_chart, suggest_visual_strategy
from src.datasets.type_review import suggest_column_categories
from src.datasets.value_merge import suggest_value_merge
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


async def _stream_upload_to_disk(file: UploadFile, destination: Path) -> str:
    """Streams the upload to disk in chunks and returns the MD5 hex digest of
    its bytes, computed over the same chunks as they're written -- no extra
    read pass. Used for upload dedup (see ingest_csv_upload); not a security
    hash, just a change-detection fingerprint, so MD5's speed is preferable
    to a stronger algorithm here."""
    written = 0
    digest = hashlib.md5()
    async with aiofiles.open(destination, "wb") as out:
        while chunk := await file.read(_UPLOAD_CHUNK_SIZE):
            written += len(chunk)
            if written > settings.max_upload_size_bytes:
                raise HTTPException(
                    status_code=413,
                    detail=f"File exceeds the {settings.max_upload_size_mb} MB upload limit",
                )
            digest.update(chunk)
            await out.write(chunk)
    if written == 0:
        raise HTTPException(status_code=400, detail="Uploaded file is empty")
    return digest.hexdigest()


async def _create_deduplicated_dataset(
    matched: repository.DatasetRecord, filename: str, content_hash: str, user: CurrentUser
) -> UploadResponse:
    """Byte-identical content to `matched` was just uploaded by the same
    owner -- create a new dataset row (its own id/filename, its own entry in
    "Your datasets") that shares `matched`'s R2 storage instead of re-parsing
    and re-uploading. Also copies `matched`'s already-computed schema/health
    and any cached report_strategy forward, since they'd be identical anyway.
    Deliberately does NOT run `_cleanup_orphaned_objects` on failure below --
    unlike the fresh-ingest path, no new R2 objects were written here, so
    there's nothing of this request's own to clean up (and cleaning up
    `matched`'s objects would break the dataset(s) still relying on them)."""
    preview = await duckdb_manager.preview_dataset(matched.parquet_key, value_remaps=matched.value_remaps)
    try:
        record = repository.create_dataset(
            owner_id=user.id,
            filename=filename,
            name=filename,
            row_count=matched.row_count,
            schema=matched.schema,
            raw_key=matched.raw_key,
            parquet_key=matched.parquet_key,
            health_score=matched.health_score,
            content_hash=content_hash,
            report_strategy=matched.report_strategy,
            value_remaps=matched.value_remaps,
        )
    except Exception as exc:
        logger.exception(
            "upload (deduplicated) failed to save dataset metadata: user=%s filename=%r", user.id, filename
        )
        raise HTTPException(
            status_code=502,
            detail="Your file was processed but we couldn't save it. Please try again.",
        ) from exc

    logger.info(
        "upload complete (deduplicated): user=%s dataset_id=%s matched_dataset_id=%s filename=%r row_count=%d",
        user.id,
        record.id,
        matched.id,
        filename,
        record.row_count,
    )

    return UploadResponse(
        dataset_id=record.id,
        filename=record.filename,
        name=record.name,
        description=record.description,
        notes=record.notes,
        row_count=record.row_count,
        health_score=record.health_score,
        schema=[ColumnInfo(**col) for col in record.schema],
        preview=DatasetPreview(columns=preview.columns, rows=preview.rows),
    )


async def ingest_csv_upload(file: UploadFile, user: CurrentUser) -> UploadResponse:
    if not file.filename or not file.filename.lower().endswith(".csv"):
        raise HTTPException(status_code=400, detail="Only .csv files are supported")

    dataset_id = uuid.uuid4().hex
    tmp_csv_path = settings.scratch_dir / f"{dataset_id}.upload.csv"
    raw_key = f"raw/{dataset_id}.csv"
    parquet_key = f"processed/{dataset_id}.parquet"

    logger.info("upload start: user=%s filename=%r", user.id, file.filename)

    try:
        content_hash = await _stream_upload_to_disk(file, tmp_csv_path)

        matched = repository.get_dataset_by_content_hash(user.id, content_hash)
        if matched is not None:
            logger.info(
                "upload deduplicated: user=%s filename=%r matched_dataset_id=%s",
                user.id,
                file.filename,
                matched.id,
            )
            return await _create_deduplicated_dataset(matched, file.filename, content_hash, user)

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
            name=file.filename,
            row_count=result.row_count,
            schema=schema_dicts,
            raw_key=raw_key,
            parquet_key=parquet_key,
            health_score=result.health_score,
            content_hash=content_hash,
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
        name=record.name,
        description=record.description,
        notes=record.notes,
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
        name=record.name,
        description=record.description,
        notes=record.notes,
        row_count=record.row_count,
        health_score=record.health_score,
        schema=[ColumnInfo(**col) for col in record.schema],
    )


def list_datasets(user: CurrentUser) -> list[DatasetInfo]:
    return [
        DatasetInfo(
            dataset_id=record.id,
            filename=record.filename,
            name=record.name,
            description=record.description,
            notes=record.notes,
            row_count=record.row_count,
            health_score=record.health_score,
            schema=[ColumnInfo(**col) for col in record.schema],
        )
        for record in repository.list_datasets(user.id)
    ]


def update_dataset_metadata(
    dataset_id: str, request: UpdateDatasetRequest, user: CurrentUser
) -> DatasetInfo:
    """Rename a dataset and/or edit its description/notes. `exclude_unset=True`
    passes through exactly the fields present in the request body -- a
    provided `description: ""` (or `notes: ""`) clears it (stored as NULL),
    while an omitted field leaves the existing value untouched. See
    UpdateDatasetRequest and repository.update_dataset_metadata."""
    fields = request.model_dump(exclude_unset=True)
    for text_field in ("description", "notes"):
        if text_field in fields and fields[text_field] is not None:
            fields[text_field] = fields[text_field].strip() or None
    if "name" in fields:
        fields["name"] = fields["name"].strip()

    updated = repository.update_dataset_metadata(dataset_id, user.id, fields)
    if updated is None:
        raise HTTPException(status_code=404, detail="Dataset not found")

    return DatasetInfo(
        dataset_id=updated.id,
        filename=updated.filename,
        name=updated.name,
        description=updated.description,
        notes=updated.notes,
        row_count=updated.row_count,
        health_score=updated.health_score,
        schema=[ColumnInfo(**col) for col in updated.schema],
    )


def delete_dataset(dataset_id: str, user: CurrentUser) -> None:
    record = repository.get_dataset(dataset_id, user.id)
    if record is None:
        raise HTTPException(status_code=404, detail="Dataset not found")

    # A deduplicated upload (see ingest_csv_upload) shares its raw_key/parquet_key
    # with another dataset row -- only delete the R2 objects once no other row
    # still references them. Accepted race (personal-scale app, not solved
    # here): two concurrent deletes of the last two sibling rows can each see
    # a nonzero count and both skip the R2 delete, leaking the objects -- never
    # the reverse (deleting storage a surviving row still needs), which is the
    # failure direction that actually matters.
    if repository.count_datasets_sharing_storage(dataset_id, record.raw_key) == 0:
        r2_client.delete_object(record.raw_key)
        r2_client.delete_object(record.parquet_key)
    repository.delete_dataset(dataset_id, user.id)


def _to_schema_response(
    record: repository.DatasetRecord, preview: QueryResult
) -> DatasetSchemaResponse:
    return DatasetSchemaResponse(
        dataset_id=record.id,
        filename=record.filename,
        name=record.name,
        description=record.description,
        notes=record.notes,
        row_count=record.row_count,
        created_at=record.created_at,
        health_score=record.health_score,
        columns=[ColumnInfo(**col) for col in record.schema],
        preview=DatasetPreview(columns=preview.columns, rows=preview.rows),
        has_report_strategy=record.report_strategy is not None,
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

    preview = await duckdb_manager.preview_dataset(record.parquet_key, value_remaps=record.value_remaps)
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

    preview = await duckdb_manager.preview_dataset(record.parquet_key, value_remaps=record.value_remaps)
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

    preview = await duckdb_manager.preview_dataset(
        updated_record.parquet_key, value_remaps=updated_record.value_remaps
    )
    return _to_schema_response(updated_record, preview)


_COLUMN_VALUES_LIMIT = 200


def _find_column(record: repository.DatasetRecord, column_name: str) -> ColumnInfo:
    for col in (ColumnInfo(**col) for col in record.schema):
        if col.name == column_name:
            return col
    raise HTTPException(status_code=404, detail=f"Column {column_name!r} not found")


def _assert_categorical(column: ColumnInfo) -> None:
    """Value merging is deliberately scoped to categorical columns: it only
    makes sense for a small, repeated set of labels, and every remapped
    column reads as text everywhere afterward (see
    duckdb_manager._remap_replace_clause) -- not a tradeoff worth offering on
    a continuous/datetime/free-text column."""
    if column.category != "categorical":
        raise HTTPException(
            status_code=400, detail="Value merging is only available for categorical columns"
        )


async def get_column_values(dataset_id: str, column_name: str, user: CurrentUser) -> ColumnValuesResponse:
    """A categorical column's current distinct values (post already-accepted
    merges) plus the merge rules in effect -- backs the "Edit column"
    dialog's value list and its list of active, individually-revertible rules."""
    record = repository.get_dataset(dataset_id, user.id)
    if record is None:
        raise HTTPException(status_code=404, detail="Dataset not found")

    column = _find_column(record, column_name)
    _assert_categorical(column)

    rules = (record.value_remaps or {}).get(column_name, [])
    counts = await duckdb_manager.column_value_counts(
        record.parquet_key, column_name, _COLUMN_VALUES_LIMIT, record.value_remaps
    )
    return ColumnValuesResponse(
        dataset_id=record.id,
        column=column_name,
        values=[ColumnValueCount(value=value, count=count) for value, count in counts],
        rules=[ValueMergeRule(**rule) for rule in rules],
    )


def _merged_remaps(
    existing: dict[str, list[dict]] | None, column_name: str, groups: list[ValueMergeRule]
) -> dict[str, list[dict]]:
    """Merges newly-accepted `groups` into a column's existing rule list. A
    source value can only ever belong to one rule at a time -- accepting a
    group that claims a source already owned by an earlier rule moves it to
    the new rule (dropping it from the old one, and dropping the old rule
    entirely if that empties it) rather than leaving it ambiguously matched
    by two WHEN clauses in the generated SQL."""
    existing = existing or {}
    current_rules = [dict(r) for r in existing.get(column_name, [])]
    new_sources = {s for g in groups for s in g.sources}

    for rule in current_rules:
        rule["sources"] = [s for s in rule["sources"] if s not in new_sources]
    current_rules = [r for r in current_rules if r["sources"]]

    by_target = {r["target"]: r for r in current_rules}
    for group in groups:
        if group.target in by_target:
            by_target[group.target]["sources"] = list(
                dict.fromkeys(by_target[group.target]["sources"] + group.sources)
            )
        else:
            new_rule = {"target": group.target, "sources": list(group.sources)}
            current_rules.append(new_rule)
            by_target[group.target] = new_rule

    return {**existing, column_name: current_rules}


async def suggest_value_merge_for_column(
    dataset_id: str, column_name: str, command: str, user: CurrentUser
) -> ValueMergeSuggestion:
    """Asks the LLM to translate a natural-language command (e.g. "merge NY
    and New York City into New York") into structured merge groups against
    the column's *current* state (including any already-accepted merges),
    then computes what the value list would look like if those groups were
    accepted -- without persisting anything, so the dialog can show a
    before/after and let the user Accept or discard the proposal."""
    record = repository.get_dataset(dataset_id, user.id)
    if record is None:
        raise HTTPException(status_code=404, detail="Dataset not found")

    column = _find_column(record, column_name)
    _assert_categorical(column)

    counts = await duckdb_manager.column_value_counts(
        record.parquet_key, column_name, _COLUMN_VALUES_LIMIT, record.value_remaps
    )
    values = [{"value": value, "count": count} for value, count in counts]

    try:
        raw_groups = await suggest_value_merge(column_name, values, command, get_llm_provider())
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Merge suggestion failed: {exc}") from exc

    groups = [ValueMergeRule(**g) for g in raw_groups]
    if not groups:
        return ValueMergeSuggestion(
            groups=[], preview_values=[ColumnValueCount(value=v, count=c) for v, c in counts]
        )

    preview_remaps = _merged_remaps(record.value_remaps, column_name, groups)
    preview_counts = await duckdb_manager.column_value_counts(
        record.parquet_key, column_name, _COLUMN_VALUES_LIMIT, preview_remaps
    )
    return ValueMergeSuggestion(
        groups=groups,
        preview_values=[ColumnValueCount(value=v, count=c) for v, c in preview_counts],
    )


async def accept_value_merge(
    dataset_id: str, column_name: str, groups: list[ValueMergeRule], user: CurrentUser
) -> ColumnValuesResponse:
    """Persists a proposed merge -- permanently, but individually revertible
    later via revert_value_merge."""
    record = repository.get_dataset(dataset_id, user.id)
    if record is None:
        raise HTTPException(status_code=404, detail="Dataset not found")

    _find_column(record, column_name)

    updated_remaps = _merged_remaps(record.value_remaps, column_name, groups)
    updated_record = repository.update_dataset_value_remaps(dataset_id, user.id, updated_remaps)
    if updated_record is None:
        raise HTTPException(status_code=404, detail="Dataset not found")

    counts = await duckdb_manager.column_value_counts(
        updated_record.parquet_key, column_name, _COLUMN_VALUES_LIMIT, updated_record.value_remaps
    )
    return ColumnValuesResponse(
        dataset_id=updated_record.id,
        column=column_name,
        values=[ColumnValueCount(value=v, count=c) for v, c in counts],
        rules=[ValueMergeRule(**r) for r in (updated_record.value_remaps or {}).get(column_name, [])],
    )


async def revert_value_merge(
    dataset_id: str, column_name: str, target: str, user: CurrentUser
) -> ColumnValuesResponse:
    """Permanently removes one active merge rule (identified by its `target`
    label) from a column -- the values it used to merge go back to reading
    as their own original labels."""
    record = repository.get_dataset(dataset_id, user.id)
    if record is None:
        raise HTTPException(status_code=404, detail="Dataset not found")

    _find_column(record, column_name)

    existing = record.value_remaps or {}
    current_rules = existing.get(column_name, [])
    remaining = [r for r in current_rules if r["target"] != target]
    if len(remaining) == len(current_rules):
        raise HTTPException(status_code=404, detail=f"No merge rule found for target {target!r}")

    updated_remaps = {**existing, column_name: remaining}
    updated_record = repository.update_dataset_value_remaps(dataset_id, user.id, updated_remaps)
    if updated_record is None:
        raise HTTPException(status_code=404, detail="Dataset not found")

    counts = await duckdb_manager.column_value_counts(
        updated_record.parquet_key, column_name, _COLUMN_VALUES_LIMIT, updated_record.value_remaps
    )
    return ColumnValuesResponse(
        dataset_id=updated_record.id,
        column=column_name,
        values=[ColumnValueCount(value=v, count=c) for v, c in counts],
        rules=[ValueMergeRule(**r) for r in remaining],
    )


async def _build_chartable_payload(record: repository.DatasetRecord) -> list[dict]:
    """Column payload for the LLM strategist -- shared by
    generate_report_strategy and add_custom_chart. Free-text columns are
    excluded before the prompt is even built -- there's no meaningful
    aggregate chart for a comments/description column."""
    columns = [ColumnInfo(**col) for col in record.schema]
    chartable = [col for col in columns if col.category != "free_text"]
    if not chartable:
        return []

    preview = await duckdb_manager.preview_dataset(record.parquet_key, value_remaps=record.value_remaps)
    samples = _sample_values(preview)
    return [
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


def _with_ids(raw: list[dict]) -> tuple[list[dict], bool]:
    """Recommendations persisted before ChartRecommendation gained `id`
    won't have one -- backfill deterministically on first load after this
    feature shipped. Returns (possibly-updated list, whether anything
    changed) so the caller only re-persists when it actually needed to.
    Every call site that reads `report_strategy` for delete/reorder/cache-hit
    purposes goes through this, so ids are stable across requests once
    backfilled -- required for delete-by-id and reorder-by-id to keep
    matching the same entries the frontend is holding."""
    changed = False
    result = []
    for r in raw:
        if not r.get("id"):
            r = {**r, "id": uuid.uuid4().hex}
            changed = True
        result.append(r)
    return result, changed


async def generate_report_strategy(
    dataset_id: str, force: bool, user: CurrentUser
) -> ReportStrategyResponse:
    """Ask the configured LLM provider for a prioritized set of chart
    recommendations (see strategy_engine.SYSTEM_PROMPT for the datetime ->
    numerical -> categorical ordering and chart-matching rules), then execute
    each recommendation's SQL for real before returning it.

    A dataset's Parquet data never changes after ingest, so the full result
    (recommendations + their already-executed SQL results) is cached on the
    `datasets` row (`report_strategy`) and reused here unless `force` is set
    or no cached result exists yet -- `update_dataset_schema` clears this
    cache whenever column categories change, since recommendations are
    derived from them. `force=True` is what the frontend's "Regenerate
    report" click sends (vs. the initial "Generate visual report" click,
    which is happy to take a cache hit).

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

    if not force and record.report_strategy is not None:
        raw, changed = _with_ids(record.report_strategy)
        if changed:
            repository.update_dataset_report_strategy(dataset_id, user.id, raw)
        cached_recommendations = [ChartRecommendation(**r) for r in raw]
        return ReportStrategyResponse(
            dataset_id=record.id, filename=record.filename, recommendations=cached_recommendations
        )

    # Regenerating (force=True, or nothing cached yet): only the "auto" set
    # is recomputed/replaced below -- any "custom" charts the user added via
    # add_custom_chart() aren't part of this whole-dataset strategy pass, so
    # they're carried forward untouched rather than wiped by a regenerate.
    existing, _ = _with_ids(record.report_strategy or [])
    custom_charts = [r for r in existing if r.get("source") == "custom"]

    payload = await _build_chartable_payload(record)

    if not payload:
        # Persisted explicitly (not just returned) so `report_strategy` reads
        # as "generated, nothing chartable" rather than looking identical to
        # "never generated" (NULL) on the next cache check.
        repository.update_dataset_report_strategy(dataset_id, user.id, custom_charts)
        recommendations = [ChartRecommendation(**r) for r in custom_charts]
        return ReportStrategyResponse(
            dataset_id=record.id, filename=record.filename, recommendations=recommendations
        )

    try:
        suggestions = await suggest_visual_strategy(payload, get_llm_provider())
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Report strategy generation failed: {exc}") from exc

    auto_recommendations = []
    for suggestion in suggestions:
        result = None
        error = None
        try:
            query_result = await duckdb_manager.execute_query(
                record.parquet_key, suggestion["sql"], value_remaps=record.value_remaps
            )
            result = QueryResponse(
                columns=query_result.columns,
                rows=query_result.rows,
                row_count=query_result.row_count,
                truncated=query_result.truncated,
            )
        except (UnsafeQueryError, duckdb.Error) as exc:
            error = str(exc)

        auto_recommendations.append(
            ChartRecommendation(
                id=uuid.uuid4().hex,
                source="auto",
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

    recommendations = auto_recommendations + [ChartRecommendation(**r) for r in custom_charts]
    repository.update_dataset_report_strategy(
        dataset_id, user.id, [r.model_dump(mode="json") for r in recommendations]
    )

    return ReportStrategyResponse(
        dataset_id=record.id, filename=record.filename, recommendations=recommendations
    )


async def add_custom_chart(dataset_id: str, prompt: str, user: CurrentUser) -> ChartRecommendation:
    """Adds one LLM-generated chart matching a user's free-text request
    (e.g. "distribution of annual income city wise") to the dataset's
    existing report -- reuses the same column payload and SQL-safety guard
    as generate_report_strategy, but asks for exactly one recommendation
    instead of a full strategy, and appends rather than replaces the
    persisted `report_strategy` cache."""
    record = repository.get_dataset(dataset_id, user.id)
    if record is None:
        raise HTTPException(status_code=404, detail="Dataset not found")

    payload = await _build_chartable_payload(record)
    if not payload:
        raise HTTPException(status_code=400, detail="This dataset has no chartable columns")

    try:
        suggestion = await suggest_custom_chart(prompt, payload, get_llm_provider())
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Couldn't generate that chart: {exc}") from exc

    result = None
    error = None
    try:
        query_result = await duckdb_manager.execute_query(
            record.parquet_key, suggestion["sql"], value_remaps=record.value_remaps
        )
        result = QueryResponse(
            columns=query_result.columns,
            rows=query_result.rows,
            row_count=query_result.row_count,
            truncated=query_result.truncated,
        )
    except (UnsafeQueryError, duckdb.Error) as exc:
        error = str(exc)

    new_chart = ChartRecommendation(
        id=uuid.uuid4().hex,
        source="custom",
        column=suggestion["column"],
        partition_type=suggestion["partition_type"],
        chart_type=suggestion["chart_type"],
        title=suggestion["title"],
        rationale=suggestion["rationale"],
        sql=suggestion["sql"],
        result=result,
        error=error,
    )

    existing, _ = _with_ids(record.report_strategy or [])
    repository.update_dataset_report_strategy(
        dataset_id, user.id, existing + [new_chart.model_dump(mode="json")]
    )

    return new_chart


def remove_chart(dataset_id: str, chart_id: str, user: CurrentUser) -> ReportStrategyResponse:
    """Deletes one chart (e.g. one the auto-generated report or a custom
    request produced that turned out useless) from the dataset's persisted
    report_strategy. Charts predating the `id` field are backfilled first
    (see _with_ids) so this can still match them."""
    record = repository.get_dataset(dataset_id, user.id)
    if record is None:
        raise HTTPException(status_code=404, detail="Dataset not found")

    existing, _ = _with_ids(record.report_strategy or [])
    remaining = [r for r in existing if r["id"] != chart_id]
    if len(remaining) == len(existing):
        raise HTTPException(status_code=404, detail="Chart not found")

    repository.update_dataset_report_strategy(dataset_id, user.id, remaining)
    recommendations = [ChartRecommendation(**r) for r in remaining]
    return ReportStrategyResponse(
        dataset_id=record.id, filename=record.filename, recommendations=recommendations
    )


def update_chart(
    dataset_id: str, chart_id: str, request: UpdateChartRequest, user: CurrentUser
) -> ChartRecommendation:
    """Edits one chart's displayed title/rationale in place -- unlike
    add_custom_chart/remove_chart/reorder_charts, this never touches `sql`
    or re-runs the query, it's purely a label edit. `exclude_unset=True`
    distinguishes "not provided" from an explicit `rationale: ""` the same
    way update_dataset_metadata does for description/notes."""
    record = repository.get_dataset(dataset_id, user.id)
    if record is None:
        raise HTTPException(status_code=404, detail="Dataset not found")

    fields = request.model_dump(exclude_unset=True)
    if "title" in fields:
        fields["title"] = fields["title"].strip()
    if "rationale" in fields and fields["rationale"] is not None:
        fields["rationale"] = fields["rationale"].strip()

    existing, _ = _with_ids(record.report_strategy or [])
    updated_chart: dict | None = None
    updated_list = []
    for r in existing:
        if r["id"] == chart_id:
            r = {**r, **fields}
            updated_chart = r
        updated_list.append(r)

    if updated_chart is None:
        raise HTTPException(status_code=404, detail="Chart not found")

    repository.update_dataset_report_strategy(dataset_id, user.id, updated_list)
    return ChartRecommendation(**updated_chart)


def reorder_charts(dataset_id: str, chart_ids: list[str], user: CurrentUser) -> ReportStrategyResponse:
    """Whole-array reorder (the frontend already holds the full list to
    reorder locally before persisting -- same pattern as
    presentations.replace_presentation()/settings' preset arrays, simpler
    than a granular "move to index N" endpoint for a capped-size list).
    `chart_ids` must be a permutation of the dataset's current chart ids
    exactly -- a mismatch (stale client state, a chart deleted elsewhere in
    the meantime) is rejected rather than silently dropping or ignoring the
    extras, since either is a sign the client's copy of the list is stale."""
    record = repository.get_dataset(dataset_id, user.id)
    if record is None:
        raise HTTPException(status_code=404, detail="Dataset not found")

    existing, _ = _with_ids(record.report_strategy or [])
    by_id = {r["id"]: r for r in existing}
    if set(chart_ids) != set(by_id):
        raise HTTPException(
            status_code=400, detail="chart_ids must match the dataset's current charts exactly"
        )

    reordered = [by_id[chart_id] for chart_id in chart_ids]
    repository.update_dataset_report_strategy(dataset_id, user.id, reordered)
    recommendations = [ChartRecommendation(**r) for r in reordered]
    return ReportStrategyResponse(
        dataset_id=record.id, filename=record.filename, recommendations=recommendations
    )


def _insights_cache_key(request: GenerateInsightsRequest) -> str:
    """Keyed by the exact chart view -- column/chart_type/partition_type plus
    the aggregated result's columns+rows -- NOT the whole dataset, since the
    same column can be viewed through many different filter/bin states, each
    producing different aggregated data (and so, potentially, different
    insight text). Deliberately excludes `title`: insights.py's build_prompt()
    does interpolate the title into the prompt, so a renamed column alias
    changing a chart's displayed title could serve stale-titled insight text
    on a cache hit -- an accepted tradeoff (the system prompt already tells
    the model not to restate the title verbatim, so the practical risk is
    low), not an oversight."""
    canonical = json.dumps(
        {
            "column": request.column,
            "chart_type": request.chart_type,
            "partition_type": request.partition_type,
            "result": {"columns": request.result.columns, "rows": request.result.rows},
        },
        sort_keys=True,
        default=str,
    )
    return hashlib.sha256(canonical.encode()).hexdigest()


async def generate_chart_insights(
    dataset_id: str, request: GenerateInsightsRequest, user: CurrentUser
) -> InsightsResponse:
    """The chart's aggregated data comes straight from the request body (the
    frontend already has it, whether from the original report-strategy
    result or a client-rebuilt fast-aggregation query) -- this only checks
    dataset ownership, it never re-runs SQL itself.

    Results are cached permanently per exact chart view (see
    _insights_cache_key) -- unlike report_strategy, there's no invalidation
    path here: the Parquet data behind any one specific aggregation never
    changes, so a cache hit is valid forever."""
    record = repository.get_dataset(dataset_id, user.id)
    if record is None:
        raise HTTPException(status_code=404, detail="Dataset not found")

    cache_key = _insights_cache_key(request)
    cached = insights_cache_repository.get_cached_insights(dataset_id, cache_key)
    if cached is not None:
        return InsightsResponse(insights=cached.insights)

    try:
        insights = await generate_insights(request.model_dump(), get_llm_provider())
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Insight generation failed: {exc}") from exc

    insights_cache_repository.save_insights_cache(
        dataset_id=dataset_id, owner_id=user.id, cache_key=cache_key, insights=insights
    )

    return InsightsResponse(insights=insights)
