#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""采矿车返程与随机公共矿区回归测试。"""

from __future__ import print_function

import math
import os
import random
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import server


def make_room(seed, map_id="gold_crater_small"):
    random.seed(seed)
    players = [
        server.create_human("经济甲", server.COLORS[0]),
        server.create_human("经济乙", server.COLORS[1]),
    ]
    room = {
        "id": "ECON01", "name": "经济测试", "status": "lobby",
        "hostId": players[0]["id"],
        "players": {player["id"]: player for player in players},
        "chat": [], "game": None, "createdAt": time.time(),
        "selectedMap": map_id,
    }
    server.start_game(room)
    return room, players


def resource_positions(seed):
    room, _players = make_room(seed)
    return [(r["x"], r["y"]) for r in room["game"]["resources"]]


def check_random_resources():
    first = resource_positions(4101)
    repeated = resource_positions(4101)
    changed = resource_positions(4102)

    map_def = server.MAPS["gold_crater_small"]
    home_count = len(map_def["homeOreAmounts"]) * 2
    fixed_count = home_count + len(map_def.get("bonusResources") or ())
    random_count = map_def["publicOreCount"]
    assert len(first) == fixed_count + random_count, len(first)
    assert first == repeated, "同一个地图 seed 应生成相同矿区"
    assert first[:fixed_count] == changed[:fixed_count], \
        "家矿与固定争夺矿不应随 seed 漂移"
    assert first[fixed_count:] != changed[fixed_count:], \
        "随机公共矿应在不同对局变化"

    public_ore = first[fixed_count:]
    for x, y in public_ore:
        nearest_spawn = min(math.hypot(x - sx, y - sy)
                            for sx, sy in map_def["spawnPoints"])
        assert nearest_spawn >= 959.0, nearest_spawn
    for index, (x, y) in enumerate(public_ore):
        for ox, oy in first[:fixed_count] + public_ore[:index]:
            assert math.hypot(x - ox, y - oy) >= 519.0


def check_harvester_drives_home():
    room, players = make_room(5101, "gold_crater_small")
    game = room["game"]
    owner = players[0]
    game["terrainCtx"] = server.FLAT_TERRAIN
    game["units"] = []
    game["structures"] = []
    game["resources"] = []

    refinery = server.make_structure("refinery", owner["id"], 500, 500, True)
    harvester = server.make_unit("harvester", owner["id"], 900, 500)
    harvester["cargo"] = harvester["capacity"]
    harvester["returnTarget"] = "pending"
    game["structures"].append(refinery)
    game["units"].append(harvester)

    cash_before = owner["cash"]
    server.tick_harvester(room, harvester, 0.05)
    assert 850 < harvester["x"] < 900, harvester["x"]
    assert harvester["y"] == 500
    assert harvester["cargo"] == harvester["capacity"]
    assert owner["cash"] == cash_before

    for _ in range(300):
        server.tick_harvester(room, harvester, 0.05)
        if harvester["cargo"] == 0:
            break
    assert harvester["cargo"] == 0, "采矿车抵达精炼厂后应卸矿"
    assert owner["cash"] == cash_before + int(harvester["capacity"])
    assert math.hypot(harvester["x"] - refinery["x"],
                      harvester["y"] - refinery["y"]) <= refinery["size"] + 9


def main():
    check_random_resources()
    check_harvester_drives_home()
    print("economy ok: public ore is random and harvesters physically drive home")


if __name__ == "__main__":
    main()
