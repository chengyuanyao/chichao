#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Deterministic checks for the vehicle repair-bay workflow."""

from __future__ import print_function

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


if __name__ == "__main__":
    main()
