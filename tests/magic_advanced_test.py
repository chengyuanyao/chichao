#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""秘法会进阶兵种：晶铠卫士 / 裂地晶兽，以及巨龙改走圣泉门槛。
   1) 目录与阵营登记齐全
   2) 圣泉门槛：只有法阵不够，缺圣泉拒绝排队
   3) 魔法能生产、科技不能；place_structure 阵营门槛仍在
   4) 混甲：磁暴/狙击不再按纯魔导 ×2；军犬不把构装当猎物
   5) 裂地晶兽用 siege 拆建筑
"""

from __future__ import print_function

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import server


ADVANCED = ("warden", "colossus", "dragon")


def make_room(tag, magic_b=True):
    a = server.create_human("A", server.COLORS[0])
    b = server.create_human("B", server.COLORS[1])
    if magic_b:
        b["faction"] = "magic"
    room = {
        "id": tag, "name": "magic adv test", "status": "lobby",
        "hostId": a["id"],
        "players": {a["id"]: a, b["id"]: b},
        "chat": [], "game": None, "createdAt": time.time(),
    }
    server.start_game(room)
    return room, a, b


def give(game, pid, kind):
    s = server.make_structure(kind, pid, 900, 900, True)
    game["structures"].append(s)
    return s


def main():
    print("=== Test 1: 目录 / 阵营 / 圣泉门槛字段 ===")
    for kind in ADVANCED:
        d = server.UNIT_TYPES[kind]
        for field in ("name", "cost", "hp", "speed", "damage", "range",
                      "cooldown", "size", "build", "producer", "projectile",
                      "projectileSpeed", "splash", "sight", "armor",
                      "damageType", "requires"):
            assert field in d, "%s 缺字段 %s" % (kind, field)
        assert d["producer"] == "mcircle", kind
        assert d["requires"] == ["mspring"], (kind, d["requires"])
        assert d["faction"] == "magic", kind
        assert kind in server.MAGIC_UNITS, kind
        assert kind in server.VEHICLE_KINDS, kind
    assert server.UNIT_TYPES["colossus"]["damageType"] == "siege"
    assert server.UNIT_TYPES["warden"]["damageType"] == "magic"
    assert server.UNIT_TYPES["dragon"]["damageType"] == "magic"
    catalog = server.public_catalog()
    for kind in ADVANCED:
        entry = catalog["units"][kind]
        assert entry["name"] == server.UNIT_TYPES[kind]["name"]
        assert entry["cost"] == server.UNIT_TYPES[kind]["cost"]
        assert entry["faction"] == "magic"
        assert entry["requires"] == ["mspring"]
        assert entry["repairable"] is True
        assert entry["producer"] == "mcircle"
    print("  定义/阵营/目录 requires: PASS")

    print("\n=== Test 2: 只有法阵不能出进阶；补圣泉放行 ===")
    room, a, b = make_room("MADV01")
    game = room["game"]
    b["cash"] = 99999
    give(game, b["id"], "mcircle")
    for kind in ADVANCED:
        try:
            server.queue_unit(room, b["id"], kind)
            raise AssertionError("无圣泉时不该能出 %s" % kind)
        except ValueError as exc:
            assert "前置建筑" in str(exc), str(exc)
    give(game, b["id"], "mspring")
    for kind in ADVANCED:
        server.queue_unit(room, b["id"], kind)
    queued = [item["kind"] for s in game["structures"]
              if s["owner"] == b["id"] for item in s["queue"]]
    for kind in ADVANCED:
        assert kind in queued, queued
    print("  缺圣泉拒绝 / 补圣泉放行: PASS")

    print("\n=== Test 3: 阵营门槛（科技不能产，魔法不能建科技）===")
    room, a, b = make_room("MADV02")
    game = room["game"]
    a["cash"] = b["cash"] = 99999
    give(game, a["id"], "factory")
    give(game, a["id"], "repair")
    give(game, b["id"], "mcircle")
    give(game, b["id"], "mspring")
    for kind in ("warden", "colossus"):
        try:
            server.queue_unit(room, a["id"], kind)
            raise AssertionError("科技不该能产 %s" % kind)
        except ValueError as exc:
            assert "阵营" in str(exc), str(exc)
    server.queue_unit(room, b["id"], "warden")
    server.queue_unit(room, b["id"], "colossus")
    try:
        server.place_structure(room, b["id"], "turret", 800, 800, free=True)
        raise AssertionError("魔法不该能放置科技炮塔")
    except ValueError as exc:
        assert "阵营" in str(exc), str(exc)
    try:
        server.place_structure(room, a["id"], "mtower", 800, 800, free=True)
        raise AssertionError("科技不该能放置奥术塔")
    except ValueError as exc:
        assert "阵营" in str(exc), str(exc)
    print("  跨阵营生产/放置仍拦截: PASS")

    print("\n=== Test 4: 混甲克制 + 军犬不扑构装 ===")
    room, a, b = make_room("MADV03")
    game = room["game"]
    warden = server.make_unit("warden", b["id"], 9000, 9000)
    warden["hp"] = 1000
    game["units"].append(warden)
    before = warden["hp"]
    server.apply_damage(room, warden, 100, a["id"], "tesla", game)
    assert abs((before - warden["hp"]) - 135.0) < 0.1, before - warden["hp"]
    print("  tesla vs 混甲: ×1.35 PASS")
    before = warden["hp"]
    server.apply_damage(room, warden, 100, a["id"], "sniper", game)
    assert abs((before - warden["hp"]) - 27.5) < 0.1, before - warden["hp"]
    print("  sniper vs 混甲: ×0.275 PASS")
    before = warden["hp"]
    server.apply_damage(room, warden, 60, a["id"], "bite", game)
    assert abs(before - warden["hp"]) < 0.1, before - warden["hp"]
    print("  bite vs 混甲: ×0 PASS")
    assert not server.is_dog_prey("warden")
    assert not server.is_dog_prey("colossus")
    assert server.is_dog_prey("mage")
    print("  军犬猎物不含混甲构装: PASS")

    print("\n=== Test 5: 裂地晶兽 siege 拆建筑 ===")
    room, a, b = make_room("MADV04")
    game = room["game"]
    turret = give(game, a["id"], "turret")
    before = turret["hp"]
    server.apply_damage(room, turret, 100, b["id"], "siege", game)
    assert abs((before - turret["hp"]) - 180.0) < 0.1, before - turret["hp"]
    print("  siege vs 建筑: ×1.8 PASS")
    mage_hp = server.make_unit("mage", a["id"], 9100, 9100)
    mage_hp["hp"] = 500
    game["units"].append(mage_hp)
    before = mage_hp["hp"]
    server.apply_damage(room, mage_hp, 100, b["id"], "siege", game)
    # siege 表没有 arcane 行，缺省 1.0
    assert abs((before - mage_hp["hp"]) - 100.0) < 0.1, before - mage_hp["hp"]
    print("  siege vs 魔导缺省 ×1.0 PASS")

    print("\n=== Test 6: 魔法 AI 在圣泉后会排进阶兵 ===")
    room, a, b = make_room("MADV05")
    game = room["game"]
    b["isBot"] = True
    b["cash"] = 99999
    give(game, b["id"], "mtemple")
    give(game, b["id"], "mcircle")
    give(game, b["id"], "mspring")
    server.random.seed(20260818)
    produced = set()
    for _ in range(120):
        server.tick_bots(room)
        for structure in game["structures"]:
            if structure["owner"] != b["id"]:
                continue
            for item in structure["queue"]:
                produced.add(item["kind"])
            # 队列满了会挡住后续掷骰；腾空再试，只为证明 AI 会点进阶。
            if len(structure["queue"]) >= 5 and not produced.intersection(ADVANCED):
                structure["queue"][:] = []
        if produced.intersection(ADVANCED):
            break
    assert produced.intersection(ADVANCED), produced
    assert produced.issubset(server.MAGIC_UNITS), produced
    print("  AI 排出 %s: PASS" % sorted(produced.intersection(ADVANCED)))

    print("\n=== 秘法会进阶兵种测试全部通过 ===")


if __name__ == "__main__":
    main()
