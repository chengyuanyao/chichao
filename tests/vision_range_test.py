#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Weapon range can extend sight, but must never shrink base/scout vision."""

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
    extended = []
    preserved = []
    utility = []
    for kind, definition in server.UNIT_TYPES.items():
        base_sight = float(definition["_baseSight"])
        attack_range = float(definition.get("range", 0.0) or 0.0)
        if attack_range > 0.0:
            armed.append(kind)
            expected = round(max(base_sight, attack_range * 1.10), 3)
            assert definition["sight"] == expected, (
                kind, definition["sight"], expected)
            assert server.unit_sight_radius(definition) == expected
            assert definition["sight"] > attack_range
            assert definition["sight"] >= base_sight
            if attack_range * 1.10 > base_sight:
                extended.append(kind)
            else:
                preserved.append(kind)
        else:
            utility.append(kind)
            assert definition["sight"] == base_sight
            assert server.unit_sight_radius(definition) == definition["sight"]

    assert armed, "catalog needs combat units"
    assert set(utility) == {"harvester", "mharvester", "mcv", "mmcv"}
    # Melee, scouts and contact detonators retain their deliberately generous
    # awareness instead of collapsing to 22-34 world units.
    assert server.UNIT_TYPES["dog"]["sight"] == 400.0
    assert server.UNIT_TYPES["panther"]["sight"] == 520.0
    assert server.UNIT_TYPES["bomb_truck"]["sight"] == 350.0
    assert server.UNIT_TYPES["hexling"]["sight"] == 350.0

    # These siege weapons had less base sight than range and must be extended.
    assert server.UNIT_TYPES["artillery"]["sight"] == 374.0
    assert server.UNIT_TYPES["v3"]["sight"] == 550.0
    assert server.UNIT_TYPES["comet"]["sight"] == 572.0
    assert server.UNIT_TYPES["colossus"]["sight"] == 374.0
    assert {"artillery", "v3", "comet", "colossus"}.issubset(extended)
    assert {"dog", "panther", "bomb_truck", "hexling"}.issubset(preserved)

    dog_sight = server.unit_sight_radius(server.UNIT_TYPES["dog"])
    dog_field = server.VisionField([(0.0, 0.0, dog_sight)])
    assert dog_field.visible(350.0, 0.0)
    assert dog_field.visible(dog_sight, 0.0)
    assert not dog_field.visible(dog_sight + 0.01, 0.0)

    # Server-side fog math uses the derived radius exactly.
    artillery = server.UNIT_TYPES["artillery"]
    artillery_sight = server.unit_sight_radius(artillery)
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

    print("vision range ok: %d extended, %d preserve base, %d utility" %
          (len(extended), len(preserved), len(utility)))


if __name__ == "__main__":
    main()
