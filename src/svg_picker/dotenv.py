"""轻量 .env 读取 —— 不依赖 python-dotenv。

支持空行、`#` 注释、`KEY=VALUE`,以及值两侧的单/双引号。
"""

import os
import sys


def load_dotenv(path: str = ".env") -> dict:
    """读取 .env 返回 dict;文件不存在返回空 dict。"""
    env: dict[str, str] = {}
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


def ensure_dotenv(path: str = ".env") -> None:
    """确保 .env 存在 —— 不存在则建空文件,stderr 提示用户后续编辑。"""
    if os.path.isfile(path):
        return
    open(path, "w", encoding="utf-8").close()
    print(
        f"[svg-picker] created empty {path} — "
        f"add e.g. 'SVG_PICKER_THEME=sky' to set a default theme",
        file=sys.stderr,
    )
