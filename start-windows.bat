@echo off
chcp 65001 >nul
setlocal EnableDelayedExpansion

cd /d "%~dp0"

set PORT=8800
set URL=http://127.0.0.1:%PORT%/

echo.
echo   ╔══════════════════════════════════════════╗
echo   ║   Jev 模型游乐场 · 正在启动…              ║
echo   ╚══════════════════════════════════════════╝
echo.

REM ── 找 Python ──
set PY=
for %%P in (py -3 python3 python) do (
  if not defined PY (
    %%P -c "import sys; raise SystemExit(0 if sys.version_info[:2] >= (3,10) else 1)" >nul 2>&1
    if !errorlevel! equ 0 set PY=%%P
  )
)

if not defined PY (
  echo   ❌ 没找到 Python 3.10+
  echo.
  echo   请安装 Python（安装时勾选 Add python.exe to PATH）：
  echo     https://www.python.org/downloads/
  echo.
  echo   安装完成后重新双击本文件。
  echo.
  pause
  exit /b 1
)

for /f "delims=" %%V in ('%PY% --version 2^>^&1') do echo   ✓ Python：%%V

REM ── 首次运行：从模板生成 .env ──
if not exist .env if exist .env.example copy /Y .env.example .env >nul && echo   ✓ 已创建 .env（可选，填 key 后 AI 功能才可用）

echo   ✓ 服务地址：%URL%
echo.
echo   浏览器即将自动打开。若没有，请手动访问上面的地址。
echo   ⚠  不要直接双击 HTML 文件，必须通过本脚本启动。
echo   ⚠  关闭本窗口 = 停止服务。
echo.

start "" "%URL%"

%PY% hub\server.py --port %PORT%

pause
