#!/bin/bash
# 把 dist/ 里的独立程序打成 GitHub Release 用的 zip
set -euo pipefail
cd "$(dirname "$0")/.."
python3 packaging/zip_release.py
echo ""
echo "上传到已有 Release（会覆盖同名文件）:"
echo "  gh release upload v1.0.0 Jev-Playground-Mac.zip Jev-Playground-Windows.zip --clobber"
