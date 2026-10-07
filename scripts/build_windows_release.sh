#!/usr/bin/env bash
# Reproducible release helper.
# On Linux / macOS this stages the source zip and checks the exclude list.
# The Windows onedir exe must be built on Windows with
# scripts/build_windows_release.ps1 (PyInstaller cannot cross-compile here).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

PYTHON="${PYTHON:-python3}"

echo "== 发行清单检查 =="
"$PYTHON" scripts/stage_release.py check

echo
echo "== 源码 / macOS / Linux 包 =="
"$PYTHON" scripts/stage_release.py source \
  --output release/ChichaoSteelFront-source \
  --zip release/ChichaoSteelFront-source.zip

echo
if [ "$(uname -s)" = "Linux" ] || [ "$(uname -s)" = "Darwin" ]; then
  echo "当前不是 Windows：不会生成 ChichaoSteelFront.exe。"
  echo "请在 Windows 10/11 上运行："
  echo "  powershell -ExecutionPolicy Bypass -File scripts/build_windows_release.ps1"
  echo
  echo "已写出: $ROOT/release/ChichaoSteelFront-source.zip"
  echo "该包给 macOS / Linux 玩家使用：解压后 ./start-game.sh（需要系统 python3）。"
  exit 0
fi

echo "== Windows 冻结包（本机检测到非 Unix，尝试调用 PowerShell） =="
if command -v powershell >/dev/null 2>&1; then
  powershell -ExecutionPolicy Bypass -File scripts/build_windows_release.ps1
else
  echo "未找到 powershell，无法在此环境完成 PyInstaller Windows 包。"
  exit 1
fi
