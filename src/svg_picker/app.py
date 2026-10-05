"""SVG Picker 主窗口 —— 控件 + 状态机 + IO 编排。

模块接收 Theme 对象(不再用模块级颜色全局),所有色值都从 self.theme 取。
网络/渲染职责已迁出到 svg_picker.iconify;主题已迁出到 svg_picker.themes。
"""

import json
import sys
import threading

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
    QToolButton, QLineEdit,
)

from svg_picker.iconify import fetch_svg_bytes, search_icons, svg_bytes_to_pixmap
from svg_picker.themes import DEFAULT_THEME, Theme, get_theme, next_theme_name


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


class IconCard(QFrame):
    def __init__(self, iconify_id, pixmap, theme, on_click, parent=None):
        super().__init__(parent)
        self.iconify_id = iconify_id
        self.theme = theme
        self._pixmap = pixmap
        self._on_click = on_click
        self._selected = False
        self.setFixedSize(80, 88)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._update_style()

    def _update_style(self):
        t = self.theme
        if self._selected:
            self.setStyleSheet(f"""
                QFrame {{
                    background: {t.accent_sel_bg};
                    border: 2px solid {t.accent};
                    border-radius: 8px;
                }}
            """)
        else:
            self.setStyleSheet(f"""
                QFrame {{
                    background: {t.bg_card};
                    border: 2px solid transparent;
                    border-radius: 8px;
                }}
                QFrame:hover {{
                    background: {t.bg_hover};
                    border: 2px solid {t.border};
                }}
            """)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._selected = not self._selected
            self._update_style()
            self._on_click(self.iconify_id, self._selected)
        super().mousePressEvent(event)

    def set_theme(self, theme, pixmap) -> None:
        """主题切换时同步:换 theme + 换 pixmap,并触发重绘。

        外部 (MainWindow.set_theme) 负责按新主题色重渲 pixmap 后传进来。
        """
        self.theme = theme
        self._pixmap = pixmap
        self._update_style()
        self.update()  # 触发 paintEvent,新 pixmap 才会被画上去

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

        painter.setPen(QColor(self.theme.text_muted))
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
    def __init__(
        self,
        keywords,
        page_size=10,
        theme: Theme | None = None,
        context: str = "",
        next_action: str = "",
        output_format: str = "svg",
    ):
        super().__init__()
        self.context = context.strip()
        self.next_action = next_action.strip()
        self.output_format = output_format
        if theme is None:
            theme = get_theme(DEFAULT_THEME)
        self.theme = theme

        # keywords 接受 list / tuple / 单 str —— 单 str 也支持是为了测试时少打字
        if isinstance(keywords, str):
            keywords = [keywords]
        if not keywords:
            raise ValueError("MainWindow requires at least one keyword")
        # 去重但保序,避免重复的关键词在 popup 里出现两次
        seen: set[str] = set()
        self.keywords: list[str] = []
        for kw in keywords:
            if kw not in seen:
                seen.add(kw)
                self.keywords.append(kw)
        self.current_keyword_idx = 0

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

        self.setWindowTitle(f"SVG Picker - {self._current_keyword()}")
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

    def _current_keyword(self) -> str:
        return self.keywords[self.current_keyword_idx]

    def _apply_theme(self):
        t = self.theme
        self.setStyleSheet(f"""
            QMainWindow, QWidget, QScrollArea, QScrollArea > QWidget {{ background: {t.bg_base}; }}
            QLabel {{ color: {t.text_primary}; background: transparent; }}
            /* header 区:由 objectName 控制颜色,切主题时自动跟着变 */
            QFrame#header {{ background: {t.bg_base}; border-bottom: 1px solid {t.border}; }}
            QPushButton#searchBtn {{
                background: transparent;
                color: {t.text_primary};
                border: 1px solid transparent;
                border-radius: 6px;
                padding: 4px 10px;
                font-size: 15px;
                font-weight: 600;
                text-align: left;
            }}
            QPushButton#searchBtn:hover {{ background: {t.bg_hover}; border-color: {t.border}; }}
            QLabel#countLabel, QLabel#pageLabel {{ color: {t.text_muted}; font-size: 13px; }}
            QLabel#statusLabel {{ color: {t.text_muted}; font-size: 12px; padding: 4px 16px; background: {t.bg_base}; }}
            /* keyword popup:每个 keyword 一行,当前 keyword 用 :checked 高亮 */
            QFrame#keywordPopup {{
                background: {t.bg_card};
                border: 1px solid {t.border};
                border-radius: 6px;
            }}
            QPushButton#keywordBtn {{
                background: {t.bg_card};
                color: {t.text_primary};
                border: none;
                border-radius: 4px;
                padding: 8px 16px;
                font-size: 13px;
                text-align: left;
            }}
            QPushButton#keywordBtn:hover {{ background: {t.bg_hover}; }}
            QPushButton#keywordBtn:checked {{
                background: {t.accent_sel_bg};
                color: {t.accent};
                font-weight: 600;
            }}
            /* popup 末尾的"添加关键词"行 */
            QFrame#popupDivider {{ background: {t.border}; max-height: 1px; border: none; }}
            QLineEdit#kwInput {{
                background: {t.bg_base};
                color: {t.text_primary};
                border: 1px solid {t.border};
                border-radius: 4px;
                padding: 4px 8px;
                font-size: 13px;
                selection-background-color: {t.accent_sel_bg};
            }}
            QLineEdit#kwInput:focus {{ border-color: {t.accent}; }}
            QPushButton#kwAddBtn {{
                background: {t.bg_base};
                color: {t.text_primary};
                border: 1px solid {t.border};
                border-radius: 4px;
                font-size: 16px;
                font-weight: 600;
                padding: 0;
            }}
            QPushButton#kwAddBtn:hover {{ background: {t.bg_hover}; border-color: {t.border_hover}; }}
            QPushButton {{
                background: {t.accent};
                color: white;
                border: none;
                border-radius: 6px;
                padding: 8px 20px;
                font-size: 13px;
                font-weight: 600;
            }}
            QPushButton:hover {{ background: {t.accent_hover}; }}
            QPushButton:disabled {{ background: {t.bg_disabled}; color: {t.text_disabled}; }}
            /* split button 左半:左侧圆角,右侧直角,和 chevron 拼成一体 */
            QPushButton#confirmBtn {{
                background: {t.accent};
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
            QPushButton#confirmBtn:hover {{ background: {t.accent_hover}; }}
            QPushButton#confirmBtn:disabled {{ background: {t.bg_disabled}; color: {t.text_disabled}; }}
            /* split button 右半(chevron):左侧直角,右侧圆角,中间一道细分隔 */
            QToolButton#moreBtn {{
                background: {t.accent};
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
            QToolButton#moreBtn:hover {{ background: {t.accent_hover}; }}
            /* 下拉面板:和 cluster 同宽同高同色,看起来就是 cluster 往下延伸一块 */
            QFrame#morePopup {{
                background: {t.accent};
                border: none;
                border-radius: 6px;
            }}
            QPushButton#dissatisfiedBtn {{
                background: {t.accent};
                color: white;
                border: none;
                border-radius: 6px;
                padding: 8px 20px;
                font-size: 13px;
                font-weight: 600;
                text-align: center;
            }}
            QPushButton#dissatisfiedBtn:hover {{ background: {t.accent_hover}; }}
            QPushButton#pageBtn {{
                background: {t.bg_card};
                color: {t.text_primary};
                border: 1px solid {t.border};
                border-radius: 6px;
                padding: 0;
                font-size: 18px;
                font-weight: 400;
            }}
            QPushButton#pageBtn:hover {{ background: {t.bg_hover}; border-color: {t.border_hover}; }}
            QPushButton#pageBtn:disabled {{
                background: {t.bg_base}; color: {t.text_disabled}; border-color: {t.bg_disabled};
            }}
            /* 主题切换按钮:跟 pageBtn 尺寸一致,里面放 emoji */
            QPushButton#themeBtn {{
                background: {t.bg_card};
                color: {t.text_primary};
                border: 1px solid {t.border};
                border-radius: 6px;
                padding: 0;
                font-size: 16px;
            }}
            QPushButton#themeBtn:hover {{ background: {t.bg_hover}; border-color: {t.border_hover}; }}
            QScrollBar:vertical {{ background: {t.bg_base}; width: 8px; border-radius: 4px; }}
            QScrollBar::handle:vertical {{ background: {t.border}; border-radius: 4px; min-height: 40px; }}
            QScrollBar::handle:hover {{ background: {t.border_hover}; }}
            QProgressBar {{
                border: none; border-radius: 4px;
                background: {t.bg_base}; text-align: center; color: {t.text_muted};
            }}
            QProgressBar::chunk {{ background: {t.accent}; border-radius: 4px; }}
            QWidget#gridWidget {{ background: {t.bg_base}; }}
        """)

    def _setup_ui(self):
        cw = QWidget()
        self.setCentralWidget(cw)
        root = QVBoxLayout(cw)
        root.setContentsMargins(0, 0, 0, 0)

        t = self.theme
        header = QFrame()
        header.setObjectName("header")
        header.setFixedHeight(58)
        hlayout = QHBoxLayout(header)
        hlayout.setContentsMargins(20, 0, 20, 0)
        hlayout.setSpacing(12)

        # Search 按钮 —— 点开是 keyword 列表。当前关键词写在按钮文字里,
        # 切换关键词会重置分页/缓存/选中并重新拉第 0 页。
        # 视觉上跟 searchLabel 等大,加 hover 反馈。
        self.search_btn = QPushButton(f"Search: {self._current_keyword()} ▾")
        self.search_btn.setObjectName("searchBtn")
        self.search_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.search_btn.setToolTip("Switch keyword")
        self.search_btn.clicked.connect(self._toggle_keyword_popup)
        hlayout.addWidget(self.search_btn)

        self.count_label = QLabel("0 selected")
        self.count_label.setObjectName("countLabel")
        hlayout.addWidget(self.count_label)

        hlayout.addStretch()

        # 主题切换按钮 —— 一个就够,点击按顺序切。无 popup / 下拉。
        # 尺寸跟翻页按钮一致(32x32),里面用 emoji 🎨 表示"换皮"。
        # 当前主题不再写在按钮上 —— 看窗口颜色就知道了。
        self.theme_btn = QPushButton("\U0001F3A8")  # 🎨 artist palette
        self.theme_btn.setObjectName("themeBtn")
        self.theme_btn.setFixedSize(32, 32)
        self.theme_btn.setToolTip("Switch theme (click to cycle)")
        self.theme_btn.clicked.connect(self._cycle_theme)
        hlayout.addWidget(self.theme_btn)

        # 翻页控件
        self.prev_btn = QPushButton("‹")
        self.prev_btn.setObjectName("pageBtn")
        self.prev_btn.setFixedSize(32, 32)
        self.prev_btn.setEnabled(False)
        self.prev_btn.setToolTip("Previous page (←)")
        self.prev_btn.clicked.connect(lambda: self._goto_page(self.current_page - 1))
        hlayout.addWidget(self.prev_btn)

        self.page_label = QLabel("— / —")
        self.page_label.setObjectName("pageLabel")
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

        # keyword popup —— 列出所有传入的关键词,当前选中那个 :checked 高亮。
        # 切换关键词会重置分页/缓存/选中,然后重新拉第 0 页。
        # 末尾带一个输入框 + Add 按钮,让用户现场加新关键词。
        self.keyword_popup = QFrame(self)
        self.keyword_popup.setObjectName("keywordPopup")
        self.keyword_popup.hide()
        kw_layout = QVBoxLayout(self.keyword_popup)
        kw_layout.setSpacing(2)
        kw_layout.setContentsMargins(4, 4, 4, 4)
        self._kw_buttons: list[QPushButton] = []
        for kw in self.keywords:
            btn = QPushButton(kw)
            btn.setObjectName("keywordBtn")
            btn.setCheckable(True)
            btn.setFixedHeight(32)
            if kw == self._current_keyword():
                btn.setChecked(True)
            btn.clicked.connect(lambda _checked=False, k=kw: self._switch_keyword(k))
            kw_layout.addWidget(btn)
            self._kw_buttons.append(btn)
        # 末尾:分隔 + 输入 + 添加按钮
        kw_layout.addSpacing(4)
        divider = QFrame()
        divider.setObjectName("popupDivider")
        divider.setFixedHeight(1)
        kw_layout.addWidget(divider)
        kw_layout.addSpacing(4)
        input_row = QHBoxLayout()
        input_row.setSpacing(4)
        input_row.setContentsMargins(0, 0, 0, 0)
        self.kw_input = QLineEdit()
        self.kw_input.setObjectName("kwInput")
        self.kw_input.setPlaceholderText("Add keyword...")
        self.kw_input.returnPressed.connect(self._add_keyword)
        input_row.addWidget(self.kw_input)
        add_btn = QPushButton("+")
        add_btn.setObjectName("kwAddBtn")
        add_btn.setFixedSize(28, 28)
        add_btn.setToolTip("Add keyword")
        add_btn.clicked.connect(self._add_keyword)
        input_row.addWidget(add_btn)
        kw_layout.addLayout(input_row)

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
        self.status_label.setObjectName("statusLabel")
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
            icons, total = search_icons(
                self._current_keyword(), self.page_size, page * self.page_size
            )
            if page == 0:
                self.total_matches = total
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
            pm = svg_bytes_to_pixmap(svg_bytes, 64, self.theme.text_primary)
            card = IconCard(iconify_id, pm, self.theme, self._on_card_click)
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

    def _show_keyword_popup(self):
        """定位 + 显示 keyword popup,左对齐挂在 search 按钮正下方。

        高度 = 关键词按钮区 + 分隔 + 输入框行。让 layout 自己算。
        """
        max_text_w = max(
            (btn.sizeHint().width() for btn in self._kw_buttons),
            default=80,
        )
        popup_w = max(self.search_btn.width(), max_text_w + 32)
        # 锁宽,让 layout 算高
        self.keyword_popup.setFixedWidth(popup_w)
        self.keyword_popup.adjustSize()
        anchor = self.search_btn.mapTo(self, QPoint(0, self.search_btn.height()))
        self.keyword_popup.move(anchor.x(), anchor.y())
        self.keyword_popup.show()
        self.keyword_popup.raise_()

    def _hide_keyword_popup(self):
        if self.keyword_popup.isVisible():
            self.keyword_popup.hide()

    def _toggle_keyword_popup(self):
        if self.keyword_popup.isVisible():
            self._hide_keyword_popup()
        else:
            self._show_keyword_popup()

    def _switch_keyword(self, kw: str) -> None:
        """切换到列表里另一个关键词:重置分页/缓存/网格/选中,重新拉第 0 页。

        不同关键词意图不同,跨关键词保留选中容易误选,所以清空 selected。
        """
        if kw == self._current_keyword():
            self._hide_keyword_popup()
            return
        if kw not in self.keywords:
            return
        self.current_keyword_idx = self.keywords.index(kw)
        self.setWindowTitle(f"SVG Picker - {kw}")
        self.search_btn.setText(f"Search: {kw} ▾")

        # 更新 popup 里哪个 button 是 :checked
        for i, btn in enumerate(self._kw_buttons):
            btn.setChecked(self.keywords[i] == kw)

        # 清掉输入框里残留文字(避免下次开 popup 看到旧输入)
        if hasattr(self, "kw_input"):
            self.kw_input.clear()

        # 重置分页 / 缓存 / 网格 / 选中
        self.current_page = 0
        self.total_matches = 0
        self._cache.clear()
        self._pending_results = {}
        self._pending_page = 0
        self._pending_total = 0
        self._pending_error = ""
        while self.grid_layout.count():
            item = self.grid_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()
        self.icon_cards.clear()
        self.selected.clear()
        self.count_label.setText("0 selected")
        self.confirm_btn.setEnabled(False)

        self._hide_keyword_popup()
        self._goto_page(0)

    def _add_keyword(self) -> None:
        """从 popup 末尾的输入框拿关键词,加进列表(去重),新建 button,
        切过去并重渲。空输入只是关 popup,什么都不做。
        """
        text = self.kw_input.text().strip()
        self.kw_input.clear()
        if not text:
            self._hide_keyword_popup()
            return
        if text in self.keywords:
            # 已存在 —— 等价于从列表里点一下
            self._switch_keyword(text)
            return
        # 新关键词:append + 插 button(在 divider 之前) + 切过去 + 重渲
        self.keywords.append(text)
        btn = QPushButton(text)
        btn.setObjectName("keywordBtn")
        btn.setCheckable(True)
        btn.setFixedHeight(32)
        btn.clicked.connect(lambda _checked=False, k=text: self._switch_keyword(k))
        self._kw_buttons.append(btn)
        layout = self.keyword_popup.layout()
        # divider 现在在 count() - 2(input_row 是最后一项)
        layout.insertWidget(layout.count() - 2, btn)
        self._switch_keyword(text)

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

    def set_theme(self, theme: Theme) -> None:
        """运行时切换主题 —— 重生 QSS、按新主题色重渲每个 card 的 SVG pixmap。

        不会改变任何选中 / 分页状态,只是换皮。
        当前主题不再写在按钮上(emoji 不变),但窗口颜色和图标颜色已经跟着切了。
        """
        self.theme = theme
        self._apply_theme()
        # 每个已渲染的 card:用缓存里的 svg bytes 重新染成新主题色
        for iconify_id, card in self.icon_cards.items():
            svg_bytes = self._lookup_svg_bytes(iconify_id)
            if svg_bytes:
                new_pm = svg_bytes_to_pixmap(svg_bytes, 64, theme.text_primary)
                card.set_theme(theme, new_pm)
            else:
                # 没找到 bytes(理论上不会发生,兜底:只换样式不换 pixmap)
                card.theme = theme
                card._update_style()

    def _lookup_svg_bytes(self, iconify_id: str):
        """在所有缓存页里找 svg bytes,找不到返回 None。"""
        for page_results in self._cache.values():
            if iconify_id in page_results:
                return page_results[iconify_id]
        return None

    def _cycle_theme(self) -> None:
        """按 THEME_CYCLE 顺序切到下一个主题。"""
        self.set_theme(get_theme(next_theme_name(self.theme.name)))

    def eventFilter(self, obj, event):
        """popup 开着时,popup 之外的鼠标按下都把对应的 popup 关掉。
        但 search 按钮 / chevron 自己点的话别在这里关 —— 它们的 clicked 信号会 toggle,
        不然会出现 filter 关一次 + clicked 又开一次,动画来回跑吃一半的 bug。

        用全局坐标判断而不是 obj is more_btn:PySide6 的 obj 身份比较偶尔不稳,
        几何对比更稳。两个 popup 互相独立,各自管自己。
        """
        if event.type() != QEvent.Type.MouseButtonPress:
            return super().eventFilter(obj, event)
        try:
            gp = event.globalPosition().toPoint()
        except AttributeError:
            gp = QCursor.pos()

        # chevron popup
        if self.more_popup.isVisible():
            chevron_tl = self.more_btn.mapToGlobal(QPoint(0, 0))
            chevron_rect = QRect(chevron_tl, self.more_btn.size())
            if not chevron_rect.contains(gp):
                popup_tl = self.more_popup.mapToGlobal(QPoint(0, 0))
                popup_rect = QRect(popup_tl, self.more_popup.size())
                if not popup_rect.contains(gp):
                    self._hide_popup()

        # keyword popup
        if self.keyword_popup.isVisible():
            search_tl = self.search_btn.mapToGlobal(QPoint(0, 0))
            search_rect = QRect(search_tl, self.search_btn.size())
            if not search_rect.contains(gp):
                popup_tl = self.keyword_popup.mapToGlobal(QPoint(0, 0))
                popup_rect = QRect(popup_tl, self.keyword_popup.size())
                if not popup_rect.contains(gp):
                    self._hide_keyword_popup()

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

        selections = []
        for iconify_id in sorted(self.selected):
            svg_bytes = None
            # 在所有缓存页里找
            for page_results in self._cache.values():
                if iconify_id in page_results:
                    svg_bytes = page_results[iconify_id]
                    break
            # 兜底:重新下载
            if not svg_bytes:
                svg_bytes = fetch_svg_bytes(iconify_id)
            if not svg_bytes:
                continue

            svg_text = svg_bytes.decode("utf-8", errors="replace")
            selections.append({
                "id": iconify_id,
                "svg": svg_text,
            })

            if self.output_format == "svg":
                print(f"<!-- {iconify_id} -->")
                print(svg_text)
                print()

        if self.output_format == "json":
            print(json.dumps({
                "event": "svg_picker.completed",
                "status": "completed",
                "context": self.context,
                "next_action": self.next_action,
                "keyword": self._current_keyword(),
                "selections": selections,
            }, ensure_ascii=False))

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
