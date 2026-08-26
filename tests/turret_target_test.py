#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Owned defense structures can manually prioritize a right-click target."""

from __future__ import print_function

import os
import random
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import server


def make_room():
    random.seed(20260826)
    alpha = server.create_human("炮塔甲", server.COLORS[0])
    beta = server.create_human("炮塔乙", server.COLORS[1])
    room = {
        "id": "TURRET", "name": "炮塔手动集火", "status": "lobby",
        "hostId": alpha["id"],
        "players": {alpha["id"]: alpha, beta["id"]: beta},
        "chat": [], "game": None, "createdAt": time.time(),
    }
    server.start_game(room)
    game = room["game"]
    game["terrainCtx"] = server.FLAT_TERRAIN
    game["units"] = []
    game["structures"] = []
    game["projectiles"] = []
    game["effects"] = []
    return room, alpha, beta


def command(room, player, turret, target):
    server.handle_game_command(room, player, {
        "command": "structureAttack",
        "structureId": turret["id"],
        "targetId": target["id"],
    })


def expect_error(fragment, callback):
    try:
        callback()
        raise AssertionError("expected ValueError containing %r" % fragment)
    except ValueError as error:
        assert fragment in str(error), (fragment, str(error))


def main():
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    with open(os.path.join(root, "public", "app.js"), "r", encoding="utf-8") as handle:
        app = handle.read()
    assert "command: 'structureAttack'" in app
    assert "structureId: defense.id" in app
    assert "targetId: target.id" in app
    assert "右键敌军指定攻击" in app

    room, alpha, beta = make_room()
    game = room["game"]
    turret = server.make_structure("turret", alpha["id"], 1000, 1000, True)
    near = server.make_unit("tank", beta["id"], 1090, 1000)
    chosen = server.make_unit("tank", beta["id"], 1260, 1000)
    game["structures"].append(turret)
    game["units"].extend([near, chosen])

    # Manual focus beats the closer automatic target.
    command(room, alpha, turret, chosen)
    assert turret["targetId"] == chosen["id"]
    turret["cooldown"] = 0.0
    server.tick_structures(room, 0.05)
    assert game["projectiles"][-1]["targetId"] == chosen["id"]

    # Dead manual targets release the lock and automatic fire resumes.
    game["projectiles"] = []
    chosen["hp"] = 0
    turret["cooldown"] = 0.0
    server.tick_structures(room, 0.05)
    assert turret["targetId"] is None
    assert game["projectiles"][-1]["targetId"] == near["id"]

    # Units and buildings are both valid point targets for all defense kinds.
    enemy_building = server.make_structure(
        "power", beta["id"], 1240, 1000, True)
    game["structures"].append(enemy_building)
    for kind in ("turret", "missile", "mtower"):
        defense = server.make_structure(kind, alpha["id"], 1000, 1000, True)
        game["structures"].append(defense)
        command(room, alpha, defense, enemy_building)
        assert defense["targetId"] == enemy_building["id"], kind

    # Ownership, role, allegiance, construction state and range stay
    # authoritative on the server rather than trusting browser selection.
    own_unit = server.make_unit("tank", alpha["id"], 1100, 1000)
    game["units"].append(own_unit)
    expect_error("无效目标", lambda: command(room, alpha, turret, own_unit))

    factory = server.make_structure("factory", alpha["id"], 1000, 1000, True)
    game["structures"].append(factory)
    expect_error("己方已启用的炮塔", lambda: command(
        room, alpha, factory, near))

    enemy_turret = server.make_structure(
        "turret", beta["id"], 1000, 1000, True)
    game["structures"].append(enemy_turret)
    expect_error("己方已启用的炮塔", lambda: command(
        room, alpha, enemy_turret, near))

    building_turret = server.make_structure(
        "turret", alpha["id"], 1000, 1000, False)
    game["structures"].append(building_turret)
    expect_error("己方已启用的炮塔", lambda: command(
        room, alpha, building_turret, near))

    out_of_range = server.make_unit("tank", beta["id"], 1400, 1000)
    game["units"].append(out_of_range)
    expect_error("超出炮塔射程", lambda: command(
        room, alpha, turret, out_of_range))

    print("turret target ok: manual focus, fallback, validation, all defenses")


if __name__ == "__main__":
    main()
