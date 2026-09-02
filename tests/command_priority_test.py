#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Regression checks for explicit player-order priority."""

from __future__ import print_function

import os
import random
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import server


def make_room():
    random.seed(20260720)
    alpha = server.create_human("指令甲", server.COLORS[0])
    beta = server.create_human("指令乙", server.COLORS[1])
    room = {
        "id": "ORDER1", "name": "指令测试", "status": "lobby",
        "hostId": alpha["id"],
        "players": {alpha["id"]: alpha, beta["id"]: beta},
        "chat": [], "game": None, "createdAt": time.time(),
        "selectedMap": "narrow_standoff",
    }
    server.start_game(room)
    game = room["game"]
    game["terrainCtx"] = server.FLAT_TERRAIN
    game["units"] = []
    game["projectiles"] = []
    game["effects"] = []
    game["victoryClock"] = 999.0
    return room, alpha, beta


def tick_for(room, seconds, step=0.05):
    for _ in range(int(seconds / step)):
        server.tick_game(room, step)


def main():
    room, alpha, beta = make_room()
    game = room["game"]

    tank = server.make_unit("tank", alpha["id"], 900, 900)
    enemy = server.make_unit("harvester", beta["id"], 1020, 900)
    tank["targetId"] = enemy["id"]
    tank["order"] = "attack"
    game["units"].extend([tank, enemy])

    # A normal move must interrupt an existing attack and must not reacquire
    # nearby enemies until the explicitly requested destination is reached.
    server.issue_move(game, alpha["id"], {tank["id"]}, 1400, 900)
    assert tank["targetId"] is None
    tick_for(room, 1.0)
    assert tank["x"] > 950, tank["x"]
    assert tank["targetId"] is None
    assert tank["order"] == "move"
    assert not any(item["owner"] == alpha["id"] for item in game["projectiles"])

    # Large selections must not silently leave unit 51+ on their old attack.
    formation = []
    for index in range(64):
        unit = server.make_unit(
            "tank", alpha["id"], 1800 + (index % 8) * 34,
            400 + (index // 8) * 34)
        unit["targetId"] = enemy["id"]
        unit["order"] = "attack"
        formation.append(unit)
    game["units"].extend(formation)
    server.handle_game_command(room, alpha, {
        "command": "move", "unitIds": [unit["id"] for unit in formation],
        "x": 2500, "y": 700,
    })
    assert all(unit["order"] == "move" for unit in formation)
    assert all(unit["targetId"] is None for unit in formation)

    # The same rule applies to harvesters, even when a long move takes more
    # than the old six-second manual-control window.
    scout_harvester = server.make_unit("harvester", alpha["id"], 500, 300)
    game["units"].append(scout_harvester)
    game["resources"] = [{
        "id": "ore-behind", "x": 100, "y": 300,
        "amount": 9000.0, "maxAmount": 9000.0, "radius": 48.0,
    }]
    server.issue_move(game, alpha["id"], {scout_harvester["id"]}, 1100, 300)
    tick_for(room, 7.0)
    assert scout_harvester["x"] > 850, scout_harvester["x"]
    assert abs(scout_harvester["y"] - 300) < 2, scout_harvester["y"]
    assert scout_harvester["order"] == "move"

    print("command priority ok: move interrupts combat, handles large groups and persists for harvesters")


if __name__ == "__main__":
    main()
