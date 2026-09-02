#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""A* pathfinding tests for Steel Front."""

from __future__ import print_function

import os
import math
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import server


def tick_for(room, seconds, step=0.05):
    count = int(seconds / step)
    for _ in range(count):
        server.tick_game(room, step)


def main():
    random.seed(20260720)

    # Use a simple test map with known water layout
    terrain = server.Terrain(
        [{"x1": 0, "y1": 1200, "x2": 3600, "y2": 1200, "width": 100}],
        [{"x": 900, "y": 1200, "w": 150, "h": 140},
         {"x": 1800, "y": 1200, "w": 150, "h": 140},
         {"x": 2700, "y": 1200, "w": 150, "h": 140}],
        3600, 2400)

    # --- Test 1: Direct path (no water crossing) ---
    path = terrain.find_path(500, 500, 800, 800)
    assert len(path) >= 1, "should return at least the destination"
    # Should be a reasonably direct route
    assert path[-1] == (800, 800), "last waypoint should be destination"

    # --- Test 2: Path crossing water uses a bridge ---
    path = terrain.find_path(500, 600, 500, 1800)
    assert len(path) > 1, "cross-water path should have multiple waypoints"
    assert path[-1] == (500, 1800), "last waypoint should be destination"

    # --- Test 3: Path from water-adjacent start finds bridge ---
    path = terrain.find_path(1000, 1200, 1000, 1800)
    assert len(path) > 0, "should find a path"
    assert path[-1] == (1000, 1800), "should reach destination"

    # --- Test 4: Path within same side is reasonable ---
    path = terrain.find_path(300, 300, 2500, 800)
    assert len(path) >= 1, "should have at least the destination"
    assert path[-1] == (2500, 800), "should reach destination"

    # --- Test 5: Path cache works ---
    path1 = terrain.find_path(600, 400, 600, 2000)
    path2 = terrain.find_path(600, 400, 600, 2000)
    assert path1 == path2, "cached path should be identical"

    # --- Test 6: Map boundary handling ---
    path = terrain.find_path(10, 10, 3590, 2390)
    assert len(path) > 0, "should find path across full map"

    # --- Test 7: Vertical river crossing ---
    terrain = server.Terrain(
        [{"x1": 1800, "y1": 0, "x2": 1800, "y2": 2400, "width": 90}],
        [{"x": 1800, "y": 600, "w": 130, "h": 120},
         {"x": 1800, "y": 1200, "w": 130, "h": 120},
         {"x": 1800, "y": 1800, "w": 130, "h": 120}],
        3600, 2400)

    path = terrain.find_path(500, 600, 3000, 600)
    assert len(path) > 1, "cross-vertical-river should use bridge"
    assert path[-1] == (3000, 600), "should reach destination"

    path = terrain.find_path(500, 1200, 3000, 1200)
    assert len(path) > 1, "cross-vertical-river at bridge y should use bridge"

    # --- Test 8: No path needed for bridge-aligned crossing ---
    path = terrain.find_path(1800, 300, 1800, 2000)
    assert len(path) >= 1, "should find path along bridge line"

    # --- Test 9: move_toward uses A* path ---
    terrain = server.Terrain(
        [{"x1": 0, "y1": 1200, "x2": 3600, "y2": 1200, "width": 100}],
        [{"x": 1800, "y": 1200, "w": 150, "h": 140}],
        3600, 2400)

    unit = server.make_unit("rifle", "test_owner", 500, 500)
    unit["destX"] = 500
    unit["destY"] = 1900
    unit["order"] = "move"
    unit["_path"] = None
    unit["_pathDest"] = None

    # Call move_toward once - it should compute a path
    arrived = server.move_toward(terrain, unit, 500, 1900, 92.0, 0.05)
    assert not arrived, "should not arrive immediately from so far"
    assert unit.get("_path") is not None, "should have computed a path"
    # Unit should have moved toward the first waypoint
    assert abs(unit["y"] - 500) > 1, "unit should have moved"

    # --- Test 10: Performance - full path finding within budget ---
    import time
    map_def = server.MAPS["gold_crater_small"]
    terrain = server.Terrain(
        map_def["rivers"], map_def["bridges"],
        map_def["width"], map_def["height"],
        map_def["mountains"], map_def["roads"])

    t0 = time.time()
    path = terrain.find_path(3200, 750, 4640, 5182)
    elapsed = (time.time() - t0) * 1000
    assert len(path) > 1, "should find path across large map"
    assert elapsed < 200, "pathfinding should complete in under 200ms"
    print("  Full-map pathfinding time: %.1f ms, path length: %d" % (elapsed, len(path)))

    # Cached path should be instant
    t0 = time.time()
    path2 = terrain.find_path(3200, 750, 4640, 5182)
    elapsed2 = (time.time() - t0) * 1000
    assert path == path2, "cached path should be identical"
    assert elapsed2 < 3, "cached lookup should be under 3ms"
    print("  Cached pathfinding time: %.1f ms" % elapsed2)

    # Multiple unique paths within budget
    t0 = time.time()
    paths = []
    start_positions = [
        (3200, 750), (5530, 2443), (4640, 5182), (1760, 5182), (870, 2443),
        (3200, 1200), (5000, 2200), (4200, 4800), (2200, 4800), (1200, 2200),
    ]
    for sx, sy in start_positions:
        p = terrain.find_path(sx, sy, 3200, 2740)
        paths.append(p)
    total_elapsed = (time.time() - t0) * 1000
    assert total_elapsed < 500, "10 unique paths should complete under 500ms"
    print("  10 unique paths time: %.1f ms" % total_elapsed)

    # --- Test 11: cache keeps each command's exact endpoint ---
    cache_terrain = server.Terrain(
        [], [], 1200, 800,
        [{"x": 600, "y": 400, "r": 180}], [])
    first = cache_terrain.find_path(100, 300, 1100, 300)
    second = cache_terrain.find_path(110, 310, 1110, 310)
    assert first[-1] == (1100, 300)
    assert second[-1] == (1110, 310), \
        "same-cell cache reuse must not inherit the previous exact endpoint"

    # --- Test 12: blocked click projects toward the issuing unit ---
    projected = cache_terrain.nearest_open_point(600, 400, 100, 400, 8)
    assert projected[0] < 600, projected
    assert not cache_terrain.blocked(projected[0], projected[1], 8)

    # --- Test 13: every live-map mountain click finishes at a safe endpoint ---
    checked = 0
    for map_id, map_def in server.MAPS.items():
        live = server.terrain_for_map(map_def)
        sx, sy = map_def["spawnPoints"][0]
        for mountain in map_def.get("mountains", []):
            unit = server.make_unit("rifle", "path-owner", sx, sy)
            game = {
                "units": [unit],
                "map": {"width": map_def["width"], "height": map_def["height"]},
                "terrainCtx": live,
            }
            server.issue_move(
                game, "path-owner", {unit["id"]},
                mountain["x"], mountain["y"])
            assert not live.blocked(unit["destX"], unit["destY"], 8), \
                "%s projected a minimap click into terrain" % map_id
            arrived = False
            for _ in range(900):
                arrived = server.move_toward(
                    live, unit, unit["destX"], unit["destY"], 300.0, 0.05)
                if arrived:
                    break
            assert arrived, "%s failed to finish a mountain-click route" % map_id
            end_x, end_y = unit["_pathEnd"]
            assert math.hypot(unit["x"] - end_x, unit["y"] - end_y) <= 10
            checked += 1
    print("  Mountain-click routes completed: %d" % checked)

    print("pathfinding tests ok: 13 tests passed")


if __name__ == "__main__":
    main()
