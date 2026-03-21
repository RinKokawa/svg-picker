"""SVG Picker — 通过关键词搜索并选择 SVG 图标（PySide6 原生窗口）"""

import re
import sys
import os
import threading

import requests

from PySide6.QtCore import Qt, QEvent, QMetaObject, Slot
from PySide6.QtGui import QPainter, QColor, QGuiApplication, QPixmap
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QGridLayout, QLabel, QPushButton, QScrollArea, QFrame, QProgressBar
)

ICONIFY_BASE = "https://api.iconify.design"


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
    """SVG 字节 -> QPixmap（指定尺寸），可指定填充颜色"""
    from PySide6.QtSvg import QSvgRenderer

    fill_color = color or "#e2e4ea"
    svg_text = svg_bytes.decode("utf-8", errors="ignore")

    svg_text = re.sub(
        r'\bfill="(currentColor|black|#000|#000000)"',
        f'fill="{fill_color}"',
        svg_text,
        flags=re.IGNORECASE
    )
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
            self.setStyleSheet("""
                QFrame {
                    background: rgba(99,102,241,0.2);
                    border: 2px solid #6366f1;
                    border-radius: 8px;
                }
            """)
        else:
            self.setStyleSheet("""
                QFrame {
                    background: #0f1117;
                    border: 2px solid transparent;
                    border-radius: 8px;
                }
                QFrame:hover {
                    background: #1e2130;
                    border: 2px solid #3d4260;
                }
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

        painter.setPen(QColor("#7a7f99"))
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
        self._all_results = {}
        self._pending_icons = []
        self._pending_results = {}
        self._pending_total = 0
        self._pending_error = ""

        self.setWindowTitle(f"SVG Picker - {keyword}")
        self.setMinimumSize(680, 520)
        self.resize(780, 620)
        self._apply_dark_style()

        screen = QGuiApplication.primaryScreen()
        if screen:
            rect = screen.availableGeometry()
            self.move(rect.center() - self.rect().center())

        self._setup_ui()
        self._start_search()

    def _apply_dark_style(self):
        self.setStyleSheet("""
            QMainWindow, QWidget, QScrollArea, QScrollArea > QWidget { background: #0f1117; }
            QLabel { color: #e2e4ea; background: transparent; }
            QPushButton {
                background: #6366f1;
                color: white;
                border: none;
                border-radius: 6px;
                padding: 8px 20px;
                font-size: 13px;
                font-weight: 600;
            }
            QPushButton:hover { background: #818cf8; }
            QPushButton:disabled { background: #2e3347; color: #5a5f7a; }
            QScrollBar:vertical { background: #0f1117; width: 8px; border-radius: 4px; }
            QScrollBar::handle:vertical { background: #2e3347; border-radius: 4px; min-height: 40px; }
            QScrollBar::handle:hover { background: #3d4260; }
            QProgressBar {
                border: none; border-radius: 4px;
                background: #0f1117; text-align: center; color: #7a7f99;
            }
            QProgressBar::chunk { background: #6366f1; border-radius: 4px; }
            QWidget#gridWidget { background: #0f1117; }
        """)

    def _setup_ui(self):
        cw = QWidget()
        self.setCentralWidget(cw)
        root = QVBoxLayout(cw)
        root.setContentsMargins(0, 0, 0, 0)

        header = QFrame()
        header.setFixedHeight(58)
        header.setStyleSheet("QFrame { background: #0f1117; border-bottom: 1px solid #2e3347; }")
        hlayout = QHBoxLayout(header)
        hlayout.setContentsMargins(20, 0, 20, 0)

        lbl = QLabel(f"Search: {self.keyword}")
        lbl.setStyleSheet("font-size: 16px; font-weight: 600; color: #e2e4ea;")
        hlayout.addWidget(lbl)

        self.count_label = QLabel("0 selected")
        self.count_label.setStyleSheet("color: #7a7f99; font-size: 13px;")
        hlayout.addWidget(self.count_label)

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
        self.status_label.setStyleSheet("color: #7a7f99; font-size: 12px; padding: 4px 16px; background: #0f1117;")
        self.status_label.setFixedHeight(28)
        root.addWidget(self.status_label)

    def _start_search(self):
        self.status_label.setText("Searching Iconify...")
        t = threading.Thread(target=self._search_thread, daemon=True)
        t.start()

    def _search_thread(self):
        try:
            resp = requests.get(
                f"{ICONIFY_BASE}/search",
                params={"query": self.keyword, "limit": 80},
                timeout=15
            )
            resp.raise_for_status()
            icons = resp.json().get("icons", [])[:10]
            self._pending_icons = icons
            QMetaObject.invokeMethod(
                self, "_do_search_done",
                Qt.ConnectionType.QueuedConnection
            )
        except Exception as e:
            self._pending_error = str(e)
            QMetaObject.invokeMethod(
                self, "_do_search_error",
                Qt.ConnectionType.QueuedConnection
            )

    @Slot()
    def _do_search_done(self):
        iconify_ids = self._pending_icons
        self.status_label.setText(f"Found {len(iconify_ids)} icons, loading SVGs...")
        self.progress.setRange(0, len(iconify_ids))
        self.progress.setValue(0)

        if not iconify_ids:
            self.status_label.setText("No icons found.")
            self.progress.hide()
            return

        t = threading.Thread(target=self._fetch_thread, args=(iconify_ids,), daemon=True)
        t.start()

    @Slot()
    def _do_search_error(self):
        self.progress.hide()
        self.status_label.setText(f"Error: {self._pending_error}")

    def _fetch_thread(self, iconify_ids):
        results = {}
        for id_ in iconify_ids:
            data = fetch_svg_bytes(id_)
            if data:
                results[id_] = data
        self._pending_results = results
        self._pending_total = len(iconify_ids)
        QMetaObject.invokeMethod(
            self, "_do_render_icons",
            Qt.ConnectionType.QueuedConnection
        )

    def event(self, event):
        if event.type() == QEvent.Type.User:
            self.progress.setValue(event.current)
            self.status_label.setText(f"Loading SVGs... {event.current}/{event.total}")
            return True
        return super().event(event)

    @Slot()
    def _do_render_icons(self):
        results = self._pending_results
        total = self._pending_total
        self._all_results = results
        self.progress.hide()
        self.status_label.setText(f"Ready - {len(results)}/{total} icons")

        cols = max(1, self.width() // 88)
        for i, (iconify_id, svg_bytes) in enumerate(results.items()):
            pm = svg_bytes_to_pixmap(svg_bytes, 64, "#e2e4ea")
            card = IconCard(iconify_id, pm, self._on_card_click)
            self.icon_cards[iconify_id] = card
            row, col = divmod(i, cols)
            self.grid_layout.addWidget(card, row, col)

    def _on_card_click(self, iconify_id, selected):
        if selected:
            self.selected.add(iconify_id)
        else:
            self.selected.discard(iconify_id)
        count = len(self.selected)
        self.count_label.setText(f"{count} selected")
        self.confirm_btn.setEnabled(count > 0)

    def _confirm(self):
        if not self.selected:
            return

        for iconify_id in self.selected:
            svg_bytes = self._all_results.get(iconify_id)
            if not svg_bytes:
                svg_bytes = fetch_svg_bytes(iconify_id)
            if svg_bytes:
                print(f"<!-- {iconify_id} -->")
                print(svg_bytes.decode("utf-8", errors="replace"))
                print()

        QApplication.instance().quit()


class _ProgressEvent(QEvent):
    def __init__(self, current, total):
        super().__init__(QEvent.Type.User)
        self.current = current
        self.total = total


def main():
    if len(sys.argv) < 2:
        print("Usage: svg-picker <keyword>")
        sys.exit(1)

    keyword = sys.argv[1]

    app = QApplication(sys.argv)
    app.setStyle("fusion")

    win = MainWindow(keyword)
    win.show()

    sys.exit(app.exec())
