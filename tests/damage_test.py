#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Damage type vs armor counter tests."""

from __future__ import print_function

import os
import random
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import server


def main():
    a = server.create_human("A", server.COLORS[0])
    b = server.create_human("B", server.COLORS[1])
    room = {
        "id": "DMG01", "name": "dmg test", "status": "lobby",
        "hostId": a["id"],
        "players": {a["id"]: a, b["id"]: b},
        "chat": [], "game": None, "createdAt": time.time(),
    }
    server.start_game(room)
    game = room["game"]

    print("=== Test 1: Sniper vs infantry (220% damage) ===")
    rifle = server.make_unit("rifle", b["id"], 2000, 2000)
    rifle["hp"] = 300
    game["units"].append(rifle)
    hp_before = rifle["hp"]
    server.apply_damage(room, rifle, 50, a["id"], "sniper", game)
    expected = 50 * 2.20
    actual = hp_before - rifle["hp"]
    assert abs(actual - expected) < 0.1, (actual, expected)
    print("  Sniper vs infantry: %.0f (expected %.0f) PASS" % (actual, expected))

    print("\n=== Test 2: Rocket vs heavy vehicle (150% damage) ===")
    tank = server.make_unit("tank", b["id"], 2100, 2100)
    game["units"].append(tank)
    hp_before = tank["hp"]
    server.apply_damage(room, tank, 100, a["id"], "rocket", game)
    expected = 100 * 1.50
    actual = hp_before - tank["hp"]
    assert abs(actual - expected) < 0.1, (actual, expected)
    print("  Rocket vs tank: %.0f (expected %.0f) PASS" % (actual, expected))

    print("\n=== Test 3: Bullet vs heavy vehicle (35% damage) ===")
    tank2 = server.make_unit("tank", b["id"], 2200, 2200)
    game["units"].append(tank2)
    hp_before = tank2["hp"]
    server.apply_damage(room, tank2, 100, a["id"], "bullet", game)
    expected = 100 * 0.35
    actual = hp_before - tank2["hp"]
    assert abs(actual - expected) < 0.1, (actual, expected)
    print("  Bullet vs tank: %.0f (expected %.0f) PASS" % (actual, expected))

    print("\n=== Test 4: Siege vs structure (180% damage) ===")
    hq = next(s for s in game["structures"] if s["kind"] == "hq" and s["owner"] == b["id"])
    hp_before = hq["hp"]
    server.apply_damage(room, hq, 200, a["id"], "siege", game)
    expected = 200 * 1.80
    actual = hp_before - hq["hp"]
    assert abs(actual - expected) < 0.1, (actual, expected)
    print("  Siege vs HQ: %.0f (expected %.0f) PASS" % (actual, expected))

    print("\n=== Test 5: Sniper vs tank (15% - almost useless) ===")
    tank3 = server.make_unit("tank", b["id"], 2300, 2300)
    game["units"].append(tank3)
    hp_before = tank3["hp"]
    server.apply_damage(room, tank3, 100, a["id"], "sniper", game)
    expected = 100 * 0.15
    actual = hp_before - tank3["hp"]
    assert abs(actual - expected) < 0.1, (actual, expected)
    print("  Sniper vs tank: %.0f (expected %.0f) PASS" % (actual, expected))

    print("\n=== Test 6: AP vs heavy vehicle (210% damage) ===")
    tank4 = server.make_unit("tank", b["id"], 2400, 2400)
    game["units"].append(tank4)
    hp_before = tank4["hp"]
    server.apply_damage(room, tank4, 100, a["id"], "ap", game)
    expected = 100 * 2.10
    actual = hp_before - tank4["hp"]
    assert abs(actual - expected) < 0.1, (actual, expected)
    print("  AP vs tank: %.0f (expected %.0f) PASS" % (actual, expected))

    print("\n=== Test 7: Unit type definitions ===")
    assert "rifle" in server.UNIT_TYPES
    assert "rocket" in server.UNIT_TYPES
    assert "sniper" in server.UNIT_TYPES
    assert "tank" in server.UNIT_TYPES
    assert "artillery" in server.UNIT_TYPES
    assert "tank_destroyer" in server.UNIT_TYPES
    assert server.UNIT_TYPES["rocket"]["damageType"] == "rocket"
    assert server.UNIT_TYPES["sniper"]["damageType"] == "sniper"
    assert server.UNIT_TYPES["artillery"]["damageType"] == "siege"
    assert server.UNIT_TYPES["rocket"]["producer"] == "barracks"
    assert server.UNIT_TYPES["artillery"]["producer"] == "factory"
    assert server.UNIT_TYPES["tank_destroyer"]["damageType"] == "ap"
    print("  Unit definitions: PASS")

    print("\n=== All damage multiplier tests passed! ===")


if __name__ == "__main__":
    main()
