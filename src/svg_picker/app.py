"""SVG Picker — 通过关键词搜索并选择 SVG 图标（PySide6 原生窗口）"""

import argparse
import os
import re
import sys
import threading

import requests

from PySide6.QtCore import (
    Qt, QEvent, QMetaObject, Slot, QPoint, QRect, QSize,
    Property, QPropertyAnimation, QEasingCurve,
)
from PySide6.QtGui import (
    QPainter, QColor, QGuiApplication, QPixmap, QCursor, QIcon, QTransform,
)
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QGridLayout, QLabel, QPushButton, QScrollArea, QFrame, QProgressBar,
    QToolButton
)

ICONIFY_BASE = "https://api.iconify.design"

# chevron 按钮的 SVG 图标 —— 自己用 svg-picker 选的 (iconmind:chevron-up-duotone-bold)。
# 用 currentColor 描线,渲染时被 svg_bytes_to_pixmap 染成 white,跟按钮文字一致。
CHEVRON_SVG = (
    b'<svg xmlns="http://www.w3.org/2000/svg" width="1em" height="1em" '
    b'viewBox="0 0 24 24">'
    b'<g fill="none" stroke="currentColor" stroke-linecap="round" '
    b'stroke-linejoin="round" stroke-width="2.5">'
    b'<path stroke-width="5.5" d="m5 15 7 -7 7 7" opacity=".2"/>'
    b'<path d="m5 15 7 -7 7 7"/>'
    b'</g></svg>'
)

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


def load_dotenv(path=".env"):
    """轻量 .env 读取。返回 dict;文件不存在返回空 dict。
    支持空行、`#` 注释、KEY=VALUE、以及值两侧的单/双引号。"""
    env = {}
    if not os.path.isfile(path):
        return env
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" not in line:
                continue
            k, _, v = line.partition("=")
            env[k.strip()] = v.strip().strip('"').strip("'")
    return env


def ensure_dotenv(path=".env"):
    """确保 .env 存在 —— 不存在则创建一个空文件,并 stderr 提示用户。
    让用户后续自行编辑(比如设置 SVG_PICKER_THEME)。"""
    if os.path.isfile(path):
        return
    open(path, "w", encoding="utf-8").close()
    print(
        f"[svg-picker] created empty {path} — "
        f"add e.g. 'SVG_PICKER_THEME=sky' to set a default theme",
        file=sys.stderr,
    )


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
        # 留 4px 左右 padding;超长名字按词自动换行,不再 [:14] 硬截断
        label_rect = self.rect().adjusted(4, 0, -4, -2)
        painter.drawText(
            label_rect,
            Qt.AlignmentFlag.AlignBottom
            | Qt.AlignmentFlag.AlignHCenter
            | Qt.TextFlag.TextWordWrap,
            name,
        )


class RotatableToolButton(QToolButton):
    """QToolButton whose icon can be smoothly rotated via QPropertyAnimation.

    The base icon is provided once via setIconBase(); the iconRotation
    property is animated, and the displayed icon is re-rendered every
    step so we never need a QGraphicsView just to spin an icon.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._icon_rotation = 180.0
        self._icon_base: QPixmap | None = None

    def setIconBase(self, pixmap: QPixmap):
        self._icon_base = pixmap
        self._rebuild_icon()

    def _rebuild_icon(self):
        if self._icon_base is None:
            return
        if self._icon_rotation == 0:
            rotated = self._icon_base
        else:
            t = QTransform()
            t.rotate(self._icon_rotation)
            rotated = self._icon_base.transformed(
                t, Qt.TransformationMode.SmoothTransformation
            )
        self.setIcon(QIcon(rotated))

    def getIconRotation(self) -> float:
        return self._icon_rotation

    def setIconRotation(self, value: float):
        self._icon_rotation = float(value)
        self._rebuild_icon()

    # QPropertyAnimation needs a real Qt property on the QObject to bind to
    iconRotation = Property(float, getIconRotation, setIconRotation)


class MainWindow(QMainWindow):
    def __init__(self, keyword, page_size=10):
        super().__init__()
        self.keyword = keyword
        self.selected = set()
        self.icon_cards = {}
        # 标记本次会话是否已通过 Confirm 走完。
        # QApplication.quit() 会顺带触发主窗口 closeEvent,
        # 若不区分,confirm 路径也会输出 cancel 标记。
        self._confirmed = False
        # 不满意信号:用户主动表达"这些都不行",Agent 应当换关键词或重做搜索,
        # 而不是静默取消 / 随机选一个。
        self._dissatisfied = False
        # chevron 旋转动画:首次 toggle 时懒构造
        self._chevron_anim = None

        # 分页状态
        self.page_size = max(1, page_size)
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
            /* split button 左半:左侧圆角,右侧直角,和 chevron 拼成一体 */
            QPushButton#confirmBtn {{
                background: {ACCENT};
                color: white;
                border: none;
                border-top-left-radius: 6px;
                border-bottom-left-radius: 6px;
                border-top-right-radius: 0;
                border-bottom-right-radius: 0;
                padding: 8px 20px;
                font-size: 13px;
                font-weight: 600;
            }}
            QPushButton#confirmBtn:hover {{ background: {ACCENT_HOVER}; }}
            QPushButton#confirmBtn:disabled {{ background: {BG_DISABLED}; color: {TEXT_DISABLED}; }}
            /* split button 右半(chevron):左侧直角,右侧圆角,中间一道细分隔 */
            QToolButton#moreBtn {{
                background: {ACCENT};
                color: white;
                border: none;
                border-top-left-radius: 0;
                border-bottom-left-radius: 0;
                border-top-right-radius: 6px;
                border-bottom-right-radius: 6px;
                border-left: 1px solid rgba(255, 255, 255, 0.28);
                padding: 0;
                qproperty-iconSize: 18px;
            }}
            QToolButton#moreBtn:hover {{ background: {ACCENT_HOVER}; }}
            /* 下拉面板:和 cluster 同宽同高同色,看起来就是 cluster 往下延伸一块 */
            QFrame#morePopup {{
                background: {ACCENT};
                border: none;
                border-radius: 6px;
            }}
            QPushButton#dissatisfiedBtn {{
                background: {ACCENT};
                color: white;
                border: none;
                border-radius: 6px;
                padding: 8px 20px;
                font-size: 13px;
                font-weight: 600;
                text-align: center;
            }}
            QPushButton#dissatisfiedBtn:hover {{ background: {ACCENT_HOVER}; }}
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
        self.confirm_btn.setObjectName("confirmBtn")
        self.confirm_btn.setFixedHeight(36)
        self.confirm_btn.setMinimumWidth(120)
        self.confirm_btn.setEnabled(False)
        self.confirm_btn.clicked.connect(self._confirm)

        # Confirm 右侧的 chevron —— 视觉上跟 Confirm 是一个 split button。
        # 点击展开一个 accent 色面板,直接挂在 chevron 正下方,
        # 而不是用 QMenu(系统原生菜单的样式不可控,会"偏出去")。
        # 图标用 svg-picker 挑的 CHEVRON_SVG,渲染时染成白色跟文字一致。
        # 默认旋转 180° 让"朝上"的 svg 看着朝下 —— 这是 dropdown 默认 UX;
        # 展开/收起时由 _animate_chevron 在 0 ↔ 180 之间 lerp。
        self.more_btn = RotatableToolButton()
        self.more_btn.setObjectName("moreBtn")
        self.more_btn.setFixedSize(36, 36)
        self.more_btn.setToolTip("More actions")
        # 没有 setMenu —— DelayedPopup 在无菜单时直接落到 clicked 信号,
        # 所以默认 popup mode 不影响 click 路由
        chevron_pm = svg_bytes_to_pixmap(CHEVRON_SVG, size=64, color="white")
        self.more_btn.setIconBase(chevron_pm)
        self.more_btn.setIconSize(QSize(18, 18))
        self.more_btn.setIconRotation(180)
        self.more_btn.clicked.connect(self._toggle_more_popup)

        # 0 间距子布局:Confirm 和 chevron 紧贴在一起,用 CSS 圆角拼成一体
        cluster = QHBoxLayout()
        cluster.setSpacing(0)
        cluster.setContentsMargins(0, 0, 0, 0)
        cluster.addWidget(self.confirm_btn)
        cluster.addWidget(self.more_btn)
        hlayout.addLayout(cluster)

        # 下拉面板 —— 当前只放"不满意"一个动作。
        # 用 child QFrame 而不是 Qt.Popup,因为:
        # 1) 样式完全自己控制(accent 色面板)
        # 2) 位置完全自己控制(紧贴 chevron 正下方,不会因 OS 风格"偏出去")
        self.more_popup = QFrame(self)
        self.more_popup.setObjectName("morePopup")
        self.more_popup.hide()
        popup_layout = QVBoxLayout(self.more_popup)
        popup_layout.setSpacing(0)
        popup_layout.setContentsMargins(0, 0, 0, 0)
        self.dissatisfied_btn = QPushButton("Reject all")
        self.dissatisfied_btn.setObjectName("dissatisfiedBtn")
        self.dissatisfied_btn.setFixedHeight(36)
        self.dissatisfied_btn.setToolTip(
            "None of these icons fit —— the agent should re-search with "
            "different keywords instead of guessing"
        )
        self.dissatisfied_btn.clicked.connect(self._signal_dissatisfied)
        popup_layout.addWidget(self.dissatisfied_btn)

        # 全局事件过滤:popup 开着时,鼠标点外面就把 popup 关掉
        QApplication.instance().installEventFilter(self)
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

    def _show_popup(self):
        """定位 + 显示 + 把 chevron 旋转到 0°(apex 朝上,表示"已展开")。"""
        popup_w = self.confirm_btn.width() + self.more_btn.width()
        popup_h = self.dissatisfied_btn.height()
        # 用 mapTo 把 chevron 的几何映射到 self(MainWindow)坐标系
        anchor = self.more_btn.mapTo(self, QPoint(0, self.more_btn.height()))
        x = anchor.x() + self.more_btn.width() - popup_w  # 右对齐 chevron 右边缘
        y = anchor.y()  # 紧贴 cluster,无空隙
        self.more_popup.setFixedSize(popup_w, popup_h)
        self.more_popup.move(x, y)
        self.more_popup.show()
        self.more_popup.raise_()
        self._animate_chevron(0)

    def _hide_popup(self):
        """隐藏 + 把 chevron 转回 180°(apex 朝下,表示"未展开")。"""
        if self.more_popup.isVisible():
            self.more_popup.hide()
        self._animate_chevron(180)

    def _toggle_more_popup(self):
        if self.more_popup.isVisible():
            self._hide_popup()
        else:
            self._show_popup()

    def _animate_chevron(self, target: float, duration_ms: int = 180):
        """用 QPropertyAnimation 在 chevron 当前角度和 target 之间 lerp。
        InOutQuad 让起步/收尾更柔和。重复触发会停掉旧的、再启新的。

        注意 stop() 会把当前值重置成上次的 startValue —— 所以先捕获 current,
        再 setStartValue/setEndValue,最后才 stop+start,避免动画起点被吃掉。
        """
        if self._chevron_anim is None:
            self._chevron_anim = QPropertyAnimation(self.more_btn, b"iconRotation")
            self._chevron_anim.setDuration(duration_ms)
            self._chevron_anim.setEasingCurve(QEasingCurve.Type.InOutQuad)
        current = self.more_btn.getIconRotation()
        self._chevron_anim.setStartValue(current)
        self._chevron_anim.setEndValue(target)
        self._chevron_anim.stop()  # reset 到刚 set 的 startValue (== current)
        self._chevron_anim.start()

    def eventFilter(self, obj, event):
        """popup 开着时,popup 之外的鼠标按下都把 popup 关掉。
        但 chevron 自己点的话别在这里关 —— 它的 clicked 信号会 toggle,
        不然会出现 filter 关一次 + clicked 又开一次,动画来回跑吃一半的 bug。

        用全局坐标判断而不是 obj is more_btn:PySide6 的 obj 身份比较偶尔不稳,
        几何对比更稳。
        """
        if self.more_popup.isVisible() and event.type() == QEvent.Type.MouseButtonPress:
            try:
                gp = event.globalPosition().toPoint()
            except AttributeError:
                gp = QCursor.pos()
            chevron_tl = self.more_btn.mapToGlobal(QPoint(0, 0))
            chevron_rect = QRect(chevron_tl, self.more_btn.size())
            if chevron_rect.contains(gp):
                # 点在 chevron 上,留给 clicked 处理 toggle
                return super().eventFilter(obj, event)
            popup_tl = self.more_popup.mapToGlobal(QPoint(0, 0))
            popup_rect = QRect(popup_tl, self.more_popup.size())
            if not popup_rect.contains(gp):
                self._hide_popup()
        return super().eventFilter(obj, event)

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

        # 先置位:quit() 会顺带触发 closeEvent,要在那之前标记成 confirmed,
        # 否则 closeEvent 会把 cancel 行也写到 stderr。
        self._confirmed = True
        self.more_popup.hide()  # 直接 hide,避免动画在 quit() 中途跑

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

    def _signal_dissatisfied(self):
        """用户主动反馈:当前结果都不行,Agent 应换关键词或换思路。
        写到 stderr 一行机器可读标记,然后退出。
        和 Confirm 路径一样,closeEvent 会顺带触发,所以要先置 _dissatisfied。
        """
        self._dissatisfied = True
        self.more_popup.hide()  # 同上,quit() 路径不开动画

        if self.selected:
            names = ", ".join(sorted(self.selected))
            print(
                f"[svg-picker] dissatisfied: user rejected all icons "
                f"(had {len(self.selected)} pre-selected: {names})",
                file=sys.stderr,
            )
        else:
            print(
                "[svg-picker] dissatisfied: user rejected all icons",
                file=sys.stderr,
            )

        QApplication.instance().quit()

    def closeEvent(self, event):
        """窗口被关闭(用户按 X / Alt+F4 等主动行为,或 _confirm() / _signal_dissatisfied() 触发的 quit())。
        在 stderr 写一行机器可读标记,让 AI 区分"用户取消"和"程序崩溃"。
        _confirmed 为 True 时(用户已点 Confirm),不再写 cancel 行 —— stdout 已经拿到 SVG。
        _dissatisfied 为 True 时同样跳过 —— 信号行已由 _signal_dissatisfied 写过了。
        """
        if not (self._confirmed or self._dissatisfied):
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

    # 确保 .env 存在(空文件也 OK,用户后续可编辑)
    ensure_dotenv()

    # 默认主题优先级:命令行 > ./env 中的 SVG_PICKER_THEME > cream
    dotenv = load_dotenv()
    env_theme = dotenv.get("SVG_PICKER_THEME")
    if env_theme and env_theme not in THEMES:
        print(
            f"[svg-picker] warning: SVG_PICKER_THEME={env_theme!r} "
            f"in .env not in {list(THEMES)}, falling back to 'cream'",
            file=sys.stderr,
        )
        env_theme = None
    default_theme = env_theme or "cream"

    parser.add_argument(
        "--theme", "-t",
        choices=list(THEMES.keys()),
        default=default_theme,
        help="背景主题。可选: " + ", ".join(THEMES)
             + f" (默认: %(default)s,亦可在 .env 中设 SVG_PICKER_THEME)",
    )
    parser.add_argument(
        "--per-page", "-n",
        type=int,
        default=10,
        help="每页显示的图标数(默认: %(default)s)",
    )
    args = parser.parse_args()

    if args.per_page < 1:
        parser.error(f"--per-page must be >= 1, got {args.per_page}")

    apply_theme(args.theme)

    app = QApplication(sys.argv)
    app.setStyle("fusion")

    win = MainWindow(args.keyword, page_size=args.per_page)
    win.show()

    sys.exit(app.exec())