#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests for new units: MCV deploy, refinery harvester gift, AP damage."""

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

    print("=== Test 1: MCV deploys into HQ ===")
    a = server.create_human("A", server.COLORS[0])
    b = server.create_human("B", server.COLORS[1])
    room = {
        "id": "MCV01", "name": "mcv test", "status": "lobby",
        "hostId": a["id"],
        "players": {a["id"]: a, b["id"]: b},
        "chat": [], "game": None, "createdAt": time.time(),
    }
    server.start_game(room)
    game = room["game"]

    hq_before = sum(1 for s in game["structures"] if s["owner"] == a["id"] and s["kind"] == "hq")
    # Deploy in the northern staging lane; the old (3000, 2000) probe is now mountain.
    deploy_x, deploy_y = 3000, 500
    mcv = server.make_unit("mcv", a["id"], deploy_x, deploy_y)
    game["units"].append(mcv)

    server.issue_deploy(game, a["id"], {mcv["id"]})
    hq_after = sum(1 for s in game["structures"] if s["owner"] == a["id"] and s["kind"] == "hq")
    assert hq_after == hq_before + 1, "MCV should have created a new HQ"
    assert mcv["hp"] <= 0, "MCV should be consumed"
    new_hq = next(s for s in game["structures"] if s["owner"] == a["id"] and s["kind"] == "hq" and abs(s["x"] - deploy_x) < 5)
    assert new_hq["active"] is True
    assert new_hq["hp"] == new_hq["maxHp"]
    print("  MCV deploy: PASS")

    print("\n=== Test 2: MCV deploy extends build territory ===")
    # Build a power near the new MCV-deployed HQ in the valley.
    power_built = False
    try:
        result = server.place_structure(room, a["id"], "power", deploy_x + 150, deploy_y, free=True)
        power_built = True
    except ValueError:
        pass
    assert power_built, "should be able to build near deployed HQ"
    print("  Build territory extension: PASS")

    print("\n=== Test 3: Can't deploy non-MCV ===")
    rifle = server.make_unit("rifle", a["id"], 3100, 2100)
    game["units"].append(rifle)
    try:
        server.issue_deploy(game, a["id"], {rifle["id"]})
        raise AssertionError("should reject non-MCV deploy")
    except ValueError as exc:
        assert "基地车" in str(exc)
    print("  Non-MCV rejection: PASS")

    print("\n=== Test 4: Refinery gift harvester ===")
    c = server.create_human("C", server.COLORS[2])
    d = server.create_human("D", server.COLORS[3])
    room2 = {
        "id": "REF01", "name": "refinery test", "status": "lobby",
        "hostId": c["id"],
        "players": {c["id"]: c, d["id"]: d},
        "chat": [], "game": None, "createdAt": time.time(),
    }
    server.start_game(room2)
    game2 = room2["game"]
    c_hq = next(s for s in game2["structures"] if s["owner"] == c["id"] and s["kind"] == "hq")
    harvesters_before = sum(1 for u in game2["units"] if u["owner"] == c["id"] and u["kind"] == "harvester")

    # Place a refinery near HQ (inactive, will become active after deploy time)
    new_ref = server.make_structure("refinery", c["id"], c_hq["x"] + 200, c_hq["y"], False)
    game2["structures"].append(new_ref)
    assert new_ref["active"] is False

    # Tick until refinery completes
    tick_for(room2, 5.0)
    assert new_ref["active"] is True, "refinery should be active"

    harvesters_after = sum(1 for u in game2["units"] if u["owner"] == c["id"] and u["kind"] == "harvester")
    assert harvesters_after == harvesters_before + 1, \
        "should have gained 1 harvester: %d -> %d" % (harvesters_before, harvesters_after)
    print("  Refinery gift harvester: PASS")

    print("\n=== Test 5: AP damage vs tank (210%) ===")
    e = server.create_human("E", server.COLORS[4])
    f = server.create_human("F", server.COLORS[5])
    room3 = {
        "id": "AP01", "name": "ap test", "status": "lobby",
        "hostId": e["id"],
        "players": {e["id"]: e, f["id"]: f},
        "chat": [], "game": None, "createdAt": time.time(),
    }
    server.start_game(room3)
    game3 = room3["game"]

    tank2 = server.make_unit("tank", f["id"], 2100, 2100)
    tank2["hp"] = 1000
    game3["units"].append(tank2)
    hp_before = tank2["hp"]
    server.apply_damage(room3, tank2, 100, e["id"], "ap", game3)
    expected = 100 * 2.10
    actual = hp_before - tank2["hp"]
    assert abs(actual - expected) < 0.1, (actual, expected)
    print("  AP vs tank: %.0f damage (expected %.0f) PASS" % (actual, expected))

    print("\n=== Test 6: AP damage vs infantry (25% - bad vs infantry) ===")
    rifle2 = server.make_unit("rifle", f["id"], 2200, 2200)
    rifle2["hp"] = 500
    game3["units"].append(rifle2)
    hp_before = rifle2["hp"]
    server.apply_damage(room3, rifle2, 100, e["id"], "ap", game3)
    expected = 100 * 0.25
    actual = hp_before - rifle2["hp"]
    assert abs(actual - expected) < 0.1, (actual, expected)
    print("  AP vs infantry: %.0f damage (expected %.0f) PASS" % (actual, expected))

    print("\n=== Test 7: Tank destroyer survives three overlord shells ===")
    destroyer = server.make_unit("tank_destroyer", f["id"], 2300, 2300)
    game3["units"].append(destroyer)
    assert destroyer["hp"] == destroyer["maxHp"] == 400
    for _ in range(3):
        server.apply_damage(room3, destroyer, 120, e["id"], "shell", game3)
    assert destroyer["hp"] == 40, destroyer["hp"]
    server.apply_damage(room3, destroyer, 120, e["id"], "shell", game3)
    assert destroyer["hp"] == 0
    print("  400 HP: survives 3 x 120 shell hits, destroyed by the fourth: PASS")

    print("\n=== Test 8: Unit definitions ===")
    assert "tank_destroyer" in server.UNIT_TYPES
    assert "mcv" in server.UNIT_TYPES
    assert server.UNIT_TYPES["tank_destroyer"]["damageType"] == "ap"
    assert server.UNIT_TYPES["tank_destroyer"]["hp"] == 400
    assert server.UNIT_TYPES["tank_destroyer"]["cost"] == 1050
    assert server.UNIT_TYPES["tank_destroyer"]["damage"] == 78.0
    assert server.UNIT_TYPES["tank_destroyer"]["range"] == 230.0
    assert server.UNIT_TYPES["tank_destroyer"]["cooldown"] == 1.7
    assert server.UNIT_TYPES["mcv"]["canDeploy"] is True
    assert server.UNIT_TYPES["tank_destroyer"]["producer"] == "factory"
    assert server.UNIT_TYPES["mcv"]["producer"] == "factory"
    print("  Unit definitions: PASS")

    print("\n=== All new unit tests passed! ===")


if __name__ == "__main__":
    main()
