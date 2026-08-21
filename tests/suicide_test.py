#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""自爆卡车 / 爆裂魔仆：
   1) 目录与阵营：钢铁是轻甲载具，秘法会是魔导活体（非载具）
   2) 工厂/法阵可训练，跨阵营拒绝
   3) 死亡爆炸打附近单位与建筑，带衰减；不伤友军
   4) 单车拆不掉满血总部；贴脸引爆
   5) 军犬：卡车不当猎物且咬不动；魔仆是猎物但一口咬不死
   6) 造价/血/速/爆炸对齐；单辆拆不掉满血总部
   7) 速胜 AI 工厂一立就出自爆卡车，同时仍会混编其他兵种
   8) 无连环爆炸：溅射未致死则邻居还活着；友军并排不炸；圈外邻居不引爆
"""

from __future__ import print_function

import math
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
        assert "chainRadius" not in definition["deathExplosion"]
    # 造价/血/速/爆炸对齐。皮相/生产者仍分阵营。
    for field in ("cost", "hp", "speed", "build", "damageType"):
        assert truck[field] == hexling[field], (field, truck[field], hexling[field])
    for field in ("damage", "radius", "damageType"):
        assert truck["deathExplosion"][field] == hexling["deathExplosion"][field], (
            field, truck["deathExplosion"][field], hexling["deathExplosion"][field])
    assert truck["deathExplosion"]["damage"] == 700.0
    assert truck["deathExplosion"]["radius"] == 120.0
    bite_to_hexling = (
        server.UNIT_TYPES["dog"]["damage"]
        * server.DAMAGE_MULTIPLIER["bite"]["arcane"])
    assert bite_to_hexling < hexling["hp"], (
        "一口咬死魔仆：咬 %.0f / 血 %.0f" % (bite_to_hexling, hexling["hp"]))
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

    print("\n=== Test 6: 单辆自爆拆不掉满血总部，友军不受伤 ===")
    for kind in ("bomb_truck", "hexling"):
        room, a, b = make_room("SU04-" + kind)
        game = room["game"]
        hq = next(s for s in game["structures"]
                  if s["owner"] == b["id"] and s["kind"] == "hq")
        ally = server.make_unit("rifle", a["id"], 4015, 4000)
        ally["hp"] = 200
        game["units"].append(ally)
        unit = server.make_unit(kind, a["id"], hq["x"], hq["y"])
        game["units"].append(unit)
        hq_before = hq["hp"]
        server.trigger_death_explosion(room, unit, game)
        hq_hit = hq_before - hq["hp"]
        expect_hq = expected_explosion(kind, 0.0, "structure")
        assert abs(expect_hq - 770.0) < 0.1, (kind, expect_hq)
        assert hq["hp"] > 0, "%s 不该拆掉总部" % kind
        assert abs(hq_hit - expect_hq) < 0.6, (kind, hq_hit, expect_hq)
        assert abs(hq["hp"] - 1630.0) < 0.6, (kind, hq["hp"])
        assert abs(ally["hp"] - 200) < 0.1, "友军不该吃自己的爆炸"
        print("  %s 总部剩 %.0f（伤 %.0f）/ 友军无损: PASS" % (
            kind, hq["hp"], hq_hit))

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

    print("\n=== Test 9: 军犬规则不把卡车当钢铁猎物，魔仆可咬但一口不死 ===")
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
    before = familiar["hp"]
    bite = server.UNIT_TYPES["dog"]["damage"]
    expect_bite = bite * server.DAMAGE_MULTIPLIER["bite"]["arcane"]
    assert expect_bite < before, (expect_bite, before)
    server.apply_damage(room, familiar, bite, a["id"], "bite", game)
    assert familiar["hp"] > 0, "魔仆不该被一口咬死，剩 %s" % familiar["hp"]
    assert abs((before - familiar["hp"]) - expect_bite) < 0.1, (
        before - familiar["hp"], expect_bite)
    room, a, b = make_room("SU08", magic_b=True)
    game = room["game"]
    game["units"].append(server.make_unit("bomb_truck", a["id"], 5050, 5000))
    game["units"].append(server.make_unit("hexling", b["id"], 5080, 5000))
    pick = server.nearest_enemy_infantry(game, a["id"], 5000, 5000, 400)
    assert pick is not None and pick["kind"] == "hexling", pick and pick["kind"]
    print("  卡车非猎物 / 魔仆可咬但一口不死: PASS")

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

    print("\n=== Test 11: 速胜 AI 工厂后排出自爆，且不当唯一兵种 ===")
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

    print("\n=== Test 12: 爆破圈外的邻近自爆不连环引爆 ===")
    room, a, b = make_room("SU11", magic_b=True)
    game = room["game"]
    truck_boom = server.UNIT_TYPES["bomb_truck"]["deathExplosion"]
    hex_boom = server.UNIT_TYPES["hexling"]["deathExplosion"]
    assert truck_boom["damage"] == hex_boom["damage"] == 700.0
    assert truck_boom["radius"] == hex_boom["radius"] == 120.0
    assert "chainRadius" not in truck_boom
    assert "chainRadius" not in hex_boom
    # 放在爆破半径外：溅射为 0。没有连环则魔仆应还活着。
    gap = truck_boom["radius"] + 10.0
    assert gap > truck_boom["radius"], gap
    truck = server.make_unit("bomb_truck", a["id"], 4000, 4000)
    other = server.make_unit("hexling", b["id"], 4000 + gap, 4000)
    # 魔仆外侧的步兵：只吃得到魔仆爆炸。魔仆没炸，步兵应还活着。
    witness = server.make_unit("rifle", a["id"], 4000 + gap + 18, 4000)
    tank = server.make_unit("tank", b["id"], 4008, 4000)
    mage = server.make_unit("mage", b["id"], 4000, 4012)
    game["units"].extend([truck, other, witness, tank, mage])
    other_hp = other["hp"]
    witness_hp = witness["hp"]
    tank_hp = tank["hp"]
    mage_hp = mage["hp"]
    expect_splash = expected_explosion("bomb_truck", gap, "arcane")
    assert expect_splash == expected_explosion("hexling", gap, "arcane")
    assert expect_splash <= 0, expect_splash
    server.trigger_death_explosion(room, truck, game)
    assert truck.get("_exploded") and truck["hp"] <= 0
    assert not other.get("_exploded"), "圈外魔仆不该连环引爆"
    assert abs(other["hp"] - other_hp) < 0.1, other["hp"]
    assert not witness.get("_exploded")
    assert abs(witness["hp"] - witness_hp) < 0.1, "魔仆没炸，外侧步兵不该死"
    assert not tank.get("_exploded"), "坦克不该被扫进假爆炸"
    assert not mage.get("_exploded"), "法师不该被扫进假爆炸"
    assert tank["hp"] < tank_hp and tank["hp"] > 0
    assert mage["hp"] < mage_hp
    print("  间距 %.0f：魔仆未吃溅射也不引爆 / 坦克法师只吃溅射: PASS" % gap)

    print("\n=== Test 12b: 爆破圈内溅射未打死则不连环 ===")
    # 700 圈内 115 已能打死轻甲 160；贴爆破边缘才溅射未致死。
    # 魔仆甲种更高，圈内会被溅射打死，所以两边都用轻甲卡车当目标。
    boom = server.UNIT_TYPES["bomb_truck"]["deathExplosion"]
    dist = boom["radius"] - 0.6
    expect = expected_explosion("bomb_truck", dist, "light")
    assert expect == expected_explosion("hexling", dist, "light")
    for source_kind in ("bomb_truck", "hexling"):
        room, a, b = make_room("SU11b-" + source_kind)
        game = room["game"]
        source = server.make_unit(source_kind, a["id"], 5000, 5000)
        other = server.make_unit("bomb_truck", b["id"], 5000 + dist, 5000)
        game["units"].extend([source, other])
        assert 0 < expect < other["hp"], (source_kind, expect, other["hp"])
        other_before = other["hp"]
        server.trigger_death_explosion(room, source, game)
        assert source.get("_exploded") and source["hp"] <= 0
        assert not other.get("_exploded"), source_kind
        assert other["hp"] > 0, source_kind
        assert abs((other_before - other["hp"]) - expect) < 0.6, (
            source_kind, other_before - other["hp"], expect)
        print("  %s 圈内 %.1f 溅射 %.0f < 160，邻居受伤但不连环: PASS" % (
            source_kind, dist, expect))

    print("\n=== Test 13: 友军并排不连环，只炸自己 ===")
    for kind in ("bomb_truck", "hexling"):
        room, a, b = make_room("SU12-" + kind)
        game = room["game"]
        first = server.make_unit(kind, a["id"], 4000, 4000)
        parked = server.make_unit(kind, a["id"], 4050, 4000)
        prey = server.make_unit("rifle", b["id"], 4025, 4000)
        prey["hp"] = 200
        game["units"].extend([first, parked, prey])
        parked_hp = parked["hp"]
        server.trigger_death_explosion(room, first, game)
        assert first.get("_exploded") and first["hp"] <= 0, kind
        assert not parked.get("_exploded"), kind
        assert abs(parked["hp"] - parked_hp) < 0.1, (kind, parked["hp"])
        assert prey["hp"] <= 0, "%s 自己的 700 圈应炸死贴脸步兵，剩 %s" % (
            kind, prey["hp"])
        print("  友军并排 %s 邻车不炸 / 步兵仍死: PASS" % kind)

    print("\n=== Test 14: 环形邻居只吃溅射，不连环；已炸过的不再炸 ===")
    room, a, b = make_room("SU13", magic_b=True)
    game = room["game"]
    # 边长 80、对角 113，都在爆破半径 120 内。魔导 160 血在 80 处
    # 会被 700 溅射打死——那是普通死亡爆炸，不是连环触发。
    # 对角换成重甲坦克：只吃溅射，不该被扫进假爆炸。
    ring = [
        server.make_unit("bomb_truck", a["id"], 4000, 4000),
        server.make_unit("hexling", b["id"], 4080, 4000),
        server.make_unit("tank", b["id"], 4080, 4080),
        server.make_unit("hexling", b["id"], 4000, 4080),
    ]
    for unit in ring:
        game["units"].append(unit)
    for i, unit in enumerate(ring):
        nxt = ring[(i + 1) % 4]
        side = math.hypot(nxt["x"] - unit["x"], nxt["y"] - unit["y"])
        assert 70 < side < 130, side
    hex_side = expected_explosion("bomb_truck", 80.0, "arcane")
    tank_diag = expected_explosion("bomb_truck", math.hypot(80.0, 80.0), "heavy")
    assert hex_side >= ring[1]["hp"], hex_side
    assert hex_side >= ring[3]["hp"], hex_side
    assert 0 < tank_diag < ring[2]["hp"], tank_diag
    tank_before = ring[2]["hp"]
    server.trigger_death_explosion(room, ring[0], game)
    assert ring[0].get("_exploded") and ring[0]["hp"] <= 0
    # 邻边魔仆被 700 溅射打死，于是走普通死亡爆炸（不是 chainRadius）。
    assert ring[1]["hp"] <= 0 and ring[1].get("_exploded")
    assert ring[3]["hp"] <= 0 and ring[3].get("_exploded")
    assert not ring[2].get("_exploded"), "坦克不该被扫进假爆炸"
    assert ring[2]["hp"] > 0
    assert abs((tank_before - ring[2]["hp"]) - tank_diag) < 0.6, (
        tank_before - ring[2]["hp"], tank_diag)
    assert server.trigger_death_explosion(room, ring[0], game) is False
    assert server.trigger_death_explosion(room, ring[1], game) is False
    print("  环形：溅射致死才炸 / 坦克不假炸 / 已炸不再炸: PASS")

    print("\n=== Test 15: 圈外环形邻居全部活着，证明没有连环 ===")
    room, a, b = make_room("SU14", magic_b=True)
    game = room["game"]
    boom = server.UNIT_TYPES["bomb_truck"]["deathExplosion"]
    # 边长 140 在爆破半径 120 外，溅射为 0。没有连环则只有被引爆的那辆倒下。
    step = boom["radius"] + 20.0
    ring = [
        server.make_unit("bomb_truck", a["id"], 4000, 4000),
        server.make_unit("hexling", b["id"], 4000 + step, 4000),
        server.make_unit("bomb_truck", a["id"], 4000 + step, 4000 + step),
        server.make_unit("hexling", b["id"], 4000, 4000 + step),
    ]
    for unit in ring:
        game["units"].append(unit)
    for i, unit in enumerate(ring):
        nxt = ring[(i + 1) % 4]
        side = math.hypot(nxt["x"] - unit["x"], nxt["y"] - unit["y"])
        assert side > boom["radius"], side
        assert expected_explosion("bomb_truck", side, "light") <= 0
    lives = [unit["hp"] for unit in ring[1:]]
    server.trigger_death_explosion(room, ring[0], game)
    assert ring[0].get("_exploded") and ring[0]["hp"] <= 0
    for unit, hp in zip(ring[1:], lives):
        assert not unit.get("_exploded"), unit["kind"]
        assert abs(unit["hp"] - hp) < 0.1, (unit["kind"], unit["hp"])
    assert server.trigger_death_explosion(room, ring[0], game) is False
    print("  圈外环形 3 邻全活: PASS")

    print("\n=== 自爆单位测试全部通过 ===")


if __name__ == "__main__":
    main()
