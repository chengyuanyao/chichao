#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""原始部落 P1：哨塔、陷阱毒、猛犸、bot。
   1) 目录 / 阵营 / 解锁 / 无自爆
   2) 跨阵营不能建；缺前置拒绝
   3) 棘矛哨塔开火；毒矢高台挂毒
   4) 兽夹上膛后定身+爆发并拆除；建筑不触发
   5) 毒雾坑脉冲只毒敌军单位
   6) 猛犸祭坛门槛、smash 拆建筑
   7) bot defense / defense_long / trap / pit 与后期混编
"""

from __future__ import print_function

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import server


def make_room(tag, tribe_a=True, magic_b=False):
    a = server.create_human("A", server.COLORS[0])
    b = server.create_human("B", server.COLORS[1])
    if tribe_a:
        a["faction"] = "tribe"
    if magic_b:
        b["faction"] = "magic"
    room = {
        "id": tag, "name": "tribe p1 test", "status": "lobby",
        "hostId": a["id"],
        "players": {a["id"]: a, b["id"]: b},
        "chat": [], "game": None, "createdAt": time.time(),
        "selectedMap": "iron_river_duel",
        "neutrals": False,
    }
    server.start_game(room)
    game = room["game"]
    game["terrainCtx"] = server.FLAT_TERRAIN
    game["victoryClock"] = 999.0
    return room, a, b


def give(game, pid, kind, x=900, y=900, active=True):
    structure = server.make_structure(kind, pid, x, y, active)
    game["structures"].append(structure)
    return structure


def isolate(game, *keep):
    keep_ids = set(unit["id"] for unit in keep)
    game["units"] = [unit for unit in keep]
    game["projectiles"] = []
    game["neutralCamps"] = []
    game["structures"] = [
        structure for structure in game["structures"]
        if structure["owner"] != server.NEUTRAL_OWNER
    ]
    for unit in game["units"]:
        assert unit["id"] in keep_ids
        unit["order"] = "hold"
        unit["targetId"] = None
        unit["destX"] = None
        unit["destY"] = None


def expect_error(fragment, callback):
    try:
        callback()
        raise AssertionError("expected ValueError containing %r" % fragment)
    except ValueError as error:
        assert fragment in str(error), (fragment, str(error))


def queued_kinds(game, pid):
    return [item["kind"] for structure in game["structures"]
            if structure["owner"] == pid for item in structure["queue"]]


def silence_defenses(game):
    for structure in game["structures"]:
        if server.structure_role(structure["kind"]) == "defense":
            structure["cooldown"] = 99.0


def main():
    print("=== Test 1: 目录 / 角色 / 无自爆 ===")
    spike = server.STRUCTURE_TYPES["tspiketower"]
    tox = server.STRUCTURE_TYPES["ttoxtower"]
    trap = server.STRUCTURE_TYPES["ttrap"]
    pit = server.STRUCTURE_TYPES["tpit"]
    mammoth = server.UNIT_TYPES["mammoth"]
    assert spike["name"] == "棘矛哨塔"
    assert spike["faction"] == "tribe"
    assert spike["role"] == "defense"
    assert 650 <= spike["cost"] <= 800
    assert 700 <= spike["hp"] <= 900
    assert 180 <= spike["range"] <= 210
    assert spike["requires"] == ["tcamp", "tpower"]
    assert spike["projectile"] == "spike"
    assert tox["name"] == "毒矢高台"
    assert tox["role"] == "defense"
    assert 900 <= tox["cost"] <= 1100
    assert 800 <= tox["hp"] <= 1000
    assert 260 <= tox["range"] <= 300
    assert tox["requires"] == ["taltar", "tpower"]
    assert tox["dot"] == {"dps": 12.0, "duration": 3.2, "damageType": "venom"}
    assert trap["name"] == "兽夹陷阱"
    assert trap["role"] == "trap"
    assert 250 <= trap["cost"] <= 400
    assert trap["requires"] == ["tcamp"]
    assert trap["slow"] == {"mult": 0.0, "duration": 2.0}
    assert trap["trapExpire"] is True
    assert pit["name"] == "毒雾坑"
    assert pit["role"] == "trap"
    assert 500 <= pit["cost"] <= 700
    assert pit["requires"] == ["taltar"]
    assert pit["dot"]["damageType"] == "venom"
    assert mammoth["name"] == "猛犸战象"
    assert mammoth["producer"] == "tpen"
    assert mammoth["requires"] == ["taltar"]
    assert 1400 <= mammoth["cost"] <= 1600
    assert 1100 <= mammoth["hp"] <= 1400
    assert 70 <= mammoth["speed"] <= 85
    assert 70 <= mammoth["damage"] <= 90
    assert 40 <= mammoth["range"] <= 60
    assert mammoth["armor"] == "beast"
    assert mammoth["damageType"] == "smash"
    assert mammoth["build"] > server.UNIT_TYPES["wolf"]["build"]
    assert "mammoth" not in server.VEHICLE_KINDS
    assert "mammoth" not in server.SUICIDE_KINDS
    assert "tspiketower" not in server.SUICIDE_KINDS
    assert server.bot_suicide_kind("tribe") is None
    assert server.structure_queue_key("tspiketower") == "defenseQueue"
    assert server.structure_queue_key("ttoxtower") == "defenseQueue"
    assert server.structure_queue_key("ttrap") == "buildQueue"
    assert server.structure_queue_key("tpit") == "buildQueue"
    buildings = server.faction_buildings("tribe")
    assert buildings["defense"] == "tspiketower"
    assert buildings["defense_long"] == "ttoxtower"
    assert buildings["trap"] == "ttrap"
    assert buildings["pit"] == "tpit"
    catalog = server.public_catalog()
    assert catalog["buildings"]["tspiketower"]["range"] == spike["range"]
    assert catalog["units"]["mammoth"]["repairable"] is False
    assert catalog["units"]["mammoth"]["canVeteran"] is True
    print("  定义/队列/bot 键/目录: PASS")

    print("\n=== Test 2: 跨阵营与前置 ===")
    room, a, b = make_room("TP101", tribe_a=True, magic_b=True)
    game = room["game"]
    a["cash"] = b["cash"] = 99999
    expect_error("阵营", lambda: server.queue_structure(room, b["id"], "tspiketower"))
    expect_error("阵营", lambda: server.queue_structure(room, b["id"], "ttrap"))
    expect_error("阵营", lambda: server.queue_unit(room, b["id"], "mammoth"))
    expect_error("前置建筑", lambda: server.queue_structure(room, a["id"], "tspiketower"))
    give(game, a["id"], "tcamp")
    item = server.queue_structure(room, a["id"], "tspiketower")
    assert item["kind"] == "tspiketower"
    assert a["defenseQueue"] == [item]
    expect_error("前置建筑", lambda: server.queue_structure(room, a["id"], "ttoxtower"))
    expect_error("前置建筑", lambda: server.queue_structure(room, a["id"], "tpit"))
    give(game, a["id"], "tpen")
    expect_error("前置建筑", lambda: server.queue_unit(room, a["id"], "mammoth"))
    give(game, a["id"], "taltar")
    a["defenseQueue"] = []
    a["buildQueue"] = []
    tox_item = server.queue_structure(room, a["id"], "ttoxtower")
    assert tox_item["kind"] == "ttoxtower"
    pit_item = server.queue_structure(room, a["id"], "tpit")
    assert pit_item["kind"] == "tpit"
    server.queue_unit(room, a["id"], "mammoth")
    assert "mammoth" in queued_kinds(game, a["id"])
    print("  跨阵营拦截 / 解锁链: PASS")

    print("\n=== Test 3: 棘矛哨塔开火 ===")
    room, a, b = make_room("TP102")
    game = room["game"]
    game["projectiles"] = []
    game["effects"] = []
    silence_defenses(game)
    tower = server.make_structure("tspiketower", a["id"], 1000, 1000, True)
    rifle = server.make_unit("rifle", b["id"], 1120, 1000)
    game["structures"].append(tower)
    game["units"].append(rifle)
    tower["cooldown"] = 0.0
    server.tick_structures(room, 0.05)
    assert game["projectiles"], "棘矛哨塔应开火"
    shot = game["projectiles"][-1]
    assert shot["kind"] == "spike"
    assert shot.get("damageType") == "bullet"
    print("  棘矛弹: PASS")

    print("\n=== Test 4: 毒矢高台挂毒 ===")
    room, a, b = make_room("TP103")
    game = room["game"]
    silence_defenses(game)
    tower = server.make_structure("ttoxtower", a["id"], 2000, 2000, True)
    rifle = server.make_unit("rifle", b["id"], 2140, 2000)
    isolate(game, rifle)
    game["structures"].append(tower)
    rifle["hp"] = 1000.0
    server.launch_projectile(game, tower, rifle, tox)
    shot = game["projectiles"][-1]
    assert shot["kind"] == "dart"
    assert shot.get("dot") == tox["dot"]
    index = {rifle["id"]: rifle}
    for _ in range(30):
        server.tick_projectiles(room, 0.05, index)
        if not game["projectiles"]:
            break
    assert abs(rifle["dotDps"] - 12.0) < 1e-6
    assert rifle["dotSourceKind"] == "ttoxtower"
    assert server.public_unit(rifle).get("dot") is True
    print("  毒矢 DoT: PASS")

    print("\n=== Test 5: 兽夹上膛、触发、拆除 ===")
    room, a, b = make_room("TP104")
    game = room["game"]
    trap_s = server.make_structure("ttrap", a["id"], 3000, 3000, True)
    rifle = server.make_unit("rifle", b["id"], 3010, 3000)
    ally = server.make_unit("spear", a["id"], 3008, 3000)
    isolate(game, rifle, ally)
    game["structures"].append(trap_s)
    assert trap_s.get("armed") is False
    pub = server.public_structure(trap_s)
    assert pub.get("armed") is False
    server.tick_structures(room, 1.0)
    assert trap_s.get("armed") is False
    server.tick_structures(room, 1.4)
    assert trap_s.get("armed") is True
    assert server.public_structure(trap_s).get("armed") is True
    hp0 = rifle["hp"]
    ally_hp0 = ally["hp"]
    server.tick_structures(room, 0.05)
    assert rifle["hp"] < hp0
    assert abs(rifle["slowMult"] - 0.0) < 1e-9
    assert server.public_unit(rifle).get("rooted") is True
    assert abs(ally["hp"] - ally_hp0) < 1e-6
    assert trap_s["hp"] <= 0
    print("  上膛 / 定身爆发 / 友军免疫 / 拆除: PASS")

    print("\n=== Test 6: 兽夹不夹建筑 ===")
    room, a, b = make_room("TP105")
    game = room["game"]
    trap_s = server.make_structure("ttrap", a["id"], 4000, 4000, True)
    trap_s["armed"] = True
    trap_s["armTimer"] = 0.0
    enemy_hq = next(s for s in game["structures"]
                    if s["owner"] == b["id"]
                    and server.structure_role(s["kind"]) == "hq")
    enemy_hq["x"], enemy_hq["y"] = 4005.0, 4000.0
    game["units"] = []
    game["structures"].append(trap_s)
    hp0 = enemy_hq["hp"]
    server.tick_structures(room, 0.05)
    assert trap_s["hp"] > 0
    assert trap_s.get("armed") is True
    assert abs(enemy_hq["hp"] - hp0) < 1e-6
    print("  建筑不触发兽夹: PASS")

    print("\n=== Test 7: 毒雾坑脉冲只毒敌军 ===")
    room, a, b = make_room("TP106")
    game = room["game"]
    pit_s = server.make_structure("tpit", a["id"], 5000, 5000, True)
    rifle = server.make_unit("rifle", b["id"], 5040, 5000)
    ally = server.make_unit("spear", a["id"], 5035, 5000)
    isolate(game, rifle, ally)
    game["structures"].append(pit_s)
    pit_s["auraTimer"] = 0.0
    server.tick_structures(room, 0.05)
    assert abs(rifle.get("dotDps", 0.0) - 16.0) < 1e-6
    assert rifle["dotSourceKind"] == "tpit"
    assert not ally.get("dotTimer")
    structure = next(s for s in game["structures"] if s["owner"] == b["id"])
    before = structure["hp"]
    server.apply_dot({"dot": pit["dot"], "owner": a["id"]}, structure)
    assert not structure.get("dotTimer")
    assert abs(structure["hp"] - before) < 1e-9
    print("  毒坑敌军 DoT / 友军与建筑免疫: PASS")

    print("\n=== Test 8: 猛犸 smash 拆建筑优于战狼 ===")
    room, a, b = make_room("TP107")
    game = room["game"]
    hq = next(s for s in game["structures"]
              if s["owner"] == b["id"]
              and server.structure_role(s["kind"]) == "hq")
    before = hq["hp"]
    server.apply_damage(room, hq, 100, a["id"], "smash", game)
    smash_dealt = before - hq["hp"]
    assert abs(smash_dealt - 150.0) < 0.1, smash_dealt
    before = hq["hp"]
    server.apply_damage(room, hq, 100, a["id"], "bite", game)
    assert abs(hq["hp"] - before) < 0.1
    wolf = server.UNIT_TYPES["wolf"]
    assert mammoth["speed"] < wolf["speed"]
    assert mammoth["hp"] > wolf["hp"]
    print("  smash ×1.50 拆建筑 / 狼咬建筑 0: PASS")

    print("\n=== Test 9: 机器人接线 ===")
    scout = server.bot_empty_scout()
    with_altar = server.bot_support_choices(
        "tribe", set(["factory", "repair"]), False, False, True, 2)
    assert "mammoth" in with_altar and "spider" in with_altar, with_altar
    no_altar = server.bot_support_choices(
        "tribe", set(["factory"]), False, False, True, 2)
    assert "mammoth" not in no_altar
    late = server.bot_unit_choices(
        "tribe", set(["factory", "repair"]), server.BOT_PHASE_CLOSE,
        scout, False, True, 2, False)
    assert "mammoth" in late and "scorpion" in late
    vehicles = dict(scout)
    vehicles["vehicles"] = 4
    anti = server.bot_unit_choices(
        "tribe", set(["factory", "repair"]), server.BOT_PHASE_CLOSE,
        vehicles, False, True, 2, False)
    assert "scorpion" in anti and "mammoth" in anti
    assert server.bot_unit_is_factory("mammoth") is True
    room, a, b = make_room("TP108")
    game = room["game"]
    a["isBot"] = True
    a["cash"] = 99999
    a["buildQueue"] = []
    a["defenseQueue"] = []
    hq = next(s for s in game["structures"]
              if s["owner"] == a["id"] and server.structure_role(s["kind"]) == "hq")
    hq["hp"] = hq["maxHp"] * 0.4
    give(game, a["id"], "tcamp")
    give(game, a["id"], "tpen")
    server.tick_bots(room)
    queued = a.get("defenseQueue") or []
    assert queued and queued[0]["kind"] == "tspiketower", queued
    a["defenseQueue"] = []
    give(game, a["id"], "tspiketower")
    give(game, a["id"], "taltar")
    server.tick_bots(room)
    queued = a.get("defenseQueue") or []
    assert queued and queued[0]["kind"] == "ttoxtower", queued
    assert server.faction_buildings("tech")["defense"] == "turret"
    assert server.faction_buildings("magic")["defense_long"] == "mstorm"
    print("  祭坛后猛犸 / 近塔远塔 / 他阵营未改: PASS")

    print("\n=== 原始部落 P1 测试全部通过 ===")


if __name__ == "__main__":
    main()
