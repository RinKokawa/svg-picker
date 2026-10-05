"""配色主题 —— 用 dataclass 表达一组 UI 颜色。

每套主题对应一套独立的窗口配色。MainWindow 接收 Theme 实例,
所有颜色都从 `theme.<字段>` 取 —— 不再依赖模块级全局。
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Theme:
    """单套 UI 配色 —— 一组互不耦合的色值常量。

    字段命名遵循 snake_case,直接对应原模块级 UPPER_CASE 常量名:
    BG_BASE / BG_CARD / BG_HOVER / BG_DISABLED / BORDER / BORDER_HOVER /
    TEXT_PRIMARY / TEXT_MUTED / TEXT_DISABLED / ACCENT / ACCENT_HOVER / ACCENT_SEL_BG
    """
    name: str
    bg_base: str
    bg_card: str
    bg_hover: str
    bg_disabled: str
    border: str
    border_hover: str
    text_primary: str
    text_muted: str
    text_disabled: str
    accent: str
    accent_hover: str
    accent_sel_bg: str


THEMES: dict[str, Theme] = {
    "cream": Theme(
        name="cream",
        bg_base="#f5f0e1",
        bg_card="#fbf6e4",
        bg_hover="#ede2bf",
        bg_disabled="#e6dcc0",
        border="#d8c79f",
        border_hover="#b9a578",
        text_primary="#2c2418",
        text_muted="#8a7a5e",
        text_disabled="#a89b78",
        accent="#6366f1",
        accent_hover="#818cf8",
        accent_sel_bg="rgba(99,102,241,0.15)",
    ),
    "sky": Theme(
        name="sky",
        bg_base="#e0f2fe",       # sky-100
        bg_card="#f0f9ff",       # sky-50
        bg_hover="#bae6fd",      # sky-200
        bg_disabled="#cbd5e1",   # slate-200
        border="#7dd3fc",        # sky-300
        border_hover="#38bdf8",  # sky-400
        text_primary="#0c4a6e",  # sky-900
        text_muted="#64748b",    # slate-500
        text_disabled="#94a3b8", # slate-400
        accent="#0284c7",        # sky-600
        accent_hover="#0ea5e9",  # sky-500
        accent_sel_bg="rgba(2,132,199,0.15)",
    ),
    "dark": Theme(
        name="dark",
        bg_base="#0f1117",
        bg_card="#0f1117",
        bg_hover="#1e2130",
        bg_disabled="#2e3347",
        border="#2e3347",
        border_hover="#3d4260",
        text_primary="#e2e4ea",
        text_muted="#7a7f99",
        text_disabled="#5a5f7a",
        accent="#6366f1",
        accent_hover="#818cf8",
        accent_sel_bg="rgba(99,102,241,0.2)",
    ),
}


DEFAULT_THEME = "cream"


def get_theme(name: str) -> Theme:
    """按名取 Theme;未知名抛 ValueError 让 CLI 给出友好提示。"""
    if name not in THEMES:
        raise ValueError(
            f"Unknown theme '{name}'. Choose from {sorted(THEMES)}"
        )
    return THEMES[name]
