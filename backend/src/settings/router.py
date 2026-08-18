from fastapi import APIRouter, Depends

from src.core.auth import CurrentUser, get_current_user
from src.settings import service
from src.settings.schemas import UpdateUserSettings, UserSettings

router = APIRouter(prefix="/api/settings", tags=["settings"])


@router.get("", response_model=UserSettings)
async def get_settings(user: CurrentUser = Depends(get_current_user)) -> UserSettings:
    return service.get_settings(user)


@router.put("", response_model=UserSettings)
async def update_settings(
    request: UpdateUserSettings, user: CurrentUser = Depends(get_current_user)
) -> UserSettings:
    return service.update_settings(request, user)
