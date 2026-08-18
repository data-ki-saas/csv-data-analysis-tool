from fastapi import APIRouter, Depends

from src.core.auth import CurrentUser, get_current_user
from src.settings import service
from src.settings.schemas import (
    UpdateFooterPresets,
    UpdateHeaderPresets,
    UpdateUserSettings,
    UserSettings,
)

router = APIRouter(prefix="/api/settings", tags=["settings"])


@router.get("", response_model=UserSettings)
async def get_settings(user: CurrentUser = Depends(get_current_user)) -> UserSettings:
    return service.get_settings(user)


@router.put("", response_model=UserSettings)
async def update_settings(
    request: UpdateUserSettings, user: CurrentUser = Depends(get_current_user)
) -> UserSettings:
    return service.update_settings(request, user)


@router.put("/header-presets", response_model=UserSettings)
async def update_header_presets(
    request: UpdateHeaderPresets, user: CurrentUser = Depends(get_current_user)
) -> UserSettings:
    return service.update_header_presets(request, user)


@router.put("/footer-presets", response_model=UserSettings)
async def update_footer_presets(
    request: UpdateFooterPresets, user: CurrentUser = Depends(get_current_user)
) -> UserSettings:
    return service.update_footer_presets(request, user)
