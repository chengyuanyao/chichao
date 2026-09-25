#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""原始部落 P0：阵营装备、血祭坛门槛、驯兽师招降中立、生产建筑。"""

from __future__ import print_function

import os
import random
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import server


def make_room(tag, tribe_a=True, neutrals=True):
    a = server.create_human("A", server.COLORS[0])
    b = server.create_human("B", server.COLORS[1])
    if tribe_a:
        a["faction"] = "tribe"
    room = {
        "id": tag, "name": "tribe test", "status": "lobby",
        "hostId": a["id"],
        "players": {a["id"]: a, b["id"]: b},
        "chat": [], "game": None, "createdAt": time.time(),
        "selectedMap": "iron_river_duel",
        "neutrals": neutrals,
    }
    server.start_game(room)
    game = room["game"]
    game["terrainCtx"] = server.FLAT_TERRAIN
    game["victoryClock"] = 999.0
    return room, a, b


def isolate_tame_scene(game, tamer, target):
    """清掉随机矿区守军/炮塔，避免它们秒杀脆弱驯兽师。"""
    game["units"] = [
        unit for unit in game["units"]
        if unit["owner"] != server.NEUTRAL_OWNER
    ]
    game["structures"] = [
        structure for structure in game["structures"]
        if structure["owner"] != server.NEUTRAL_OWNER
    ]
    game["neutralCamps"] = []
    game["projectiles"] = []
    for unit in game["units"]:
        if unit["id"] not in (tamer["id"], target["id"]):
            unit["order"] = "hold"
            unit["targetId"] = None
            unit["destX"] = None
            unit["destY"] = None
    game["units"].append(tamer)
    game["units"].append(target)


def give(game, pid, kind):
    structure = server.make_structure(kind, pid, 900, 900, True)
    game["structures"].append(structure)
    return structure


def main():
    random.seed(20260924)
    print("=== Test 1: 部落装备与角色 ===")
    loadout = server.faction_loadout("tribe")
    assert loadout["hq"] == "thq"
    assert loadout["power"] == "tpower"
    assert loadout["refinery"] == "trefinery"
    assert loadout["harvester"] == "tharvester"
    assert loadout["mcv"] == "tmcv"
    assert loadout["infantry"] == "spear"
    assert loadout["armor"] == "wolf"
    buildings = server.faction_buildings("tribe")
    assert buildings["factory"] == "tpen"
    assert buildings["barracks"] == "tcamp"
    assert buildings["repair"] == "taltar"
    assert buildings["defense"] == "tspiketower"
    assert buildings["defense_long"] == "ttoxtower"
    assert buildings["trap"] == "ttrap"
    assert buildings["pit"] == "tpit"
    assert server.structure_role("thq") == "hq"
    assert server.structure_role("tpower") == "power"
    assert server.structure_role("trefinery") == "refinery"
    assert server.structure_role("tcamp") == "barracks"
    assert server.structure_role("tpen") == "factory"
    assert server.structure_role("taltar") == "repair"
    assert server.unit_role("tharvester") == "harvester"
    assert server.unit_role("tmcv") == "mcv"
    for kind in ("thq", "tpower", "trefinery", "tcamp", "tpen", "taltar",
                 "tspiketower", "ttoxtower", "ttrap", "tpit"):
        assert kind in server.TRIBE_STRUCTURES
        assert server.STRUCTURE_TYPES[kind]["faction"] == "tribe"
    for kind in ("tharvester", "tmcv", "spear", "tamer", "wolf", "spider",
                 "scorpion", "mammoth"):
        assert kind in server.TRIBE_UNITS
        assert server.UNIT_TYPES[kind]["faction"] == "tribe"
    assert server.UNIT_TYPES["tmcv"]["deploysInto"] == "thq"
    assert server.STRUCTURE_TYPES["thq"]["packsInto"] == "tmcv"
    assert server.UNIT_TYPES["tharvester"]["capacity"] == server.UNIT_TYPES["harvester"]["capacity"]
    assert server.UNIT_TYPES["tharvester"]["harvestRate"] == server.UNIT_TYPES["harvester"]["harvestRate"]
    assert server.UNIT_TYPES["wolf"]["armor"] == "beast"
    assert "wolf" not in server.SUICIDE_KINDS
    assert "mammoth" not in server.SUICIDE_KINDS
    assert server.bot_suicide_kind("tribe") is None
    catalog = server.public_catalog()
    assert catalog["units"]["tamer"]["canTame"] is True
    assert catalog["units"]["wolf"]["canTame"] is False
    assert catalog["buildings"]["taltar"]["requires"] == ["tpen", "tpower"]
    room, a, b = make_room("TRIBE01")
    game = room["game"]

    def owned(pid, lst):
        return sorted(e["kind"] for e in lst if e["owner"] == pid)

    assert owned(a["id"], game["structures"]) == ["thq", "tpower", "trefinery"]
    a_units = owned(a["id"], game["units"])
    assert a_units.count("spear") == 3 and "wolf" in a_units and "tharvester" in a_units, a_units
    print("  出生配置 / role / 目录: PASS")

    print("\n=== Test 2: 血祭坛需要围栏+图腾 ===")
    room, a, b = make_room("TRIBE02")
    game = room["game"]
    a["cash"] = 99999
    try:
        server.queue_structure(room, a["id"], "taltar")
        raise AssertionError("缺围栏时不该能排血祭坛")
    except ValueError as exc:
        assert "前置建筑" in str(exc), str(exc)
    give(game, a["id"], "tpen")
    server.queue_structure(room, a["id"], "taltar")
    assert a["buildQueue"] and a["buildQueue"][0]["kind"] == "taltar"
    print("  taltar requires tpen+tpower: PASS")

    print("\n=== Test 3: 驯兽师不能招降敌方玩家单位 ===")
    room, a, b = make_room("TRIBE03")
    game = room["game"]
    a["cash"] = 99999
    tamer = server.make_unit("tamer", a["id"], 800, 800)
    game["units"].append(tamer)
    enemy = server.make_unit("rifle", b["id"], 860, 800)
    game["units"].append(enemy)
    try:
        server.issue_tame(room, a["id"], {tamer["id"]}, enemy["id"])
        raise AssertionError("不该能驯化敌方玩家单位")
    except ValueError as exc:
        assert "中立" in str(exc), str(exc)
    assert enemy["owner"] == b["id"]
    print("  敌方玩家单位不可驯: PASS")

    print("\n=== Test 4: 关闭中立时驯化失败，围栏战狼仍可训练 ===")
    room, a, b = make_room("TRIBE04", neutrals=False)
    game = room["game"]
    a["cash"] = 99999
    tamer = server.make_unit("tamer", a["id"], 800, 800)
    game["units"].append(tamer)
    stray = server.make_unit("rifle", server.NEUTRAL_OWNER, 860, 800)
    game["units"].append(stray)
    try:
        server.issue_tame(room, a["id"], {tamer["id"]}, stray["id"])
        raise AssertionError("关闭中立后不该能驯化")
    except ValueError as exc:
        assert "中立" in str(exc), str(exc)
    give(game, a["id"], "tpen")
    server.queue_unit(room, a["id"], "wolf")
    queued = [item["kind"] for s in game["structures"] if s["owner"] == a["id"]
              for item in s["queue"]]
    assert "wolf" in queued, queued
    print("  neutrals off 拒绝驯化 / 战狼可训: PASS")

    print("\n=== Test 5: 生产建筑与阵营门槛 ===")
    room, a, b = make_room("TRIBE05")
    game = room["game"]
    a["cash"] = b["cash"] = 99999
    give(game, a["id"], "tcamp")
    give(game, a["id"], "tpen")
    server.queue_unit(room, a["id"], "spear")
    server.queue_unit(room, a["id"], "tamer")
    server.queue_unit(room, a["id"], "tharvester")
    server.queue_unit(room, a["id"], "wolf")
    produced = [item["kind"] for s in game["structures"] if s["owner"] == a["id"]
                for item in s["queue"]]
    assert produced.count("spear") == 1
    assert produced.count("tamer") == 1
    assert produced.count("tharvester") == 1
    assert produced.count("wolf") == 1
    assert server.UNIT_TYPES["spear"]["producer"] == "tcamp"
    assert server.UNIT_TYPES["tamer"]["producer"] == "tcamp"
    assert server.UNIT_TYPES["wolf"]["producer"] == "tpen"
    assert server.UNIT_TYPES["tharvester"]["producer"] == "tpen"
    assert server.UNIT_TYPES["spider"]["producer"] == "tpen"
    assert server.UNIT_TYPES["spider"]["requires"] == ["taltar"]
    assert server.UNIT_TYPES["scorpion"]["producer"] == "tpen"
    assert server.UNIT_TYPES["scorpion"]["requires"] == ["taltar"]
    try:
        server.queue_unit(room, a["id"], "rifle")
        raise AssertionError("部落不该能产突击兵")
    except ValueError as exc:
        assert "阵营" in str(exc), str(exc)
    try:
        server.queue_structure(room, a["id"], "barracks")
        raise AssertionError("部落不该能建步兵营")
    except ValueError as exc:
        assert "阵营" in str(exc), str(exc)
    give(game, b["id"], "barracks")
    try:
        server.queue_unit(room, b["id"], "spear")
        raise AssertionError("科技不该能产骨矛")
    except ValueError as exc:
        assert "阵营" in str(exc), str(exc)
    print("  生产建筑 / 双向门槛: PASS")

    print("\n=== Test 6: 驯兽师招降中立单位 ===")
    room, a, b = make_room("TRIBE06")
    game = room["game"]
    a["cash"] = 99999
    tamer = server.make_unit("tamer", a["id"], 220, 220)
    guard = server.make_unit("rifle", server.NEUTRAL_OWNER, 250, 220)
    guard["hp"] = 77.0
    isolate_tame_scene(game, tamer, guard)
    cash0 = a["cash"]
    server.handle_game_command(room, a, {
        "command": "tame", "unitIds": [tamer["id"]], "targetId": guard["id"],
    })
    assert tamer["order"] == "tame"
    assert tamer["tameTargetId"] == guard["id"]
    for _ in range(120):
        server.tick_game(room, 0.05)
        if guard["owner"] == a["id"]:
            break
    assert guard["owner"] == a["id"], (
        "owner=%s tamer_hp=%s tamer_order=%s progress=%s guard_hp=%s"
        % (guard["owner"], tamer.get("hp"), tamer.get("order"),
           tamer.get("tameProgress"), guard.get("hp")))
    assert guard["kind"] == "rifle"
    assert abs(guard["hp"] - 77.0) < 0.2
    assert a["cash"] < cash0
    assert not guard.get("neutralCampId")
    print("  招降成功且保留 HP/kind: PASS")

    print("\n=== Test 7: 打断驯化会使中立敌对 ===")
    room, a, b = make_room("TRIBE07")
    game = room["game"]
    a["cash"] = 99999
    tamer = server.make_unit("tamer", a["id"], 800, 800)
    game["units"].append(tamer)
    guard = server.make_unit("rocket", server.NEUTRAL_OWNER, 820, 800)
    game["units"].append(guard)
    server.issue_tame(room, a["id"], {tamer["id"]}, guard["id"])
    server.issue_move(game, a["id"], {tamer["id"]}, 400, 400)
    assert tamer["order"] == "move"
    assert guard["owner"] == server.NEUTRAL_OWNER
    assert guard.get("targetId") == tamer["id"]
    print("  打断后中立敌对驯兽师: PASS")

    print("\n=== Test 8: 大厅可选 tribe ===")
    host = server.create_human("房主", server.COLORS[0])
    guest = server.create_human("访客", server.COLORS[1])
    lobby = {
        "id": "TRIBE08", "name": "lobby", "status": "lobby",
        "hostId": host["id"],
        "players": {host["id"]: host, guest["id"]: guest},
        "chat": [], "game": None, "createdAt": time.time(),
    }
    assert "tribe" in server.VALID_FACTIONS
    server.set_faction(lobby, guest, "tribe")
    assert guest["faction"] == "tribe"
    try:
        server.set_faction(lobby, guest, "orcs")
        raise AssertionError("未知阵营应被拒绝")
    except ValueError as exc:
        assert "阵营" in str(exc)
    print("  set_faction tribe: PASS")

    print("\n=== 原始部落 P0 测试全部通过 ===")


if __name__ == "__main__":
    main()
