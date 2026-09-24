#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""秘法会雷暴塔：对位钢铁远程塔的联网雷电防御。
   1) 目录：魔法-only、防御队列、圣殿+法力塔、射程 420、tesla、70/1.1
   2) 科技不能建；缺圣殿拒绝；补齐前置放行
   3) 公开目录带射程；客户端是哥特风暴尖碑而不是虹光矛
   4) rush AI 仍先造奥术塔；后期/第一波失败后才补雷暴塔
   5) 开火走 tesla；联网伤害 70+35*extras（上限 3）；奥术塔不支援
   6) 命中单位挂 0.5×/1.8s 麻痹，刷新不叠乘；建筑不受减速
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
        "id": tag, "name": "storm tower test", "status": "lobby",
        "hostId": a["id"],
        "players": {a["id"]: a, b["id"]: b},
        "chat": [], "game": None, "createdAt": time.time(),
    }
    server.start_game(room)
    return room, a, b


def give(game, pid, kind, x=900, y=900, active=True):
    structure = server.make_structure(kind, pid, x, y, active)
    game["structures"].append(structure)
    return structure


def expect_error(fragment, callback):
    try:
        callback()
        raise AssertionError("expected ValueError containing %r" % fragment)
    except ValueError as error:
        assert fragment in str(error), (fragment, str(error))


def silence_defenses(game):
    for structure in game["structures"]:
        if server.structure_role(structure["kind"]) == "defense":
            structure["cooldown"] = 99.0


def main():
    print("=== Test 1: 目录 / 阵营 / 远程射程对齐导弹塔 ===")
    storm = server.STRUCTURE_TYPES["mstorm"]
    missile = server.STRUCTURE_TYPES["missile"]
    for field in ("name", "cost", "hp", "size", "build", "deploy", "power",
                  "requires", "sight", "damage", "range", "cooldown",
                  "projectile", "projectileSpeed", "splash", "armor",
                  "damageType", "faction", "role", "slow",
                  "supportRadius", "supportBonus", "supportMax"):
        assert field in storm, "mstorm 缺字段 %s" % field
    assert "mrail" not in server.STRUCTURE_TYPES
    assert storm["name"] == "雷暴塔"
    assert storm["faction"] == "magic"
    assert storm["role"] == "defense"
    assert "mstorm" in server.MAGIC_STRUCTURES
    assert storm["requires"] == ["mtemple", "mpower"]
    for field in ("cost", "hp", "size", "build", "deploy", "power", "sight", "range"):
        assert storm[field] == missile[field], (field, storm[field], missile[field])
    assert storm["damage"] == 70.0
    assert storm["cooldown"] == 1.1
    assert storm["splash"] == 0.0
    assert storm["damageType"] == "tesla"
    assert missile["damageType"] == "shell"
    assert storm["projectile"] == "storm"
    assert storm["projectileSpeed"] >= 800.0
    assert storm["slow"] == {"mult": 0.5, "duration": 1.8}
    assert storm["supportRadius"] == 420.0
    assert storm["supportBonus"] == 35.0
    assert storm["supportMax"] == 3
    assert server.storm_network_damage(storm, 0) == 70.0
    assert server.storm_network_damage(storm, 1) == 105.0
    assert server.storm_network_damage(storm, 3) == 175.0
    assert server.storm_network_damage(storm, 8) == 175.0
    assert server.structure_role("mstorm") == "defense"
    assert server.structure_queue_key("mstorm") == "defenseQueue"
    assert server.faction_buildings("magic")["defense"] == "mtower"
    assert server.faction_buildings("magic")["defense_long"] == "mstorm"
    assert server.faction_buildings("tech")["defense_long"] == "missile"
    catalog = server.public_catalog()
    entry = catalog["buildings"]["mstorm"]
    assert entry["name"] == "雷暴塔"
    assert entry["cost"] == 1200
    assert entry["faction"] == "magic"
    assert entry["role"] == "defense"
    assert entry["requires"] == ["mtemple", "mpower"]
    assert entry["range"] == 420.0
    assert catalog["buildings"]["missile"]["range"] == 420.0
    mtower = server.STRUCTURE_TYPES["mtower"]
    assert mtower["damage"] == 80.0 and mtower["range"] == 360.0
    assert missile["damage"] == 120.0 and missile["cooldown"] == 1.6
    print("  定义/阵营/目录/tesla/联网公式: PASS")

    print("\n=== Test 2: 科技不能建；缺圣殿拒绝；补齐前置放行 ===")
    room, a, b = make_room("STORM01")
    game = room["game"]
    a["cash"] = b["cash"] = 99999
    expect_error("阵营", lambda: server.queue_structure(room, a["id"], "mstorm"))
    expect_error("阵营", lambda: server.place_structure(
        room, a["id"], "mstorm", 800, 800, free=True))
    expect_error("阵营", lambda: server.queue_structure(room, b["id"], "missile"))
    expect_error("前置建筑", lambda: server.queue_structure(room, b["id"], "mstorm"))
    give(game, b["id"], "mtemple")
    item = server.queue_structure(room, b["id"], "mstorm")
    assert item["kind"] == "mstorm"
    assert b["defenseQueue"] == [item]
    assert not b.get("buildQueue")
    print("  跨阵营拦截 / 缺圣殿拒绝 / 防御队列放行: PASS")

    print("\n=== Test 3: 客户端部署提示与雷暴模型 ===")
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    with open(os.path.join(root, "public", "app.js"), "r", encoding="utf-8") as handle:
        app = handle.read()
    assert "range: src.range || 0," in app
    assert "基础射程 ' + definition.range" in app
    assert "mstorm: { icon:" in app
    assert "联网雷暴" in app
    assert "哥特风暴尖碑" in app
    assert "虹光塔" not in app
    assert "远程虹光矛" not in app
    with open(os.path.join(root, "public", "render3d.js"), "r", encoding="utf-8") as handle:
        render = handle.read()
    assert "kind === 'mstorm'" in render
    assert "function stormHeadParts" in render
    assert "function addStormBolt" in render
    assert "MAT.stormSlate" in render
    assert "哥特风暴尖碑" in render
    assert "双侧雷线圈" not in render
    assert "type === 'tether'" in render
    assert "storm: { len:" in render
    assert "虹光塔" not in render
    print("  射程预览字符串 / 雷暴模型: PASS")

    print("\n=== Test 4: rush 不插雷暴塔；后期才补远程塔 ===")
    room, a, b = make_room("STORM02")
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
    assert not queued or queued[0]["kind"] != "mstorm", queued
    print("  总部受伤先造奥术塔，rush 不插雷暴塔: PASS")

    room, a, b = make_room("STORM03")
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
    assert queued and queued[0]["kind"] == "mstorm", queued
    print("  后期已有奥术塔后再补雷暴塔: PASS")

    print("\n=== Test 5: tesla 伤种 + 单塔 70 ===")
    room, a, b = make_room("STORM04")
    game = room["game"]
    game["terrainCtx"] = server.FLAT_TERRAIN
    game["projectiles"] = []
    game["effects"] = []
    silence_defenses(game)
    firer = server.make_structure("mstorm", b["id"], 1000, 1000, True)
    tank = server.make_unit("tank", a["id"], 1180, 1000)
    game["structures"].append(firer)
    game["units"].append(tank)
    firer["cooldown"] = 0.0
    server.tick_structures(room, 0.05)
    assert game["projectiles"], "雷暴塔应放电弧"
    shot = game["projectiles"][-1]
    assert shot["kind"] == "storm"
    assert shot["damageType"] == "tesla"
    assert abs(shot["damage"] - 70.0) < 0.001
    assert shot.get("slow") == {"mult": 0.5, "duration": 1.8}
    hq = next(s for s in game["structures"]
              if s["owner"] == a["id"] and server.structure_role(s["kind"]) == "hq")
    before = hq["hp"]
    server.apply_damage(room, hq, storm["damage"], b["id"], storm["damageType"], game)
    expect = storm["damage"] * server.DAMAGE_MULTIPLIER["tesla"]["structure"]
    assert abs((before - hq["hp"]) - expect) < 0.1
    print("  弹种 storm / tesla 拆建筑 ×0.50: PASS")

    print("\n=== Test 6: 光棱式支援加伤；奥术塔不支援 ===")
    room, a, b = make_room("STORM05")
    game = room["game"]
    game["terrainCtx"] = server.FLAT_TERRAIN
    game["projectiles"] = []
    game["effects"] = []
    silence_defenses(game)
    firer = give(game, b["id"], "mstorm", 1000, 1000)
    helper = give(game, b["id"], "mstorm", 1200, 1000)
    decoy = give(game, b["id"], "mtower", 1100, 1000)
    unfinished = give(game, b["id"], "mstorm", 1080, 1080, active=False)
    enemy = give(game, a["id"], "mstorm", 1150, 950)
    tank = server.make_unit("tank", a["id"], 1180, 1000)
    game["units"].append(tank)
    firer["cooldown"] = helper["cooldown"] = decoy["cooldown"] = enemy["cooldown"] = 0.0
    unfinished["cooldown"] = 0.0
    supports = server.collect_storm_supports(game, firer)
    assert helper in supports
    assert decoy not in supports
    assert unfinished not in supports
    assert enemy not in supports
    assert firer not in supports
    server.tick_structures(room, 0.05)
    shots = [p for p in game["projectiles"] if p.get("sourceId") == firer["id"]]
    assert shots, game["projectiles"]
    assert abs(shots[-1]["damage"] - 105.0) < 0.001, shots[-1]["damage"]
    helper_shots = [p for p in game["projectiles"] if p.get("sourceId") == helper["id"]]
    assert not helper_shots, "支援塔本轮不应独立开火"
    assert helper["cooldown"] > 0
    tethers = [fx for fx in game["effects"] if fx.get("type") == "tether"]
    assert tethers, game["effects"]
    assert tethers[0]["kind"] == "storm"
    assert abs(tethers[0]["fromX"] - helper["x"]) < 0.2
    assert abs(tethers[0]["x"] - firer["x"]) < 0.2
    public = server.public_effect(tethers[0])
    assert public.get("fromX") == tethers[0]["fromX"]
    print("  一座支援 = 105；奥术/未建成/敌塔不喂: PASS")

    silence_defenses(game)
    extras = [
        give(game, b["id"], "mstorm", 1000 + 40 * (i + 1), 1040)
        for i in range(4)
    ]
    for tower in extras:
        tower["cooldown"] = 0.0
    firer["cooldown"] = 0.0
    game["projectiles"] = []
    game["effects"] = []
    tank["hp"] = tank["maxHp"]
    server.tick_structures(room, 0.05)
    shots = [p for p in game["projectiles"] if p.get("sourceId") == firer["id"]]
    assert shots and abs(shots[-1]["damage"] - 175.0) < 0.001, shots[-1]["damage"] if shots else None
    assert len([fx for fx in game["effects"] if fx.get("type") == "tether"]) == 3
    print("  三座支援封顶 175: PASS")

    print("\n=== Test 7: 友军同队可支援 ===")
    room, a, b = make_room("STORM06")
    game = room["game"]
    game["terrainCtx"] = server.FLAT_TERRAIN
    game["playerTeams"] = {a["id"]: 1, b["id"]: 1}
    game["projectiles"] = []
    silence_defenses(game)
    firer = give(game, b["id"], "mstorm", 1000, 1000)
    ally = give(game, a["id"], "mstorm", 1180, 1000)
    firer["cooldown"] = ally["cooldown"] = 0.0
    tank = server.make_unit("tank", a["id"], 2000, 2000)
    game["units"].append(tank)
    supports = server.collect_storm_supports(game, firer)
    assert ally in supports, supports
    print("  同队友军雷暴塔可联网: PASS")

    print("\n=== Test 8: 命中麻痹，刷新不叠乘，建筑免疫 ===")
    room, a, b = make_room("STORM07")
    game = room["game"]
    game["terrainCtx"] = server.FLAT_TERRAIN
    game["projectiles"] = []
    silence_defenses(game)
    firer = give(game, b["id"], "mstorm", 1000, 1000)
    tank = server.make_unit("tank", a["id"], 1120, 1000)
    game["units"].append(tank)
    firer["cooldown"] = 0.0
    server.tick_structures(room, 0.05)
    assert game["projectiles"]
    for _ in range(20):
        server.tick_projectiles(room, 0.05)
    assert abs(tank["slowMult"] - 0.5) < 1e-6
    assert abs(tank["slowTimer"] - 1.8) < 1e-6
    tank["slowTimer"] = 0.3
    server.apply_slow({"slow": {"mult": 0.5, "duration": 1.8}}, tank)
    assert abs(tank["slowMult"] - 0.5) < 1e-6
    assert abs(tank["slowTimer"] - 1.8) < 1e-6
    hq = next(s for s in game["structures"]
              if s["owner"] == a["id"] and server.structure_role(s["kind"]) == "hq")
    hq["slowMult"] = 1.0
    hq["slowTimer"] = 0.0
    server.apply_slow({"slow": {"mult": 0.5, "duration": 1.8}}, hq)
    assert hq.get("slowMult", 1.0) == 1.0
    print("  单位 0.5×/1.8s；刷新；建筑不减速: PASS")

    print("\n=== 雷暴塔测试全部通过 ===")


if __name__ == "__main__":
    main()
