#!/usr/bin/env bash
# 赤潮：钢铁前线 — Linux / macOS 启动脚本
# 局域网地址由 server.py 自己探测并打印，这里只负责进目录、设端口。
set -euo pipefail
cd "$(dirname "$0")"

if [ "${1:-}" != "" ]; then
  export PORT="$1"
else
  export PORT="${PORT:-18081}"
fi

exec python3 server.py
