from dataclasses import dataclass

from src.core.supabase_client import get_supabase_client

_TABLE = "chart_insights_cache"


@dataclass
class InsightsCacheRecord:
    id: str
    dataset_id: str
    owner_id: str
    cache_key: str
    insights: list[str]
    created_at: str


def get_cached_insights(dataset_id: str, cache_key: str) -> InsightsCacheRecord | None:
    """Permanent cache -- a hit means this exact (column, chart_type,
    partition_type, aggregated result) combination has been explained before.
    Unlike datasets.report_strategy, there's no invalidation path: the
    underlying Parquet data behind any specific aggregation never changes."""
    result = (
        get_supabase_client()
        .table(_TABLE)
        .select("*")
        .eq("dataset_id", dataset_id)
        .eq("cache_key", cache_key)
        .limit(1)
        .execute()
    )
    if not result.data:
        return None
    return InsightsCacheRecord(**result.data[0])


def save_insights_cache(
    *, dataset_id: str, owner_id: str, cache_key: str, insights: list[str]
) -> InsightsCacheRecord:
    """Upsert on (dataset_id, cache_key) rather than a plain insert, so a race
    between two requests computing the same never-before-seen chart view
    doesn't throw a duplicate-key error -- the loser's insights just overwrite
    the winner's, harmlessly (both are valid outputs for identical input)."""
    payload = {
        "dataset_id": dataset_id,
        "owner_id": owner_id,
        "cache_key": cache_key,
        "insights": insights,
    }
    result = (
        get_supabase_client()
        .table(_TABLE)
        .upsert(payload, on_conflict="dataset_id,cache_key")
        .execute()
    )
    return InsightsCacheRecord(**result.data[0])
