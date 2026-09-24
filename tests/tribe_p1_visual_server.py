#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""本机验收夹具：真实客户端 + 部落 P1 哨塔/陷阱/猛犸。

运行：python3 tests/tribe_p1_visual_server.py
打开 http://127.0.0.1:8881 ，建房、选原始部落、加 AI、开战。
主机开局即有营地/围栏/祭坛、四座 P1 建筑和一头猛犸；对面突击兵踩在兽夹上。
"""

import os
import sys
from pathlib import Path

os.environ["HOST"] = "127.0.0.1"
os.environ["PORT"] = "8881"
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import server


original_start = server.start_game


def start_tribe_p1_fixture(room):
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
            ("tspiketower", 120, 170),
            ("ttoxtower", 230, 190),
            ("ttrap", 320, 150),
            ("tpit", 390, 195),
    ):
        game["structures"].append(
            server.make_structure(kind, host["id"], hq["x"] + dx, hq["y"] + dy, True)
        )
    mammoth = server.make_unit("mammoth", host["id"], hq["x"] + 200, hq["y"] + 260)
    game["units"].append(mammoth)
    if foe:
        foe["cash"] = 99999
        rifle = server.make_unit("rifle", foe["id"], hq["x"] + 322, hq["y"] + 152)
        rifle["order"] = "hold"
        rifle["destX"] = None
        rifle["destY"] = None
        game["units"].append(rifle)
        spike = next(structure for structure in game["structures"]
                     if structure["kind"] == "tspiketower")
        spike["targetId"] = rifle["id"]
        spike["cooldown"] = 0.0
    server.invalidate_game_snapshot(game)


if __name__ == "__main__":
    server.start_game = start_tribe_p1_fixture
    server.tick_bots = lambda room: None
    raise SystemExit(server.main())
