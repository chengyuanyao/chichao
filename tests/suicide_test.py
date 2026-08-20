#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""自爆卡车 / 爆裂魔仆：
   1) 目录与阵营：钢铁是轻甲载具，秘法会是魔导活体（非载具）
   2) 工厂/法阵可训练，跨阵营拒绝
   3) 死亡爆炸打附近单位与建筑，带衰减；不伤友军
   4) 单车拆不掉满血总部；贴脸引爆
   5) 军犬：卡车不当猎物且咬不动，魔仆是猎物且一口咬死
   6) AI 在成团建筑时会掺一辆，不当唯一兵种
"""

from __future__ import print_function

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import server


def make_room(tag, magic_b=False):
    a = server.create_human("A", server.COLORS[0])
    b = server.create_human("B", server.COLORS[1])
    if magic_b:
        b["faction"] = "magic"
    room = {
        "id": tag, "name": "suicide test", "status": "lobby",
        "hostId": a["id"],
        "players": {a["id"]: a, b["id"]: b},
        "chat": [], "game": None, "createdAt": time.time(),
    }
    server.start_game(room)
    game = room["game"]
    game["terrainCtx"] = server.FLAT_TERRAIN
    game["botClock"] = 999.0
    game["victoryClock"] = 999.0
    return room, a, b


def give(game, pid, kind, x=900, y=900):
    s = server.make_structure(kind, pid, x, y, True)
    game["structures"].append(s)
    return s


def expected_explosion(kind, distance, armor):
    boom = server.UNIT_TYPES[kind]["deathExplosion"]
    falloff = server.death_explosion_falloff(distance, boom["radius"])
    return boom["damage"] * falloff * server.damage_armor_multiplier(
        boom["damageType"], armor)


def main():
    print("=== Test 1: 目录 / 阵营 / 载具归类 ===")
    truck = server.UNIT_TYPES["bomb_truck"]
    hexling = server.UNIT_TYPES["hexling"]
    for kind, definition in (("bomb_truck", truck), ("hexling", hexling)):
        for field in ("name", "cost", "hp", "speed", "damage", "range",
                      "cooldown", "size", "build", "producer", "projectile",
                      "projectileSpeed", "splash", "sight", "armor",
                      "damageType", "deathExplosion", "detonateOnContact"):
            assert field in definition, "%s 缺字段 %s" % (kind, field)
        assert definition["damage"] == 0.0, kind
        assert definition["detonateOnContact"] is True
        assert definition["deathExplosion"]["damage"] > 0
        assert definition["deathExplosion"]["radius"] > 0
    assert truck["name"] == "自爆卡车"
    assert hexling["name"] == "爆裂魔仆"
    assert truck["producer"] == "factory"
    assert hexling["producer"] == "mcircle"
    assert truck["faction"] == "tech"
    assert hexling["faction"] == "magic"
    assert truck["armor"] == "light"
    assert hexling["armor"] == "arcane"
    assert "bomb_truck" in server.VEHICLE_KINDS
    assert "hexling" not in server.VEHICLE_KINDS
    assert "hexling" in server.MAGIC_UNITS
    assert "bomb_truck" not in server.MAGIC_UNITS
    assert "bomb_truck" in server.SUICIDE_KINDS
    assert "hexling" in server.SUICIDE_KINDS
    assert "explosive" in server.DAMAGE_MULTIPLIER
    catalog = server.public_catalog()
    assert catalog["units"]["bomb_truck"]["repairable"] is True
    assert catalog["units"]["hexling"]["repairable"] is False
    assert catalog["units"]["hexling"]["faction"] == "magic"
    print("  定义/阵营/载具不对称: PASS")

    print("\n=== Test 2: 工厂/法阵训练，跨阵营拒绝 ===")
    room, a, b = make_room("SU01", magic_b=True)
    game = room["game"]
    a["cash"] = b["cash"] = 99999
    give(game, a["id"], "factory")
    give(game, b["id"], "mcircle")
    server.queue_unit(room, a["id"], "bomb_truck")
    server.queue_unit(room, b["id"], "hexling")
    queued_a = [item["kind"] for s in game["structures"]
                if s["owner"] == a["id"] for item in s["queue"]]
    queued_b = [item["kind"] for s in game["structures"]
                if s["owner"] == b["id"] for item in s["queue"]]
    assert "bomb_truck" in queued_a, queued_a
    assert "hexling" in queued_b, queued_b
    try:
        server.queue_unit(room, a["id"], "hexling")
        raise AssertionError("科技不该能产爆裂魔仆")
    except ValueError as exc:
        assert "阵营" in str(exc), str(exc)
    try:
        server.queue_unit(room, b["id"], "bomb_truck")
        raise AssertionError("魔法不该能产自爆卡车")
    except ValueError as exc:
        assert "阵营" in str(exc), str(exc)
    print("  本阵营放行 / 跨阵营拒绝: PASS")

    print("\n=== Test 3: 队列走完能刷出单位 ===")
    factory = next(s for s in game["structures"]
                   if s["owner"] == a["id"] and s["kind"] == "factory")
    factory["queue"][0]["remaining"] = 0.0
    before = sum(1 for u in game["units"]
                 if u["owner"] == a["id"] and u["kind"] == "bomb_truck")
    server.tick_structures(room, 0.05)
    after = sum(1 for u in game["units"]
                if u["owner"] == a["id"] and u["kind"] == "bomb_truck")
    assert after == before + 1, (before, after)
    print("  工厂刷出自爆卡车: PASS")

    print("\n=== Test 4: 死亡爆炸打附近步兵，远处不受伤 ===")
    room, a, b = make_room("SU02")
    game = room["game"]
    truck = server.make_unit("bomb_truck", a["id"], 4000, 4000)
    game["units"].append(truck)
    near = server.make_unit("rifle", b["id"], 4020, 4000)
    far = server.make_unit("rifle", b["id"], 4300, 4000)
    near["hp"] = far["hp"] = 200
    game["units"].extend([near, far])
    server.apply_damage(room, truck, 999, b["id"], "shell", game)
    assert truck["hp"] <= 0
    assert near["hp"] <= 0, "贴脸步兵应被炸死，剩 %s" % near["hp"]
    assert abs(far["hp"] - 200) < 0.1, far["hp"]
    print("  近处步兵死亡 / 远处不受伤: PASS")

    print("\n=== Test 5: 爆炸打建筑，带衰减 ===")
    room, a, b = make_room("SU03")
    game = room["game"]
    truck = server.make_unit("bomb_truck", a["id"], 4000, 4000)
    game["units"].append(truck)
    close = give(game, b["id"], "turret", 4010, 4000)
    mid = give(game, b["id"], "turret", 4055, 4000)
    close_before, mid_before = close["hp"], mid["hp"]
    server.trigger_death_explosion(room, truck, game)
    close_hit = close_before - close["hp"]
    mid_hit = mid_before - mid["hp"]
    expect_close = expected_explosion(
        "bomb_truck", 10.0, "structure")
    expect_mid = expected_explosion(
        "bomb_truck", 55.0, "structure")
    assert abs(close_hit - expect_close) < 0.6, (close_hit, expect_close)
    assert abs(mid_hit - expect_mid) < 0.6, (mid_hit, expect_mid)
    assert close_hit > mid_hit
    print("  建筑近伤 %.0f > 远伤 %.0f: PASS" % (close_hit, mid_hit))

    print("\n=== Test 6: 单车拆不掉满血总部，友军不受伤 ===")
    room, a, b = make_room("SU04")
    game = room["game"]
    hq = next(s for s in game["structures"]
              if s["owner"] == b["id"] and s["kind"] == "hq")
    ally = server.make_unit("rifle", a["id"], 4015, 4000)
    ally["hp"] = 200
    game["units"].append(ally)
    truck = server.make_unit("bomb_truck", a["id"], hq["x"], hq["y"])
    game["units"].append(truck)
    hq_before = hq["hp"]
    server.trigger_death_explosion(room, truck, game)
    assert hq["hp"] > 0, "总部不该被单车拆掉"
    assert hq["hp"] > hq_before * 0.75, hq["hp"]
    assert hq_before - hq["hp"] < 500, hq_before - hq["hp"]
    assert abs(ally["hp"] - 200) < 0.1, "友军不该吃自己的爆炸"
    print("  总部剩 %.0f / 友军无损: PASS" % hq["hp"])

    print("\n=== Test 7: 魔仆爆炸同样生效 ===")
    room, a, b = make_room("SU05", magic_b=True)
    game = room["game"]
    familiar = server.make_unit("hexling", b["id"], 4000, 4000)
    game["units"].append(familiar)
    clump = [
        server.make_unit("rifle", a["id"], 4008, 4000),
        server.make_unit("rifle", a["id"], 4000, 4008),
        server.make_unit("rocket", a["id"], 3992, 4000),
    ]
    for unit in clump:
        game["units"].append(unit)
    server.apply_damage(room, familiar, 999, a["id"], "tesla", game)
    assert all(unit["hp"] <= 0 for unit in clump), [u["hp"] for u in clump]
    print("  魔仆炸死成团步兵: PASS")

    print("\n=== Test 8: 贴脸引爆 ===")
    room, a, b = make_room("SU06")
    game = room["game"]
    truck = server.make_unit("bomb_truck", a["id"], 4000, 4000)
    prey = server.make_unit("rifle", b["id"], 4018, 4000)
    prey["hp"] = 200
    truck["cooldown"] = 0
    truck["scan"] = 0
    truck["order"] = "attack"
    truck["targetId"] = prey["id"]
    game["units"].extend([truck, prey])
    server.tick_units(room, 0.05)
    assert truck["hp"] <= 0, "贴脸应自爆"
    assert prey["hp"] < 200, "目标应吃爆炸"
    print("  贴脸引爆: PASS")

    print("\n=== Test 9: 军犬规则不把卡车当钢铁猎物，魔仆可咬 ===")
    assert server.is_dog_prey("hexling")
    assert not server.is_dog_prey("bomb_truck")
    assert server.unit_can_attack("bomb_truck")
    assert server.unit_can_attack("hexling")
    room, a, b = make_room("SU07", magic_b=True)
    game = room["game"]
    truck = server.make_unit("bomb_truck", a["id"], 9000, 9000)
    game["units"].append(truck)
    before = truck["hp"]
    server.apply_damage(room, truck, 60, b["id"], "bite", game)
    assert abs(truck["hp"] - before) < 0.001, "卡车是载具，咬不动"
    familiar = server.make_unit("hexling", b["id"], 9100, 9100)
    game["units"].append(familiar)
    server.apply_damage(room, familiar, 60, a["id"], "bite", game)
    assert familiar["hp"] <= 0, "魔仆应被一口咬死，剩 %s" % familiar["hp"]
    room, a, b = make_room("SU08", magic_b=True)
    game = room["game"]
    game["units"].append(server.make_unit("bomb_truck", a["id"], 5050, 5000))
    game["units"].append(server.make_unit("hexling", b["id"], 5080, 5000))
    pick = server.nearest_enemy_infantry(game, a["id"], 5000, 5000, 400)
    assert pick is not None and pick["kind"] == "hexling", pick and pick["kind"]
    print("  卡车非猎物 / 魔仆可咬可锁: PASS")

    print("\n=== Test 10: 攻击指令能发给自爆单位 ===")
    room, a, b = make_room("SU09")
    game = room["game"]
    truck = server.make_unit("bomb_truck", a["id"], 3000, 3000)
    game["units"].append(truck)
    hq = next(s for s in game["structures"]
              if s["owner"] == b["id"] and s["kind"] == "hq")
    server.issue_attack(game, a["id"], {truck["id"]}, hq["id"])
    assert truck["order"] == "attack" and truck["targetId"] == hq["id"]
    print("  issue_attack 接受自爆卡车: PASS")

    print("\n=== Test 11: AI 在成团建筑时会掺自爆，不当唯一兵种 ===")
    room, a, b = make_room("SU10")
    game = room["game"]
    a["isBot"] = True
    a["cash"] = 99999
    give(game, a["id"], "factory")
    # 敌方再摆几座建筑，让「成团建筑」条件成立
    give(game, b["id"], "power", 1200, 900)
    give(game, b["id"], "barracks", 1400, 900)
    server.random.seed(20260820)
    produced = set()
    for _ in range(80):
        server.tick_bots(room)
        for structure in game["structures"]:
            if structure["owner"] != a["id"]:
                continue
            for item in structure["queue"]:
                produced.add(item["kind"])
            if len(structure["queue"]) >= 5 and "bomb_truck" not in produced:
                structure["queue"][:] = []
        if "bomb_truck" in produced and len(produced) > 1:
            break
    assert "bomb_truck" in produced, produced
    assert produced != set(["bomb_truck"]), produced
    print("  AI 排出 %s: PASS" % sorted(produced))

    print("\n=== 自爆单位测试全部通过 ===")


if __name__ == "__main__":
    main()
