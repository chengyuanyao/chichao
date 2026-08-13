# -*- coding: utf-8 -*-
"""随机扣指定玩家的钱（仅服务器本机可用）。用法：python give_cash.py <玩家名> <金额上限>
   例：python give_cash.py erickchen 10000  → 随机减掉 0~10000 之间的金额，最低扣到 0

   走本机 HTTP 接口连接正在运行的服务器进程。服务端 /api/give 仅对 127.0.0.1
   开放（或设 IFL_CHEATS=1 放开），所以本脚本要在跑服务器的那台机器上执行；
   端口用 PORT 环境变量对齐（默认 18081）。
"""
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

PORT = int(os.environ.get("PORT", "18081"))

name = sys.argv[1] if len(sys.argv) > 1 else "erickchen"
amount = sys.argv[2] if len(sys.argv) > 2 else "10000"

url = "http://127.0.0.1:%d/api/give?%s" % (
    PORT, urllib.parse.urlencode({"name": name, "cash": amount}))
try:
    with urllib.request.urlopen(url, timeout=5) as resp:
        data = json.loads(resp.read().decode("utf-8"))
except urllib.error.HTTPError as exc:
    # 服务器返回了错误 JSON（403 非本机 / 404 没找到玩家 / 400 金额无效）
    try:
        err = json.loads(exc.read().decode("utf-8")).get("error")
    except Exception:
        err = "HTTP %d" % exc.code
    print("失败: %s" % err)
    sys.exit(1)
except urllib.error.URLError as exc:
    print("连不上服务器（它在跑吗？端口 %d）：%s" % (PORT, exc.reason))
    sys.exit(1)

print("OK: %s -%.0f -> %.0f" % (name, data.get("removed", 0), data.get("cash", 0)))
