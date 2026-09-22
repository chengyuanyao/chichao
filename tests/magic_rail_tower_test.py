#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""秘法会虹光塔：对位钢铁导弹炮塔的远程防御。
   1) 目录锁定：魔法-only、防御队列、圣殿+法力塔门槛、与导弹炮塔数值对齐
   2) 科技不能建；缺圣殿拒绝；补齐前置放行
   3) 公开目录带射程，客户端部署提示锁「基础射程」
   4) rush AI 仍先造奥术塔；后期/第一波失败后才补虹光塔
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
        "id": tag, "name": "rail tower test", "status": "lobby",
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


def expect_error(fragment, callback):
    try:
        callback()
        raise AssertionError("expected ValueError containing %r" % fragment)
    except ValueError as error:
        assert fragment in str(error), (fragment, str(error))


def main():
    print("=== Test 1: 目录 / 阵营 / 与导弹炮塔数值对齐 ===")
    rail = server.STRUCTURE_TYPES["mrail"]
    missile = server.STRUCTURE_TYPES["missile"]
    for field in ("name", "cost", "hp", "size", "build", "deploy", "power",
                  "requires", "sight", "damage", "range", "cooldown",
                  "projectile", "projectileSpeed", "splash", "armor",
                  "damageType", "faction", "role"):
        assert field in rail, "mrail 缺字段 %s" % field
    assert rail["name"] == "虹光塔"
    assert rail["faction"] == "magic"
    assert rail["role"] == "defense"
    assert "mrail" in server.MAGIC_STRUCTURES
    assert rail["requires"] == ["mtemple", "mpower"]
    for field in ("cost", "hp", "size", "build", "deploy", "power",
                  "sight", "damage", "range", "cooldown", "splash"):
        assert rail[field] == missile[field], (field, rail[field], missile[field])
    assert rail["damageType"] == "missile"
    assert missile["damageType"] == "shell"
    assert rail["projectile"] == "rail"
    assert rail["projectileSpeed"] >= missile["projectileSpeed"]
    assert rail["armor"] == "structure"
    assert server.structure_role("mrail") == "defense"
    assert server.structure_queue_key("mrail") == "defenseQueue"
    assert server.faction_buildings("magic")["defense"] == "mtower"
    assert server.faction_buildings("magic")["defense_long"] == "mrail"
    assert server.faction_buildings("tech")["defense_long"] == "missile"
    catalog = server.public_catalog()
    entry = catalog["buildings"]["mrail"]
    assert entry["name"] == "虹光塔"
    assert entry["cost"] == 1200
    assert entry["faction"] == "magic"
    assert entry["role"] == "defense"
    assert entry["requires"] == ["mtemple", "mpower"]
    assert entry["range"] == 420.0
    assert catalog["buildings"]["missile"]["range"] == 420.0
    mtower = server.STRUCTURE_TYPES["mtower"]
    assert mtower["damage"] == 80.0 and mtower["range"] == 360.0
    assert missile["damage"] == 120.0 and missile["range"] == 420.0
    print("  定义/阵营/目录/导弹塔对齐: PASS")

    print("\n=== Test 2: 科技不能建；缺圣殿拒绝；补齐前置放行 ===")
    room, a, b = make_room("RAIL01")
    game = room["game"]
    a["cash"] = b["cash"] = 99999
    expect_error("阵营", lambda: server.queue_structure(room, a["id"], "mrail"))
    expect_error("阵营", lambda: server.place_structure(
        room, a["id"], "mrail", 800, 800, free=True))
    expect_error("阵营", lambda: server.queue_structure(room, b["id"], "missile"))
    expect_error("前置建筑", lambda: server.queue_structure(room, b["id"], "mrail"))
    give(game, b["id"], "mtemple")
    item = server.queue_structure(room, b["id"], "mrail")
    assert item["kind"] == "mrail"
    assert b["defenseQueue"] == [item]
    assert not b.get("buildQueue")
    print("  跨阵营拦截 / 缺圣殿拒绝 / 防御队列放行: PASS")

    print("\n=== Test 3: 客户端部署提示锁基础射程 ===")
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    with open(os.path.join(root, "public", "app.js"), "r", encoding="utf-8") as handle:
        app = handle.read()
    assert "range: src.range || 0," in app
    assert "基础射程 ' + definition.range" in app
    assert "mrail: { icon:" in app
    assert "远程虹光矛" in app
    with open(os.path.join(root, "public", "render3d.js"), "r", encoding="utf-8") as handle:
        render = handle.read()
    assert "kind === 'mrail'" in render
    assert "function railHeadParts" in render
    assert "look: 'lance'" in render
    print("  射程预览字符串 / 虹光模型: PASS")

    print("\n=== Test 4: rush 不插虹光塔；后期才补远程塔 ===")
    room, a, b = make_room("RAIL02")
    game = room["game"]
    b["isBot"] = True
    b["cash"] = 99999
    b["buildQueue"] = []
    b["defenseQueue"] = []
    hq = next(s for s in game["structures"]
              if s["owner"] == b["id"] and server.structure_role(s["kind"]) == "hq")
    hq["hp"] = hq["maxHp"] * 0.4
    give(game, b["id"], "mtemple")
    give(game, b["id"], "mcircle")
    server.tick_bots(room)
    queued = b.get("defenseQueue") or []
    assert queued and queued[0]["kind"] == "mtower", queued
    b["defenseQueue"] = []
    give(game, b["id"], "mtower")
    server.tick_bots(room)
    queued = b.get("defenseQueue") or []
    assert not queued or queued[0]["kind"] != "mrail", queued
    print("  总部受伤先造奥术塔，rush 不插虹光塔: PASS")

    room, a, b = make_room("RAIL03")
    game = room["game"]
    b["isBot"] = True
    b["cash"] = 99999
    b["defenseQueue"] = []
    hq = next(s for s in game["structures"]
              if s["owner"] == b["id"] and server.structure_role(s["kind"]) == "hq")
    hq["hp"] = hq["maxHp"] * 0.4
    give(game, b["id"], "mtemple")
    give(game, b["id"], "mcircle")
    give(game, b["id"], "mspring")
    give(game, b["id"], "mtower")
    server.tick_bots(room)
    queued = b.get("defenseQueue") or []
    assert queued and queued[0]["kind"] == "mrail", queued
    print("  后期已有奥术塔后再补虹光塔: PASS")

    print("\n=== Test 5: 虹光塔开火走 missile 伤种 ===")
    room, a, b = make_room("RAIL04")
    game = room["game"]
    game["terrainCtx"] = server.FLAT_TERRAIN
    game["projectiles"] = []
    tower = server.make_structure("mrail", b["id"], 1000, 1000, True)
    tank = server.make_unit("tank", a["id"], 1180, 1000)
    game["structures"].append(tower)
    game["units"].append(tank)
    tower["cooldown"] = 0.0
    server.tick_structures(room, 0.05)
    assert game["projectiles"], "虹光塔应发射虹光矛"
    shot = game["projectiles"][-1]
    assert shot["kind"] == "rail"
    assert abs(shot["damage"] - rail["damage"]) < 0.001
    hq = next(s for s in game["structures"]
              if s["owner"] == a["id"] and server.structure_role(s["kind"]) == "hq")
    before = hq["hp"]
    server.apply_damage(room, hq, rail["damage"], b["id"], rail["damageType"], game)
    expect = rail["damage"] * server.DAMAGE_MULTIPLIER["missile"]["structure"]
    assert abs((before - hq["hp"]) - expect) < 0.1
    print("  弹种 rail / 拆建筑 ×1.50: PASS")

    print("\n=== 虹光塔测试全部通过 ===")


if __name__ == "__main__":
    main()
