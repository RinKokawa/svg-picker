"""CLI 入口 —— `python -m svg_picker <关键词>`。

负责解析 CLI 参数、加载 .env、选主题,然后启动 QApplication + MainWindow。
GUI 模块本身不感知 argparse / .env,只接收 Theme 对象。
"""

import argparse
import sys

from PySide6.QtWidgets import QApplication

from svg_picker.dotenv import ensure_dotenv, load_dotenv
from svg_picker.themes import DEFAULT_THEME, THEMES, get_theme


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="svg-picker",
        description="搜索 Iconify 图标,GUI 视觉选择,SVG 输出到 stdout。",
    )
    parser.add_argument(
        "keyword",
        nargs="+",
        help="搜索关键词。可传多个,失败时在窗口里快速切换(不用每次 reject 重新拉起)",
    )

    # 确保 .env 存在(空文件也 OK,用户后续可编辑)
    ensure_dotenv()

    # 默认主题优先级:命令行 > .env 中的 SVG_PICKER_THEME > cream
    dotenv = load_dotenv()
    env_theme = dotenv.get("SVG_PICKER_THEME")
    if env_theme and env_theme not in THEMES:
        print(
            f"[svg-picker] warning: SVG_PICKER_THEME={env_theme!r} "
            f"in .env not in {sorted(THEMES)}, falling back to {DEFAULT_THEME!r}",
            file=sys.stderr,
        )
        env_theme = None
    default_theme = env_theme or DEFAULT_THEME

    parser.add_argument(
        "--theme", "-t",
        choices=sorted(THEMES),
        default=default_theme,
        help="背景主题。可选: " + ", ".join(sorted(THEMES))
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

    theme = get_theme(args.theme)

    app = QApplication(sys.argv)
    app.setStyle("fusion")

    # 延迟导入 —— 让 `svg-picker --help` 不需要拉起整个 Qt 堆栈
    from svg_picker.app import MainWindow
    win = MainWindow(args.keyword, page_size=args.per_page, theme=theme)
    win.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
