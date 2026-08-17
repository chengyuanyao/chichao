#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Deterministic checks for the vehicle repair-bay workflow."""

from __future__ import print_function

import math
import os
import random
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import server


def tick_for(room, seconds, step=0.05):
    for _ in range(int(seconds / step)):
        server.tick_game(room, step)


def main():
    random.seed(20260721)
    alpha = server.create_human("维修甲", server.COLORS[0])
    beta = server.create_human("维修乙", server.COLORS[1])
    room = {
        "id": "FIX001", "name": "维修测试", "status": "lobby",
        "hostId": alpha["id"],
        "players": {alpha["id"]: alpha, beta["id"]: beta},
        "chat": [], "game": None, "createdAt": time.time(),
    }
    server.start_game(room)
    game = room["game"]
    game["victoryClock"] = 999.0

    repair_bay = server.make_structure("repair", alpha["id"], 820, 720, True)
    game["structures"].append(repair_bay)
    tank = server.make_unit("tank", alpha["id"], 620, 720)
    tank["hp"] = 140.0
    game["units"].append(tank)
    alpha["cash"] = 1000.0

    server.handle_game_command(room, alpha, {
        "command": "repair", "unitIds": [tank["id"]],
        "structureId": repair_bay["id"],
    })
    assert tank["order"] == "repair"
    assert tank["repairTargetId"] == repair_bay["id"]

    start_x = tank["x"]
    tick_for(room, 3.2)
    assert tank["x"] > start_x + 40
    assert tank["hp"] > 140.0
    assert alpha["cash"] < 1000.0
    assert tank["repairing"] is True
    public_tank = next(item for item in server.public_game(game, alpha["id"])["units"]
                       if item["id"] == tank["id"])
    assert public_tank["repairing"] is True

    tick_for(room, 6.0)
    assert tank["hp"] == tank["maxHp"]
    assert tank["order"] == "guard"
    assert tank["repairTargetId"] is None

    # A new player command immediately interrupts the repair trip.
    tank["hp"] = 220.0
    server.issue_repair(game, alpha["id"], {tank["id"]}, repair_bay["id"])
    server.issue_move(game, alpha["id"], {tank["id"]}, 1300, 720)
    assert tank["order"] == "move"
    assert tank["repairTargetId"] is None
    assert tank["repairing"] is False

    infantry = server.make_unit("rifle", alpha["id"], 700, 700)
    infantry["hp"] = 20.0
    game["units"].append(infantry)
    try:
        server.issue_repair(game, alpha["id"], {infantry["id"]}, repair_bay["id"])
        raise AssertionError("infantry should not enter a vehicle repair bay")
    except ValueError as error:
        assert "受损载具" in str(error)

    enemy_bay = server.make_structure("repair", beta["id"], 900, 720, True)
    game["structures"].append(enemy_bay)
    try:
        server.issue_repair(game, alpha["id"], {tank["id"]}, enemy_bay["id"])
        raise AssertionError("enemy repair bays must not accept orders")
    except ValueError as error:
        assert "维修厂" in str(error)

    print("repair ok: routing, paid healing, completion, interruption and validation")

    print("\n=== Magic 圣泉: queue/place + golem repair path ===")
    mage = server.create_human("秘法甲", server.COLORS[2])
    foe = server.create_human("秘法乙", server.COLORS[3])
    mage["faction"] = "magic"
    magic_room = {
        "id": "FIX002", "name": "圣泉测试", "status": "lobby",
        "hostId": mage["id"],
        "players": {mage["id"]: mage, foe["id"]: foe},
        "chat": [], "game": None, "createdAt": time.time(),
    }
    server.start_game(magic_room)
    magic_game = magic_room["game"]
    magic_game["victoryClock"] = 999.0
    mage["cash"] = 99999
    try:
        server.queue_structure(magic_room, mage["id"], "mspring")
        raise AssertionError("圣泉缺召唤法阵时不该能排队")
    except ValueError as error:
        assert "前置建筑" in str(error)
    magic_game["structures"].append(
        server.make_structure("mcircle", mage["id"], 900, 900, True))
    server.queue_structure(magic_room, mage["id"], "mspring")
    assert mage["buildQueue"] and mage["buildQueue"][0]["kind"] == "mspring"

    mhq = next(s for s in magic_game["structures"]
               if s["owner"] == mage["id"] and s["kind"] == "mhq")
    placed = None
    for radius in (150, 180, 210, 250, 300):
        for deg in range(0, 360, 15):
            rad = math.radians(deg)
            x = mhq["x"] + math.cos(rad) * radius
            y = mhq["y"] + math.sin(rad) * radius
            try:
                placed = server.place_structure(
                    magic_room, mage["id"], "mspring", x, y, free=True)
                break
            except ValueError:
                continue
        if placed:
            break
    assert placed is not None and placed["kind"] == "mspring"
    placed["active"] = True
    placed["buildRemaining"] = 0.0

    golem = server.make_unit("golem", mage["id"], placed["x"] - 180, placed["y"])
    golem["hp"] = 160.0
    magic_game["units"].append(golem)
    cash_before = mage["cash"]
    server.handle_game_command(magic_room, mage, {
        "command": "repair", "unitIds": [golem["id"]],
        "structureId": placed["id"],
    })
    assert golem["order"] == "repair"
    assert golem["repairTargetId"] == placed["id"]
    tick_for(magic_room, 5.0)
    assert golem["hp"] > 160.0
    assert mage["cash"] < cash_before
    assert golem["repairing"] is True

    mage_unit = server.make_unit("mage", mage["id"], placed["x"] - 80, placed["y"])
    mage_unit["hp"] = 20.0
    magic_game["units"].append(mage_unit)
    try:
        server.issue_repair(magic_game, mage["id"], {mage_unit["id"]}, placed["id"])
        raise AssertionError("mage infantry should not enter the spring")
    except ValueError as error:
        assert "受损载具" in str(error)
    print("  magic queue/place 圣泉 + golem repair: PASS")


if __name__ == "__main__":
    main()
