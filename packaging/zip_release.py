#!/usr/bin/env python3
"""把 dist/ 里的独立程序打成 GitHub Release 用的 zip。

压缩包文件名只用英文，避免上传后中文被吃掉、链接对不上：
    Jev-Playground-Mac.zip
    Jev-Playground-Windows.zip

包内仍是 Jev游乐场.app / Jev游乐场.exe，并标上 UTF-8，
解压后名字不会变成乱码。
"""

from __future__ import annotations

import stat
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DIST = ROOT / "dist"

PACKAGES = (
    ("Jev游乐场.app", "Jev-Playground-Mac.zip"),
    ("Jev游乐场.exe", "Jev-Playground-Windows.zip"),
)
EXTRA = ("怎么启动.txt", ".env.example")


def _info(path: Path, arcname: str) -> zipfile.ZipInfo:
    info = zipfile.ZipInfo.from_file(path, arcname)
    info.flag_bits |= 0x800  # 文件名按 UTF-8 存
    info.create_system = 3
    mode = path.lstat().st_mode
    info.external_attr = (mode & 0xFFFF) << 16
    return info


def _add(zf: zipfile.ZipFile, path: Path, arcname: str) -> None:
    arcname = arcname.replace("\\", "/")
    if path.is_symlink():
        info = _info(path, arcname)
        info.external_attr = (stat.S_IFLNK | 0o777) << 16
        zf.writestr(info, str(path.readlink()).encode())
        return
    if path.is_dir():
        zf.writestr(_info(path, arcname.rstrip("/") + "/"), b"")
        for child in sorted(path.iterdir(), key=lambda p: p.name):
            _add(zf, child, f"{arcname.rstrip('/')}/{child.name}")
        return
    info = _info(path, arcname)
    info.compress_type = zipfile.ZIP_DEFLATED
    with path.open("rb") as handle:
        zf.writestr(info, handle.read())


def build_zip(src_name: str, zip_name: str) -> Path | None:
    src = DIST / src_name
    if not src.exists():
        return None
    out = ROOT / zip_name
    if out.exists():
        out.unlink()
    with zipfile.ZipFile(out, "w") as zf:
        _add(zf, src, src_name)
        for name in EXTRA:
            extra = ROOT / name
            if extra.is_file():
                _add(zf, extra, name)
    return out


def main() -> None:
    made: list[Path] = []
    for src_name, zip_name in PACKAGES:
        out = build_zip(src_name, zip_name)
        if out is not None:
            made.append(out)
            print(f"✓ {out}")
    if not made:
        print("❌ 请先运行: python3 packaging/build.py", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
