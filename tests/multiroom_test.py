#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Two rooms on different maps must not share terrain or navigation state.

Regression test. Terrain used to live in module globals that tick_game
overwrote for whichever room ticked last. Later it was cached per map, but the
cache also shared random neutral-camp costs, so second and later matches kept
inheriting old danger zones and invalidating each other's A* routes.
"""

from __future__ import print_function

import os
import random
import sys
import threading
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

    small = make_room("SMALL1", "iron_river_duel")   # 4800 x 3200
    large = make_room("LARGE1", "gold_crater_small")  # 6400 x 6400
    server.start_game(small)
    server.start_game(large)

    # --- Test 1: each game carries its own terrain context ---
    small_terrain = server.game_terrain(small["game"])
    large_terrain = server.game_terrain(large["game"])
    assert small_terrain is not large_terrain, "different maps need different terrain"
    for map_id, terrain in (("iron_river_duel", small_terrain),
                            ("gold_crater_small", large_terrain)):
        expected = (float(server.MAPS[map_id]["width"]), float(server.MAPS[map_id]["height"]))
        assert (terrain.width, terrain.height) == expected, \
            "%s should be %s, got %s" % (map_id, expected, (terrain.width, terrain.height))
    print("  Per-room terrain context: PASS")

    # --- Test 2: rooms on the SAME map still isolate mutable navigation ---
    original_zones = set(large_terrain._camp_zones)
    twin = make_room("LARGE2", "gold_crater_small")
    server.start_game(twin)
    twin_terrain = server.game_terrain(twin["game"])
    assert twin_terrain is not large_terrain, \
        "same-map rooms must not share camp zones or route caches"
    assert set(large_terrain._camp_zones) == original_zones, \
        "starting another match must not append danger zones to a live match"
    assert twin_terrain._camp_zones, "new match should carry its own guarded ore zones"
    print("  Same-map mutable navigation isolation: PASS")

    # --- Test 3: blockers stay correct while the other room ticks ---
    # Pick a point blocked on gold_crater_small but open on iron_river_duel.
    probe = None
    for cx in range(160, int(small_terrain.width), 80):
        for cy in range(160, int(small_terrain.height), 80):
            if (large_terrain.blocked(cx, cy)
                    and not small_terrain.blocked(cx, cy)):
                probe = (cx, cy)
                break
        if probe:
            break
    assert probe, "expected a blocked point that is open on the other map"

    for _ in range(20):
        # Interleave ticks the way game_loop() does across live rooms.
        server.tick_game(small, 0.05)
        server.tick_game(large, 0.05)
        # Terrain answers must depend on the game, not on who ticked last.
        assert large_terrain.blocked(*probe), \
            "gold_crater_small blocker must stay active regardless of tick order"
        assert not small_terrain.blocked(*probe), \
            "iron_river_duel must stay open at the other map's mountain point"
        assert not server.position_clear(large["game"], probe[0], probe[1], 30), \
            "building on gold_crater_small blocked terrain must be rejected mid-interleave"
    print("  Interleaved ticks keep mountain blockers correct: PASS")

    # --- Test 4: interleaved ticks do not thrash the path cache ---
    small_terrain._path_cache.clear()
    large_terrain._path_cache.clear()
    small_terrain.find_path(200, 200, small_terrain.width - 400, small_terrain.height - 400)
    large_terrain.find_path(3200, 750, 4640, 5182)
    assert len(small_terrain._path_cache) > 0 and len(large_terrain._path_cache) > 0

    for _ in range(20):
        server.tick_game(small, 0.05)
        server.tick_game(large, 0.05)
    assert len(small_terrain._path_cache) > 0, "small room lost its cached paths"
    assert len(large_terrain._path_cache) > 0, "large room lost its cached paths"

    # A repeated query must be served from cache, not recomputed.
    t0 = time.time()
    for _ in range(50):
        large_terrain.find_path(3200, 750, 4640, 5182)
    cached_ms = (time.time() - t0) * 1000
    assert cached_ms < 25, "50 cached lookups took %.1f ms; cache is being flushed" % cached_ms
    print("  Path cache survives interleaving (50 lookups %.1f ms): PASS" % cached_ms)

    # --- Test 5: units in the small room stay inside the small map ---
    small_w = server.MAPS["iron_river_duel"]["width"]
    small_h = server.MAPS["iron_river_duel"]["height"]
    for unit in small["game"]["units"]:
        assert 0 <= unit["x"] <= small_w and 0 <= unit["y"] <= small_h, \
            "unit escaped iron_river_duel bounds: %s" % ((unit["x"], unit["y"]),)
    print("  Small-map bounds respected: PASS")

    # --- Test 6: rooms no longer share one global sim lock ---
    lock_a = server.room_lock(small)
    lock_b = server.room_lock(large)
    assert lock_a is not lock_b
    assert lock_a is not server.LOCK
    saved = dict(server.ROOMS)
    try:
        server.ROOMS.clear()
        server.ROOMS[small["id"]] = small
        server.ROOMS[large["id"]] = large
        held = threading.Event()
        release = threading.Event()

        def hold_small():
            with lock_a:
                held.set()
                release.wait(2.0)

        blocker = threading.Thread(target=hold_small)
        blocker.start()
        assert held.wait(1.0), "room A lock holder did not start"
        t0 = time.time()
        with lock_b:
            server.tick_game(large, 0.05)
        elapsed = time.time() - t0
        release.set()
        blocker.join(2.0)
        assert elapsed < 0.2, "room B blocked by room A lock: %.3fs" % elapsed

        # Holding the registry LOCK must not block a room-B tick/snapshot.
        registry_held = threading.Event()
        registry_release = threading.Event()

        def hold_registry():
            with server.LOCK:
                registry_held.set()
                registry_release.wait(2.0)

        registry_blocker = threading.Thread(target=hold_registry)
        registry_blocker.start()
        assert registry_held.wait(1.0)
        t1 = time.time()
        with lock_b:
            server.tick_game(large, 0.05)
            viewer = next(iter(large["players"]))
            server.public_room(large, viewer_id=viewer, full=False)
        registry_elapsed = time.time() - t1
        registry_release.set()
        registry_blocker.join(2.0)
        assert registry_elapsed < 0.2, (
            "room B still waits on the global registry lock: %.3fs" % registry_elapsed)
        assert small.get("lock") is not large.get("lock")
    finally:
        server.ROOMS.clear()
        server.ROOMS.update(saved)
    print("  Per-room sim locks (A does not block B): PASS")

    print("multiroom tests ok: 6 tests passed")


if __name__ == "__main__":
    main()
