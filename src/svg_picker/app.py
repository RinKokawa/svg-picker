"""SVG Picker — 通过关键词搜索并选择 SVG 图标（PySide6 原生窗口）"""

import argparse
import re
import sys
import threading

import requests

from PySide6.QtCore import Qt, QEvent, QMetaObject, Slot
from PySide6.QtGui import QPainter, QColor, QGuiApplication, QPixmap
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QGridLayout, QLabel, QPushButton, QScrollArea, QFrame, QProgressBar
)

ICONIFY_BASE = "https://api.iconify.design"

# 主题字典 — 每套配色覆盖所有 UI 元素
THEMES = {
    "cream": {
        "BG_BASE":       "#f5f0e1",
        "BG_CARD":       "#fbf6e4",
        "BG_HOVER":      "#ede2bf",
        "BG_DISABLED":   "#e6dcc0",
        "BORDER":        "#d8c79f",
        "BORDER_HOVER":  "#b9a578",
        "TEXT_PRIMARY":  "#2c2418",
        "TEXT_MUTED":    "#8a7a5e",
        "TEXT_DISABLED": "#a89b78",
        "ACCENT":        "#6366f1",
        "ACCENT_HOVER":  "#818cf8",
        "ACCENT_SEL_BG": "rgba(99,102,241,0.15)",
    },
    "sky": {
        "BG_BASE":       "#e0f2fe",   # sky-100
        "BG_CARD":       "#f0f9ff",   # sky-50
        "BG_HOVER":      "#bae6fd",   # sky-200
        "BG_DISABLED":   "#cbd5e1",   # slate-200
        "BORDER":        "#7dd3fc",   # sky-300
        "BORDER_HOVER":  "#38bdf8",   # sky-400
        "TEXT_PRIMARY":  "#0c4a6e",   # sky-900
        "TEXT_MUTED":    "#64748b",   # slate-500
        "TEXT_DISABLED": "#94a3b8",   # slate-400
        "ACCENT":        "#0284c7",   # sky-600
        "ACCENT_HOVER":  "#0ea5e9",   # sky-500
        "ACCENT_SEL_BG": "rgba(2,132,199,0.15)",
    },
    "dark": {
        "BG_BASE":       "#0f1117",
        "BG_CARD":       "#0f1117",
        "BG_HOVER":      "#1e2130",
        "BG_DISABLED":   "#2e3347",
        "BORDER":        "#2e3347",
        "BORDER_HOVER":  "#3d4260",
        "TEXT_PRIMARY":  "#e2e4ea",
        "TEXT_MUTED":    "#7a7f99",
        "TEXT_DISABLED": "#5a5f7a",
        "ACCENT":        "#6366f1",
        "ACCENT_HOVER":  "#818cf8",
        "ACCENT_SEL_BG": "rgba(99,102,241,0.2)",
    },
}

# 默认主题常量(cream);main() 会通过 apply_theme 覆盖
BG_BASE       = THEMES["cream"]["BG_BASE"]
BG_CARD       = THEMES["cream"]["BG_CARD"]
BG_HOVER      = THEMES["cream"]["BG_HOVER"]
BG_DISABLED   = THEMES["cream"]["BG_DISABLED"]
BORDER        = THEMES["cream"]["BORDER"]
BORDER_HOVER  = THEMES["cream"]["BORDER_HOVER"]
TEXT_PRIMARY  = THEMES["cream"]["TEXT_PRIMARY"]
TEXT_MUTED    = THEMES["cream"]["TEXT_MUTED"]
TEXT_DISABLED = THEMES["cream"]["TEXT_DISABLED"]
ACCENT        = THEMES["cream"]["ACCENT"]
ACCENT_HOVER  = THEMES["cream"]["ACCENT_HOVER"]
ACCENT_SEL_BG = THEMES["cream"]["ACCENT_SEL_BG"]


def apply_theme(name):
    """根据主题名更新模块级颜色常量,影响后续所有 UI。"""
    if name not in THEMES:
        raise ValueError(f"Unknown theme '{name}'. Choose from {list(THEMES)}")
    for key, value in THEMES[name].items():
        globals()[key] = value


def fetch_svg_bytes(iconify_id):
    """从 Iconify 获取 SVG 原始字节"""
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


def svg_bytes_to_pixmap(svg_bytes, size=64, color=None):
    """SVG 字节 -> QPixmap（指定尺寸），可指定填充颜色。
    同时处理 fill 和 stroke 的 currentColor/black 替换。"""
    from PySide6.QtSvg import QSvgRenderer

    fill_color = color or TEXT_PRIMARY
    svg_text = svg_bytes.decode("utf-8", errors="ignore")

    # fill 替换
    svg_text = re.sub(
        r'\bfill="(currentColor|black|#000|#000000)"',
        f'fill="{fill_color}"',
        svg_text,
        flags=re.IGNORECASE
    )
    # stroke 替换(描线图标也按主题色染)
    svg_text = re.sub(
        r'\bstroke="(currentColor|black|#000|#000000)"',
        f'stroke="{fill_color}"',
        svg_text,
        flags=re.IGNORECASE
    )
    # 如果 SVG 完全没 fill,默认给一个(避免无色)
    if 'fill=' not in svg_text and '<svg' in svg_text:
        svg_text = svg_text.replace('<svg', f'<svg fill="{fill_color}"', 1)

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


class IconCard(QFrame):
    def __init__(self, iconify_id, pixmap, on_click, parent=None):
        super().__init__(parent)
        self.iconify_id = iconify_id
        self._pixmap = pixmap
        self._on_click = on_click
        self._selected = False
        self.setFixedSize(80, 88)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._update_style()

    def _update_style(self):
        if self._selected:
            self.setStyleSheet(f"""
                QFrame {{
                    background: {ACCENT_SEL_BG};
                    border: 2px solid {ACCENT};
                    border-radius: 8px;
                }}
            """)
        else:
            self.setStyleSheet(f"""
                QFrame {{
                    background: {BG_CARD};
                    border: 2px solid transparent;
                    border-radius: 8px;
                }}
                QFrame:hover {{
                    background: {BG_HOVER};
                    border: 2px solid {BORDER};
                }}
            """)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._selected = not self._selected
            self._update_style()
            self._on_click(self.iconify_id, self._selected)
        super().mousePressEvent(event)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        if not self._pixmap.isNull():
            icon_w, icon_h = 48, 48
            x = (self.width() - icon_w) // 2
            y = (self.height() - icon_h - 14) // 2
            scaled = self._pixmap.scaled(
                icon_w, icon_h,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation
            )
            painter.drawPixmap(x, y, scaled)

        painter.setPen(QColor(TEXT_MUTED))
        font = painter.font()
        font.setPointSize(7)
        painter.setFont(font)
        name = self.iconify_id.split(":")[-1] if ":" in self.iconify_id else self.iconify_id
        painter.drawText(
            self.rect(),
            Qt.AlignmentFlag.AlignBottom | Qt.AlignmentFlag.AlignHCenter,
            name[:14]
        )


class MainWindow(QMainWindow):
    def __init__(self, keyword):
        super().__init__()
        self.keyword = keyword
        self.selected = set()
        self.icon_cards = {}

        # 分页状态
        self.page_size = 10
        self.current_page = 0
        self.total_matches = 0
        self._cache = {}  # page -> {iconify_id: bytes}

        # 后台任务状态
        self._pending_results = {}
        self._pending_page = 0
        self._pending_total = 0
        self._pending_error = ""

        self.setWindowTitle(f"SVG Picker - {keyword}")
        self.setMinimumSize(680, 520)
        self.resize(780, 620)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self._apply_theme()

        screen = QGuiApplication.primaryScreen()
        if screen:
            rect = screen.availableGeometry()
            self.move(rect.center() - self.rect().center())

        self._setup_ui()
        self._goto_page(0)

    def _apply_theme(self):
        self.setStyleSheet(f"""
            QMainWindow, QWidget, QScrollArea, QScrollArea > QWidget {{ background: {BG_BASE}; }}
            QLabel {{ color: {TEXT_PRIMARY}; background: transparent; }}
            QPushButton {{
                background: {ACCENT};
                color: white;
                border: none;
                border-radius: 6px;
                padding: 8px 20px;
                font-size: 13px;
                font-weight: 600;
            }}
            QPushButton:hover {{ background: {ACCENT_HOVER}; }}
            QPushButton:disabled {{ background: {BG_DISABLED}; color: {TEXT_DISABLED}; }}
            QPushButton#pageBtn {{
                background: {BG_CARD};
                color: {TEXT_PRIMARY};
                border: 1px solid {BORDER};
                border-radius: 6px;
                padding: 0;
                font-size: 18px;
                font-weight: 400;
            }}
            QPushButton#pageBtn:hover {{ background: {BG_HOVER}; border-color: {BORDER_HOVER}; }}
            QPushButton#pageBtn:disabled {{
                background: {BG_BASE}; color: {TEXT_DISABLED}; border-color: {BG_DISABLED};
            }}
            QScrollBar:vertical {{ background: {BG_BASE}; width: 8px; border-radius: 4px; }}
            QScrollBar::handle:vertical {{ background: {BORDER}; border-radius: 4px; min-height: 40px; }}
            QScrollBar::handle:hover {{ background: {BORDER_HOVER}; }}
            QProgressBar {{
                border: none; border-radius: 4px;
                background: {BG_BASE}; text-align: center; color: {TEXT_MUTED};
            }}
            QProgressBar::chunk {{ background: {ACCENT}; border-radius: 4px; }}
            QWidget#gridWidget {{ background: {BG_BASE}; }}
        """)

    def _setup_ui(self):
        cw = QWidget()
        self.setCentralWidget(cw)
        root = QVBoxLayout(cw)
        root.setContentsMargins(0, 0, 0, 0)

        header = QFrame()
        header.setFixedHeight(58)
        header.setStyleSheet(f"QFrame {{ background: {BG_BASE}; border-bottom: 1px solid {BORDER}; }}")
        hlayout = QHBoxLayout(header)
        hlayout.setContentsMargins(20, 0, 20, 0)
        hlayout.setSpacing(12)

        lbl = QLabel(f"Search: {self.keyword}")
        lbl.setStyleSheet(f"font-size: 16px; font-weight: 600; color: {TEXT_PRIMARY};")
        hlayout.addWidget(lbl)

        self.count_label = QLabel("0 selected")
        self.count_label.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 13px;")
        hlayout.addWidget(self.count_label)

        hlayout.addStretch()

        # 翻页控件
        self.prev_btn = QPushButton("‹")
        self.prev_btn.setObjectName("pageBtn")
        self.prev_btn.setFixedSize(32, 32)
        self.prev_btn.setEnabled(False)
        self.prev_btn.setToolTip("Previous page (←)")
        self.prev_btn.clicked.connect(lambda: self._goto_page(self.current_page - 1))
        hlayout.addWidget(self.prev_btn)

        self.page_label = QLabel("— / —")
        self.page_label.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 13px;")
        self.page_label.setFixedWidth(60)
        self.page_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        hlayout.addWidget(self.page_label)

        self.next_btn = QPushButton("›")
        self.next_btn.setObjectName("pageBtn")
        self.next_btn.setFixedSize(32, 32)
        self.next_btn.setEnabled(False)
        self.next_btn.setToolTip("Next page (→)")
        self.next_btn.clicked.connect(lambda: self._goto_page(self.current_page + 1))
        hlayout.addWidget(self.next_btn)

        self.confirm_btn = QPushButton("Confirm")
        self.confirm_btn.setFixedWidth(120)
        self.confirm_btn.setEnabled(False)
        self.confirm_btn.clicked.connect(self._confirm)
        hlayout.addWidget(self.confirm_btn)
        root.addWidget(header)

        self.progress = QProgressBar()
        self.progress.setFixedHeight(3)
        self.progress.setTextVisible(False)
        self.progress.setRange(0, 0)
        root.addWidget(self.progress)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.grid_widget = QWidget()
        self.grid_widget.setObjectName("gridWidget")
        self.grid_layout = QGridLayout(self.grid_widget)
        self.grid_layout.setSpacing(8)
        self.grid_layout.setContentsMargins(16, 16, 16, 16)
        scroll.setWidget(self.grid_widget)
        root.addWidget(scroll)

        self.status_label = QLabel("Searching...")
        self.status_label.setStyleSheet(
            f"color: {TEXT_MUTED}; font-size: 12px; padding: 4px 16px; background: {BG_BASE};"
        )
        self.status_label.setFixedHeight(28)
        root.addWidget(self.status_label)

    def _goto_page(self, page):
        """切到第 page 页(0-based)"""
        if page < 0:
            return
        # 已经在这一页(防止重复触发)
        if page == self.current_page and page in self._cache:
            return
        # 边界:总匹配数已知则不能超过
        if self.total_matches and page * self.page_size >= self.total_matches:
            return

        # 缓存命中
        if page in self._cache:
            self._pending_page = page
            self._pending_results = self._cache[page]
            self._do_render_icons()
            return

        # 触发拉取
        self.prev_btn.setEnabled(False)
        self.next_btn.setEnabled(False)
        self.status_label.setText(f"Loading page {page + 1}...")
        self.progress.setRange(0, 0)
        self.progress.show()
        self._pending_page = page
        t = threading.Thread(target=self._fetch_page_thread, args=(page,), daemon=True)
        t.start()

    def _fetch_page_thread(self, page):
        try:
            resp = requests.get(
                f"{ICONIFY_BASE}/search",
                params={
                    "query": self.keyword,
                    "limit": self.page_size,
                    "start": page * self.page_size,
                },
                timeout=15
            )
            resp.raise_for_status()
            data = resp.json()
            icons = data.get("icons", [])[:self.page_size]
            # 第一次成功时记录 total
            if page == 0:
                self.total_matches = data.get("total", len(icons))
            # 下载 SVG
            results = {}
            for id_ in icons:
                svg_bytes = fetch_svg_bytes(id_)
                if svg_bytes:
                    results[id_] = svg_bytes
            self._cache[page] = results
            self._pending_results = results
            self._pending_total = len(icons)
            self._pending_page = page
            QMetaObject.invokeMethod(
                self, "_do_render_icons",
                Qt.ConnectionType.QueuedConnection
            )
        except Exception as e:
            self._pending_error = str(e)
            QMetaObject.invokeMethod(
                self, "_do_render_error",
                Qt.ConnectionType.QueuedConnection
            )

    @Slot()
    def _do_render_icons(self):
        page = self._pending_page
        results = self._pending_results
        total_fetched = self._pending_total

        self.current_page = page

        # 清空网格
        while self.grid_layout.count():
            item = self.grid_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()
        self.icon_cards.clear()

        # 总页数估算
        if self.total_matches > 0:
            total_pages = max(1, (self.total_matches + self.page_size - 1) // self.page_size)
        else:
            total_pages = 1

        # 状态文字
        if not results:
            self.status_label.setText(f"No icons on page {page + 1}.")
        else:
            self.status_label.setText(f"Page {page + 1}/{total_pages} · {len(results)} icons")
        self.progress.hide()

        # 渲染
        cols = 5
        for i, (iconify_id, svg_bytes) in enumerate(results.items()):
            pm = svg_bytes_to_pixmap(svg_bytes, 64, TEXT_PRIMARY)
            card = IconCard(iconify_id, pm, self._on_card_click)
            # 跨页选中恢复
            if iconify_id in self.selected:
                card._selected = True
                card._update_style()
            self.icon_cards[iconify_id] = card
            row, col = divmod(i, cols)
            self.grid_layout.addWidget(card, row, col)

        # 页码 + 按钮启用/禁用
        self.page_label.setText(f"{page + 1} / {total_pages}")
        self.prev_btn.setEnabled(page > 0)
        # 下一页条件:本次拿满了 AND 还没到最后一页
        has_more = (total_fetched == self.page_size) and (page + 1 < total_pages)
        self.next_btn.setEnabled(has_more)

    @Slot()
    def _do_render_error(self):
        self.progress.hide()
        self.status_label.setText(f"Error: {self._pending_error}")
        self.prev_btn.setEnabled(self.current_page > 0)

    def _on_card_click(self, iconify_id, selected):
        if selected:
            self.selected.add(iconify_id)
        else:
            self.selected.discard(iconify_id)
        count = len(self.selected)
        self.count_label.setText(f"{count} selected")
        self.confirm_btn.setEnabled(count > 0)

    def keyPressEvent(self, event):
        key = event.key()
        if key == Qt.Key.Key_Left:
            if self.prev_btn.isEnabled():
                self._goto_page(self.current_page - 1)
                event.accept()
                return
        elif key == Qt.Key.Key_Right:
            if self.next_btn.isEnabled():
                self._goto_page(self.current_page + 1)
                event.accept()
                return
        super().keyPressEvent(event)

    def _confirm(self):
        if not self.selected:
            return

        for iconify_id in self.selected:
            svg_bytes = None
            # 在所有缓存页里找
            for page_results in self._cache.values():
                if iconify_id in page_results:
                    svg_bytes = page_results[iconify_id]
                    break
            # 兜底:重新下载
            if not svg_bytes:
                svg_bytes = fetch_svg_bytes(iconify_id)
            if svg_bytes:
                print(f"<!-- {iconify_id} -->")
                print(svg_bytes.decode("utf-8", errors="replace"))
                print()

        QApplication.instance().quit()

    def closeEvent(self, event):
        """窗口被关闭(用户按 X / Alt+F4 等主动行为)。
        在 stderr 写一行机器可读标记,让 AI 区分"用户取消"和"程序崩溃"。"
        """
        if not self.selected:
            print("[svg-picker] cancelled: window closed without selection", file=sys.stderr)
        else:
            names = ", ".join(sorted(self.selected))
            print(
                f"[svg-picker] cancelled: window closed with "
                f"{len(self.selected)} icons selected but not confirmed ({names})",
                file=sys.stderr
            )
        event.accept()
        QApplication.instance().quit()


def main():
    parser = argparse.ArgumentParser(
        prog="svg-picker",
        description="搜索 Iconify 图标,GUI 视觉选择,SVG 输出到 stdout。",
    )
    parser.add_argument("keyword", help="搜索关键词")
    parser.add_argument(
        "--theme", "-t",
        choices=list(THEMES.keys()),
        default="cream",
        help="背景主题(默认: %(default)s)。可选: " + ", ".join(THEMES),
    )
    args = parser.parse_args()

    apply_theme(args.theme)

    app = QApplication(sys.argv)
    app.setStyle("fusion")

    win = MainWindow(args.keyword)
    win.show()

    sys.exit(app.exec())