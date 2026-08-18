import nh3
from fastapi import HTTPException

from src.core.auth import CurrentUser
from src.core.config import settings as app_settings
from src.settings import repository
from src.settings.schemas import (
    FooterPreset,
    HeaderPreset,
    UpdateFooterPresets,
    UpdateHeaderPresets,
    UpdateUserSettings,
    UserSettings,
)

# Matches exactly what the frontend's hand-rolled RichTextEditor can produce
# (Bold/Italic/Link/line-break) -- nothing else, so no <script>/<style>/
# <iframe>/on*-handler can ever survive into a stored footer, which is later
# rendered to other people (shared links, exported PDFs), not just the owner.
_FOOTER_ALLOWED_TAGS = {"p", "br", "b", "strong", "i", "em", "u", "a", "ul", "ol", "li"}
_FOOTER_ALLOWED_ATTRIBUTES = {"a": {"href"}}


def _to_user_settings(record: repository.UserSettingsRecord) -> UserSettings:
    return UserSettings(
        theme_mode=record.theme_mode,
        color_theme=record.color_theme,
        header_presets=[HeaderPreset(**p) for p in record.header_presets],
        footer_presets=[FooterPreset(**p) for p in record.footer_presets],
    )


def get_settings(user: CurrentUser) -> UserSettings:
    record = repository.get_settings(user.id)
    if record is None:
        return UserSettings(
            theme_mode=repository.DEFAULT_THEME_MODE,
            color_theme=repository.DEFAULT_COLOR_THEME,
        )
    return _to_user_settings(record)


def update_settings(request: UpdateUserSettings, user: CurrentUser) -> UserSettings:
    record = repository.upsert_settings(
        owner_id=user.id, theme_mode=request.theme_mode, color_theme=request.color_theme
    )
    return _to_user_settings(record)


def _assert_at_most_one_enabled(presets: list) -> None:
    if sum(1 for p in presets if p.enabled) > 1:
        raise HTTPException(status_code=400, detail="Only one preset can be enabled at a time")


def update_header_presets(request: UpdateHeaderPresets, user: CurrentUser) -> UserSettings:
    _assert_at_most_one_enabled(request.presets)
    for preset in request.presets:
        if preset.logo and len(preset.logo.encode()) > app_settings.max_logo_size_bytes:
            raise HTTPException(
                status_code=400,
                detail=f"Logo exceeds the {app_settings.max_logo_size_kb}KB limit",
            )
    record = repository.update_header_presets(user.id, [p.model_dump() for p in request.presets])
    return _to_user_settings(record)


def update_footer_presets(request: UpdateFooterPresets, user: CurrentUser) -> UserSettings:
    _assert_at_most_one_enabled(request.presets)
    sanitized = [
        p.model_copy(
            update={
                "html": nh3.clean(
                    p.html, tags=_FOOTER_ALLOWED_TAGS, attributes=_FOOTER_ALLOWED_ATTRIBUTES
                )
            }
        )
        for p in request.presets
    ]
    record = repository.update_footer_presets(user.id, [p.model_dump() for p in sanitized])
    return _to_user_settings(record)
