#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""大师 AI：开局仍按拆总部剧本，随后按可见编制克制。
   1) 科技 2 人开局先排兵营再排工厂，总部没掉血就不造维修厂/炮塔
   2) 工厂一转就排自爆卡车，不必凑齐 8 个野战单位
   3) 魔法法阵立了就排爆裂魔仆，不等圣泉
   4) 自爆指令只打敌方总部或成团建筑，不追野战部队
   5) 自爆上限 5；凑齐 2 辆才出发
   6) 多人局锁定最近的一座敌方总部
   7) 总部掉血或家矿有敌军时改练守军/炮塔，不再排下一辆自爆
   8) 看见成堆军犬时，魔法改出傀儡/载具，不再堆法师
   9) 第一波没拆掉敌方总部时补第二精炼所或电力，而不是只排卡车
"""

from __future__ import print_function

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import server


def make_room(tag, magic_b=False, extra=None):
    a = server.create_human("A", server.COLORS[0])
    b = server.create_human("B", server.COLORS[1])
    if magic_b:
        b["faction"] = "magic"
    players = {a["id"]: a, b["id"]: b}
    if extra:
        for player in extra:
            players[player["id"]] = player
    room = {
        "id": tag, "name": "bot rush test", "status": "lobby",
        "hostId": a["id"],
        "players": players,
        "chat": [], "game": None, "createdAt": time.time(),
    }
    server.start_game(room)
    game = room["game"]
    game["terrainCtx"] = server.FLAT_TERRAIN
    game["botClock"] = 999.0
    game["victoryClock"] = 999.0
    return room, a, b


def give(game, pid, kind, x=900, y=900):
    structure = server.make_structure(kind, pid, x, y, True)
    game["structures"].append(structure)
    return structure


def combat_count(game, pid):
    return sum(
        1 for unit in game["units"]
        if unit["owner"] == pid and unit["hp"] > 0
        and server.unit_role(unit["kind"]) != "harvester")


def queued_kinds(game, pid):
    kinds = []
    for structure in game["structures"]:
        if structure["owner"] != pid:
            continue
        for item in structure["queue"]:
            kinds.append(item["kind"])
    return kinds


def player_hq(game, pid):
    for structure in game["structures"]:
        if (structure["owner"] == pid and structure["hp"] > 0
                and server.structure_role(structure["kind"]) == "hq"):
            return structure
    return None


def main():
    print("=== Test 1: 科技 2 人开局先兵营后工厂，总部完好不造维修厂/炮塔 ===")
    room, a, b = make_room("BOT01")
    game = room["game"]
    a["isBot"] = True
    a["faction"] = "tech"
    a["buildQueue"] = []
    hq = player_hq(game, a["id"])
    assert hq and hq["hp"] == hq["maxHp"]
    server.tick_bots(room)
    queued = a.get("buildQueue") or []
    assert queued and queued[0]["kind"] == "barracks", queued
    a["buildQueue"] = []
    give(game, a["id"], "barracks")
    server.tick_bots(room)
    queued = a.get("buildQueue") or []
    assert queued and queued[0]["kind"] == "factory", queued
    assert queued[0]["kind"] not in ("repair", "turret", "missile"), queued
    print("  兵营 → 工厂，未插维修厂/炮塔: PASS")

    print("\n=== Test 2: 总部掉血且工厂已在时允许补炮塔 ===")
    room, a, b = make_room("BOT02")
    game = room["game"]
    a["isBot"] = True
    a["faction"] = "tech"
    a["buildQueue"] = []
    a["cash"] = server.STRUCTURE_TYPES["turret"]["cost"]
    give(game, a["id"], "barracks")
    give(game, a["id"], "factory")
    hq = player_hq(game, a["id"])
    hq["hp"] = hq["maxHp"] * 0.4
    server.tick_bots(room)
    queued = a.get("buildQueue") or []
    assert queued and queued[0]["kind"] == "turret", queued
    print("  总部受伤 → 哨戒炮塔: PASS")

    print("\n=== Test 3: 工厂一转就排自爆卡车，不等 8 个野战 ===")
    room, a, b = make_room("BOT03")
    game = room["game"]
    a["isBot"] = True
    a["faction"] = "tech"
    a["cash"] = 99999
    a["buildQueue"] = [{"id": "busy", "kind": "power",
                        "remaining": 4.0, "total": 8.0, "ready": False}]
    give(game, a["id"], "factory")
    before = combat_count(game, a["id"])
    assert before < 8, before
    assert server.bot_should_train_suicide(game, a, "bomb_truck")
    server.tick_bots(room)
    produced = queued_kinds(game, a["id"])
    assert "bomb_truck" in produced, produced
    assert combat_count(game, a["id"]) < 8
    print("  野战 %d 人时已排 bomb_truck: PASS" % before)

    print("\n=== Test 4: 魔法法阵后排魔仆，不等圣泉 ===")
    room, a, b = make_room("BOT04", magic_b=True)
    game = room["game"]
    b["isBot"] = True
    b["cash"] = 99999
    b["buildQueue"] = [{"id": "busy", "kind": "mpower",
                        "remaining": 4.0, "total": 8.0, "ready": False}]
    give(game, b["id"], "mcircle")
    assert not any(s["owner"] == b["id"] and s["kind"] == "mspring"
                   for s in game["structures"])
    server.tick_bots(room)
    produced = queued_kinds(game, b["id"])
    assert "hexling" in produced, produced
    assert not b.get("buildQueue") or b["buildQueue"][0]["kind"] != "mspring"
    print("  无法阵外圣泉也排出 hexling: PASS")

    print("\n=== Test 5: 自爆指令打总部/成团建筑，不追野战部队 ===")
    room, a, b = make_room("BOT05")
    game = room["game"]
    a["isBot"] = True
    a["faction"] = "tech"
    a["cash"] = 100
    a["buildQueue"] = [{"id": "busy", "kind": "power",
                        "remaining": 4.0, "total": 8.0, "ready": False}]
    enemy_hq = player_hq(game, b["id"])
    decoy = server.make_unit("rifle", b["id"], 200, 200)
    decoy["hp"] = 200
    game["units"].append(decoy)
    trucks = [
        server.make_unit("bomb_truck", a["id"], 220, 200),
        server.make_unit("bomb_truck", a["id"], 240, 210),
    ]
    game["units"].extend(trucks)
    picked = server.bot_pick_suicide_target(game, a["id"])
    assert picked is not None
    assert picked["id"] in set(s["id"] for s in game["structures"])
    assert picked["kind"] not in server.UNIT_TYPES
    assert picked["id"] != decoy["id"]
    role = server.structure_role(picked["kind"])
    assert role == "hq" or picked["owner"] == b["id"], (picked["kind"], role)
    server.tick_bots(room)
    for truck in trucks:
        assert truck["order"] == "attack", truck["order"]
        assert truck["targetId"] != decoy["id"], truck["targetId"]
        target = server.find_entity(game, truck["targetId"])
        assert target is not None
        assert target["kind"] in server.STRUCTURE_TYPES
        assert server.structure_role(target["kind"]) == "hq" or (
            math_near_hq(target, enemy_hq))
    print("  两辆卡车锁定建筑 %s，不是步枪: PASS" % trucks[0]["targetId"])

    print("\n=== Test 6: 单辆自爆先等第二辆；上限 5 ===")
    room, a, b = make_room("BOT06")
    game = room["game"]
    a["isBot"] = True
    a["cash"] = 100
    a["buildQueue"] = [{"id": "busy", "kind": "power",
                        "remaining": 4.0, "total": 8.0, "ready": False}]
    lone = server.make_unit("bomb_truck", a["id"], 300, 300)
    game["units"].append(lone)
    server.tick_bots(room)
    assert lone.get("order") != "attack", lone.get("order")
    # 五辆已在场，不应再排第六辆
    for _ in range(4):
        extra = server.make_unit("bomb_truck", a["id"], 320 + _ * 20, 300)
        game["units"].append(extra)
    a["cash"] = 99999
    give(game, a["id"], "factory", 1400, 900)
    assert server.bot_suicide_count(game, a["id"], "bomb_truck") >= 5
    assert not server.bot_should_train_suicide(game, a, "bomb_truck")
    before = queued_kinds(game, a["id"]).count("bomb_truck")
    server.tick_bots(room)
    after = queued_kinds(game, a["id"]).count("bomb_truck")
    assert after == before, (before, after)
    print("  1 辆不出发 / 满 5 不再排: PASS")

    print("\n=== Test 7: 多人局打最近的敌方总部 ===")
    c = server.create_human("C", server.COLORS[2])
    room, a, b = make_room("BOT07", extra=[c])
    game = room["game"]
    a["isBot"] = True
    a["cash"] = 100
    a["buildQueue"] = [{"id": "busy", "kind": "power",
                        "remaining": 4.0, "total": 8.0, "ready": False}]
    focus = server.bot_focus_hq(game, a["id"])
    assert focus is not None
    assert focus["owner"] in (b["id"], c["id"])
    other = b["id"] if focus["owner"] == c["id"] else c["id"]
    other_hq = player_hq(game, other)
    origin_x, origin_y = server.bot_own_origin(game, a["id"])
    focus_d = hypot(focus["x"] - origin_x, focus["y"] - origin_y)
    other_d = hypot(other_hq["x"] - origin_x, other_hq["y"] - origin_y)
    assert focus_d <= other_d + 0.01, (focus_d, other_d)
    trucks = [
        server.make_unit("bomb_truck", a["id"], origin_x + 40, origin_y),
        server.make_unit("bomb_truck", a["id"], origin_x + 60, origin_y),
    ]
    game["units"].extend(trucks)
    server.tick_bots(room)
    for truck in trucks:
        target = server.find_entity(game, truck["targetId"])
        assert target is not None
        assert target["owner"] == focus["owner"], (target["owner"], focus["owner"])
        assert target["owner"] != other
    print("  锁定最近的 %s，不拆去另一家: PASS" % focus["kind"])

    print("\n=== Test 8: 没有总部时改打成团建筑 ===")
    room, a, b = make_room("BOT08")
    game = room["game"]
    for structure in game["structures"]:
        if structure["owner"] == b["id"] and server.structure_role(structure["kind"]) == "hq":
            structure["hp"] = 0
    clump = [
        give(game, b["id"], "power", 5000, 5000),
        give(game, b["id"], "barracks", 5050, 5010),
        give(game, b["id"], "refinery", 5020, 5080),
    ]
    picked = server.bot_pick_suicide_target(game, a["id"])
    assert picked is not None
    assert picked["id"] in set(s["id"] for s in clump)
    assert picked["kind"] not in server.UNIT_TYPES
    print("  成团建筑 %s: PASS" % picked["kind"])

    print("\n=== Test 9: 总部受伤/敌军进家时改防，不再排自爆卡车 ===")
    room, a, b = make_room("BOT09")
    game = room["game"]
    a["isBot"] = True
    a["faction"] = "tech"
    a["cash"] = 99999
    a["buildQueue"] = []
    give(game, a["id"], "barracks")
    give(game, a["id"], "factory")
    hq = player_hq(game, a["id"])
    hq["hp"] = hq["maxHp"] * 0.45
    rifle = server.make_unit("rifle", b["id"], hq["x"] + 80, hq["y"] + 30)
    game["units"].append(rifle)
    assert server.bot_needs_defense(game, a["id"])
    assert not server.bot_should_train_suicide(game, a, "bomb_truck")
    server.tick_bots(room)
    produced = queued_kinds(game, a["id"])
    queued = a.get("buildQueue") or []
    assert "bomb_truck" not in produced, produced
    defended = (queued and queued[0]["kind"] in ("turret", "repair", "power")
                or any(kind in produced for kind in (
                    "dog", "rifle", "rocket", "tesla", "tank", "scout")))
    assert defended, (queued, produced)
    print("  受伤总部 → 未排卡车，改 %s / %s: PASS" % (
        queued[0]["kind"] if queued else "-", produced))

    print("\n=== Test 10: 看见成堆军犬时魔法改出傀儡，不再堆法师 ===")
    room, a, b = make_room("BOT10", magic_b=True)
    game = room["game"]
    b["isBot"] = True
    b["cash"] = 99999
    b["buildQueue"] = [{"id": "busy", "kind": "mpower",
                        "remaining": 4.0, "total": 8.0, "ready": False}]
    give(game, b["id"], "mtemple")
    give(game, b["id"], "mcircle")
    hq = player_hq(game, b["id"])
    for index in range(6):
        dog = server.make_unit(
            "dog", a["id"], hq["x"] + 70, hq["y"] + 24 + index * 16)
        game["units"].append(dog)
    assert server.bot_needs_defense(game, b["id"])
    server.tick_bots(room)
    produced = queued_kinds(game, b["id"])
    assert "golem" in produced, produced
    assert produced.count("mage") == 0, produced
    assert "hexling" not in produced, produced
    print("  6 军犬进家 → 法阵排 %s: PASS" % produced)

    print("\n=== Test 11: 第一波没拆掉总部时补第二精炼所或电力 ===")
    room, a, b = make_room("BOT11")
    game = room["game"]
    a["isBot"] = True
    a["faction"] = "tech"
    a["cash"] = 100
    a["buildQueue"] = [{"id": "busy", "kind": "power",
                        "remaining": 4.0, "total": 8.0, "ready": False}]
    give(game, a["id"], "barracks")
    give(game, a["id"], "factory", 1400, 900)
    trucks = [
        server.make_unit("bomb_truck", a["id"], 300, 300),
        server.make_unit("bomb_truck", a["id"], 320, 310),
    ]
    game["units"].extend(trucks)
    server.tick_bots(room)
    assert a.get("_ai", {}).get("waves_sent", 0) >= 1, a.get("_ai")
    game["units"] = [unit for unit in game["units"]
                     if unit["kind"] != "bomb_truck"]
    assert player_hq(game, b["id"]) is not None
    a["cash"] = 2000
    a["buildQueue"] = []
    before_trucks = queued_kinds(game, a["id"]).count("bomb_truck")
    server.tick_bots(room)
    queued = a.get("buildQueue") or []
    assert queued, queued
    assert queued[0]["kind"] in ("refinery", "power"), queued
    after_trucks = queued_kinds(game, a["id"]).count("bomb_truck")
    assert after_trucks == before_trucks, (before_trucks, after_trucks,
                                           queued_kinds(game, a["id"]))
    print("  波次失败 → 建造 %s，未加卡车: PASS" % queued[0]["kind"])

    print("\n=== 大师 AI 测试全部通过 ===")


def hypot(dx, dy):
    return (dx * dx + dy * dy) ** 0.5


def math_near_hq(target, hq):
    if hq is None:
        return False
    return hypot(target["x"] - hq["x"], target["y"] - hq["y"]) < server.BOT_CLUSTER_RADIUS


if __name__ == "__main__":
    main()
