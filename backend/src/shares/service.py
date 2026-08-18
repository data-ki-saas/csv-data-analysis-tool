import secrets

from fastapi import HTTPException

from src.core.auth import CurrentUser
from src.datasets import repository as datasets_repository
from src.datasets.schemas import GenerateInsightsRequest
from src.shares import repository
from src.shares.schemas import ChartShare


def _assert_owns_dataset(dataset_id: str, user: CurrentUser) -> None:
    if datasets_repository.get_dataset(dataset_id, user.id) is None:
        raise HTTPException(status_code=404, detail="Dataset not found")


def _to_chart_share(record: repository.ChartShareRecord) -> ChartShare:
    return ChartShare(
        token=record.token,
        title=record.title,
        chart_type=record.chart_type,
        partition_type=record.partition_type,
        column=record.column_name,
        result=record.result,
        created_at=record.created_at,
    )


def create_chart_share(
    dataset_id: str, request: GenerateInsightsRequest, user: CurrentUser
) -> ChartShare:
    """Snapshots the chart's already-aggregated result at share time -- same
    reasoning as generate_chart_insights() and "Pin to presentation": once
    computed, a chart's result is immutable and safe to persist, so the
    public /share/<token> page never needs to touch the dataset's Parquet,
    R2, or SQL execution at all, only this one row."""
    _assert_owns_dataset(dataset_id, user)
    token = secrets.token_urlsafe(24)
    record = repository.create_share(
        dataset_id=dataset_id,
        owner_id=user.id,
        token=token,
        title=request.title,
        chart_type=request.chart_type,
        partition_type=request.partition_type,
        column_name=request.column,
        result=request.result.model_dump(),
    )
    return _to_chart_share(record)


def revoke_chart_share(dataset_id: str, token: str, user: CurrentUser) -> None:
    _assert_owns_dataset(dataset_id, user)
    repository.delete_share(dataset_id, user.id, token)


def get_public_chart_share(token: str) -> ChartShare:
    """No ownership check -- this is the public endpoint. Anyone with the
    (unguessable) token can read the snapshot; the token itself is the only
    access control."""
    record = repository.get_share_by_token(token)
    if record is None:
        raise HTTPException(status_code=404, detail="This share link is invalid or has been revoked")
    return _to_chart_share(record)
