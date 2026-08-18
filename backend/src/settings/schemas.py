from typing import Annotated, Literal

from pydantic import BaseModel, Field

ThemeMode = Literal["light", "dark", "system"]
ColorTheme = Literal["winter", "pastel", "photochromatic", "warm", "spring", "contrast"]

MAX_PRESETS = 5


class UserSettings(BaseModel):
    theme_mode: ThemeMode
    color_theme: ColorTheme
    header_presets: list["HeaderPreset"] = []
    footer_presets: list["FooterPreset"] = []


class UpdateUserSettings(BaseModel):
    theme_mode: ThemeMode
    color_theme: ColorTheme


class HeaderPreset(BaseModel):
    id: str
    title: str
    logo: str | None = None  # a data URL, capped at settings.max_logo_size_bytes
    enabled: bool = False


class FooterPreset(BaseModel):
    id: str
    # Rich-text HTML from the frontend's hand-rolled editor -- sanitized
    # server-side (see service.py) before ever being persisted, since this is
    # rendered to other people (shared links, exported PDFs), not just the owner.
    html: str
    enabled: bool = False


class UpdateHeaderPresets(BaseModel):
    presets: Annotated[list[HeaderPreset], Field(max_length=MAX_PRESETS)]


class UpdateFooterPresets(BaseModel):
    presets: Annotated[list[FooterPreset], Field(max_length=MAX_PRESETS)]
