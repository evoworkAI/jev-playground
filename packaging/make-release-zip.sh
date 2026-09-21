#!/bin/bash
# 把 dist/ 里的独立程序打成 GitHub Release 用的 zip
set -euo pipefail
cd "$(dirname "$0")/.."

VER="${1:-v1.0.0}"
OUT="."

if [[ ! -d dist/Jev游乐场.app && ! -f dist/Jev游乐场.exe ]]; then
  echo "❌ 请先运行: python3 packaging/build.py"
  exit 1
fi

if [[ -d dist/Jev游乐场.app ]]; then
  ZIP="$OUT/Jev游乐场-Mac.zip"
  rm -f "$ZIP"
  (cd dist && zip -r "../$ZIP" "Jev游乐场.app")
  zip -j "$ZIP" 怎么启动.txt .env.example
  echo "✓ $ZIP"
fi

if [[ -f dist/Jev游乐场.exe ]]; then
  ZIP="$OUT/Jev游乐场-Windows.zip"
  rm -f "$ZIP"
  (cd dist && zip -r "../$ZIP" "Jev游乐场.exe")
  zip -j "$ZIP" 怎么启动.txt .env.example
  echo "✓ $ZIP"
fi

echo ""
echo "上传 Release:"
echo "  gh release create $VER Jev游乐场-*.zip --title \"$VER\" --notes-file RELEASE.md"
