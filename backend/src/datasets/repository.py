import uuid
from dataclasses import dataclass

from src.core.supabase_client import get_supabase_client

_TABLE = "datasets"


@dataclass
class DatasetRecord:
    id: str
    owner_id: str
    filename: str
    name: str
    description: str | None
    notes: str | None
    row_count: int
    schema: list[dict]
    raw_key: str
    parquet_key: str
    health_score: float
    created_at: str
    content_hash: str | None
    report_strategy: list[dict] | None


def create_dataset(
    *,
    owner_id: str,
    filename: str,
    name: str,
    row_count: int,
    schema: list[dict],
    raw_key: str,
    parquet_key: str,
    health_score: float,
    content_hash: str,
    description: str | None = None,
    notes: str | None = None,
    report_strategy: list[dict] | None = None,
) -> DatasetRecord:
    payload = {
        "id": str(uuid.uuid4()),
        "owner_id": owner_id,
        "filename": filename,
        "name": name,
        "description": description,
        "notes": notes,
        "row_count": row_count,
        "schema": schema,
        "raw_key": raw_key,
        "parquet_key": parquet_key,
        "health_score": health_score,
        "content_hash": content_hash,
        "report_strategy": report_strategy,
    }
    result = get_supabase_client().table(_TABLE).insert(payload).execute()
    return DatasetRecord(**result.data[0])


def get_dataset(dataset_id: str, owner_id: str) -> DatasetRecord | None:
    result = (
        get_supabase_client()
        .table(_TABLE)
        .select("*")
        .eq("id", dataset_id)
        .eq("owner_id", owner_id)
        .limit(1)
        .execute()
    )
    if not result.data:
        return None
    return DatasetRecord(**result.data[0])


def get_dataset_by_content_hash(owner_id: str, content_hash: str) -> DatasetRecord | None:
    """Look up an existing dataset with byte-identical CSV content for this
    owner, for upload dedup (see service.ingest_csv_upload). If more than one
    match exists (earlier duplicate uploads), returns the oldest -- arbitrary
    but stable, and it doesn't matter which one gets pointed at since their
    storage is identical."""
    result = (
        get_supabase_client()
        .table(_TABLE)
        .select("*")
        .eq("owner_id", owner_id)
        .eq("content_hash", content_hash)
        .order("created_at")
        .limit(1)
        .execute()
    )
    if not result.data:
        return None
    return DatasetRecord(**result.data[0])


def count_datasets_sharing_storage(dataset_id: str, raw_key: str) -> int:
    """How many OTHER dataset rows currently point at this raw_key. Used by
    service.delete_dataset to decide whether it's safe to delete the
    underlying R2 objects, or whether a sibling row deduped from this content
    still needs them. Checking raw_key alone is sufficient: raw_key and
    parquet_key are always assigned or copied together as a pair (see
    ingest_csv_upload/get_dataset_by_content_hash), never independently, so
    their reference counts are always equal."""
    result = (
        get_supabase_client()
        .table(_TABLE)
        .select("id", count="exact")
        .eq("raw_key", raw_key)
        .neq("id", dataset_id)
        .execute()
    )
    return result.count or 0


def update_dataset_report_strategy(
    dataset_id: str, owner_id: str, report_strategy: list[dict] | None
) -> DatasetRecord | None:
    """Persist (or, passing None, clear) the cached report-strategy result."""
    result = (
        get_supabase_client()
        .table(_TABLE)
        .update({"report_strategy": report_strategy})
        .eq("id", dataset_id)
        .eq("owner_id", owner_id)
        .execute()
    )
    if not result.data:
        return None
    return DatasetRecord(**result.data[0])


def update_dataset_metadata(dataset_id: str, owner_id: str, fields: dict) -> DatasetRecord | None:
    """Partial update for the user-editable name/description -- `fields` is
    whatever the caller decided actually changed (see
    service.update_dataset_metadata, which uses Pydantic's
    `exclude_unset=True` to distinguish "not provided" from "explicitly
    cleared to empty/null", something a plain `None`-means-unset convention
    can't express since description's own valid range already includes
    None)."""
    result = (
        get_supabase_client()
        .table(_TABLE)
        .update(fields)
        .eq("id", dataset_id)
        .eq("owner_id", owner_id)
        .execute()
    )
    if not result.data:
        return None
    return DatasetRecord(**result.data[0])


def list_datasets(owner_id: str) -> list[DatasetRecord]:
    result = (
        get_supabase_client()
        .table(_TABLE)
        .select("*")
        .eq("owner_id", owner_id)
        .order("created_at", desc=True)
        .execute()
    )
    return [DatasetRecord(**row) for row in result.data]


def delete_dataset(dataset_id: str, owner_id: str) -> None:
    get_supabase_client().table(_TABLE).delete().eq("id", dataset_id).eq(
        "owner_id", owner_id
    ).execute()


def update_dataset_schema(dataset_id: str, owner_id: str, schema: list[dict]) -> DatasetRecord | None:
    """Persist an updated column schema -- used after an AI type-review pass
    or a user's manual category override. Row count/health/keys are set once
    at ingestion and never change here. Also clears any cached report_strategy
    in the same statement (rather than a separate call, which could race a
    concurrent report-strategy write) -- chart recommendations are derived
    from column categories, so a stale cache must not survive a schema edit."""
    result = (
        get_supabase_client()
        .table(_TABLE)
        .update({"schema": schema, "report_strategy": None})
        .eq("id", dataset_id)
        .eq("owner_id", owner_id)
        .execute()
    )
    if not result.data:
        return None
    return DatasetRecord(**result.data[0])
