"""资源路径解析 —— 开发模式 vs PyInstaller 打包后都能找对文件。

打包后静态资源在 exe 内部的临时目录（_MEIPASS），
.env 必须放在 exe / .app 旁边（可写），不能塞进包内。
"""

from __future__ import annotations

import sys
from pathlib import Path


def _bundle_root() -> Path:
    """只读资源根目录（html / js / css）。"""
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    return Path(__file__).resolve().parent.parent


def runtime_root() -> Path:
    """用户可写目录：.env 放这里（exe 或 .app 所在文件夹）。"""
    exe = Path(sys.executable).resolve()
    if sys.platform == "darwin" and exe.name != "Python":
        # Jev游乐场.app/Contents/MacOS/Jev游乐场 → 含 .app 的文件夹
        for parent in exe.parents:
            if parent.suffix == ".app":
                return parent.parent
    return exe.parent


def resolve() -> dict[str, Path]:
    if getattr(sys, "frozen", False):
        root = _bundle_root()
        here = root / "hub"
        return {
            "HERE": here,
            "PROJECT": root,
            "STATIC": here / "static",
            "PLAYGROUND": root / "playground" / "static",
            "PACMAN_INDEX": root / "pacman_demo" / "index.html",
            "ZH_ASSETS": root / "zh",
            "ENV_FILE": runtime_root() / ".env",
            "ENV_EXAMPLE": root / ".env.example",
        }

    here = Path(__file__).resolve().parent
    project = here.parent
    return {
        "HERE": here,
        "PROJECT": project,
        "STATIC": here / "static",
        "PLAYGROUND": project / "playground" / "static",
        "PACMAN_INDEX": project / "pacman_demo" / "index.html",
        "ZH_ASSETS": project / "zh",
        "ENV_FILE": project / ".env",
        "ENV_EXAMPLE": project / ".env.example",
    }
