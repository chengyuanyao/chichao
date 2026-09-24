#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""本机验收夹具：真实客户端 + 已解锁的蛛网巨蛛对射。

运行：python3 tests/spider_visual_server.py
打开 http://127.0.0.1:8878 ，建房、选原始部落、加 AI、开战。
主机开局即有围栏+血祭坛、一只巨蛛，对面一只突击兵在吐丝射程内。
"""

import os
import sys
from pathlib import Path

os.environ["HOST"] = "127.0.0.1"
os.environ["PORT"] = "8878"
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import server


original_start = server.start_game


def start_spider_fixture(room):
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
    spider = server.make_unit("spider", host["id"], hq["x"] + 210, hq["y"] + 210)
    game["units"].append(spider)
    if foe:
        foe["cash"] = 99999
        rifle = server.make_unit("rifle", foe["id"], spider["x"] + 130, spider["y"] + 10)
        rifle["order"] = "hold"
        rifle["destX"] = None
        rifle["destY"] = None
        game["units"].append(rifle)
        spider["order"] = "attack"
        spider["targetId"] = rifle["id"]
        spider["cooldown"] = 0.0
    server.invalidate_game_snapshot(game)


if __name__ == "__main__":
    server.start_game = start_spider_fixture
    server.tick_bots = lambda room: None
    raise SystemExit(server.main())
