#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""军犬（attack dog）测试：
   1) 单位定义齐全：归兵营、步兵甲、全场最速、不算载具
   2) bite 克制系数：对步兵 ×4 一击必杀，对载具/建筑/巨龙 ×0 咬不动
   3) 自动索敌扑步兵与魔导（nearest_enemy_infantry 忽略贴脸的坦克，不漏法师）
   4) 秘法巨龙虽是 arcane，但是载具：不当猎物，bite 也不掉血；法师/女巫仍可咬
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
        "id": tag, "name": "dog test", "status": "lobby",
        "hostId": a["id"],
        "players": {a["id"]: a, b["id"]: b},
        "chat": [], "game": None, "createdAt": time.time(),
    }
    server.start_game(room)
    return room, a, b


def main():
    print("=== Test 1: 军犬定义齐全 ===")
    d = server.UNIT_TYPES["dog"]
    for field in ("name", "cost", "hp", "speed", "damage", "range",
                  "cooldown", "size", "build", "producer", "projectile",
                  "projectileSpeed", "splash", "sight", "armor", "damageType"):
        assert field in d, "dog 缺字段 %s" % field
    assert d["producer"] == "barracks"
    assert d["armor"] == "infantry"
    assert d["damageType"] == "bite"
    assert d["projectile"] == "bite"
    # 全场最速：要快过猎犬战车(108)
    assert d["speed"] > server.UNIT_TYPES["scout"]["speed"]
    # 生物不是载具，进不了维修厂
    assert "dog" not in server.VEHICLE_KINDS
    assert "bite" in server.DAMAGE_MULTIPLIER
    print("  定义/归类/最速/非载具: PASS")

    print("\n=== Test 2: 兵营直接出军犬（无前置建筑） ===")
    room, a, b = make_room("DOG01")
    game = room["game"]
    a["cash"] = 99999
    game["structures"].append(server.make_structure("barracks", a["id"], 900, 900, True))
    server.queue_unit(room, a["id"], "dog")
    print("  兵营放行: PASS")

    print("\n=== Test 3: 扑咬对步兵一击必杀 ===")
    room, a, b = make_room("DOG02")
    game = room["game"]
    bite = server.UNIT_TYPES["dog"]["damage"]            # 60
    mult = server.DAMAGE_MULTIPLIER["bite"]["infantry"]  # 4.0
    assert bite * mult >= 240.0
    for kind in ("rifle", "rocket", "sniper", "tesla"):
        victim = server.make_unit(kind, b["id"], 9000, 9000)
        game["units"].append(victim)
        server.apply_damage(room, victim, bite, a["id"], "bite", game)
        assert victim["hp"] <= 0, "%s 应被一口咬死，剩 %s" % (kind, victim["hp"])
    print("  60×4.0=240 咬死全部步兵（含 190 血磁暴）: PASS")

    print("\n=== Test 4: 扑咬对载具/建筑/巨龙零伤害 ===")
    room, a, b = make_room("DOG03")
    game = room["game"]
    tank = server.make_unit("tank", b["id"], 9000, 9000)
    game["units"].append(tank)
    before = tank["hp"]
    server.apply_damage(room, tank, 60, a["id"], "bite", game)
    assert abs(tank["hp"] - before) < 0.001, "坦克不该掉血"
    turret = server.make_structure("turret", b["id"], 9000, 9000, True)
    game["structures"].append(turret)
    before = turret["hp"]
    server.apply_damage(room, turret, 60, a["id"], "bite", game)
    assert abs(turret["hp"] - before) < 0.001, "建筑不该掉血"
    dragon = server.make_unit("dragon", b["id"], 9100, 9100)
    game["units"].append(dragon)
    before = dragon["hp"]
    server.apply_damage(room, dragon, 60, a["id"], "bite", game)
    assert abs(dragon["hp"] - before) < 0.001, "巨龙不该掉血（载具规则，不是 arcane ×1.5）"
    print("  坦克/建筑/巨龙 0 伤害: PASS")

    print("\n=== Test 5: 自动索敌只扑步兵 ===")
    room, a, b = make_room("DOG04")
    game = room["game"]
    # 坦克贴脸（更近，50），步兵稍远（80）：军犬必须舍近求远去咬步兵
    game["units"].append(server.make_unit("tank", b["id"], 5050, 5000))
    game["units"].append(server.make_unit("rifle", b["id"], 5080, 5000))
    pick = server.nearest_enemy_infantry(game, a["id"], 5000, 5000, 400)
    assert pick is not None and pick["kind"] == "rifle", \
        "应锁定步兵而非坦克，实际 %s" % (pick and pick["kind"])
    print("  忽略贴脸坦克、锁定步兵: PASS")

    print("\n=== Test 6: 自动索敌会扑 arcane 法师/女巫 ===")
    assert server.is_dog_prey("mage") and server.is_dog_prey("frost")
    assert not server.is_dog_prey("tank")
    assert not server.is_dog_prey("dragon")
    for kind in ("mage", "frost"):
        room, a, b = make_room("DOG-" + kind)
        game = room["game"]
        # 坦克贴脸（更近），法师稍远：旧扫描只认 infantry，会从法师身边走过
        game["units"].append(server.make_unit("tank", b["id"], 5050, 5000))
        game["units"].append(server.make_unit(kind, b["id"], 5080, 5000))
        pick = server.nearest_enemy_infantry(game, a["id"], 5000, 5000, 400)
        assert pick is not None and pick["kind"] == kind, \
            "应锁定 %s 而非坦克，实际 %s" % (kind, pick and pick["kind"])
    print("  忽略贴脸坦克、锁定法师/女巫: PASS")

    print("\n=== Test 7: 扑咬对魔导有伤害 ===")
    room, a, b = make_room("DOG06")
    game = room["game"]
    mage = server.make_unit("mage", b["id"], 9000, 9000)
    game["units"].append(mage)
    server.apply_damage(room, mage, 60, a["id"], "bite", game)
    assert mage["hp"] <= 0, "法师应被咬死，剩 %s" % mage["hp"]
    print("  60×1.5=90 咬死 90 血法师: PASS")

    print("\n=== Test 8: 自动索敌不扑秘法巨龙 ===")
    room, a, b = make_room("DOG07")
    game = room["game"]
    # 巨龙贴脸（更近），法师稍远：旧逻辑按 arcane 会扑龙
    game["units"].append(server.make_unit("dragon", b["id"], 5050, 5000))
    game["units"].append(server.make_unit("mage", b["id"], 5080, 5000))
    pick = server.nearest_enemy_infantry(game, a["id"], 5000, 5000, 400)
    assert pick is not None and pick["kind"] == "mage", \
        "应锁定法师而非巨龙，实际 %s" % (pick and pick["kind"])
    only_dragon = server.nearest_enemy_infantry(game, a["id"], 5000, 5000, 40)
    assert only_dragon is None, "射程内只有巨龙时不该锁定"
    print("  忽略贴脸巨龙、锁定法师；单独巨龙不入猎物: PASS")

    print("\n=== 军犬测试全部通过 ===")


if __name__ == "__main__":
    main()
