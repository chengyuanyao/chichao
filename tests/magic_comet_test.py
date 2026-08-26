#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""秘法会坠星台：东风快递同角色的超远曲射装甲。
   1) 目录锁定：魔法-only、法阵产、圣泉门槛、missile、造价/射程
   2) 圣殿单独不能出；科技不能产
   3) 军犬当载具：不当猎物，bite 不掉血
   4) 一发拆不掉满血总部
   5) 大师 AI 无圣泉时不出坠星台，开局仍先出魔仆
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
        "id": tag, "name": "comet test", "status": "lobby",
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
    comet = server.UNIT_TYPES["comet"]
    for field in ("name", "cost", "hp", "speed", "damage", "range",
                  "cooldown", "size", "build", "producer", "projectile",
                  "projectileSpeed", "splash", "sight", "armor",
                  "damageType", "requires"):
        assert field in comet, "comet 缺字段 %s" % field
    assert comet["name"] == "坠星台"
    assert comet["producer"] == "mcircle"
    assert comet["requires"] == ["mspring"]
    assert comet["faction"] == "magic"
    assert comet["cost"] == 2000
    assert comet["hp"] == 280
    assert comet["speed"] == 36.0
    assert comet["damage"] == 190.0
    assert comet["range"] == 520.0
    assert comet["cooldown"] == 5.2
    assert comet["size"] == 22.0
    assert comet["build"] == 18.0
    assert comet["splash"] == 110.0
    assert comet["sight"] == round(comet["range"] * 1.10, 3)
    assert comet["armor"] == "light"
    assert comet["damageType"] == "missile"
    assert comet["projectile"] == "comet"
    assert 150.0 <= comet["projectileSpeed"] <= 180.0
    assert comet["projectileSpeed"] <= server.UNIT_TYPES["v3"]["projectileSpeed"] + 20.0
    assert "comet" in server.MAGIC_UNITS
    assert "comet" in server.VEHICLE_KINDS
    assert "comet" not in server.SUICIDE_KINDS
    catalog = server.public_catalog()
    entry = catalog["units"]["comet"]
    assert entry["name"] == "坠星台"
    assert entry["cost"] == 2000
    assert entry["faction"] == "magic"
    assert entry["requires"] == ["mspring"]
    assert entry["producer"] == "mcircle"
    assert entry["repairable"] is True
    assert entry["damageType"] == "missile"
    print("  定义/阵营/目录/锁定数值: PASS")

    print("\n=== Test 2: 圣殿单独不能出；法阵缺圣泉拒绝；补圣泉放行 ===")
    room, a, b = make_room("CMT01")
    game = room["game"]
    b["cash"] = 99999
    give(game, b["id"], "mtemple")
    try:
        server.queue_unit(room, b["id"], "comet")
        raise AssertionError("只有圣殿不该能出坠星台")
    except ValueError as exc:
        assert "生产建筑" in str(exc) or "前置" in str(exc), str(exc)
    give(game, b["id"], "mcircle")
    try:
        server.queue_unit(room, b["id"], "comet")
        raise AssertionError("无法阵外圣泉不该能出坠星台")
    except ValueError as exc:
        assert "前置建筑" in str(exc), str(exc)
    give(game, b["id"], "mspring")
    server.queue_unit(room, b["id"], "comet")
    assert "comet" in queued_kinds(game, b["id"])
    print("  圣殿拒绝 / 缺圣泉拒绝 / 补圣泉放行: PASS")

    print("\n=== Test 3: 科技不能产坠星台 ===")
    room, a, b = make_room("CMT02")
    game = room["game"]
    a["cash"] = b["cash"] = 99999
    give(game, a["id"], "factory")
    give(game, a["id"], "repair")
    give(game, b["id"], "mcircle")
    give(game, b["id"], "mspring")
    try:
        server.queue_unit(room, a["id"], "comet")
        raise AssertionError("科技不该能产坠星台")
    except ValueError as exc:
        assert "阵营" in str(exc), str(exc)
    server.queue_unit(room, b["id"], "comet")
    print("  跨阵营拦截 / 魔法放行: PASS")

    print("\n=== Test 4: 军犬不扑、咬不动 ===")
    room, a, b = make_room("CMT03")
    game = room["game"]
    launcher = server.make_unit("comet", b["id"], 9000, 9000)
    game["units"].append(launcher)
    before = launcher["hp"]
    server.apply_damage(room, launcher, 60, a["id"], "bite", game)
    assert abs(launcher["hp"] - before) < 0.1, launcher["hp"]
    assert not server.is_dog_prey("comet")
    assert server.is_dog_prey("mage")
    game["units"].append(server.make_unit("comet", b["id"], 5050, 5000))
    game["units"].append(server.make_unit("mage", b["id"], 5080, 5000))
    pick = server.nearest_enemy_infantry(game, a["id"], 5000, 5000, 400)
    assert pick is not None and pick["kind"] == "mage", pick and pick["kind"]
    print("  bite ×0 / 不当猎物: PASS")

    print("\n=== Test 5: missile 拆建筑，一发拆不掉满血总部 ===")
    room, a, b = make_room("CMT04")
    game = room["game"]
    hq = next(s for s in game["structures"]
              if s["owner"] == a["id"] and server.structure_role(s["kind"]) == "hq")
    assert hq["hp"] == hq["maxHp"] == 2400
    before = hq["hp"]
    server.apply_damage(room, hq, comet["damage"], b["id"], "missile", game)
    dealt = before - hq["hp"]
    expect = comet["damage"] * server.DAMAGE_MULTIPLIER["missile"]["structure"]
    assert abs(dealt - expect) < 0.1, (dealt, expect)
    assert hq["hp"] > 0, hq["hp"]
    assert dealt < hq["maxHp"], (dealt, hq["maxHp"])
    assert expect == 285.0
    print("  190×1.50=285，总部剩 %s: PASS" % hq["hp"])

    print("\n=== Test 6: 大师 AI 无圣泉不出坠星台，仍先出魔仆 ===")
    room, a, b = make_room("CMT05")
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
                if "comet" not in produced:
                    structure["queue"][:] = []
    assert "comet" not in produced, produced
    assert "hexling" in produced, produced
    print("  无圣泉未排 comet，仍排 hexling: PASS")

    print("\n=== 坠星台测试全部通过 ===")


if __name__ == "__main__":
    main()
