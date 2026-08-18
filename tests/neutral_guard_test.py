#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""公共矿中立守军、采矿锁与脱战回防回归测试。"""

from __future__ import print_function

import math
import os
import random
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import server


def make_room(map_id="north_conflict", seed=7301):
    random.seed(seed)
    alpha = server.create_human("守矿甲", server.COLORS[0])
    beta = server.create_human("守矿乙", server.COLORS[1])
    room = {
        "id": "GUARD1", "name": "中立守矿测试", "status": "lobby",
        "hostId": alpha["id"],
        "players": {alpha["id"]: alpha, beta["id"]: beta},
        "chat": [], "game": None, "createdAt": time.time(),
        "selectedMap": map_id,
    }
    server.start_game(room)
    return room, alpha


def camp_entities(game, camp):
    ids = set(camp["guardIds"])
    return [entity for entity in game["units"] + game["structures"]
            if entity["id"] in ids]


def check_spawn_and_lock(room, alpha):
    game = room["game"]
    public_ore = [resource for resource in game["resources"]
                  if resource.get("public")]
    assert len(public_ore) == 4
    assert len(game["neutralCamps"]) == 4
    assert server.NEUTRAL_OWNER not in room["players"]

    for resource in public_ore:
        assert resource["guarded"] is True
        camp = next(c for c in game["neutralCamps"]
                    if c["id"] == resource["neutralCampId"])
        guards = camp_entities(game, camp)
        assert len(guards) >= 1
        assert all(entity["owner"] == server.NEUTRAL_OWNER for entity in guards)
        assert any(entity["id"].startswith("s") for entity in guards), \
            "普通公共矿应至少有一座中立防御建筑"

    snapshot = server.public_game(game, alpha["id"], full=True)
    public_snapshot = [resource for resource in snapshot["resources"]
                       if resource["public"]]
    assert all(resource["guarded"] for resource in public_snapshot)
    assert all(len(item) == 3 for item in snapshot["ore"])

    target = public_ore[0]
    camp = next(c for c in game["neutralCamps"]
                if c["id"] == target["neutralCampId"])
    harvester = next(unit for unit in game["units"]
                     if unit["owner"] == alpha["id"]
                     and unit["kind"] == "harvester")
    for resource in game["resources"]:
        if resource is not target:
            resource["amount"] = 0.0
    harvester["x"], harvester["y"] = target["x"], target["y"]
    harvester["cargo"] = 0.0
    harvester["harvestTarget"] = target["id"]
    harvester["returnTarget"] = None
    harvester["order"] = "guard"

    server.refresh_neutral_camps(game)
    server.tick_harvester(room, harvester, 0.5)
    assert harvester["cargo"] == 0.0, "守军存活时停在矿上也不能采集"

    guards = camp_entities(game, camp)
    guards[0]["hp"] = 0.0
    server.refresh_neutral_camps(game)
    assert target["guarded"] is (len(guards) > 1), \
        "只清掉部分守军不能提前解锁"

    for entity in guards:
        entity["hp"] = 0.0
    server.refresh_neutral_camps(game)
    assert target["guarded"] is False
    server.tick_harvester(room, harvester, 0.5)
    assert harvester["cargo"] > 0.0, "守军全灭后公共矿应立即可采"


def check_leash(room):
    game = room["game"]
    game["terrainCtx"] = server.FLAT_TERRAIN
    camp = game["neutralCamps"][1]
    guard = next(unit for unit in game["units"]
                 if unit.get("neutralCampId") == camp["id"] and unit["hp"] > 0)

    # 选择矿区左右两侧空间更大的一边，把守军和诱饵都放到缰绳外。
    direction = 1.0 if camp["x"] < game["map"]["width"] * 0.5 else -1.0
    guard["x"] = camp["x"] + direction * (server.NEUTRAL_GUARD_LEASH + 90.0)
    guard["y"] = camp["y"]
    intruder = server.make_unit(
        "rifle", next(iter(room["players"])),
        camp["x"] + direction * (server.NEUTRAL_GUARD_LEASH + 150.0),
        camp["y"])
    game["units"].append(intruder)
    guard["targetId"] = intruder["id"]
    guard["order"] = "guard"

    before = math.hypot(guard["x"] - guard["guardPostX"],
                        guard["y"] - guard["guardPostY"])
    entity_index, _spatial = server.build_combat_indexes(game)
    handled = server.tick_neutral_guard(
        game, guard, server.UNIT_TYPES[guard["kind"]], 0.5,
        entity_index, server.FLAT_TERRAIN, 1.0)
    after = math.hypot(guard["x"] - guard["guardPostX"],
                       guard["y"] - guard["guardPostY"])
    assert handled is True
    assert guard["targetId"] is None
    assert guard["order"] == "neutralReturn"
    assert after < before, "守军越过缰绳后应朝原哨位返回"

    for _ in range(400):
        if guard["order"] != "neutralReturn":
            break
        server.tick_neutral_guard(
            game, guard, server.UNIT_TYPES[guard["kind"]], 0.1,
            entity_index, server.FLAT_TERRAIN, 1.0)
    assert guard["order"] == "guard"
    assert math.hypot(guard["x"] - guard["guardPostX"],
                      guard["y"] - guard["guardPostY"]) <= \
        server.NEUTRAL_GUARD_POST_RADIUS


def expected_public_camps(map_def):
    bonus = sum(1 for resource in map_def.get("bonusResources") or ()
                if resource.get("public", True))
    return int(map_def.get("publicOreCount", 4)) + bonus


def check_all_maps_spawn_camps():
    for index, map_id in enumerate(server.MAPS):
        map_def = server.MAPS[map_id]
        room, _alpha = make_room(map_id, 7400 + index)
        game = room["game"]
        assert len(game["neutralCamps"]) == expected_public_camps(map_def), map_id
        for camp in game["neutralCamps"]:
            guards = camp_entities(game, camp)
            assert any(entity["id"].startswith("s") for entity in guards), map_id
            assert any(entity["id"].startswith("u") for entity in guards), map_id
            assert all(entity["owner"] == server.NEUTRAL_OWNER
                       for entity in guards), map_id


def main():
    room, alpha = make_room()
    check_spawn_and_lock(room, alpha)
    check_leash(room)
    check_all_maps_spawn_camps()
    print("neutral guards ok: public ore stays locked and pulled guards return to their posts")


if __name__ == "__main__":
    main()
