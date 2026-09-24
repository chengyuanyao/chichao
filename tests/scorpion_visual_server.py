#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""本机验收夹具：真实客户端 + 已解锁的穿甲巨蝎对射。

运行：python3 tests/scorpion_visual_server.py
打开 http://127.0.0.1:8879 ，建房、选原始部落、加 AI、开战。
主机开局即有围栏+血祭坛、一只巨蝎，对面一辆坦克在尾刺射程内。
"""

import os
import sys
from pathlib import Path

os.environ["HOST"] = "127.0.0.1"
os.environ["PORT"] = "8879"
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import server


original_start = server.start_game


def start_scorpion_fixture(room):
    for player in room["players"].values():
        if player.get("isBot"):
            player["faction"] = "tech"
        else:
            player["faction"] = "tribe"
    room["selectedMap"] = "iron_river_duel"
    room["neutrals"] = False
    original_start(room)
    game = room["game"]
    game["terrainCtx"] = server.FLAT_TERRAIN
    game["victoryClock"] = 999.0
    game["units"] = [
        unit for unit in game["units"]
        if server.unit_role(unit["kind"]) in ("harvester", "mcv")
    ]
    host = next(player for player in room["players"].values()
                if not player.get("isBot"))
    foe = next((player for player in room["players"].values()
                if player.get("id") != host["id"]), None)
    host["cash"] = 99999
    hq = next(structure for structure in game["structures"]
              if structure["owner"] == host["id"]
              and server.structure_role(structure["kind"]) == "hq")
    for kind, dx, dy in (("tpen", 160, -40), ("taltar", 220, 70)):
        structure = server.make_structure(kind, host["id"], hq["x"] + dx, hq["y"] + dy, True)
        game["structures"].append(structure)
    scorpion = server.make_unit("scorpion", host["id"], hq["x"] + 210, hq["y"] + 210)
    game["units"].append(scorpion)
    if foe:
        foe["cash"] = 99999
        tank = server.make_unit("tank", foe["id"], scorpion["x"] + 120, scorpion["y"] + 8)
        tank["order"] = "hold"
        tank["destX"] = None
        tank["destY"] = None
        game["units"].append(tank)
        scorpion["order"] = "attack"
        scorpion["targetId"] = tank["id"]
        scorpion["cooldown"] = 0.0
    server.invalidate_game_snapshot(game)


if __name__ == "__main__":
    server.start_game = start_scorpion_fixture
    server.tick_bots = lambda room: None
    raise SystemExit(server.main())
