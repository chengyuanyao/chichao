#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Two rooms on different maps must not share terrain or navigation state.

Regression test. Terrain used to live in module globals that tick_game
overwrote for whichever room ticked last, so a build validated on an HTTP
thread could be checked against another room's mountains, and the shared A*
grid was rebuilt (flushing the path cache) on every interleaved tick.
"""

from __future__ import print_function

import os
import random
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import server


def make_room(room_id, map_id):
    alpha = server.create_human("%s甲" % room_id, server.COLORS[0])
    beta = server.create_human("%s乙" % room_id, server.COLORS[1])
    return {
        "id": room_id, "name": room_id, "status": "lobby",
        "hostId": alpha["id"],
        "players": {alpha["id"]: alpha, beta["id"]: beta},
        "chat": [], "game": None, "createdAt": time.time(),
        "selectedMap": map_id,
    }


def main():
    random.seed(20260725)

    small = make_room("SMALL1", "narrow_standoff")   # 4800 x 3200
    large = make_room("LARGE1", "north_conflict")    # 9600 x 6000
    server.start_game(small)
    server.start_game(large)

    # --- Test 1: each game carries its own terrain context ---
    small_terrain = server.game_terrain(small["game"])
    large_terrain = server.game_terrain(large["game"])
    assert small_terrain is not large_terrain, "different maps need different terrain"
    for map_id, terrain in (("narrow_standoff", small_terrain),
                            ("north_conflict", large_terrain)):
        expected = (float(server.MAPS[map_id]["width"]), float(server.MAPS[map_id]["height"]))
        assert (terrain.width, terrain.height) == expected, \
            "%s should be %s, got %s" % (map_id, expected, (terrain.width, terrain.height))
    print("  Per-room terrain context: PASS")

    # --- Test 2: rooms on the SAME map share one context (grid built once) ---
    twin = make_room("LARGE2", "north_conflict")
    server.start_game(twin)
    assert server.game_terrain(twin["game"]) is large_terrain, \
        "rooms on the same map should share the navigation grid"
    print("  Same-map context sharing: PASS")

    # --- Test 3: mountain blockers stay correct while the other room ticks ---
    # Pick a point that is mountain on north_conflict but open on narrow_standoff.
    probe = None
    for mountain in large_terrain.mountains:
        cx, cy = mountain["x"], mountain["y"]
        if (0 < cx < small_terrain.width and 0 < cy < small_terrain.height
                and large_terrain.point_in_mountain(cx, cy)
                and not small_terrain.point_in_mountain(cx, cy)):
            probe = (cx, cy)
            break
    assert probe, "expected a mountain point that is open on the other map"

    for _ in range(20):
        # Interleave ticks the way game_loop() does across live rooms.
        server.tick_game(small, 0.05)
        server.tick_game(large, 0.05)
        # Terrain answers must depend on the game, not on who ticked last.
        assert large_terrain.point_in_mountain(*probe), \
            "north_conflict mountain must stay blocked regardless of tick order"
        assert not small_terrain.point_in_mountain(*probe), \
            "narrow_standoff must stay open at the other map's mountain point"
        assert not server.position_clear(large["game"], probe[0], probe[1], 30), \
            "building on a north_conflict mountain must be rejected mid-interleave"
    print("  Interleaved ticks keep mountain blockers correct: PASS")

    # --- Test 4: interleaved ticks do not thrash the path cache ---
    small_terrain._path_cache.clear()
    large_terrain._path_cache.clear()
    small_terrain.find_path(200, 200, small_terrain.width - 400, small_terrain.height - 400)
    large_terrain.find_path(700, 600, 6500, 3800)
    assert len(small_terrain._path_cache) > 0 and len(large_terrain._path_cache) > 0

    for _ in range(20):
        server.tick_game(small, 0.05)
        server.tick_game(large, 0.05)
    assert len(small_terrain._path_cache) > 0, "small room lost its cached paths"
    assert len(large_terrain._path_cache) > 0, "large room lost its cached paths"

    # A repeated query must be served from cache, not recomputed.
    t0 = time.time()
    for _ in range(50):
        large_terrain.find_path(700, 600, 6500, 3800)
    cached_ms = (time.time() - t0) * 1000
    assert cached_ms < 25, "50 cached lookups took %.1f ms; cache is being flushed" % cached_ms
    print("  Path cache survives interleaving (50 lookups %.1f ms): PASS" % cached_ms)

    # --- Test 5: units in the small room stay inside the small map ---
    small_w = server.MAPS["narrow_standoff"]["width"]
    small_h = server.MAPS["narrow_standoff"]["height"]
    for unit in small["game"]["units"]:
        assert 0 <= unit["x"] <= small_w and 0 <= unit["y"] <= small_h, \
            "unit escaped narrow_standoff bounds: %s" % ((unit["x"], unit["y"]),)
    print("  Small-map bounds respected: PASS")

    print("multiroom tests ok: 5 tests passed")


if __name__ == "__main__":
    main()
