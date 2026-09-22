#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""秘法会玄岩巨像：岩石傀儡进阶的地面重甲前排。
   1) 目录锁定：魔法-only、法阵产、圣泉门槛、造价/血/移速/溅射
   2) 移速必须与岩石傀儡完全一致
   3) VEHICLE_KINDS + MAGIC_UNITS；圣泉可修
   4) 圣殿单独不能出；科技不能产
   5) 军犬当载具：不当猎物，bite 不掉血
   6) 大师 AI 无圣泉不出巨像；圣泉+法阵后期/防守可排
"""

from __future__ import print_function

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import server


def make_room(tag, magic_b=True):
    a = server.create_human("A", server.COLORS[0])
    b = server.create_human("B", server.COLORS[1])
    if magic_b:
        b["faction"] = "magic"
    room = {
        "id": tag, "name": "behemoth test", "status": "lobby",
        "hostId": a["id"],
        "players": {a["id"]: a, b["id"]: b},
        "chat": [], "game": None, "createdAt": time.time(),
    }
    server.start_game(room)
    return room, a, b


def give(game, pid, kind):
    structure = server.make_structure(kind, pid, 900, 900, True)
    game["structures"].append(structure)
    return structure


def queued_kinds(game, pid):
    kinds = []
    for structure in game["structures"]:
        if structure["owner"] != pid:
            continue
        for item in structure["queue"]:
            kinds.append(item["kind"])
    return kinds


def main():
    print("=== Test 1: 目录 / 阵营 / 圣泉门槛 / 锁定数值 ===")
    behemoth = server.UNIT_TYPES["behemoth"]
    golem = server.UNIT_TYPES["golem"]
    for field in ("name", "cost", "hp", "speed", "damage", "range",
                  "cooldown", "size", "build", "producer", "projectile",
                  "projectileSpeed", "splash", "sight", "armor",
                  "damageType", "requires"):
        assert field in behemoth, "behemoth 缺字段 %s" % field
    assert behemoth["name"] == "玄岩巨像"
    assert behemoth["producer"] == "mcircle"
    assert behemoth["requires"] == ["mspring"]
    assert behemoth["faction"] == "magic"
    assert behemoth["cost"] == 1520
    assert behemoth["hp"] == 1520
    assert behemoth["speed"] == 52.0
    assert behemoth["speed"] == golem["speed"]
    assert behemoth["damage"] == 90.0
    assert behemoth["range"] == 145.0
    assert behemoth["cooldown"] == 1.15
    assert behemoth["size"] == 26.0
    assert behemoth["build"] == 14.0
    assert behemoth["splash"] == 52.0
    assert behemoth["sight"] == 380.0
    assert behemoth["armor"] == ("heavy", "light")
    assert behemoth["damageType"] == "magic"
    assert behemoth["projectile"] == "rune_boulder"
    assert behemoth["projectileSpeed"] == 400.0
    assert "behemoth" in server.MAGIC_UNITS
    assert "behemoth" in server.VEHICLE_KINDS
    assert "behemoth" not in server.SUICIDE_KINDS
    catalog = server.public_catalog()
    entry = catalog["units"]["behemoth"]
    assert entry["name"] == "玄岩巨像"
    assert entry["cost"] == 1520
    assert entry["faction"] == "magic"
    assert entry["requires"] == ["mspring"]
    assert entry["producer"] == "mcircle"
    assert entry["repairable"] is True
    assert entry["damageType"] == "magic"
    print("  定义/阵营/目录/锁定数值 / 移速==傀儡: PASS")

    print("\n=== Test 2: 圣殿单独不能出；法阵缺圣泉拒绝；补圣泉放行 ===")
    room, a, b = make_room("BHM01")
    game = room["game"]
    b["cash"] = 99999
    give(game, b["id"], "mtemple")
    try:
        server.queue_unit(room, b["id"], "behemoth")
        raise AssertionError("只有圣殿不该能出玄岩巨像")
    except ValueError as exc:
        assert "生产建筑" in str(exc) or "前置" in str(exc), str(exc)
    give(game, b["id"], "mcircle")
    try:
        server.queue_unit(room, b["id"], "behemoth")
        raise AssertionError("无法阵外圣泉不该能出玄岩巨像")
    except ValueError as exc:
        assert "前置建筑" in str(exc), str(exc)
    give(game, b["id"], "mspring")
    server.queue_unit(room, b["id"], "behemoth")
    assert "behemoth" in queued_kinds(game, b["id"])
    print("  圣殿拒绝 / 缺圣泉拒绝 / 补圣泉放行: PASS")

    print("\n=== Test 3: 科技不能产玄岩巨像 ===")
    room, a, b = make_room("BHM02")
    game = room["game"]
    a["cash"] = b["cash"] = 99999
    give(game, a["id"], "factory")
    give(game, a["id"], "repair")
    give(game, b["id"], "mcircle")
    give(game, b["id"], "mspring")
    try:
        server.queue_unit(room, a["id"], "behemoth")
        raise AssertionError("科技不该能产玄岩巨像")
    except ValueError as exc:
        assert "阵营" in str(exc), str(exc)
    server.queue_unit(room, b["id"], "behemoth")
    print("  跨阵营拦截 / 魔法放行: PASS")

    print("\n=== Test 4: 军犬不扑、咬不动 ===")
    room, a, b = make_room("BHM03")
    game = room["game"]
    giant = server.make_unit("behemoth", b["id"], 9000, 9000)
    game["units"].append(giant)
    before = giant["hp"]
    server.apply_damage(room, giant, 60, a["id"], "bite", game)
    assert abs(giant["hp"] - before) < 0.1, giant["hp"]
    assert not server.is_dog_prey("behemoth")
    assert server.is_dog_prey("mage")
    game["units"].append(server.make_unit("behemoth", b["id"], 5050, 5000))
    game["units"].append(server.make_unit("mage", b["id"], 5080, 5000))
    pick = server.nearest_enemy_infantry(game, a["id"], 5000, 5000, 400)
    assert pick is not None and pick["kind"] == "mage", pick and pick["kind"]
    print("  bite ×0 / 不当猎物: PASS")

    print("\n=== Test 5: 混甲让磁暴/狙击不能当纯魔导一锅端 ===")
    room, a, b = make_room("BHM04")
    game = room["game"]
    giant = server.make_unit("behemoth", b["id"], 9100, 9100)
    giant["hp"] = 1000
    game["units"].append(giant)
    before = giant["hp"]
    server.apply_damage(room, giant, 100, a["id"], "tesla", game)
    assert abs((before - giant["hp"]) - 135.0) < 0.1, before - giant["hp"]
    before = giant["hp"]
    server.apply_damage(room, giant, 100, a["id"], "sniper", game)
    assert abs((before - giant["hp"]) - 27.5) < 0.1, before - giant["hp"]
    print("  tesla ×1.35 / sniper ×0.275: PASS")

    print("\n=== Test 6: 大师 AI 无圣泉不出巨像；圣泉+法阵可排 ===")
    room, a, b = make_room("BHM05")
    game = room["game"]
    b["isBot"] = True
    b["cash"] = 99999
    b["buildQueue"] = [{"id": "busy", "kind": "mpower",
                        "remaining": 4.0, "total": 8.0, "ready": False}]
    give(game, b["id"], "mtemple")
    give(game, b["id"], "mcircle")
    assert not any(s["owner"] == b["id"] and s["kind"] == "mspring"
                   for s in game["structures"])
    produced = set()
    for _ in range(40):
        server.tick_bots(room)
        produced.update(queued_kinds(game, b["id"]))
        for structure in game["structures"]:
            if structure["owner"] == b["id"] and len(structure["queue"]) >= 5:
                if "behemoth" not in produced:
                    structure["queue"][:] = []
    assert "behemoth" not in produced, produced
    scout = server.bot_empty_scout()
    late = server.bot_unit_choices(
        "magic", set(["factory", "repair"]), server.BOT_PHASE_CLOSE,
        scout, False, True, 2, False)
    defend = server.bot_unit_choices(
        "magic", set(["factory", "repair"]), server.BOT_PHASE_CLOSE,
        scout, True, True, 2, False)
    assert "behemoth" in late, late
    assert "behemoth" in defend, defend
    print("  无圣泉未排 behemoth；圣泉+法阵后期/防守可选: PASS")

    print("\n=== 玄岩巨像测试全部通过 ===")


if __name__ == "__main__":
    main()
