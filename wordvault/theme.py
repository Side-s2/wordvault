"""全局主题与配色。"""

from __future__ import annotations

import flet as ft

# 品牌主色（靛蓝）
PRIMARY = "#5B67F1"
PRIMARY_DARK = "#8C96F5"

SUCCESS = "#2E9E5B"
DANGER = "#D9534F"
WARN = "#E8A13D"
INFO = "#3E8BD9"

# 熟练度五档颜色
TIER_COLORS = {
    "生疏": "#D9534F",
    "学习中": "#E8A13D",
    "熟练": "#3E8BD9",
    "已掌握": "#2E9E5B",
    "未开始": "#9AA0AC",
}


def build_theme(font_family: str | None = None) -> ft.Theme:
    """Material 3 主题，颜色跟随品牌主色。"""
    return ft.Theme(
        color_scheme_seed=PRIMARY,
        use_material3=True,
        font_family=font_family,
    )


def build_dark_theme(font_family: str | None = None) -> ft.Theme:
    return ft.Theme(
        color_scheme_seed=PRIMARY_DARK,
        use_material3=True,
        font_family=font_family,
    )


def apply_theme_mode(page: ft.Page, mode: str) -> None:
    mapping = {
        "system": ft.ThemeMode.SYSTEM,
        "light": ft.ThemeMode.LIGHT,
        "dark": ft.ThemeMode.DARK,
    }
    page.theme_mode = mapping.get(mode, ft.ThemeMode.SYSTEM)
    page.update()
