# -*- coding: utf-8 -*-
"""给指定玩家加钱。用法：python give_cash.py <玩家名> <金额>
   例：python give_cash.py erickchen 10000
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import server

name = sys.argv[1] if len(sys.argv) > 1 else "erickchen"
amount = int(sys.argv[2]) if len(sys.argv) > 2 else 10000

for rid, room in list(server.ROOMS.items()):
    for pid, player in room["players"].items():
        if player["name"] == name:
            player["cash"] += amount
            print("OK: %s +%d → %.0f" % (name, amount, player["cash"]))
            break
    else:
        continue
    break
else:
    print("NOT FOUND: %s" % name)
