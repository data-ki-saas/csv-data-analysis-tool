from typing import Literal

from pydantic import BaseModel

ThemeMode = Literal["light", "dark", "system"]
ColorTheme = Literal["winter", "pastel", "photochromatic", "warm", "spring", "contrast"]


class UserSettings(BaseModel):
    theme_mode: ThemeMode
    color_theme: ColorTheme


class UpdateUserSettings(BaseModel):
    theme_mode: ThemeMode
    color_theme: ColorTheme
