"""Iconify API 客户端 —— 搜索 + 单图标下载 + 字节流 -> QPixmap。

所有 IO 和 SVG 处理集中在这里,让 GUI 模块只关心 UI。
"""

import re

import requests

from PySide6.QtCore import Qt
from PySide6.QtGui import QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer


ICONIFY_BASE = "https://api.iconify.design"


def search_icons(keyword: str, limit: int, start: int = 0) -> tuple[list[str], int]:
    """搜索 Iconify,返回 (icons, total)。

    icons 是 Iconify ID 列表(prefix:name),total 是数据库估算总量。
    失败抛 requests 异常,由调用方负责 UI 错误提示。
    """
    r = requests.get(
        f"{ICONIFY_BASE}/search",
        params={"query": keyword, "limit": limit, "start": start},
        timeout=15,
    )
    r.raise_for_status()
    data = r.json()
    return data.get("icons", [])[:limit], data.get("total", 0)


def fetch_svg_bytes(iconify_id: str) -> bytes | None:
    """按 Iconify ID 拉取单个 SVG 原始字节;网络/解析失败返回 None。"""
    if ":" in iconify_id:
        prefix, name = iconify_id.split(":", 1)
    else:
        parts = iconify_id.split("/")
        prefix, name = parts[0], parts[1] if len(parts) > 1 else parts[0]
    url = f"{ICONIFY_BASE}/{prefix}/{name}.svg"
    try:
        r = requests.get(url, timeout=10)
        r.raise_for_status()
        return r.content
    except Exception:
        return None


def svg_bytes_to_pixmap(svg_bytes: bytes, size: int, color: str) -> QPixmap:
    """SVG 字节 -> QPixmap。

    把 SVG 里的 currentColor / black / #000(...) 替换成 color 后渲染。
    无 fill 时给 svg 根节点补一个 fill,避免完全无色。
    颜色由调用方提供 —— 不再用模块级常量,避免 UI 层和 IO 层耦合。
    """
    svg_text = svg_bytes.decode("utf-8", errors="ignore")

    # fill 替换
    svg_text = re.sub(
        r'\bfill="(currentColor|black|#000|#000000)"',
        f'fill="{color}"',
        svg_text,
        flags=re.IGNORECASE,
    )
    # stroke 替换(描线图标也按主题色染)
    svg_text = re.sub(
        r'\bstroke="(currentColor|black|#000|#000000)"',
        f'stroke="{color}"',
        svg_text,
        flags=re.IGNORECASE,
    )
    # 如果 SVG 完全没 fill,默认给一个(避免无色)
    if "fill=" not in svg_text and "<svg" in svg_text:
        svg_text = svg_text.replace("<svg", f'<svg fill="{color}"', 1)

    svg_bytes_colored = svg_text.encode("utf-8")

    renderer = QSvgRenderer(svg_bytes_colored)
    if not renderer.isValid():
        return QPixmap()

    out = QPixmap(size, size)
    out.fill(Qt.GlobalColor.transparent)
    painter = QPainter(out)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    renderer.render(painter)
    painter.end()
    return out
