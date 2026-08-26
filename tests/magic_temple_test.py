#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""秘法会圣殿补兵：晶刺 / 虹视使。
   1) 目录锁定：圣殿产、无圣泉门槛、魔导甲、魔法伤、造价血量
   2) 阵营门槛：科技不能产；魔法圣殿能产
   3) 军犬：一口咬不死晶刺，两口死；载具仍咬不动
   4) 大师 AI 法阵后仍排魔仆
"""

from __future__ import print_function

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import server

TEMPLE = ("imp", "oracle")


def make_room(tag, magic_b=True):
    a = server.create_human("A", server.COLORS[0])
    b = server.create_human("B", server.COLORS[1])
    if magic_b:
        b["faction"] = "magic"
    room = {
        "id": tag, "name": "magic temple test", "status": "lobby",
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
    print("=== Test 1: 目录 / 阵营 / 圣殿门槛 ===")
    imp = server.UNIT_TYPES["imp"]
    oracle = server.UNIT_TYPES["oracle"]
    for kind in TEMPLE:
        definition = server.UNIT_TYPES[kind]
        for field in ("name", "cost", "hp", "speed", "damage", "range",
                      "cooldown", "size", "build", "producer", "projectile",
                      "projectileSpeed", "splash", "sight", "armor",
                      "damageType"):
            assert field in definition, "%s 缺字段 %s" % (kind, field)
        assert definition["producer"] == "mtemple", kind
        assert not definition.get("requires"), (kind, definition.get("requires"))
        assert definition["armor"] == "arcane", kind
        assert definition["damageType"] == "magic", kind
        assert definition["splash"] == 0.0, kind
        assert definition["faction"] == "magic", kind
        assert kind in server.MAGIC_UNITS, kind
        assert kind not in server.VEHICLE_KINDS, kind
        assert kind not in server.SUICIDE_KINDS, kind
    assert imp["name"] == "晶刺"
    assert oracle["name"] == "虹视使"
    assert imp["cost"] == 200
    assert oracle["cost"] == 450
    assert imp["hp"] == 95
    assert oracle["hp"] == 80
    assert imp["speed"] == 120.0
    assert oracle["speed"] == 88.0
    assert imp["range"] == 90.0
    assert oracle["range"] == 300.0
    assert imp["damage"] == 18.0
    assert oracle["damage"] == 48.0
    assert imp["cooldown"] == 0.7
    assert oracle["cooldown"] == 1.55
    assert imp["sight"] == round(imp["range"] * 1.10, 3)
    assert oracle["sight"] == round(oracle["range"] * 1.10, 3)
    # 不抄钢铁突击/狙击数字
    assert imp["cost"] != server.UNIT_TYPES["rifle"]["cost"]
    assert oracle["cost"] != server.UNIT_TYPES["sniper"]["cost"]
    assert imp["hp"] != server.UNIT_TYPES["rifle"]["hp"]
    assert oracle["hp"] != server.UNIT_TYPES["sniper"]["hp"]
    catalog = server.public_catalog()
    for kind in TEMPLE:
        entry = catalog["units"][kind]
        assert entry["name"] == server.UNIT_TYPES[kind]["name"]
        assert entry["cost"] == server.UNIT_TYPES[kind]["cost"]
        assert entry["faction"] == "magic"
        assert entry["producer"] == "mtemple"
        assert entry["requires"] == []
        assert entry["repairable"] is False
    print("  定义/阵营/目录: PASS")

    print("\n=== Test 2: 科技不能产；魔法圣殿能产 ===")
    room, a, b = make_room("MTEMP01")
    game = room["game"]
    a["cash"] = b["cash"] = 99999
    give(game, a["id"], "barracks")
    give(game, b["id"], "mtemple")
    for kind in TEMPLE:
        try:
            server.queue_unit(room, a["id"], kind)
            raise AssertionError("科技不该能产 %s" % kind)
        except ValueError as exc:
            assert "阵营" in str(exc), str(exc)
    for kind in TEMPLE:
        server.queue_unit(room, b["id"], kind)
    queued = queued_kinds(game, b["id"])
    for kind in TEMPLE:
        assert kind in queued, queued
    # 无圣殿时魔法也排队不了
    room, a, b = make_room("MTEMP02")
    game = room["game"]
    b["cash"] = 99999
    try:
        server.queue_unit(room, b["id"], "imp")
        raise AssertionError("无圣殿不该能产晶刺")
    except ValueError as exc:
        assert "生产建筑" in str(exc), str(exc)
    print("  双向阵营门槛 / 圣殿放行: PASS")

    print("\n=== Test 3: 军犬一口咬不死晶刺，两口死；载具仍免疫 ===")
    bite = server.UNIT_TYPES["dog"]["damage"]
    expect = bite * server.DAMAGE_MULTIPLIER["bite"]["arcane"]
    assert abs(expect - 90.0) < 0.1, expect
    assert server.UNIT_TYPES["imp"]["hp"] > expect
    assert server.UNIT_TYPES["imp"]["hp"] <= expect * 2
    assert server.is_dog_prey("imp")
    assert server.is_dog_prey("oracle")
    assert not server.is_dog_prey("tank")
    assert not server.is_dog_prey("golem")
    room, a, b = make_room("MTEMP03")
    game = room["game"]
    victim = server.make_unit("imp", b["id"], 9000, 9000)
    game["units"].append(victim)
    server.apply_damage(room, victim, bite, a["id"], "bite", game)
    assert victim["hp"] > 0, "晶刺不该被一口咬死，剩 %s" % victim["hp"]
    leftover = victim["hp"]
    server.apply_damage(room, victim, bite, a["id"], "bite", game)
    assert victim["hp"] <= 0, "晶刺两口应死，一口后剩 %s" % leftover
    tank = server.make_unit("tank", b["id"], 9100, 9100)
    game["units"].append(tank)
    before = tank["hp"]
    server.apply_damage(room, tank, bite, a["id"], "bite", game)
    assert abs(tank["hp"] - before) < 0.001, "坦克不该掉血"
    print("  咬 90 / 晶刺 95 一口剩 5；坦克 0: PASS")

    print("\n=== Test 4: 法阵后仍排爆裂魔仆 ===")
    room, a, b = make_room("MTEMP04")
    game = room["game"]
    game["terrainCtx"] = server.FLAT_TERRAIN
    game["botClock"] = 999.0
    b["isBot"] = True
    b["cash"] = 99999
    b["buildQueue"] = [{"id": "busy", "kind": "mpower",
                        "remaining": 4.0, "total": 8.0, "ready": False}]
    give(game, b["id"], "mcircle")
    assert server.bot_should_train_suicide(game, b, "hexling")
    server.tick_bots(room)
    produced = queued_kinds(game, b["id"])
    assert "hexling" in produced, produced
    print("  无法阵外圣泉也排出 hexling: PASS")

    print("\n=== 秘法会圣殿补兵测试全部通过 ===")


if __name__ == "__main__":
    main()
