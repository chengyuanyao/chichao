#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Local simulation budget check with four populated armies."""

from __future__ import print_function

import json
import os
import random
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import server


def main():
    random.seed(110)
    players = [server.create_human("性能%d" % index, server.COLORS[index])
               for index in range(4)]
    room = {
        "id": "PERF01", "name": "性能战场", "status": "lobby",
        "hostId": players[0]["id"],
        "players": {player["id"]: player for player in players},
        "chat": [], "game": None, "createdAt": time.time(),
        # 五车争霸没有中立守军，适合稳定衡量密集部队本身的实时预算。
        "selectedMap": "central_scramble",
    }
    server.start_game(room)
    game = room["game"]
    # Keep four large armies alive in one combat zone. This exercises target
    # acquisition, unit separation, projectile tracking, splash damage and
    # per-player snapshots at the same time instead of benchmarking idle bases.
    for player_index, player in enumerate(players):
        side_x = -1 if player_index % 2 == 0 else 1
        side_y = -1 if player_index < 2 else 1
        for index in range(100):
            unit = server.make_unit(
                "tank", player["id"],
                1800 + side_x * 105 + (index % 10) * 24,
                1100 + side_y * 105 + (index // 10) * 24)
            unit["hp"] = 1000000.0
            unit["maxHp"] = 1000000.0
            unit["cooldown"] = 0.0
            unit["scan"] = 0.0
            game["units"].append(unit)

    tick_times = []
    snapshot_bytes = 0
    for index in range(120):
        started = time.perf_counter()
        server.tick_game(room, 0.05)
        tick_times.append(time.perf_counter() - started)
        if index % 2 == 0:
            for player in players:
                payload = server.public_room(room, viewer_id=player["id"])
                snapshot_bytes += len(json.dumps(payload, separators=(",", ":")))

    maximum_ms = max(tick_times) * 1000
    average_ms = sum(tick_times) / len(tick_times) * 1000
    ordered_ms = sorted(value * 1000 for value in tick_times)
    p95_ms = ordered_ms[int(len(ordered_ms) * 0.95) - 1]
    # The server advances at 20Hz (50ms budget). Keep normal ticks far below
    # that budget and even the deliberately synchronized first target scan
    # below one frame, otherwise the client's 60Hz interpolation will hitch.
    assert average_ms < 15.0, average_ms
    assert p95_ms < 25.0, p95_ms
    assert maximum_ms < 45.0, maximum_ms
    print("performance ok: 4 players, %d units, avg %.2f ms/tick, p95 %.2f ms, max %.2f ms, snapshots %.1f KiB" % (
        len(game["units"]), average_ms, p95_ms, maximum_ms,
        snapshot_bytes / 1024.0))


if __name__ == "__main__":
    main()
