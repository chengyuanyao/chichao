#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Unit sight must stay exactly 10% beyond authoritative attack range."""

from __future__ import print_function

import os
import random
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import server


def main():
    assert server.UNIT_SIGHT_RANGE_MULTIPLIER == 1.10

    armed = []
    utility = []
    for kind, definition in server.UNIT_TYPES.items():
        attack_range = float(definition.get("range", 0.0) or 0.0)
        if attack_range > 0.0:
            armed.append(kind)
            expected = round(attack_range * 1.10, 3)
            assert definition["sight"] == expected, (
                kind, definition["sight"], expected)
            assert server.unit_sight_radius(definition) == expected
            assert definition["sight"] > attack_range
        else:
            utility.append(kind)
            assert definition["sight"] > 0.0, "%s must not become blind" % kind
            assert server.unit_sight_radius(definition) == definition["sight"]

    assert armed, "catalog needs combat units"
    assert set(utility) == {"harvester", "mharvester", "mcv", "mmcv"}
    # Contact detonation range is still an attack range, even though its direct
    # damage field is zero; both suicide counterparts must follow the same rule.
    assert server.UNIT_TYPES["bomb_truck"]["sight"] == 24.2
    assert server.UNIT_TYPES["hexling"]["sight"] == 24.2

    # Server-side fog math uses the derived radius exactly.
    artillery = server.UNIT_TYPES["artillery"]
    artillery_sight = round(artillery["range"] * 1.10, 3)
    field = server.VisionField([(0.0, 0.0, artillery_sight)])
    assert field.visible(artillery_sight, 0.0)
    assert not field.visible(artillery_sight + 0.01, 0.0)

    # The full snapshot is the client's only unit-vision table. It must carry
    # the same values so rendered fog cannot disagree with authoritative fog.
    random.seed(20260826)
    alpha = server.create_human("视野甲", server.COLORS[0])
    beta = server.create_human("视野乙", server.COLORS[1])
    room = {
        "id": "SIGHT1", "name": "视野比例测试", "status": "lobby",
        "hostId": alpha["id"],
        "players": {alpha["id"]: alpha, beta["id"]: beta},
        "chat": [], "game": None, "createdAt": time.time(),
    }
    server.start_game(room)
    client_sight = server.public_game(
        room["game"], alpha["id"], full=True)["sight"]["units"]
    for kind, definition in server.UNIT_TYPES.items():
        assert client_sight[kind] == server.unit_sight_radius(definition), kind

    print("vision range ok: %d combat units use range x1.10; utility units keep sight" %
          len(armed))


if __name__ == "__main__":
    main()
