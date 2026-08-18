from fastapi import APIRouter, Depends

from src.core.auth import CurrentUser, get_current_user
from src.datasets.schemas import GenerateInsightsRequest
from src.shares import service
from src.shares.schemas import ChartShare

# No single fixed prefix here (unlike presentations/router.py) -- this module
# serves two different path shapes: owner-scoped routes under
# /api/datasets/{dataset_id}/... and the public read under /api/shares/....
router = APIRouter(tags=["shares"])


@router.post("/api/datasets/{dataset_id}/shares", response_model=ChartShare)
async def create_share(
    dataset_id: str,
    request: GenerateInsightsRequest,
    user: CurrentUser = Depends(get_current_user),
) -> ChartShare:
    return service.create_chart_share(dataset_id, request, user)


@router.delete("/api/datasets/{dataset_id}/shares/{token}", status_code=204)
async def revoke_share(
    dataset_id: str, token: str, user: CurrentUser = Depends(get_current_user)
) -> None:
    service.revoke_chart_share(dataset_id, token, user)


@router.get("/api/shares/{token}", response_model=ChartShare)
async def get_share(token: str) -> ChartShare:
    # Deliberately no Depends(get_current_user) -- this is the public route.
    return service.get_public_chart_share(token)
