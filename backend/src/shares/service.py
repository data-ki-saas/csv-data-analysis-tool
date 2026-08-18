import secrets

from fastapi import HTTPException

from src.core.auth import CurrentUser
from src.datasets import repository as datasets_repository
from src.datasets.schemas import GenerateInsightsRequest
from src.settings import repository as settings_repository
from src.shares import repository
from src.shares.schemas import ChartShare


def _get_owned_dataset(dataset_id: str, user: CurrentUser) -> datasets_repository.DatasetRecord:
    record = datasets_repository.get_dataset(dataset_id, user.id)
    if record is None:
        raise HTTPException(status_code=404, detail="Dataset not found")
    return record


def _active_preset(presets: list[dict]) -> dict | None:
    return next((p for p in presets if p.get("enabled")), None)


def _to_chart_share(record: repository.ChartShareRecord) -> ChartShare:
    return ChartShare(
        token=record.token,
        title=record.title,
        chart_type=record.chart_type,
        partition_type=record.partition_type,
        column=record.column_name,
        result=record.result,
        created_at=record.created_at,
        header_snapshot=record.header_snapshot,
        footer_snapshot=record.footer_snapshot,
        dataset_name=record.dataset_name,
        dataset_description=record.dataset_description,
    )


def create_chart_share(
    dataset_id: str, request: GenerateInsightsRequest, user: CurrentUser
) -> ChartShare:
    """Snapshots the chart's already-aggregated result at share time -- same
    reasoning as generate_chart_insights() and "Pin to presentation": once
    computed, a chart's result is immutable and safe to persist, so the
    public /share/<token> page never needs to touch the dataset's Parquet,
    R2, or SQL execution at all, only this one row.

    Also snapshots the owner's currently-active header/footer branding
    presets (if any), and the dataset's own name/description, for the same
    reason: the public page has no session to fetch either live with, and a
    later branding change or dataset rename shouldn't retroactively alter a
    link already shared."""
    dataset = _get_owned_dataset(dataset_id, user)
    token = secrets.token_urlsafe(24)

    owner_settings = settings_repository.get_settings(user.id)
    header_snapshot = _active_preset(owner_settings.header_presets) if owner_settings else None
    footer_snapshot = _active_preset(owner_settings.footer_presets) if owner_settings else None

    record = repository.create_share(
        dataset_id=dataset_id,
        owner_id=user.id,
        token=token,
        title=request.title,
        chart_type=request.chart_type,
        partition_type=request.partition_type,
        column_name=request.column,
        result=request.result.model_dump(),
        header_snapshot=header_snapshot,
        footer_snapshot=footer_snapshot,
        dataset_name=dataset.name,
        dataset_description=dataset.description,
    )
    return _to_chart_share(record)


def revoke_chart_share(dataset_id: str, token: str, user: CurrentUser) -> None:
    _get_owned_dataset(dataset_id, user)
    repository.delete_share(dataset_id, user.id, token)


def get_public_chart_share(token: str) -> ChartShare:
    """No ownership check -- this is the public endpoint. Anyone with the
    (unguessable) token can read the snapshot; the token itself is the only
    access control."""
    record = repository.get_share_by_token(token)
    if record is None:
        raise HTTPException(status_code=404, detail="This share link is invalid or has been revoked")
    return _to_chart_share(record)
