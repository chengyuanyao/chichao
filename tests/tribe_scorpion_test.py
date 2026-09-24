#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""原始部落进阶：穿甲巨蝎。
   1) 目录 / 阵营 / 血祭坛门槛
   2) 复用 ap 伤种：重甲 ×2.10，步兵 ×0.25
   3) 玻璃血、无溅射、非载具、无自爆
   4) 跨阵营不能产；机器人祭坛后才偏好
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
        "id": tag, "name": "scorpion test", "status": "lobby",
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


def give(game, pid, kind):
    structure = server.make_structure(kind, pid, 900, 900, True)
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


def queued_kinds(game, pid):
    return [item["kind"] for structure in game["structures"]
            if structure["owner"] == pid for item in structure["queue"]]


def main():
    print("=== Test 1: 目录 / 阵营 / 血祭坛门槛字段 ===")
    scorpion = server.UNIT_TYPES["scorpion"]
    spider = server.UNIT_TYPES["spider"]
    wolf = server.UNIT_TYPES["wolf"]
    spear = server.UNIT_TYPES["spear"]
    tank = server.UNIT_TYPES["tank"]
    tank_destroyer = server.UNIT_TYPES["tank_destroyer"]
    golem = server.UNIT_TYPES["golem"]
    for field in ("name", "cost", "hp", "speed", "damage", "range",
                  "cooldown", "size", "build", "producer", "projectile",
                  "projectileSpeed", "splash", "sight", "armor",
                  "damageType", "requires"):
        assert field in scorpion, "scorpion 缺字段 %s" % field
    assert scorpion["name"] == "穿甲巨蝎"
    assert scorpion["producer"] == "tpen"
    assert scorpion["requires"] == ["taltar"]
    assert scorpion["faction"] == "tribe"
    assert scorpion["cost"] == 820
    assert 700 <= scorpion["cost"] <= 900
    assert scorpion["hp"] == 165
    assert 120 <= scorpion["hp"] <= 200
    assert scorpion["hp"] < wolf["hp"]
    assert scorpion["hp"] < spider["hp"]
    assert scorpion["speed"] == 100.0
    assert scorpion["damage"] == 82.0
    assert scorpion["range"] == 145.0
    assert spear["range"] < scorpion["range"] < spider["range"]
    assert scorpion["cooldown"] == 1.80
    assert scorpion["cooldown"] >= 1.5
    assert scorpion["size"] == 13.0
    assert scorpion["build"] == 7.5
    assert scorpion["splash"] == 0.0
    assert scorpion["sight"] == 390.0
    assert scorpion["projectile"] == "sting"
    assert scorpion["projectileSpeed"] == 640.0
    assert scorpion["armor"] == "beast"
    assert scorpion["damageType"] == "ap"
    assert scorpion.get("slow") is None
    assert scorpion.get("dot") is None
    assert "scorpion" in server.TRIBE_UNITS
    assert "scorpion" not in server.VEHICLE_KINDS
    assert "scorpion" not in server.SUICIDE_KINDS
    assert not server.is_dog_prey("scorpion")
    assert scorpion["cost"] < tank_destroyer["cost"]
    assert scorpion["hp"] < tank_destroyer["hp"]
    assert scorpion["range"] < tank_destroyer["range"]
    catalog = server.public_catalog()
    entry = catalog["units"]["scorpion"]
    assert entry["name"] == "穿甲巨蝎"
    assert entry["producer"] == "tpen"
    assert entry["requires"] == ["taltar"]
    assert entry["faction"] == "tribe"
    assert entry["repairable"] is False
    assert entry["canVeteran"] is True
    assert entry["damageType"] == "ap"
    print("  目录字段 / 玻璃血 / ap 尾刺: PASS")

    print("\n=== Test 2: 围栏+祭坛才许驯养，跨阵营拒绝 ===")
    room, a, b = make_room("SCORP01")
    game = room["game"]
    a["cash"] = 99999
    try:
        server.queue_unit(room, a["id"], "scorpion")
        raise AssertionError("缺围栏时不该能排巨蝎")
    except ValueError as exc:
        assert "生产建筑" in str(exc) or "前置" in str(exc), str(exc)
    give(game, a["id"], "tpen")
    try:
        server.queue_unit(room, a["id"], "scorpion")
        raise AssertionError("缺祭坛时不该能排巨蝎")
    except ValueError as exc:
        assert "前置" in str(exc), str(exc)
    give(game, a["id"], "taltar")
    server.queue_unit(room, a["id"], "scorpion")
    assert "scorpion" in queued_kinds(game, a["id"])
    room2, tech, magic = make_room("SCORP02", tribe_a=False, magic_b=True)
    for pid in (tech["id"], magic["id"]):
        room2["players"][pid]["cash"] = 99999
        give(room2["game"], pid, "tpen")
        give(room2["game"], pid, "taltar")
        try:
            server.queue_unit(room2, pid, "scorpion")
            raise AssertionError("%s 不该能产巨蝎" % pid)
        except ValueError as exc:
            assert "阵营" in str(exc), str(exc)
    print("  taltar 门槛 / 跨阵营拒绝: PASS")

    print("\n=== Test 3: 尾刺弹无溅射、无定身、无 DoT ===")
    room, a, b = make_room("SCORP03")
    game = room["game"]
    scorpion_u = server.make_unit("scorpion", a["id"], 2000, 2000)
    foe = server.make_unit("tank", b["id"], 2100, 2000)
    isolate(game, scorpion_u, foe)
    server.launch_projectile(game, scorpion_u, foe, scorpion)
    assert game["projectiles"], "应射出尾刺"
    shot = game["projectiles"][0]
    assert shot["kind"] == "sting"
    assert shot.get("splash", 0) == 0
    assert shot.get("slow") is None
    assert shot.get("dot") is None
    assert shot["damageType"] == "ap"
    print("  sting 弹道 / 无控制: PASS")

    print("\n=== Test 4: ap 克重甲，打步兵弱，优于骨矛/战狼打坦克 ===")
    room, a, b = make_room("SCORP04")
    game = room["game"]
    rifle = server.make_unit("rifle", b["id"], 3000, 3000)
    tank_u = server.make_unit("tank", b["id"], 3100, 3000)
    golem_u = server.make_unit("golem", b["id"], 3200, 3000)
    rifle["hp"] = tank_u["hp"] = golem_u["hp"] = 1000.0
    game["units"].extend((rifle, tank_u, golem_u))
    before = rifle["hp"]
    server.apply_damage(room, rifle, 100, a["id"], "ap", game)
    assert abs((before - rifle["hp"]) - 25.0) < 0.1, before - rifle["hp"]
    before = tank_u["hp"]
    server.apply_damage(room, tank_u, 100, a["id"], "ap", game)
    assert abs((before - tank_u["hp"]) - 210.0) < 0.1, before - tank_u["hp"]
    before = golem_u["hp"]
    server.apply_damage(room, golem_u, 100, a["id"], "ap", game)
    assert abs((before - golem_u["hp"]) - 100.0) < 0.1, before - golem_u["hp"]
    scorpion_vs_tank = scorpion["damage"] * server.damage_armor_multiplier(
        "ap", tank["armor"])
    spear_vs_tank = spear["damage"] * server.damage_armor_multiplier(
        spear["damageType"], tank["armor"])
    wolf_vs_tank = wolf["damage"] * server.damage_armor_multiplier(
        wolf["damageType"], tank["armor"])
    assert abs(scorpion_vs_tank - 172.2) < 0.1, scorpion_vs_tank
    assert scorpion_vs_tank > spear_vs_tank * 8
    assert scorpion_vs_tank > wolf_vs_tank
    scorpion_vs_golem = scorpion["damage"] * server.damage_armor_multiplier(
        "ap", golem["armor"])
    assert abs(scorpion_vs_golem - 82.0) < 0.1, scorpion_vs_golem
    print("  ap 克制 / 对坦克优于矛狼: PASS")

    print("\n=== Test 5: 尾刺命中结算穿甲直伤 ===")
    room, a, b = make_room("SCORP05")
    game = room["game"]
    scorpion_u = server.make_unit("scorpion", a["id"], 4000, 4000)
    tank_u = server.make_unit("tank", b["id"], 4080, 4000)
    isolate(game, scorpion_u, tank_u)
    before = tank_u["hp"]
    server.launch_projectile(game, scorpion_u, tank_u, scorpion)
    index = {scorpion_u["id"]: scorpion_u, tank_u["id"]: tank_u}
    for _ in range(40):
        server.tick_projectiles(room, 0.05, index)
        if not game["projectiles"]:
            break
    dealt = before - tank_u["hp"]
    assert abs(dealt - 172.2) < 0.2, dealt
    assert tank_u.get("slowTimer", 0) == 0
    assert tank_u.get("dotTimer", 0) == 0
    print("  命中坦克 82×2.10: PASS")

    print("\n=== Test 6: 机器人在祭坛后才偏好巨蝎 ===")
    scout = server.bot_empty_scout()
    with_altar = server.bot_support_choices(
        "tribe", set(["factory", "repair"]), False, False, True, 2)
    assert "scorpion" in with_altar, with_altar
    assert "spider" in with_altar, with_altar
    no_altar = server.bot_support_choices(
        "tribe", set(["factory"]), False, False, True, 2)
    assert "scorpion" not in no_altar, no_altar
    late = server.bot_unit_choices(
        "tribe", set(["factory", "repair"]), server.BOT_PHASE_CLOSE,
        scout, False, True, 2, False)
    assert "scorpion" in late, late
    print("  围栏+祭坛才排巨蝎: PASS")

    print("\n=== 穿甲巨蝎测试全部通过 ===")


if __name__ == "__main__":
    main()
