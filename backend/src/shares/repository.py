from dataclasses import dataclass

from src.core.supabase_client import get_supabase_client

_TABLE = "chart_shares"


@dataclass
class ChartShareRecord:
    id: str
    dataset_id: str
    owner_id: str
    token: str
    title: str
    chart_type: str
    partition_type: str
    column_name: str
    result: dict
    created_at: str
    header_snapshot: dict | None
    footer_snapshot: dict | None


def create_share(
    *,
    dataset_id: str,
    owner_id: str,
    token: str,
    title: str,
    chart_type: str,
    partition_type: str,
    column_name: str,
    result: dict,
    header_snapshot: dict | None = None,
    footer_snapshot: dict | None = None,
) -> ChartShareRecord:
    payload = {
        "dataset_id": dataset_id,
        "owner_id": owner_id,
        "token": token,
        "title": title,
        "chart_type": chart_type,
        "partition_type": partition_type,
        "column_name": column_name,
        "result": result,
        "header_snapshot": header_snapshot,
        "footer_snapshot": footer_snapshot,
    }
    result_row = get_supabase_client().table(_TABLE).insert(payload).execute()
    return ChartShareRecord(**result_row.data[0])


def get_share_by_token(token: str) -> ChartShareRecord | None:
    """No owner_id filter -- this is the public, unauthenticated lookup a
    /share/<token> page visitor hits. Ownership only matters for creating and
    revoking a share, never for reading one by its (unguessable) token."""
    result = get_supabase_client().table(_TABLE).select("*").eq("token", token).limit(1).execute()
    if not result.data:
        return None
    return ChartShareRecord(**result.data[0])


def delete_share(dataset_id: str, owner_id: str, token: str) -> None:
    get_supabase_client().table(_TABLE).delete().eq("dataset_id", dataset_id).eq(
        "owner_id", owner_id
    ).eq("token", token).execute()
