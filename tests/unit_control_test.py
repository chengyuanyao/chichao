#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Large units must spawn on valid terrain and obey a move immediately."""

from __future__ import print_function

import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import server


def assert_spawn_and_move(kind, producer_kind):
    terrain = server.Terrain(
        [], [], 1200, 800,
        [{"x": 600, "y": 400, "r": 180}], [])
    producer = server.make_structure(producer_kind, "owner", 430, 400, True)
    game = {
        "units": [],
        "structures": [producer],
        "map": {"width": 1200, "height": 800},
        "terrainCtx": terrain,
    }

    # The preferred east-facing exit points straight into the mountain.  The
    # production search must find another angle that fits the whole footprint.
    x, y = server.find_unit_spawn_point(
        game, producer, kind, preferred_angle=0.0)
    clearance = max(8.0, server.UNIT_TYPES[kind]["size"] * 0.55)
    assert not terrain.blocked(x, y, clearance), \
        "%s spawned partly inside blocked terrain at %s" % (kind, (x, y))

    # Also rescue units created by an old save/edge case at an invalid point.
    unit = server.make_unit(kind, "owner", 600, 400)
    game["units"] = [unit]
    before = (unit["x"], unit["y"])
    server.issue_move(game, "owner", {unit["id"]}, 1080, 400)
    assert unit["order"] == "move"
    assert not terrain.blocked(unit["x"], unit["y"], unit["size"] * 0.5), \
        "%s was not pushed out of blocked terrain" % kind
    assert (unit["x"], unit["y"]) != before

    command_start = (unit["x"], unit["y"])
    for _ in range(20):
        server.move_toward(
            terrain, unit, unit["destX"], unit["destY"],
            server.UNIT_TYPES[kind]["speed"], 0.05)
    progress = math.hypot(
        unit["x"] - command_start[0], unit["y"] - command_start[1])
    assert progress > 5.0, "%s accepted move but did not travel: %.2f" % (kind, progress)
    assert unit.get("_pathUnavailable") is not True


def main():
    assert_spawn_and_move("tank", "factory")
    print("  Tank blocked-edge spawn/control: PASS")
    assert_spawn_and_move("dragon", "mcircle")
    print("  Dragon blocked-edge spawn/control: PASS")
    print("large-unit control tests ok: 2 tests passed")


if __name__ == "__main__":
    main()
