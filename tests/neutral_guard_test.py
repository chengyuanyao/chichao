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


def make_room(map_id="narrow_standoff", seed=7301, neutrals=None):
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
    if neutrals is not None:
        room["neutrals"] = neutrals
    server.start_game(room)
    return room, alpha


def camp_entities(game, camp):
    ids = set(camp["guardIds"])
    return [entity for entity in game["units"] + game["structures"]
            if entity["id"] in ids]


def living_neutrals(game):
    return [entity for entity in game["units"] + game["structures"]
            if entity.get("owner") == server.NEUTRAL_OWNER and entity["hp"] > 0]


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
    if not map_def.get("neutralOreGuards", True):
        return 0
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


def check_default_on_spawns_camps():
    room, alpha = make_room()
    game = room["game"]
    assert game.get("neutrals") is True
    lobby = server.public_room(room, viewer_id=alpha["id"])
    assert lobby["neutrals"] is True
    view = server.public_game(game, alpha["id"], full=True)
    assert view["neutrals"] is True
    check_spawn_and_lock(room, alpha)
    check_leash(room)


def check_flag_off_no_guards():
    room, alpha = make_room(neutrals=False)
    game = room["game"]
    assert game.get("neutrals") is False
    public_ore = [resource for resource in game["resources"] if resource.get("public")]
    assert len(public_ore) == 4, len(public_ore)
    assert game.get("neutralCamps") == []
    assert living_neutrals(game) == []
    assert all(not resource.get("guarded") for resource in public_ore)
    assert all(not resource.get("neutralCampId") for resource in public_ore)

    server.refresh_neutral_camps(game)
    assert game.get("neutralCamps") == []
    assert living_neutrals(game) == []
    assert all(not resource.get("guarded") for resource in public_ore)

    before_units = len(game["units"])
    before_structures = len(game["structures"])
    server.spawn_neutral_ore_camp(game, public_ore[0], random.Random(1))
    assert game.get("neutralCamps") == []
    assert living_neutrals(game) == []
    assert len(game["units"]) == before_units
    assert len(game["structures"]) == before_structures

    harvester = next(unit for unit in game["units"]
                     if unit["owner"] == alpha["id"] and unit["kind"] == "harvester")
    target = public_ore[0]
    for resource in game["resources"]:
        if resource is not target:
            resource["amount"] = 0.0
    harvester["x"], harvester["y"] = target["x"], target["y"]
    harvester["cargo"] = 0.0
    harvester["harvestTarget"] = target["id"]
    harvester["returnTarget"] = None
    harvester["order"] = "guard"
    server.tick_harvester(room, harvester, 0.5)
    assert harvester["cargo"] > 0.0, "关闭中立守卫后公共矿应立即可采"

    crater, _alpha = make_room("gold_crater_small", seed=7501, neutrals=False)
    crater_game = crater["game"]
    crater_public = [resource for resource in crater_game["resources"]
                     if resource.get("public")]
    assert crater_public
    assert crater_game.get("neutralCamps") == []
    assert living_neutrals(crater_game) == []
    assert all(not resource.get("guarded") for resource in crater_public)


def check_lobby_toggle_and_lock():
    host = server.create_human("房主", server.COLORS[0])
    guest = server.create_human("访客", server.COLORS[1])
    lobby_room = {
        "id": "GUARD2", "name": "大厅守卫开关", "status": "lobby",
        "hostId": host["id"],
        "players": {host["id"]: host, guest["id"]: guest},
        "chat": [], "game": None, "createdAt": time.time(),
    }
    assert server.neutrals_enabled(lobby_room) is True
    guest_view = server.public_room(lobby_room, viewer_id=guest["id"])
    assert guest_view["neutrals"] is True
    try:
        server.set_neutrals(lobby_room, guest, False)
        raise AssertionError("访客不该能关中立守卫")
    except ValueError as exc:
        assert "房主" in str(exc)
    server.set_neutrals(lobby_room, host, False)
    assert lobby_room["neutrals"] is False
    guest_view = server.public_room(lobby_room, viewer_id=guest["id"])
    assert guest_view["neutrals"] is False
    server.start_game(lobby_room)
    assert lobby_room["game"]["neutrals"] is False
    playing = server.public_room(lobby_room, viewer_id=guest["id"], full=True)
    assert playing["neutrals"] is False
    assert playing["game"]["neutrals"] is False
    try:
        server.set_neutrals(lobby_room, host, True)
        raise AssertionError("开战后不该还能改")
    except ValueError as exc:
        assert "开始" in str(exc)


def check_lobby_label():
    index = open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                              "public", "index.html"), "r", encoding="utf-8").read()
    assert "中立守卫" in index
    assert "矿区中立单位，可关闭" in index
    assert 'data-mode="neutral_camps"' in index
    assert "neutralCampsToggle" in index
    assert server.NEUTRAL_CAMPS_MODE == "neutral_camps"


def main():
    check_default_on_spawns_camps()
    check_flag_off_no_guards()
    check_lobby_toggle_and_lock()
    check_lobby_label()
    check_all_maps_spawn_camps()
    print("neutral guards ok: public ore stays locked, toggle off skips camps, pulled guards return")


if __name__ == "__main__":
    main()
