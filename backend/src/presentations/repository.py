from dataclasses import dataclass

from src.core.supabase_client import get_supabase_client

_TABLE = "presentations"

DEFAULT_TITLE = "Untitled Presentation"


@dataclass
class PresentationRecord:
    dataset_id: str
    owner_id: str
    title: str
    pages: list[dict]
    updated_at: str


def get_presentation(dataset_id: str, owner_id: str) -> PresentationRecord | None:
    result = (
        get_supabase_client()
        .table(_TABLE)
        .select("*")
        .eq("dataset_id", dataset_id)
        .eq("owner_id", owner_id)
        .limit(1)
        .execute()
    )
    if not result.data:
        return None
    row = result.data[0]
    return PresentationRecord(
        dataset_id=row["dataset_id"], owner_id=row["owner_id"], title=row["title"],
        pages=row["pages"], updated_at=row["updated_at"],
    )


def upsert_presentation(
    *, dataset_id: str, owner_id: str, title: str, pages: list[dict]
) -> PresentationRecord:
    payload = {"dataset_id": dataset_id, "owner_id": owner_id, "title": title, "pages": pages}
    result = (
        get_supabase_client()
        .table(_TABLE)
        .upsert(payload, on_conflict="dataset_id,owner_id")
        .execute()
    )
    row = result.data[0]
    return PresentationRecord(
        dataset_id=row["dataset_id"], owner_id=row["owner_id"], title=row["title"],
        pages=row["pages"], updated_at=row["updated_at"],
    )
