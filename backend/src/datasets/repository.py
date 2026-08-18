import uuid
from dataclasses import dataclass

from src.core.supabase_client import get_supabase_client

_TABLE = "datasets"


@dataclass
class DatasetRecord:
    id: str
    owner_id: str
    filename: str
    row_count: int
    schema: list[dict]
    raw_key: str
    parquet_key: str
    health_score: float
    created_at: str


def create_dataset(
    *,
    owner_id: str,
    filename: str,
    row_count: int,
    schema: list[dict],
    raw_key: str,
    parquet_key: str,
    health_score: float,
) -> DatasetRecord:
    payload = {
        "id": str(uuid.uuid4()),
        "owner_id": owner_id,
        "filename": filename,
        "row_count": row_count,
        "schema": schema,
        "raw_key": raw_key,
        "parquet_key": parquet_key,
        "health_score": health_score,
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
    at ingestion and never change here."""
    result = (
        get_supabase_client()
        .table(_TABLE)
        .update({"schema": schema})
        .eq("id", dataset_id)
        .eq("owner_id", owner_id)
        .execute()
    )
    if not result.data:
        return None
    return DatasetRecord(**result.data[0])
