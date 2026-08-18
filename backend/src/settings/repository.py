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
    header_presets: list[dict]
    footer_presets: list[dict]


def _to_record(row: dict) -> UserSettingsRecord:
    return UserSettingsRecord(
        owner_id=row["owner_id"],
        theme_mode=row["theme_mode"],
        color_theme=row["color_theme"],
        header_presets=row.get("header_presets") or [],
        footer_presets=row.get("footer_presets") or [],
    )


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
    return _to_record(result.data[0])


def upsert_settings(*, owner_id: str, theme_mode: str, color_theme: str) -> UserSettingsRecord:
    payload = {"owner_id": owner_id, "theme_mode": theme_mode, "color_theme": color_theme}
    result = (
        get_supabase_client().table(_TABLE).upsert(payload, on_conflict="owner_id").execute()
    )
    return _to_record(result.data[0])


def update_header_presets(owner_id: str, presets: list[dict]) -> UserSettingsRecord:
    # Deliberately omits theme_mode/color_theme/footer_presets from the
    # payload -- PostgREST's upsert only SETs the columns present in the
    # payload on conflict, so this can't clobber the other independently-
    # edited fields on this same singleton row. A fresh row falls back to
    # the table's own column defaults for everything else.
    payload = {"owner_id": owner_id, "header_presets": presets}
    result = (
        get_supabase_client().table(_TABLE).upsert(payload, on_conflict="owner_id").execute()
    )
    return _to_record(result.data[0])


def update_footer_presets(owner_id: str, presets: list[dict]) -> UserSettingsRecord:
    payload = {"owner_id": owner_id, "footer_presets": presets}
    result = (
        get_supabase_client().table(_TABLE).upsert(payload, on_conflict="owner_id").execute()
    )
    return _to_record(result.data[0])
