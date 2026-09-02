#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Live-map dry-land rules plus legacy terrain primitive compatibility tests."""

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


def make_room():
    alpha = server.create_human("河川甲", server.COLORS[0])
    beta = server.create_human("河川乙", server.COLORS[1])
    room = {
        "id": "RIV001",
        "name": "河流测试",
        "status": "lobby",
        "hostId": alpha["id"],
        "players": {alpha["id"]: alpha, beta["id"]: beta},
        "chat": [],
        "game": None,
        "createdAt": time.time(),
        "selectedMap": "narrow_standoff",
    }
    return room


def main():
    random.seed(20260719)

    # --- Test 1: only 赤金陨坑·紧凑 uses live rivers / bridges ---
    for map_id in sorted(server.MAPS):
        map_data = server.MAPS[map_id]
        if map_id == "gold_crater_small":
            assert map_data.get("rivers"), "%s should use rim rivers" % map_id
            assert map_data.get("bridges"), "%s should use rim bridges" % map_id
        else:
            assert not map_data.get("rivers"), "%s should not have rivers" % map_id
            assert not map_data.get("bridges"), "%s should not have bridges" % map_id
        assert map_data.get("mountains"), "%s should use mountain blockers" % map_id

    # --- Test 2: started games publish mountain-only blockers ---
    room = make_room()
    server.start_game(room)
    game = room["game"]
    terrain = game["terrain"]
    assert not terrain["rivers"], "game terrain should not have rivers"
    assert not terrain["bridges"], "game terrain should not have bridges"
    assert terrain["mountains"], "game terrain should publish mountains"

    # --- Test 3: point_in_water detects water correctly ---
    # Force a known river config
    water = server.Terrain(
        [{"x1": 0, "y1": 2000, "x2": 3600, "y2": 2000, "width": 100}],
        [{"x": 1800, "y": 2000, "w": 120, "h": 140}],
        7200, 4400)

    assert water.point_in_water(1000, 2000), "center of river should be water"
    assert water.point_in_water(100, 2005), "near river center should be water"
    assert not water.point_in_water(100, 2500), "far from river should not be water"
    assert not water.point_in_water(100, 1500), "far from other side should not be water"
    
    # --- Test 4: point is NOT water when inside bridge ---
    assert not water.point_in_water(1800, 2000), "bridge center should not be water"
    assert not water.point_in_water(1800, 2050), "near bridge edge should not be water"
    assert not water.point_in_water(1850, 2000), "within bridge width should not be water"
    
    # But outside the bridge bounds, same y should be water
    assert water.point_in_water(600, 2000), "outside bridge should be water"

    # --- Test 5: segment_blocked_by_water ---
    # Path that crosses the river should be blocked
    assert water.segment_blocked(1000, 1500, 1000, 2500), \
        "path crossing river should be blocked"
    # Path that goes through the bridge should NOT be blocked
    assert not water.segment_blocked(1800, 1500, 1800, 2500), \
        "path through bridge should not be blocked"
    # Path fully on one side should not be blocked
    assert not water.segment_blocked(100, 1500, 500, 1600), \
        "path on one side should not be blocked"
    # Path fully on other side should not be blocked
    assert not water.segment_blocked(100, 2200, 500, 2400), \
        "path on other side should not be blocked"

    # --- Test 6: nearest_bridge_waypoint ---
    # A unit on the north side wanting to cross south via a path NOT going through a bridge
    waypoint = water.nearest_bridge_waypoint(1000, 1500, 1000, 2500)
    # Path should find the nearest bridge at (1800, 2000)
    assert waypoint is not None, "should find a bridge waypoint for blocked path"
    assert abs(waypoint[0] - 1800) < 50, "waypoint x should be near bridge"
    assert abs(waypoint[1] - 2000) < 50, "waypoint y should be near bridge"

    # A path that naturally crosses through a bridge should not need a waypoint
    assert water.nearest_bridge_waypoint(1800, 1500, 1800, 2500) is None, \
        "path through bridge should not need waypoint"

    # --- Test 7: position_clear rejects water positions ---
    room_game = room["game"]
    room_game["terrainCtx"] = water
    assert not server.position_clear(room_game, 500, 2000, 30), \
        "water position should not be clear for building"

    # --- Test 8: move_toward avoids water ---
    
    unit = server.make_unit("rifle", "test", 1800, 1550)
    unit["dir"] = 0
    unit["destX"] = 1800
    unit["destY"] = 2550
    
    # Tick the unit for a short time
    room_game = room["game"]
    room_game["units"] = [unit]
    entity_index, combat_spatial = server.build_combat_indexes(room_game)
    server.tick_units(room, 0.05, entity_index, combat_spatial)
    
    # Unit should be moving toward the bridge (not stuck)
    assert abs(unit["y"] - 1550) < 20, "unit should be near starting y (approaching bridge)"
    
    # Move unit to bridge center and try to cross
    unit["x"] = 1800
    unit["y"] = 2000
    room_game["units"] = [unit]
    entity_index, combat_spatial = server.build_combat_indexes(room_game)
    server.tick_units(room, 0.05, entity_index, combat_spatial)
    
    # Unit should now move toward destination on the other side
    # It should be south of 2000 within a few ticks
    for _ in range(60):
        entity_index, combat_spatial = server.build_combat_indexes(room_game)
        server.tick_units(room, 0.05, entity_index, combat_spatial)
    assert unit["y"] > 2000, "unit should cross river via bridge"

    # --- Test 9: vertical river works with segment_blocked ---
    water = server.Terrain(
        [{"x1": 1800, "y1": 0, "x2": 1800, "y2": 2400, "width": 90}],
        [{"x": 1800, "y": 1200, "w": 130, "h": 120}],
        3600, 2400)

    assert water.point_in_water(1800, 800), "vertical river center should be water"
    assert not water.point_in_water(500, 800), "west of vertical river should be dry"
    assert not water.point_in_water(3000, 800), "east of vertical river should be dry"
    
    # Path crossing vertical river should be blocked
    assert water.segment_blocked(1000, 800, 3000, 800), \
        "east-west path crossing vertical river should be blocked"
    # Path through bridge should not be blocked
    assert not water.segment_blocked(1000, 1200, 3000, 1200), \
        "path through vertical river bridge should not be blocked"
    # Path parallel to vertical river should NOT be blocked (stays on one side)
    assert not water.segment_blocked(500, 200, 500, 2000), \
        "path parallel to vertical river should not be blocked"

    # --- Test 10: horizontal river placement check ---
    room_game["terrainCtx"] = server.Terrain(
        [{"x1": 0, "y1": 2000, "x2": 3600, "y2": 2000, "width": 120}],
        [{"x": 1800, "y": 2000, "w": 150, "h": 150}],
        3600, 3600)
    
    assert not server.position_clear(room_game, 500, 2000, 30), \
        "water position should not be clear for building"
    assert server.position_clear(room_game, 500, 2400, 30), \
        "dry position should be clear for building"

    # --- Test 11: 赤金陨坑·紧凑 live rivers / bridges ---
    crater_rim_checks = {
        "gold_crater_small": ((3476, 5382, 2924, 5382), (3341, 5880, 3059, 5880)),
    }
    for map_id, (blocked_way, bridge_way) in crater_rim_checks.items():
        crater = server.MAPS[map_id]
        live = server.terrain_for_map(crater)
        assert live.rivers and live.bridges
        for bridge in crater["bridges"]:
            assert not live.point_in_water(bridge["x"], bridge["y"]), map_id
            assert not live.blocked(bridge["x"], bridge["y"]), map_id
            assert live.cell_open(bridge["x"], bridge["y"]), map_id
        # 南缘抄近道必须被河拦住，从桥上则能过。
        assert live.segment_blocked(*blocked_way), map_id
        assert not live.segment_blocked(*bridge_way), map_id

    print("water tests ok: 11 tests passed")


if __name__ == "__main__":
    main()
