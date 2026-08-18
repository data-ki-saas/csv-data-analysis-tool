from fastapi import APIRouter, Depends

from src.core.auth import CurrentUser, get_current_user
from src.presentations import service
from src.presentations.schemas import PinBlockRequest, Presentation, UpdatePresentationRequest

router = APIRouter(prefix="/api/datasets/{dataset_id}/presentation", tags=["presentations"])


@router.get("", response_model=Presentation)
async def get_presentation(
    dataset_id: str, user: CurrentUser = Depends(get_current_user)
) -> Presentation:
    return service.get_presentation(dataset_id, user)


@router.put("", response_model=Presentation)
async def replace_presentation(
    dataset_id: str,
    request: UpdatePresentationRequest,
    user: CurrentUser = Depends(get_current_user),
) -> Presentation:
    return service.replace_presentation(dataset_id, request, user)


@router.post("/pin", response_model=Presentation)
async def pin_block(
    dataset_id: str, request: PinBlockRequest, user: CurrentUser = Depends(get_current_user)
) -> Presentation:
    return service.pin_block(dataset_id, request, user)
