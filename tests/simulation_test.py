#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Deterministic in-process checks for economy, production and victory."""

from __future__ import print_function

import os
import random
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import server


def tick_for(room, seconds, step=0.05):
    count = int(seconds / step)
    for _ in range(count):
        server.tick_game(room, step)


def main():
    random.seed(20260718)
    alpha = server.create_human("模拟甲", server.COLORS[0])
    beta = server.create_human("模拟乙", server.COLORS[1])
    room = {
        "id": "SIM001",
        "name": "模拟战场",
        "status": "lobby",
        "hostId": alpha["id"],
        "players": {alpha["id"]: alpha, beta["id"]: beta},
        "chat": [],
        "game": None,
        "createdAt": time.time(),
    }
    server.start_game(room)
    game = room["game"]
    assert game["map"]["width"] == server.MAPS[server.DEFAULT_MAP]["width"]
    assert game["map"]["height"] == server.MAPS[server.DEFAULT_MAP]["height"]
    alpha_view = server.public_room(room, viewer_id=alpha["id"])["game"]
    assert alpha_view["units"], "viewer should see their own units"
    assert all(item["owner"] == alpha["id"] for item in alpha_view["structures"])

    hq = next(item for item in game["structures"]
              if item["owner"] == alpha["id"] and item["kind"] == "hq")
    server.queue_structure(room, alpha["id"], "barracks")
    assert alpha["buildQueue"][0]["ready"] is False
    tick_for(room, 10.2)
    assert alpha["buildQueue"][0]["ready"] is True
    barracks = server.place_prepared_structure(
        room, alpha["id"], "barracks", hq["x"] + 200, hq["y"] - 120)
    assert barracks["active"] is False
    tick_for(room, 3.0)
    assert barracks["active"] is True

    # A turret foundation remains vulnerable and damage is never healed away.
    server.queue_structure(room, alpha["id"], "turret")
    tick_for(room, 12.2)
    turret = server.place_prepared_structure(
        room, alpha["id"], "turret", hq["x"] - 190, hq["y"] + 40)
    server.apply_damage(room, turret, 130, beta["id"])
    tick_for(room, 0.4)
    undamaged_material_hp = turret["maxHp"] * (
        1.0 - turret["buildRemaining"] / turret["buildTotal"])
    assert turret["constructionDamage"] == 130
    assert turret["hp"] < undamaged_material_hp
    server.apply_damage(room, turret, 500, beta["id"])
    assert turret["hp"] == 0

    # Defensive structures cannot be chained to extend construction territory.
    chain_turret = server.make_structure("turret", alpha["id"], hq["x"] + 300, hq["y"], True)
    game["structures"].append(chain_turret)
    try:
        server.place_structure(room, alpha["id"], "turret", hq["x"] + 600, hq["y"], free=True)
        raise AssertionError("turret chaining should have been rejected")
    except ValueError as error:
        assert "核心基地" in str(error)

    before_units = len([item for item in game["units"] if item["owner"] == alpha["id"]])
    server.queue_unit(room, alpha["id"], "rifle")
    tick_for(room, 3.5)
    after_units = len([item for item in game["units"] if item["owner"] == alpha["id"]])
    assert after_units == before_units + 1

    cash_before_harvest = alpha["cash"]
    tick_for(room, 25.0)
    assert alpha["harvested"] > 0
    assert alpha["cash"] > cash_before_harvest

    for s in game["structures"]:
        if s["owner"] == beta["id"]:
            s["hp"] = 0
    tick_for(room, 1.0)
    assert beta["eliminated"] is True
    assert room["status"] == "finished"
    assert game["winnerId"] == alpha["id"]
    print("simulation ok: fog, territory, vulnerable construction, queues, economy, victory")


if __name__ == "__main__":
    main()
