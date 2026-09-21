# PyInstaller 打包配置
# 在本机执行：python3 packaging/build.py
# 产出：
#   dist/Jev游乐场.app   (Mac)
#   dist/Jev游乐场.exe   (Windows)

import sys
from pathlib import Path

ROOT = Path(SPECPATH).resolve().parent

a = Analysis(
    [str(ROOT / "hub" / "server.py")],
    pathex=[str(ROOT / "hub"), str(ROOT)],
    binaries=[],
    datas=[
        (str(ROOT / "hub" / "static"), "hub/static"),
        (str(ROOT / "playground" / "static"), "playground/static"),
        (str(ROOT / "pacman_demo" / "index.html"), "pacman_demo"),
        (str(ROOT / "zh"), "zh"),
        (str(ROOT / ".env.example"), "."),
        (str(ROOT / "怎么启动.txt"), "."),
    ],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="Jev游乐场",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,          # 保留控制台：小白能看到「关窗口=停止」，也方便排错
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,
)

if sys.platform == "darwin":
    app = BUNDLE(
        exe,
        name="Jev游乐场.app",
        icon=None,
        bundle_identifier="com.j-ai99.jev-playground",
    )
