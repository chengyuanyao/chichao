#!/usr/bin/env bash
# 赤潮：钢铁前线 — 带 AI 指挥官启动（Linux / macOS）
# 和 start-game.sh 等价，只是把内置 AI 换成 ai_commander。
# 用法：./ai_commander/start-ai.sh [端口] [传给 start.py 的其它参数...]
set -euo pipefail
cd "$(dirname "$0")/.."

if [ "${1:-}" != "" ] && [[ "${1}" =~ ^[0-9]+$ ]]; then
  export PORT="$1"
  shift
else
  export PORT="${PORT:-18081}"
fi

exec python3 ai_commander/start.py "$@"
