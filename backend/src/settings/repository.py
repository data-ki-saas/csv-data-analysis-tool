from dataclasses import dataclass

from src.core.supabase_client import get_supabase_client

_TABLE = "user_settings"

DEFAULT_THEME_MODE = "system"
DEFAULT_COLOR_THEME = "winter"


@dataclass
class UserSettingsRecord:
    owner_id: str
    theme_mode: str
    color_theme: str


def get_settings(owner_id: str) -> UserSettingsRecord | None:
    result = (
        get_supabase_client()
        .table(_TABLE)
        .select("*")
        .eq("owner_id", owner_id)
        .limit(1)
        .execute()
    )
    if not result.data:
        return None
    row = result.data[0]
    return UserSettingsRecord(
        owner_id=row["owner_id"], theme_mode=row["theme_mode"], color_theme=row["color_theme"]
    )


def upsert_settings(*, owner_id: str, theme_mode: str, color_theme: str) -> UserSettingsRecord:
    payload = {"owner_id": owner_id, "theme_mode": theme_mode, "color_theme": color_theme}
    result = (
        get_supabase_client().table(_TABLE).upsert(payload, on_conflict="owner_id").execute()
    )
    row = result.data[0]
    return UserSettingsRecord(
        owner_id=row["owner_id"], theme_mode=row["theme_mode"], color_theme=row["color_theme"]
    )
