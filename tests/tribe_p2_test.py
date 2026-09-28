#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""原始部落 P2：竹甲熊猫 + 投石猎手。
   1) 目录数字 / 阵营 / 解锁 / 无自爆、非载具
   2) 营地即可训投石；熊猫需围栏+血祭坛
   3) 跨阵营拒绝；训花费
   4) 熊猫低血狂暴迟滞：<0.40 进入，>0.60 解除，输出 ×1.25
   5) smash 拆建筑；投石 rock/bullet 溅射
   6) bot：中期营地投石，祭坛后熊猫与狼/蛛混编
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
        "id": tag, "name": "tribe p2 test", "status": "lobby",
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


def main():
    print("=== Test 1: 目录 / 阵营 / 无自爆 ===")
    panda = server.UNIT_TYPES["panda"]
    slinger = server.UNIT_TYPES["slinger"]
    wolf = server.UNIT_TYPES["wolf"]
    mammoth = server.UNIT_TYPES["mammoth"]
    spear = server.UNIT_TYPES["spear"]
    assert panda["name"] == "竹甲熊猫"
    assert panda["faction"] == "tribe"
    assert panda["producer"] == "tpen"
    assert panda["requires"] == ["taltar"]
    assert panda["cost"] == 980
    assert panda["hp"] == 860
    assert panda["speed"] == 88.0
    assert panda["size"] == 16.0
    assert panda["build"] == 9.0
    assert panda["damage"] == 58.0
    assert panda["range"] == 42.0
    assert panda["cooldown"] == 1.05
    assert panda["splash"] == 22.0
    assert panda["projectile"] == "smash"
    assert panda["projectileSpeed"] == 1000.0
    assert panda["armor"] == "beast"
    assert panda["damageType"] == "smash"
    assert panda["sight"] == 380.0
    assert wolf["hp"] < panda["hp"] < mammoth["hp"]
    assert mammoth["speed"] < panda["speed"] < wolf["speed"]
    assert slinger["name"] == "投石猎手"
    assert slinger["faction"] == "tribe"
    assert slinger["producer"] == "tcamp"
    assert slinger.get("requires") in (None, [])
    assert slinger["cost"] == 300
    assert slinger["hp"] == 100
    assert slinger["speed"] == 100.0
    assert slinger["size"] == 10.5
    assert slinger["build"] == 4.5
    assert slinger["damage"] == 26.0
    assert slinger["range"] == 185.0
    assert slinger["cooldown"] == 1.15
    assert slinger["splash"] == 18.0
    assert slinger["projectile"] == "rock"
    assert slinger["projectileSpeed"] == 420.0
    assert slinger["armor"] == "infantry"
    assert slinger["damageType"] == "bullet"
    assert slinger["sight"] == 390.0
    assert spear["range"] < slinger["range"]
    for kind in ("panda", "slinger"):
        assert kind in server.TRIBE_UNITS
        assert kind not in server.VEHICLE_KINDS
        assert kind not in server.SUICIDE_KINDS
    assert not server.is_dog_prey("panda")
    assert server.is_dog_prey("slinger")
    assert server.bot_suicide_kind("tribe") is None
    assert server.PANDA_RAGE_ENTER == 0.40
    assert server.PANDA_RAGE_EXIT == 0.60
    assert server.PANDA_RAGE_DAMAGE == 1.25
    catalog = server.public_catalog()
    assert catalog["units"]["panda"]["name"] == "竹甲熊猫"
    assert catalog["units"]["panda"]["cost"] == 980
    assert catalog["units"]["panda"]["producer"] == "tpen"
    assert catalog["units"]["panda"]["requires"] == ["taltar"]
    assert catalog["units"]["panda"]["repairable"] is False
    assert catalog["units"]["panda"]["canVeteran"] is True
    assert catalog["units"]["slinger"]["name"] == "投石猎手"
    assert catalog["units"]["slinger"]["cost"] == 300
    assert catalog["units"]["slinger"]["producer"] == "tcamp"
    assert catalog["units"]["slinger"]["requires"] == []
    assert catalog["units"]["slinger"]["repairable"] is False
    assert catalog["units"]["slinger"]["canVeteran"] is True
    print("  定义/阵营/目录: PASS")

    print("\n=== Test 2: 解锁与花费 ===")
    room, a, b = make_room("TP201")
    game = room["game"]
    a["cash"] = 99999
    expect_error("生产建筑", lambda: server.queue_unit(room, a["id"], "slinger"))
    expect_error("生产建筑", lambda: server.queue_unit(room, a["id"], "panda"))
    give(game, a["id"], "tcamp")
    a["cash"] = 299
    expect_error("资金", lambda: server.queue_unit(room, a["id"], "slinger"))
    a["cash"] = 300
    server.queue_unit(room, a["id"], "slinger")
    assert a["cash"] == 0
    assert "slinger" in queued_kinds(game, a["id"])
    expect_error("生产建筑", lambda: server.queue_unit(room, a["id"], "panda"))
    give(game, a["id"], "tpen")
    a["cash"] = 980
    expect_error("前置建筑", lambda: server.queue_unit(room, a["id"], "panda"))
    give(game, a["id"], "taltar")
    a["cash"] = 979
    expect_error("资金", lambda: server.queue_unit(room, a["id"], "panda"))
    a["cash"] = 980
    server.queue_unit(room, a["id"], "panda")
    assert a["cash"] == 0
    assert "panda" in queued_kinds(game, a["id"])
    print("  营地投石 / 祭坛熊猫 / 花费: PASS")

    print("\n=== Test 3: 跨阵营拒绝 ===")
    room, a, b = make_room("TP202", tribe_a=False, magic_b=True)
    game = room["game"]
    a["cash"] = b["cash"] = 99999
    give(game, a["id"], "barracks")
    give(game, a["id"], "factory")
    give(game, a["id"], "repair")
    give(game, b["id"], "mtemple")
    give(game, b["id"], "mcircle")
    give(game, b["id"], "mspring")
    expect_error("阵营", lambda: server.queue_unit(room, a["id"], "slinger"))
    expect_error("阵营", lambda: server.queue_unit(room, a["id"], "panda"))
    expect_error("阵营", lambda: server.queue_unit(room, b["id"], "slinger"))
    expect_error("阵营", lambda: server.queue_unit(room, b["id"], "panda"))
    print("  钢铁/秘法拦截: PASS")

    print("\n=== Test 4: 熊猫狂暴迟滞与输出 ===")
    room, a, b = make_room("TP203")
    game = room["game"]
    panda_u = server.make_unit("panda", a["id"], 1000, 1000)
    rifle = server.make_unit("rifle", b["id"], 1030, 1000)
    isolate(game, panda_u, rifle)
    assert panda_u.get("rage") is False
    assert server.update_panda_rage(panda_u) is False
    panda_u["hp"] = panda["hp"] * 0.39
    assert server.update_panda_rage(panda_u) is True
    assert panda_u["rage"] is True
    assert server.public_unit(panda_u).get("rage") is True
    panda_u["hp"] = panda["hp"] * 0.50
    assert server.update_panda_rage(panda_u) is True
    panda_u["hp"] = panda["hp"] * 0.61
    assert server.update_panda_rage(panda_u) is False
    assert panda_u["rage"] is False
    assert server.public_unit(panda_u).get("rage") is None
    wolf_u = server.make_unit("wolf", a["id"], 1100, 1000)
    wolf_u["hp"] = 10
    wolf_u["rage"] = True
    assert server.update_panda_rage(wolf_u) is False
    assert wolf_u["rage"] is False

    isolate(game, panda_u, rifle)
    panda_u["hp"] = panda["hp"] * 0.35
    panda_u["rage"] = False
    panda_u["order"] = "hold"
    panda_u["targetId"] = rifle["id"]
    panda_u["cooldown"] = 0.0
    rifle["hp"] = 10000.0
    rifle["order"] = "hold"
    rifle["targetId"] = None
    rifle["cooldown"] = 99.0
    rifle["scan"] = 99.0
    server.tick_units(room, 0.05)
    panda_shots = [shot for shot in game["projectiles"]
                   if shot.get("sourceKind") == "panda"]
    assert panda_shots, "狂暴熊猫应开火"
    raging_shot = panda_shots[-1]
    assert raging_shot["kind"] == "smash"
    assert abs(raging_shot["damage"] - panda["damage"] * 1.25) < 1e-6
    game["projectiles"] = []
    panda_u["hp"] = panda["hp"]
    panda_u["rage"] = True
    panda_u["cooldown"] = 0.0
    server.tick_units(room, 0.05)
    calm_shots = [shot for shot in game["projectiles"]
                  if shot.get("sourceKind") == "panda"]
    assert calm_shots, "满血熊猫应仍能开火"
    calm_shot = calm_shots[-1]
    assert abs(calm_shot["damage"] - panda["damage"]) < 1e-6
    print("  迟滞开关 / 开火 ×1.25: PASS")

    print("\n=== Test 5: smash 拆建筑与投石弹 ===")
    room, a, b = make_room("TP204")
    game = room["game"]
    hq = next(s for s in game["structures"]
              if s["owner"] == b["id"]
              and server.structure_role(s["kind"]) == "hq")
    before = hq["hp"]
    server.apply_damage(room, hq, 100, a["id"], "smash", game)
    assert abs((before - hq["hp"]) - 150.0) < 0.1
    slinger_u = server.make_unit("slinger", a["id"], 2000, 2000)
    rifle = server.make_unit("rifle", b["id"], 2140, 2000)
    isolate(game, slinger_u, rifle)
    game["structures"].append(hq)
    server.launch_projectile(game, slinger_u, rifle, slinger)
    shot = game["projectiles"][-1]
    assert shot["kind"] == "rock"
    assert shot.get("damageType") == "bullet"
    assert abs(shot.get("splash", 0.0) - 18.0) < 1e-6
    assert abs(shot["speed"] - 420.0) < 1e-6
    print("  smash ×1.50 / rock 弹: PASS")

    print("\n=== Test 6: 机器人接线 ===")
    scout = server.bot_empty_scout()
    opening = server.bot_support_choices(
        "tribe", set(["barracks", "factory"]), True, False, True, 2)
    assert "slinger" not in opening
    assert "panda" not in opening
    mid_camp = server.bot_support_choices(
        "tribe", set(["barracks"]), False, False, True, 2)
    assert "slinger" in mid_camp, mid_camp
    no_altar = server.bot_support_choices(
        "tribe", set(["factory"]), False, False, True, 2)
    assert "panda" not in no_altar
    with_altar = server.bot_support_choices(
        "tribe", set(["factory", "repair"]), False, False, True, 2)
    assert "panda" in with_altar and "wolf" in with_altar, with_altar
    late = server.bot_unit_choices(
        "tribe", set(["factory", "repair", "barracks"]), server.BOT_PHASE_CLOSE,
        scout, False, True, 2, False)
    assert "panda" in late and "slinger" in late, late
    assert server.bot_unit_is_factory("panda") is True
    assert server.bot_unit_is_factory("slinger") is False
    print("  中期投石 / 祭坛熊猫 / 无自爆: PASS")

    print("\n=== 原始部落 P2 测试全部通过 ===")


if __name__ == "__main__":
    main()
