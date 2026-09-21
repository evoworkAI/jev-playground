#!/bin/bash
# Jev 模型游乐场 —— Mac 一键启动
# 用法：解压 zip 后，双击本文件（首次若被拦截：右键 → 打开）

set -e
cd "$(dirname "$0")"

PORT=8800
URL="http://127.0.0.1:${PORT}/"

echo ""
echo "  ╔══════════════════════════════════════════╗"
echo "  ║   Jev 模型游乐场 · 正在启动…              ║"
echo "  ╚══════════════════════════════════════════╝"
echo ""

# ── 找 Python ──
PY=""
for cmd in python3 python; do
  if command -v "$cmd" >/dev/null 2>&1; then
    ver=$("$cmd" -c 'import sys; print(sys.version_info[:2] >= (3, 10))' 2>/dev/null || echo False)
    if [ "$ver" = "True" ]; then PY=$cmd; break; fi
  fi
done

if [ -z "$PY" ]; then
  echo "  ❌ 没找到 Python 3.10+"
  echo ""
  echo "  Mac 通常自带 python3。若提示没有，请安装："
  echo "    https://www.python.org/downloads/"
  echo ""
  echo "  安装完成后重新双击本文件。"
  echo ""
  read -r -p "  按回车键关闭…"
  exit 1
fi

echo "  ✓ Python：$("$PY" --version 2>&1)"

# ── 首次运行：从模板生成 .env（没有 key 也能先玩手工吃豆人）──
if [ ! -f .env ] && [ -f .env.example ]; then
  cp .env.example .env
  echo "  ✓ 已创建 .env（可选，填 key 后 AI 功能才可用）"
fi

# ── 等浏览器能连上再打开页面 ──
(
  for i in $(seq 1 60); do
    if curl -sf "$URL" >/dev/null 2>&1; then
      open "$URL"
      exit 0
    fi
    sleep 0.25
  done
) &

echo "  ✓ 服务地址：$URL"
echo ""
echo "  浏览器会自动打开。若没有，请手动访问上面的地址。"
echo "  ⚠  不要直接双击 HTML 文件，必须通过本脚本启动。"
echo "  ⚠  关闭本窗口 = 停止服务。"
echo ""

exec "$PY" hub/server.py --port "$PORT"
