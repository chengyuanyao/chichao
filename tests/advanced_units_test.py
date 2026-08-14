#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""高级兵种（天启坦克/磁暴步兵/光棱坦克）测试：
   1) 单位定义齐全、归入正确的生产方与克制表
   2) 二级科技门槛：磁暴需工厂，天启/光棱需维修厂，缺了则拒绝排队
   3) 新伤害类型 tesla / laser 的克制系数生效
"""

from __future__ import print_function

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import server


def make_room(tag):
    a = server.create_human("A", server.COLORS[0])
    b = server.create_human("B", server.COLORS[1])
    room = {
        "id": tag, "name": "adv test", "status": "lobby",
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
    print("=== Test 1: 单位定义齐全 ===")
    for kind in ("overlord", "tesla", "prism"):
        d = server.UNIT_TYPES[kind]
        for field in ("name", "cost", "hp", "speed", "damage", "range",
                      "cooldown", "size", "build", "producer", "projectile",
                      "projectileSpeed", "splash", "sight", "armor",
                      "damageType", "requires"):
            assert field in d, "%s 缺字段 %s" % (kind, field)
    assert server.UNIT_TYPES["overlord"]["producer"] == "factory"
    assert server.UNIT_TYPES["prism"]["producer"] == "factory"
    assert server.UNIT_TYPES["tesla"]["producer"] == "barracks"
    assert server.UNIT_TYPES["overlord"]["damageType"] == "shell"
    assert server.UNIT_TYPES["tesla"]["damageType"] == "tesla"
    assert server.UNIT_TYPES["prism"]["damageType"] == "laser"
    # 新伤害类型已入克制表；载具已入维修厂白名单（磁暴是步兵不算）
    assert "tesla" in server.DAMAGE_MULTIPLIER
    assert "laser" in server.DAMAGE_MULTIPLIER
    assert "overlord" in server.VEHICLE_KINDS
    assert "prism" in server.VEHICLE_KINDS
    assert "tesla" not in server.VEHICLE_KINDS
    print("  定义/克制表/载具归类: PASS")

    print("\n=== Test 2: 磁暴步兵需工厂 ===")
    room, a, b = make_room("ADV01")
    game = room["game"]
    a["cash"] = 99999
    give(game, a["id"], "barracks")   # 只有兵营，没有工厂
    try:
        server.queue_unit(room, a["id"], "tesla")
        raise AssertionError("无工厂时不该能出磁暴步兵")
    except ValueError as exc:
        assert "前置建筑" in str(exc), str(exc)
    give(game, a["id"], "factory")    # 补上工厂
    server.queue_unit(room, a["id"], "tesla")
    print("  缺工厂拒绝 / 补工厂放行: PASS")

    print("\n=== Test 3: 天启/光棱需维修厂 ===")
    room, a, b = make_room("ADV02")
    game = room["game"]
    a["cash"] = 99999
    give(game, a["id"], "factory")    # 只有工厂，没有维修厂
    for kind in ("overlord", "prism"):
        try:
            server.queue_unit(room, a["id"], kind)
            raise AssertionError("无维修厂时不该能出 %s" % kind)
        except ValueError as exc:
            assert "前置建筑" in str(exc), str(exc)
    give(game, a["id"], "repair")     # 补上维修厂
    server.queue_unit(room, a["id"], "overlord")
    server.queue_unit(room, a["id"], "prism")
    print("  缺维修厂拒绝 / 补维修厂放行: PASS")

    print("\n=== Test 4: 新伤害类型克制系数 ===")
    room, a, b = make_room("ADV03")
    game = room["game"]
    # 磁暴 vs 轻型载具（猎犬）×1.4
    scout = server.make_unit("scout", b["id"], 9000, 9000)
    scout["hp"] = 1000
    game["units"].append(scout)
    before = scout["hp"]
    server.apply_damage(room, scout, 100, a["id"], "tesla", game)
    assert abs((before - scout["hp"]) - 100 * 1.4) < 0.1, (before - scout["hp"])
    print("  tesla vs 轻型: ×1.4 PASS")
    # 光棱 vs 建筑 ×1.7
    turret = server.make_structure("turret", b["id"], 9000, 9000, True)
    game["structures"].append(turret)
    before = turret["hp"]
    server.apply_damage(room, turret, 100, a["id"], "laser", game)
    assert abs((before - turret["hp"]) - 100 * 1.7) < 0.1, (before - turret["hp"])
    print("  laser vs 建筑: ×1.7 PASS")

    print("\n=== 高级兵种测试全部通过 ===")


if __name__ == "__main__":
    main()
