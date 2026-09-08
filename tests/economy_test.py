#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""采矿车返程与随机公共矿区回归测试。"""

from __future__ import print_function

import math
import os
import random
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
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


def check_manual_stop_and_priority_mine():
    room, players = make_room(5201, "gold_crater_small")
    game = room["game"]
    owner = players[0]
    game["terrainCtx"] = server.FLAT_TERRAIN
    game["units"] = []
    game["structures"] = []
    game["resources"] = []

    refinery = server.make_structure("refinery", owner["id"], 500, 500, True)
    harvester = server.make_unit("harvester", owner["id"], 900, 500)
    tank = server.make_unit("tank", owner["id"], 850, 650)
    near_ore = server.add_resource(game, 1050, 500, 9000)
    chosen_ore = server.add_resource(game, 1600, 500, 9000)
    game["structures"].append(refinery)
    game["units"].extend((harvester, tank))

    # H/stop 对所有单位立即撤销当前指令；矿车进入持久停采。
    tank["destX"], tank["destY"], tank["order"] = 1400, 700, "move"
    harvester["harvestTarget"] = near_ore["id"]
    assert server.issue_stop(game, owner["id"], {tank["id"], harvester["id"]}) == 2
    assert tank["destX"] is None and tank["order"] == "guard"
    assert harvester["harvestPaused"] is True
    assert harvester["harvestTarget"] is None
    stopped_at = (harvester["x"], harvester["y"], harvester["cargo"])
    for _ in range(20):
        server.tick_harvester(room, harvester, 0.1)
    assert (harvester["x"], harvester["y"], harvester["cargo"]) == stopped_at
    assert server.public_unit(harvester)["harvestPaused"] is True

    # 即使近处有矿，显式指定远矿后也必须优先驶向、采集远矿。
    near_before = near_ore["amount"]
    chosen_before = chosen_ore["amount"]
    assert server.issue_harvest(
        game, owner["id"], {harvester["id"]}, chosen_ore["id"]) == 1
    assert harvester["harvestPaused"] is False
    assert harvester["preferredResourceId"] == chosen_ore["id"]
    for _ in range(300):
        server.tick_harvester(room, harvester, 0.05)
        if chosen_ore["amount"] < chosen_before:
            break
    assert chosen_ore["amount"] < chosen_before
    assert near_ore["amount"] == near_before

    # 满载回厂不会忘记指定矿，卸货后仍然返回同一矿。
    harvester["cargo"] = harvester["capacity"]
    harvester["returnTarget"] = "pending"
    for _ in range(500):
        server.tick_harvester(room, harvester, 0.05)
        if harvester["cargo"] == 0:
            break
    assert harvester["cargo"] == 0
    assert harvester["preferredResourceId"] == chosen_ore["id"]
    server.tick_harvester(room, harvester, 0.05)
    assert harvester["harvestTarget"] == chosen_ore["id"]

    # 普通移动同样暂停自动采矿，必须再次右键矿脉才能恢复。
    server.issue_move(game, owner["id"], {harvester["id"]}, 800, 800)
    assert harvester["harvestPaused"] is True
    assert harvester["preferredResourceId"] is None

    with open(os.path.join(ROOT, "public", "index.html"), "r", encoding="utf-8") as handle:
        index = handle.read()
    with open(os.path.join(ROOT, "public", "app.js"), "r", encoding="utf-8") as handle:
        app = handle.read()
    assert 'title="停止当前命令 (H)"' in index
    assert "event.code === 'KeyH'" in app
    assert "command: 'harvest'" in app


def main():
    check_random_resources()
    check_harvester_drives_home()
    check_manual_stop_and_priority_mine()
    print("economy ok: random ore, physical return, persistent H stop and priority mining")


if __name__ == "__main__":
    main()
