#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""本机验收夹具：真实客户端 + 竹甲熊猫 / 投石猎手。

运行：python3 tests/tribe_p2_visual_server.py
打开 http://127.0.0.1:8882 ，建房、选原始部落、加 AI、开战。
主机开局即有营地/围栏/祭坛、一头狂暴熊猫和一名投石猎手；对面突击兵在砸击/投石射程内。
"""

import os
import sys
from pathlib import Path

os.environ["HOST"] = "127.0.0.1"
os.environ["PORT"] = "8882"
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import server


original_start = server.start_game


def start_tribe_p2_fixture(room):
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
    for kind, dx, dy in (
            ("tcamp", 140, -90),
            ("tpen", 200, -30),
            ("taltar", 260, 70),
    ):
        game["structures"].append(
            server.make_structure(kind, host["id"], hq["x"] + dx, hq["y"] + dy, True)
        )
    panda = server.make_unit("panda", host["id"], hq["x"] + 190, hq["y"] + 220)
    panda["hp"] = panda["maxHp"] * 0.32
    panda["rage"] = True
    slinger = server.make_unit("slinger", host["id"], hq["x"] + 250, hq["y"] + 180)
    game["units"].extend((panda, slinger))
    if foe:
        foe["cash"] = 99999
        rifle = server.make_unit("rifle", foe["id"], hq["x"] + 230, hq["y"] + 250)
        rifle["order"] = "hold"
        rifle["destX"] = None
        rifle["destY"] = None
        game["units"].append(rifle)
        panda["order"] = "attack"
        panda["targetId"] = rifle["id"]
        panda["cooldown"] = 0.0
        slinger["order"] = "attack"
        slinger["targetId"] = rifle["id"]
        slinger["cooldown"] = 0.0
    server.invalidate_game_snapshot(game)


if __name__ == "__main__":
    server.start_game = start_tribe_p2_fixture
    server.tick_bots = lambda room: None
    raise SystemExit(server.main())
