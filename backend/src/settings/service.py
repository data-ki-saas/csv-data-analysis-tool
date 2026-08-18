from src.core.auth import CurrentUser
from src.settings import repository
from src.settings.schemas import UpdateUserSettings, UserSettings


def get_settings(user: CurrentUser) -> UserSettings:
    record = repository.get_settings(user.id)
    if record is None:
        return UserSettings(
            theme_mode=repository.DEFAULT_THEME_MODE,
            color_theme=repository.DEFAULT_COLOR_THEME,
        )
    return UserSettings(theme_mode=record.theme_mode, color_theme=record.color_theme)


def update_settings(request: UpdateUserSettings, user: CurrentUser) -> UserSettings:
    record = repository.upsert_settings(
        owner_id=user.id, theme_mode=request.theme_mode, color_theme=request.color_theme
    )
    return UserSettings(theme_mode=record.theme_mode, color_theme=record.color_theme)
