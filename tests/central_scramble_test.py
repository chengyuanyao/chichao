#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""五车争疆：中央折叠开局、中央双倍矿、全图无中立矿营。"""

from __future__ import print_function

import math
import os
import random
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import server


MAP_ID = "central_scramble"


def make_room(seed, with_bot=False):
    random.seed(seed)
    human_count = 4 if with_bot else 5
    players = [server.create_human("迁徙%d" % (index + 1), server.COLORS[index])
               for index in range(human_count)]
    for index, player in enumerate(players):
        player["faction"] = "magic" if index % 2 else "tech"
    room = {
        "id": "PACK%d" % seed,
        "name": "五车争疆测试",
        "status": "lobby",
        "hostId": players[0]["id"],
        "players": {player["id"]: player for player in players},
        "chat": [],
        "game": None,
        "createdAt": time.time(),
        "selectedMap": MAP_ID,
    }
    bot = None
    if with_bot:
        bot = server.create_bot(room)
        bot["faction"] = "magic"
    server.start_game(room)
    return room, players, bot


def outer_positions(game):
    return sorted((round(resource["x"], 1), round(resource["y"], 1))
                  for resource in game["resources"]
                  if math.hypot(resource["x"] - 2000, resource["y"] - 2000) > 300)


def main():
    map_def = server.MAPS[MAP_ID]
    assert map_def["width"] == map_def["height"] == 4000
    assert map_def["maxPlayers"] == 5
    assert len(map_def["spawnPoints"]) == 5
    assert map_def.get("packedStart") is True
    assert map_def.get("neutralOreGuards") is False
    assert map_def.get("publicOreCount") == 5
    assert map_def.get("publicOreAmount") == 230000
    assert server.PUBLIC_MAPS[MAP_ID]["maxPlayers"] == 5
    app_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                            "public", "app.js")
    with open(app_path, "r", encoding="utf-8") as handle:
        assert "central_scramble:" in handle.read(), "客户端内置地图目录缺少五车争疆"

    print("=== Test 1: 五人都只带折叠基地车，集中停在中央 ===")
    room, players, _bot = make_room(71101)
    game = room["game"]
    assert not game["structures"], game["structures"]
    assert len(game["units"]) == 5, len(game["units"])
    for player in players:
        commands = [unit for unit in game["units"]
                    if unit["owner"] == player["id"] and unit["hp"] > 0]
        assert len(commands) == 1, (player["name"], commands)
        command = commands[0]
        expected = server.faction_loadout(player["faction"])["mcv"]
        assert command["kind"] == expected, (command["kind"], expected)
        assert server.unit_role(command["kind"]) == "mcv"
        distance = math.hypot(command["x"] - 2000, command["y"] - 2000)
        assert 180 <= distance <= 200, distance
        assert command["order"] == "guard"
        assert command["destX"] is None and command["destY"] is None
        assert server.player_has_command(game, player["id"])
    print("  科技基地车/秘法迁徙法阵共 5 辆，中央静止折叠: PASS")

    print("\n=== Test 2: 中央矿量稳定为外围单片矿的两倍 ===")
    assert len(game["resources"]) == 6, len(game["resources"])
    center = [resource for resource in game["resources"]
              if math.hypot(resource["x"] - 2000, resource["y"] - 2000) < 20]
    outer = [resource for resource in game["resources"] if resource not in center]
    assert len(center) == 1 and center[0]["amount"] == 460000, center
    assert len(outer) == 5, len(outer)
    assert all(resource["amount"] == 230000 for resource in outer), outer
    assert all(center[0]["amount"] == resource["amount"] * 2
               for resource in outer), (center, outer)
    assert all(math.hypot(resource["x"] - 2000, resource["y"] - 2000) > 700
               for resource in outer)
    assert all(resource.get("public") for resource in game["resources"])
    room2, _players2, _bot2 = make_room(71102)
    assert outer_positions(game) != outer_positions(room2["game"]), \
        "不同对局的外围矿坐标应重新随机"
    print("  总计 6 片；中央固定 460000，外围每片固定 230000，比例 2:1: PASS")

    print("\n=== Test 3: 固定矿和随机矿都没有中立守军 ===")
    assert game.get("neutralCamps") == []
    assert all(not resource.get("guarded") for resource in game["resources"])
    assert all(not resource.get("neutralCampId") for resource in game["resources"])
    neutral_entities = [entity for entity in game["units"] + game["structures"]
                        if entity.get("owner") == server.NEUTRAL_OWNER]
    assert not neutral_entities, neutral_entities
    print("  无中立炮塔、突击兵、火箭兵，矿区开局即开放: PASS")

    print("\n=== Test 4: AI 会驶离中央后展开，不会折叠等三分钟 ===")
    bot_room, _humans, bot = make_room(71103, with_bot=True)
    bot_game = bot_room["game"]
    command = next(unit for unit in bot_game["units"]
                   if unit["owner"] == bot["id"] and server.unit_role(unit["kind"]) == "mcv")
    assert command.get("_openingDeployX") is not None
    assert command["destX"] is None and command["order"] == "guard"
    for _ in range(int(45.0 / 0.05)):
        server.tick_game(bot_room, 0.05)
    headquarters = [structure for structure in bot_game["structures"]
                    if structure["owner"] == bot["id"] and structure["hp"] > 0
                    and server.structure_role(structure["kind"]) == "hq"]
    assert len(headquarters) == 1, headquarters
    assert math.hypot(headquarters[0]["x"] - 2000,
                      headquarters[0]["y"] - 2000) > 900
    print("  AI 沿外环目标迁出并在 45 秒内展开: PASS")

    print("\n=== 五车争疆测试全部通过 ===")


if __name__ == "__main__":
    main()
