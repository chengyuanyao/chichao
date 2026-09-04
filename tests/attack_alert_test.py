#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Deterministic checks for authoritative under-attack battle zones."""

from __future__ import print_function

import os
import random
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import server


def main():
    random.seed(20260903)
    alpha = server.create_human("警报甲", server.COLORS[0])
    beta = server.create_human("警报乙", server.COLORS[1])
    room = {
        "id": "ALERT1", "name": "受袭警报测试", "status": "lobby",
        "hostId": alpha["id"],
        "players": {alpha["id"]: alpha, beta["id"]: beta},
        "chat": [], "game": None, "createdAt": time.time(),
        "selectedMap": "narrow_standoff", "neutrals": False,
    }
    server.start_game(room)
    game = room["game"]
    game["terrainCtx"] = server.FLAT_TERRAIN
    game["victoryClock"] = 999.0

    victim = next(unit for unit in game["units"] if unit["owner"] == alpha["id"])
    attacker = next(unit for unit in game["units"] if unit["owner"] == beta["id"])
    victim["x"], victim["y"] = 1000.0, 1000.0
    attacker["x"], attacker["y"] = 4000.0, 2600.0
    server.apply_damage(
        room, victim, 10.0, beta["id"], None, game,
        attacker["id"], attacker)
    assert len(game["attackAlerts"]) == 1
    first = game["attackAlerts"][0]
    first_id = first["id"]
    assert first["owner"] == alpha["id"]
    assert first["structure"] is False
    assert first["entityKind"] == victim["kind"]
    assert first["expiresAt"] == game["elapsed"] + server.ATTACK_ALERT_TTL

    # Nearby hits merge into one zone; a building becomes the stable anchor.
    hq = next(structure for structure in game["structures"]
              if structure["owner"] == alpha["id"]
              and server.structure_role(structure["kind"]) == "hq")
    hq["x"], hq["y"] = 1110.0, 1040.0
    server.apply_damage(room, hq, 12.0, beta["id"], None, game)
    assert len(game["attackAlerts"]) == 1
    merged = game["attackAlerts"][0]
    assert merged["id"] == first_id
    assert merged["hits"] == 2
    assert merged["structure"] is True
    assert merged["entityKind"] == hq["kind"]
    assert (merged["x"], merged["y"]) == (hq["x"], hq["y"])

    # A distant fight remains independently jumpable.
    victim["x"], victim["y"] = 2200.0, 2300.0
    server.apply_damage(room, victim, 8.0, beta["id"], None, game)
    assert len(game["attackAlerts"]) == 2

    alpha_view = server.public_game(game, alpha["id"])
    beta_view = server.public_game(game, beta["id"])
    assert len(alpha_view["attackAlerts"]) == 2
    assert beta_view["attackAlerts"] == []
    assert all(0 < alert["ttl"] <= server.ATTACK_ALERT_TTL
               for alert in alpha_view["attackAlerts"])

    # The server owns expiry; stale zones disappear from later snapshots.
    for alert in game["attackAlerts"]:
        alert["expiresAt"] = game["elapsed"]
    server.tick_game(room, 0.05)
    assert game["attackAlerts"] == []

    print("attack alerts ok: unit/building merge, private snapshots and expiry")


if __name__ == "__main__":
    main()
