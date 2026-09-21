#!/usr/bin/env python3
"""把 Jev 模型游乐场打成独立程序（用户电脑不用装 Python）。

在本机（Mac 或 Windows）运行一次：
    python3 packaging/build.py

产出在 dist/ 目录：
    Mac     → dist/Jev游乐场.app
    Windows → dist/Jev游乐场.exe

把 dist/ 里的文件 + .env.example 打 zip 发到 GitHub Release 即可。
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DIST = ROOT / "dist"
SPEC = ROOT / "packaging" / "jev-hub.spec"


def main() -> None:
    print("=" * 60)
    print("  Jev 模型游乐场 · 打包独立程序")
    print("=" * 60)
    print(f"  项目目录 : {ROOT}")
    print(f"  当前系统 : {sys.platform}")
    print()

    try:
        import PyInstaller  # noqa: F401
    except ImportError:
        print("  正在安装 PyInstaller…")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "pyinstaller"])
        print()

    if DIST.exists():
        shutil.rmtree(DIST)

    subprocess.check_call([
        sys.executable, "-m", "PyInstaller",
        str(SPEC),
        "--noconfirm",
        "--clean",
        "--distpath", str(DIST),
        "--workpath", str(ROOT / "build" / "pyinstaller"),
    ], cwd=str(ROOT))

    print()
    print("=" * 60)
    print("  ✓ 打包完成")
    if sys.platform == "darwin":
        app = DIST / "Jev游乐场.app"
        print(f"  产出     : {app}")
        print()
        print("  发给粉丝：把 Jev游乐场.app 和 .env.example 一起打 zip")
        print("  用法     : 解压后双击 Jev游乐场.app")
    else:
        exe = DIST / "Jev游乐场.exe"
        print(f"  产出     : {exe}")
        print()
        print("  发给粉丝：把 Jev游乐场.exe 和 .env.example 一起打 zip")
        print("  用法     : 解压后双击 Jev游乐场.exe")
    print("=" * 60)


if __name__ == "__main__":
    main()
