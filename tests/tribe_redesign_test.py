#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""原始部落重设计（tribe-faction-redesign）回归。
   1) 部落野兽集合 = 目录中全部兽甲单位
   2) 维修集合 = 载具 ∪ 部落野兽
   3) 猎印 / 加成封顶 / 定身抗性常量
   4) server 再导出 catalog 新符号

   猎印、号令、充能、治疗与 bot 回归均在 main() 里按序调用；
   性质测试开头用 property_banner() 打印
   「Feature: tribe-faction-redesign, Property N: <标题>」。
"""

from __future__ import print_function

import os
import random
import math
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import catalog
import server


FEATURE = "tribe-faction-redesign"

# 本 spec 在 catalog 新增、server 必须原样再导出的符号（需求 31.8）。
# 后续任务新增常量、集合或函数时追加到这里，Test 4 自动覆盖。
REEXPORTED_NAMES = (
    "COMMAND_AURA_QUERY", "HUNT_MARK_SOURCES", "START_GARRISON_OFFSETS",
    "faction_start_garrison",
    "HUNT_MARK_BONUS",
    "HUNT_MARK_SECONDS",
    "REPAIRABLE_KINDS",
    "ROOT_RESIST_SECONDS",
    "ROOT_RESIST_SLOW_MULT",
    "TRIBE_BEAST_KINDS",
    "TRIBE_BONUS_CAP",
)


# ---------------------------------------------------------------- 辅助函数

def property_banner(number, title):
    print("Feature: %s, Property %d: %s" % (FEATURE, number, title))


def make_room(tag, faction_a="tribe", faction_b="tech", neutrals=False,
              selected_map="iron_river_duel"):
    """两人房间：A 默认部落、B 默认钢铁；中立默认关闭，地形压平。"""
    a = server.create_human("A", server.COLORS[0])
    b = server.create_human("B", server.COLORS[1])
    a["faction"] = faction_a
    b["faction"] = faction_b
    room = {
        "id": tag, "name": "tribe redesign test", "status": "lobby",
        "hostId": a["id"],
        "players": {a["id"]: a, b["id"]: b},
        "chat": [], "game": None, "createdAt": time.time(),
        "selectedMap": selected_map,
        "neutrals": neutrals,
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
    """只留 keep 里的单位；清空弹丸、中立营与中立建筑，保留单位原地待命。"""
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


# ---------------------------------------------------------------- 测试分节

def test_beast_kinds():
    print("=== Test 1: 部落野兽集合 = 目录全部兽甲单位 ===")
    beasts = catalog.TRIBE_BEAST_KINDS
    assert isinstance(beasts, frozenset), type(beasts)
    assert beasts == frozenset(
        ("wolf", "spider", "scorpion", "mammoth", "panda")), sorted(beasts)
    armored = frozenset(kind for kind, definition in catalog.UNIT_TYPES.items()
                        if definition.get("armor") == "beast")
    assert beasts == armored, (sorted(beasts), sorted(armored))
    for kind in sorted(beasts):
        assert catalog.kind_faction(kind) == "tribe", kind
    print("  TRIBE_BEAST_KINDS == {armor == beast} / 全属部落: PASS")


def test_repairable_kinds():
    print("\n=== Test 2: 维修集合 = 载具 ∪ 部落野兽 ===")
    repairable = catalog.REPAIRABLE_KINDS
    assert isinstance(repairable, frozenset), type(repairable)
    assert repairable == catalog.VEHICLE_KINDS | catalog.TRIBE_BEAST_KINDS
    # 野兽不是载具：维修集合比载具集合恰好多出全部部落野兽；
    # 扑咬 ×0、is_dog_prey、BOT_SCOUT_VEHICLES 仍只读 VEHICLE_KINDS。
    extra = repairable - catalog.VEHICLE_KINDS
    assert extra == catalog.TRIBE_BEAST_KINDS, sorted(extra)
    unknown = repairable - frozenset(catalog.UNIT_TYPES)
    assert not unknown, sorted(unknown)
    print("  REPAIRABLE_KINDS 组成 / 野兽不入载具集合: PASS")


def test_constants():
    print("\n=== Test 3: 猎印 / 加成封顶 / 定身抗性常量 ===")
    assert catalog.HUNT_MARK_SECONDS == 4.0, catalog.HUNT_MARK_SECONDS
    assert catalog.HUNT_MARK_BONUS == 1.15, catalog.HUNT_MARK_BONUS
    assert catalog.TRIBE_BONUS_CAP == 1.45, catalog.TRIBE_BONUS_CAP
    assert catalog.ROOT_RESIST_SECONDS == 1.0, catalog.ROOT_RESIST_SECONDS
    assert catalog.ROOT_RESIST_SLOW_MULT == 0.5, catalog.ROOT_RESIST_SLOW_MULT
    print("  HUNT_MARK_* / TRIBE_BONUS_CAP / ROOT_RESIST_*: PASS")


def test_server_reexports():
    print("\n=== Test 4: server 再导出 catalog 新符号 ===")
    for name in REEXPORTED_NAMES:
        assert hasattr(catalog, name), "catalog 缺少 %s" % name
        assert hasattr(server, name), "server 未再导出 %s" % name
        assert getattr(server, name) is getattr(catalog, name), name
    print("  %d 个符号 server.X is catalog.X: PASS" % len(REEXPORTED_NAMES))


def property_hunt_marks():
    property_banner(4, "猎印来源、刷新、过期与单位守卫")
    rng = random.Random(401)
    for _ in range(240):
        source = rng.choice(sorted(server.UNIT_TYPES))
        target = (server.make_unit("tank", "b", 1000, 1000) if rng.random() < .8
                  else server.make_structure("hq", "b", 1000, 1000))
        target["huntMarkTimer"] = 0.0
        if rng.random() < .2:
            target["hp"] = 0
        server.apply_hit_status({"sourceKind": source}, target)
        valid = source in server.HUNT_MARK_SOURCES and target["id"].startswith("u") and target["hp"] > 0
        assert target["huntMarkTimer"] == (4.0 if valid else 0.0)
        if valid:
            server.tick_status_timers(target, .8)
            server.apply_hunt_mark({"sourceKind": source}, target)
            assert target["huntMarkTimer"] == 4.0
            assert server.public_unit(target)["marked"] is True
            server.tick_status_timers(target, 4.0)
            assert "marked" not in server.public_unit(target)


def settle_shot(room, attacker, target, bonus=1.0):
    game = room["game"]
    before = target["hp"]
    server.launch_projectile(game, attacker, target, server.UNIT_TYPES[attacker["kind"]],
                             bonus, tribe_bonus=bonus)
    for _ in range(80):
        server.tick_projectiles(room, .05, {u["id"]: u for u in game["units"]})
        if not game["projectiles"]:
            break
    assert not game["projectiles"]
    return before - target["hp"]


def property_attack_bonus():
    property_banner(5, "号令按敌我与距离判定，连乘封顶与弹丸结算")
    room, a, b = make_room("BONUS")
    game = room["game"]
    rng = random.Random(501)
    for _ in range(240):
        kind = rng.choice(sorted(server.TRIBE_BEAST_KINDS))
        beast = server.make_unit(kind, a["id"], 2000, 2000)
        foe = server.make_unit("tank", b["id"], 2080, 2000)
        foe["hp"] = 10000.0
        distance = rng.uniform(0, 300)
        owner = rng.choice((a["id"], "ally", b["id"]))
        tamer = server.make_unit("tamer", owner, 2000 + distance, 2000)
        duplicate = server.make_unit("tamer", owner, tamer["x"], tamer["y"])
        game["playerTeams"] = {a["id"]: 1, "ally": 1, b["id"]: 2}
        if rng.random() < .2:
            tamer["hp"] = duplicate["hp"] = 0
        raging = kind == "panda" and rng.random() < .5
        marked = rng.random() < .5
        foe["huntMarkTimer"] = 4.0 if marked else 0.0
        isolate(game, beast, foe, tamer, duplicate)
        aura = 1.1 if owner != b["id"] and distance <= 220 and tamer["hp"] > 0 else 1.0
        rage = 1.25 if raging else 1.0
        expected = min(1.45, aura * rage * (1.15 if marked else 1.0))
        bonus = server.tribe_attack_bonus(game, beast, raging)
        assert abs(bonus - aura * rage) < 1e-9
        damage = settle_shot(room, beast, foe, bonus)
        dtype = server.UNIT_TYPES[kind]["damageType"]
        expected *= server.UNIT_TYPES[kind]["damage"] * server.damage_armor_multiplier(dtype, "heavy")
        assert abs(damage - expected) < 1e-6, (kind, damage, expected)
    # 毒伤直接走 tick_dot，不再吃号令与猎印；目标侧逐个结算溅射。
    spider = server.make_unit("spider", a["id"], 2000, 2000)
    foe = server.make_unit("tank", b["id"], 2080, 2000)
    foe["huntMarkTimer"] = 4.0
    isolate(game, spider, foe)
    server.apply_dot({"dot": server.UNIT_TYPES["spider"]["dot"], "owner": a["id"],
                      "sourceKind": "spider", "sourceId": spider["id"]}, foe)
    before = foe["hp"]
    server.tick_dot(room, foe, .1)
    assert abs(before - foe["hp"] - 14 * .1 * .55) < 1e-6
    # 号令 + 猎印巨蝎尾刺 217.833，三刺击毁坦克。
    scorpion = server.make_unit("scorpion", a["id"], 2000, 2000)
    foe = server.make_unit("tank", b["id"], 2080, 2000)
    foe["huntMarkTimer"] = 4.0
    isolate(game, scorpion, foe)
    assert abs(settle_shot(room, scorpion, foe, 1.1) - 217.833) < 1e-6
    settle_shot(room, scorpion, foe, 1.1)
    settle_shot(room, scorpion, foe, 1.1)
    assert foe["hp"] <= 0


def property_tower_poison():
    property_banner(6, "毒矢 ap 直伤、范围内挂 venom 毒、友军免疫")
    room, a, b = make_room("POISON")
    game = room["game"]
    rng = random.Random(601)
    tower = server.make_structure("ttoxtower", a["id"], 1900, 2000)
    for _ in range(240):
        target = server.make_unit("tank", b["id"], 2000, 2000)
        offset = rng.uniform(0, 50)
        bystander = server.make_unit("rifle", b["id"], 2000 + offset, 2000)
        ally = server.make_unit("spear", a["id"], 2000, 2000)
        isolate(game, target, bystander, ally)
        server.launch_projectile(game, tower, target, server.STRUCTURE_TYPES["ttoxtower"])
        server.tick_projectiles(room, 1.0)
        assert abs(620 - target["hp"] - 34 * 2.1) < 1e-6
        assert target["dotDps"] == 16 and target["dotDamageType"] == "venom"
        assert bool(bystander["dotTimer"]) == (offset < 28)
        assert ally["hp"] == ally["maxHp"] and not ally["dotTimer"]


def property_trap_charges():
    property_banner(7, "兽夹两次充能、重新上膛与静默移除")
    room, a, b = make_room("CHARGES")
    game = room["game"]
    rng = random.Random(701)
    for _ in range(200):
        trap = server.make_structure("ttrap", a["id"], 2000, 2000)
        foe = server.make_unit("tank", b["id"], 2005, 2000)
        ally = server.make_unit("wolf", a["id"], 2005, 2000)
        isolate(game, foe, ally)
        remain = 2.2
        while remain > 0:
            dt = min(remain, rng.uniform(.01, .3))
            server.tick_trap_structure(room, trap, dt)
            remain = max(0.0, remain - dt)
        assert trap["armed"] and trap["charges"] == 2
        server.tick_trap_structure(room, trap, .05)
        assert trap["charges"] == 1 and trap["hp"] > 0
        assert trap["armTimer"] == 8.0 and not trap["armed"]
        assert server.public_structure(trap)["charges"] == 1
        server.tick_trap_structure(room, trap, 7.9)
        assert not trap["armed"]
        server.tick_trap_structure(room, trap, .11)
        server.tick_trap_structure(room, trap, .05)
        assert trap["charges"] == 0 and trap["hp"] == 0
        assert trap["_silentRemoval"] and trap["_combatDestroyed"]
        assert ally["hp"] == ally["maxHp"] and not ally["slowTimer"]


def property_repair_and_bite():
    property_banner(8, "治疗集合与扑咬集合分离，祭坛治疗全流程")
    room, a, b = make_room("HEAL")
    game = room["game"]
    altar = give(game, a["id"], "taltar", 2000, 2000)
    rng = random.Random(801)
    for _ in range(200):
        kind = rng.choice(sorted(server.UNIT_TYPES))
        unit = server.make_unit(kind, a["id"], 2010, 2000)
        unit["hp"] *= .5
        isolate(game, unit)
        before_cash = a["cash"] = 10000.0
        if kind in server.REPAIRABLE_KINDS:
            server.issue_repair(game, a["id"], [unit["id"]], altar["id"])
            before = unit["hp"]
            server.tick_repair_unit(room, unit, .1, None, {}, server.FLAT_TERRAIN)
            restored = unit["hp"] - before
            assert restored > 0
            assert abs(before_cash - a["cash"] - restored * server.REPAIR_COST_PER_HP) < 1e-6
        else:
            expect_error("受损载具", lambda: server.issue_repair(game, a["id"], [unit["id"]], altar["id"]))
            unit["order"] = "repair"
            unit["repairTargetId"] = altar["id"]
            server.tick_repair_unit(room, unit, .1, None, {}, server.FLAT_TERRAIN)
            assert unit["order"] == "guard" and a["cash"] == before_cash
        before = unit["hp"]
        server.apply_damage(room, unit, 1, b["id"], "bite", game)
        if kind in server.VEHICLE_KINDS:
            assert unit["hp"] == before
    wolf = server.make_unit("wolf", a["id"], 2300, 2000)
    wolf["hp"] = 50.0
    isolate(game, wolf)
    a["cash"] = 10000.0
    server.issue_repair(game, a["id"], [wolf["id"]], altar["id"])
    for _ in range(200):
        server.tick_repair_unit(room, wolf, .05, None, {}, server.FLAT_TERRAIN)
        if wolf["order"] == "guard":
            break
    assert wolf["hp"] == 200 and wolf["order"] == "guard"
    assert math.hypot(wolf["x"] - altar["x"], wolf["y"] - altar["y"]) < 100
    assert abs(a["cash"] - (10000 - 150 * .35)) < 1e-6


def property_bot_tamers():
    property_banner(9, "驯兽师过滤完整枚举，中立、野兽与含队列存量")
    room, a, b = make_room("FILTER")
    game = room["game"]
    camp = give(game, a["id"], "tcamp")
    for enabled in (False, True):
        for target in (False, True):
            for beasts in range(7):
                for stock in range(4):
                    for choices in ([], ["spear"], ["tamer"], ["tamer", "spear", "tamer"]):
                        room["neutrals"] = game["neutrals"] = enabled
                        units = [server.make_unit("wolf", a["id"], 2000, 2000) for _ in range(beasts)]
                        if target:
                            units.append(server.make_unit("rifle", server.NEUTRAL_OWNER, 2200, 2000))
                        isolate(game, *units)
                        camp["queue"] = [{"kind": "tamer"} for _ in range(stock)]
                        expected = stock < 2 and ((enabled and target) or beasts >= 3)
                        result = server.bot_filter_choices(room, a, choices)
                        assert result == (choices if expected else [k for k in choices if k != "tamer"])
    roles = {"barracks", "factory"}
    scout = server.bot_empty_scout()
    scout["vehicles"] = 3
    choices = server.bot_unit_choices("tribe", roles, server.BOT_PHASE_COMMIT, scout, False, False, 2, False)
    assert "javelin" in choices and "scorpion" in choices and "wolf" not in choices
    inbound = server.bot_unit_choices("tribe", roles, server.BOT_PHASE_COMMIT, scout, False, False, 2, True)
    assert inbound == ["javelin", "slinger", "spear"]


def test_new_units_and_garrison():
    print("\n=== 新兵种生产、克制与守军兼容 ===")
    room, a, b = make_room("NEWUNITS")
    game = room["game"]
    a["cash"] = b["cash"] = 99999
    give(game, a["id"], "tcamp")
    server.queue_unit(room, a["id"], "javelin")
    give(game, a["id"], "tpen")
    server.queue_unit(room, a["id"], "scorpion")
    expect_error("前置", lambda: server.queue_unit(room, a["id"], "catapult"))
    give(game, a["id"], "taltar")
    server.queue_unit(room, a["id"], "catapult")
    for kind in ("javelin", "catapult"):
        expect_error("阵营", lambda: server.queue_unit(room, b["id"], kind))
    for kind, damage in (("tank", 60), ("scout", 52), ("rifle", 30)):
        unit = server.make_unit(kind, b["id"], 2000, 2000)
        before = unit["hp"]
        server.apply_damage(room, unit, 40, a["id"], "rocket", game)
        assert abs(before - unit["hp"] - damage) < 1e-6
    for faction in ("tech", "magic", "tribe"):
        garrison = server.faction_start_garrison(faction)
        assert len(garrison) <= len(server.START_GARRISON_OFFSETS)
        assert all(server.kind_faction(k) == faction for k in garrison)
    assert server.faction_start_garrison("tech") == ["rifle"] * 3 + ["tank"]
    assert server.faction_start_garrison("magic") == ["mage"] * 3 + ["golem"]
    assert server.faction_start_garrison("tribe") == ["spear"] * 3 + ["wolf", "javelin"]

    # 自动索敌优先建筑，手动点名单位保留；炮弹按 siege 拆建筑。
    catapult = server.make_unit("catapult", a["id"], 2000, 2000)
    tank = server.make_unit("tank", b["id"], 2080, 2000)
    tower = server.make_structure("turret", b["id"], 2200, 2000)
    # 坦克随机冷却/扫描就绪时会回击，不能用 projectiles[-1] 当投石车开火结果。
    tank["scan"] = tank["cooldown"] = 99.0
    isolate(game, catapult, tank)
    game["structures"] = [tower]
    catapult["order"] = "guard"
    catapult["scan"] = catapult["cooldown"] = 0
    server.tick_units(room, .05)
    assert any(shot.get("sourceId") == catapult["id"] and shot.get("targetId") == tower["id"]
               for shot in game["projectiles"])
    before = tower["hp"]
    server.tick_projectiles(room, 2.0)
    assert abs(before - tower["hp"] - 171) < 1e-6
    server.issue_attack(game, a["id"], [catapult["id"]], tank["id"])
    catapult["cooldown"] = 0
    server.tick_units(room, .05)
    assert any(shot.get("sourceId") == catapult["id"] and shot.get("targetId") == tank["id"]
               for shot in game["projectiles"])
    # 真实开火路径会记录攻方号令倍率；命中逐个读取目标猎印。
    scorpion = server.make_unit("scorpion", a["id"], 2000, 2000)
    tamer = server.make_unit("tamer", a["id"], 2100, 2100)
    tank["hp"] = tank["maxHp"]
    tank["huntMarkTimer"] = 4.0
    isolate(game, scorpion, tamer, tank)
    server.issue_attack(game, a["id"], [scorpion["id"]], tank["id"])
    scorpion["cooldown"] = 0
    server.tick_units(room, .05)
    shot = next(q for q in game["projectiles"] if q["sourceId"] == scorpion["id"])
    assert abs(shot["tribeBonus"] - 1.1) < 1e-9
    assert abs(shot["damage"] - 90.2) < 1e-9

    # 钢铁、秘法前四守军的 kind、创建顺序与相对落位保持一致。
    for faction in ("tech", "magic", "tribe"):
        fresh_room, player, _ = make_room("GARRISON", faction_a=faction)
        fresh_game = fresh_room["game"]
        hq = next(s for s in fresh_game["structures"] if s["owner"] == player["id"]
                  and server.structure_role(s["kind"]) == "hq")
        garrison = [u for u in fresh_game["units"] if u["owner"] == player["id"]
                    and server.unit_role(u["kind"]) != "harvester"]
        assert [u["kind"] for u in garrison] == server.faction_start_garrison(faction)
        for unit, (dx, dy) in zip(garrison, server.START_GARRISON_OFFSETS):
            assert abs(abs(unit["x"] - hq["x"]) - dx) < .01
            assert abs(abs(unit["y"] - hq["y"]) - dy) < .01


def test_bot_tamer_smoke():
    print("\n=== 无中立地图 bot 驯兽师上限冒烟 ===")
    room, a, b = make_room("BOTCAP")
    game = room["game"]
    a["isBot"] = True
    a["cash"] = 100000.0
    game["elapsed"] = 240.0
    for kind in ("tcamp", "tpen", "taltar"):
        give(game, a["id"], kind)
    game["units"].extend(server.make_unit("wolf", a["id"], 900, 900) for _ in range(3))
    for _ in range(40):
        game["elapsed"] += .6
        server.tick_bots(room)
        assert server.bot_kind_stock(game, a["id"], "tamer") <= 2
        server.tick_structures(room, .5)
    assert server.bot_kind_stock(game, a["id"], "tamer") >= 1


def main():
    test_beast_kinds()
    test_repairable_kinds()
    test_constants()
    test_server_reexports()
    property_hunt_marks()
    property_attack_bonus()
    property_tower_poison()
    property_trap_charges()
    property_repair_and_bite()
    property_bot_tamers()
    test_new_units_and_garrison()
    test_bot_tamer_smoke()
    print("\n=== 原始部落重设计测试全部通过 ===")


if __name__ == "__main__":
    main()
