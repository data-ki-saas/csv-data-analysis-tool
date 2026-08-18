import uuid

from fastapi import HTTPException

from src.core.auth import CurrentUser
from src.datasets import repository as datasets_repository
from src.presentations import repository
from src.presentations.repository import DEFAULT_TITLE
from src.presentations.schemas import (
    Presentation,
    PresentationPage,
    PinBlockRequest,
    UpdatePresentationRequest,
)


def _assert_owns_dataset(dataset_id: str, user: CurrentUser) -> None:
    if datasets_repository.get_dataset(dataset_id, user.id) is None:
        raise HTTPException(status_code=404, detail="Dataset not found")


def _to_presentation(record: repository.PresentationRecord | None, dataset_id: str) -> Presentation:
    if record is None:
        return Presentation(dataset_id=dataset_id, title=DEFAULT_TITLE, pages=[])
    return Presentation(
        dataset_id=record.dataset_id, title=record.title, pages=record.pages, updated_at=record.updated_at
    )


def get_presentation(dataset_id: str, user: CurrentUser) -> Presentation:
    """Returns a default empty presentation rather than 404ing when none has
    been saved yet -- there's nothing to "not find," the user just hasn't
    pinned anything (same reasoning as src.settings.service.get_settings())."""
    _assert_owns_dataset(dataset_id, user)
    return _to_presentation(repository.get_presentation(dataset_id, user.id), dataset_id)


def replace_presentation(
    dataset_id: str, request: UpdatePresentationRequest, user: CurrentUser
) -> Presentation:
    """The builder's autosave: persists the whole document verbatim. Reorder/
    rename/delete all happen client-side; this just writes the result."""
    _assert_owns_dataset(dataset_id, user)
    pages_dicts = [page.model_dump() for page in request.pages]
    record = repository.upsert_presentation(
        dataset_id=dataset_id, owner_id=user.id, title=request.title, pages=pages_dicts
    )
    return _to_presentation(record, dataset_id)


def pin_block(dataset_id: str, request: PinBlockRequest, user: CurrentUser) -> Presentation:
    """Pinning is its own atomic, immediately-persisted write -- separate
    from the builder's debounced autosave -- so a pin from the report feed
    is never lost if the user never opens the builder at all."""
    _assert_owns_dataset(dataset_id, user)

    current = _to_presentation(repository.get_presentation(dataset_id, user.id), dataset_id)
    pages = [page.model_dump() for page in current.pages]

    new_blocks = [
        {
            "type": "chart",
            "id": request.chart.id,
            "title": request.chart.title,
            "chart_type": request.chart.chart_type,
            "partition_type": request.chart.partition_type,
            "column": request.chart.column,
            "result": request.chart.result.model_dump(),
        }
    ]
    if request.insights:
        new_blocks.append(
            {
                "type": "insights",
                "id": f"{request.chart.id}-insights",
                "chart_title": request.chart.title,
                "bullets": request.insights,
            }
        )

    if not pages:
        pages = [PresentationPage(id=str(uuid.uuid4()), title="Page 1", blocks=[]).model_dump()]
    pages[-1]["blocks"] = [*pages[-1]["blocks"], *new_blocks]

    record = repository.upsert_presentation(
        dataset_id=dataset_id, owner_id=user.id, title=current.title, pages=pages
    )
    return _to_presentation(record, dataset_id)
