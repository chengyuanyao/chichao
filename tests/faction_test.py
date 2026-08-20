#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""阵营对抗（科技·钢铁军团 vs 魔法·秘法会）测试：
   1) 出生配置按阵营分叉（独立经济：主堡/法力塔/精炼所/浮游晶簇）
   2) 阵营门槛：跨阵营不能建造/生产
   3) 克制矩阵：magic 熔重甲、tesla 干扰魔导甲（×1.6）
   4) 冰霜减速：命中挂 slow，到期恢复
   5) 基地车展开/折叠的阵营映射（mmcv <-> mhq）
   6) 独立经济：浮游晶簇把水晶运回精炼所结算资金
   7) 魔法 AI：按 role 决策，只建/产本阵营（圣殿/法阵/法师/傀儡…）
   8) 魔法可在主堡旁放置圣殿（建造锚点按 role，不是写死 tech kind）
   9) 摧毁总部即淘汰；折叠成基地车不算失去指挥
"""

from __future__ import print_function

import math
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import server


def make_room(tag, magic_b=False):
    a = server.create_human("A", server.COLORS[0])
    b = server.create_human("B", server.COLORS[1])
    if magic_b:
        b["faction"] = "magic"
    room = {
        "id": tag, "name": "faction test", "status": "lobby",
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


def find_clear(game, size=58.0):
    terrain = server.game_terrain(game)
    m = game["map"]
    x = 700.0
    while x < m["width"] - 700:
        y = 700.0
        while y < m["height"] - 700:
            if server.position_clear(game, x, y, size) and not terrain.blocked(x, y, 30):
                return x, y
            y += 350.0
        x += 350.0
    return None


def main():
    print("=== Test 1: 出生配置按阵营分叉 ===")
    room, a, b = make_room("FAC01", magic_b=True)
    game = room["game"]

    def owned(pid, lst):
        return sorted(e["kind"] for e in lst if e["owner"] == pid)

    a_structs = owned(a["id"], game["structures"])
    b_structs = owned(b["id"], game["structures"])
    a_units = owned(a["id"], game["units"])
    b_units = owned(b["id"], game["units"])
    assert a_structs == ["hq", "power", "refinery"], a_structs
    assert b_structs == ["mhq", "mpower", "mrefinery"], b_structs
    assert a_units.count("rifle") == 3 and "tank" in a_units and "harvester" in a_units, a_units
    assert b_units.count("mage") == 3 and "golem" in b_units and "mharvester" in b_units, b_units
    print("  科技基地/魔法基地各自成体系: PASS")

    print("\n=== Test 2: 阵营门槛 ===")
    room, a, b = make_room("FAC02", magic_b=True)
    game = room["game"]
    a["cash"] = b["cash"] = 99999
    # 魔法不能建/产科技
    for bad in ("barracks", "factory", "turret"):
        try:
            server.queue_structure(room, b["id"], bad)
            raise AssertionError("魔法不该能建 %s" % bad)
        except ValueError as exc:
            assert "阵营" in str(exc), str(exc)
    # 科技不能建/产魔法
    for bad in ("mtemple", "mcircle", "mtower", "mspring"):
        try:
            server.queue_structure(room, a["id"], bad)
            raise AssertionError("科技不该能建 %s" % bad)
        except ValueError as exc:
            assert "阵营" in str(exc), str(exc)
    # place_structure 也要挡跨阵营，不能只靠 queue_structure
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
    # 魔法有圣殿就能出法师；科技给兵营也产不出法师
    give(game, b["id"], "mtemple")
    server.queue_unit(room, b["id"], "mage")
    give(game, a["id"], "barracks")
    try:
        server.queue_unit(room, a["id"], "mage")
        raise AssertionError("科技不该能产法师")
    except ValueError as exc:
        assert "阵营" in str(exc), str(exc)
    print("  双向阵营门槛: PASS")

    print("\n=== Test 3: 克制矩阵（magic 熔重甲 / tesla 干扰魔导） ===")
    room, a, b = make_room("FAC03")
    game = room["game"]
    # magic vs 重甲坦克 ×1.6
    tank = server.make_unit("tank", b["id"], 9000, 9000)
    game["units"].append(tank)
    before = tank["hp"]
    server.apply_damage(room, tank, 100, a["id"], "magic", game)
    assert abs((before - tank["hp"]) - 100 * 1.6) < 0.1, (before - tank["hp"])
    print("  magic vs 重甲: ×1.6 PASS")
    # tesla vs 魔导法师 ×1.6（仍高于对步兵 0.80 / 对轻甲 1.40）
    mage = server.make_unit("mage", b["id"], 9000, 9000)
    game["units"].append(mage)
    before = mage["hp"]
    server.apply_damage(room, mage, 26, a["id"], "tesla", game)
    assert abs((before - mage["hp"]) - 26 * 1.6) < 0.1, (before - mage["hp"])
    print("  tesla vs 魔导: ×1.6 PASS")
    # magic 拆不动建筑 ×0.6
    turret = give(game, b["id"], "turret")
    before = turret["hp"]
    server.apply_damage(room, turret, 100, a["id"], "magic", game)
    assert abs((before - turret["hp"]) - 100 * 0.6) < 0.1, (before - turret["hp"])
    print("  magic vs 建筑: ×0.6 PASS")

    print("\n=== Test 4: 冰霜减速 ===")
    room, a, b = make_room("FAC04")
    game = room["game"]
    tank = server.make_unit("tank", b["id"], 9000, 9000)
    game["units"].append(tank)
    # 直接挂减速
    server.apply_slow({"slow": {"mult": 0.45, "duration": 2.5}}, tank)
    assert abs(tank["slowMult"] - 0.45) < 1e-6 and abs(tank["slowTimer"] - 2.5) < 1e-6
    # 实测减速生效：move_toward 的位移应小于满速
    terrain = server.game_terrain(game)
    tank["destX"], tank["destY"] = 9500.0, 9000.0
    x0 = tank["x"]
    server.move_toward(terrain, tank, tank["destX"], tank["destY"],
                       server.UNIT_TYPES["tank"]["speed"], 0.05)
    slowed_step = tank["x"] - x0
    tank2 = server.make_unit("tank", b["id"], 9000, 9000)
    x1 = tank2["x"]
    server.move_toward(terrain, tank2, 9500.0, 9000.0, server.UNIT_TYPES["tank"]["speed"], 0.05)
    full_step = tank2["x"] - x1
    assert slowed_step < full_step * 0.6, (slowed_step, full_step)
    print("  挂减速后位移≈45%%（%.2f vs %.2f）: PASS" % (slowed_step, full_step))

    print("\n=== Test 5: 基地车展开/折叠阵营映射 ===")
    assert server.UNIT_TYPES["mmcv"]["deploysInto"] == "mhq"
    assert server.STRUCTURE_TYPES["mhq"]["packsInto"] == "mmcv"
    assert server.UNIT_TYPES["mcv"]["deploysInto"] == "hq"
    assert server.STRUCTURE_TYPES["hq"]["packsInto"] == "mcv"
    room, a, b = make_room("FAC05", magic_b=True)
    game = room["game"]
    spot = find_clear(game)
    assert spot, "找不到空地"
    mmcv = server.make_unit("mmcv", b["id"], spot[0], spot[1])
    game["units"].append(mmcv)
    server.issue_deploy(game, b["id"], [mmcv["id"]])
    assert any(s["owner"] == b["id"] and s["kind"] == "mhq" for s in game["structures"]), "mmcv 应展开为 mhq"
    print("  mmcv→mhq 展开: PASS")

    print("\n=== Test 6: 独立经济（浮游晶簇→精炼所→资金） ===")
    assert server.UNIT_TYPES["mharvester"]["armor"] == server.UNIT_TYPES["harvester"]["armor"] == "heavy"
    assert server.UNIT_TYPES["mmcv"]["armor"] == server.UNIT_TYPES["mcv"]["armor"] == "heavy"
    assert server.UNIT_TYPES["mharvester"]["capacity"] == server.UNIT_TYPES["harvester"]["capacity"]
    assert server.UNIT_TYPES["mharvester"]["harvestRate"] == server.UNIT_TYPES["harvester"]["harvestRate"]
    room, a, b = make_room("FAC06", magic_b=True)
    game = room["game"]
    # 现成激活的水晶精炼所 + 满载的浮游晶簇
    mref = server.make_structure("mrefinery", b["id"], 5000, 5000, True)
    game["structures"].append(mref)
    hv = server.make_unit("mharvester", b["id"], 5040, 5000)
    hv["cargo"] = 850.0
    game["units"].append(hv)
    cash0 = b["cash"]
    terrain = server.game_terrain(game)
    for _ in range(30):
        server.tick_harvester(room, hv, 0.05, None, terrain)
        if b["cash"] > cash0:
            break
    assert b["cash"] > cash0, "浮游晶簇应把水晶运回精炼所换钱"
    print("  交付 %d 资金: PASS" % (b["cash"] - cash0))

    print("\n=== Test 7: 魔法 AI 只建/产本阵营 ===")
    room, a, b = make_room("FAC07", magic_b=True)
    game = room["game"]
    b["isBot"] = True
    # 7a 建筑决策：fresh 魔法基地（主堡/法力塔/精炼所齐备、不缺电）下一步该立圣殿
    b["cash"] = 99999
    b["buildQueue"] = []
    server.tick_bots(room)
    queued = b.get("buildQueue", [])
    assert queued and queued[0]["kind"] == "mtemple", queued
    print("  魔法 AI 首选建造圣殿 mtemple: PASS")
    # 7b 出兵决策：圣殿+法阵都在转时，产的必须全是魔法兵种
    b["buildQueue"] = []
    give(game, b["id"], "mtemple")
    give(game, b["id"], "mcircle")
    for _ in range(6):
        server.tick_bots(room)
    produced = [item for s in game["structures"] if s["owner"] == b["id"] for item in s["queue"]]
    assert produced, "魔法 AI 应已开始生产"
    assert all(item["kind"] in server.MAGIC_UNITS for item in produced), produced
    # 也绝不能偷偷排进科技建筑
    assert not b.get("buildQueue") or b["buildQueue"][0]["kind"] in server.MAGIC_STRUCTURES, b["buildQueue"]
    print("  魔法 AI 生产的全是魔法兵种: %s PASS" % sorted(set(i["kind"] for i in produced)))

    print("\n=== Test 8: 魔法可在主堡旁放置圣殿 ===")
    room, a, b = make_room("FAC08", magic_b=True)
    game = room["game"]
    b["cash"] = 99999
    mhq = next(s for s in game["structures"] if s["owner"] == b["id"] and s["kind"] == "mhq")
    assert server.construction_anchor_near(game, b["id"], mhq["x"] + 80, mhq["y"] + 80), \
        "mhq 应按 hq role 提供建造锚点"
    assert not server.construction_anchor_near(game, b["id"], mhq["x"] + 2000, mhq["y"] + 2000), \
        "远离主堡不应有锚点"

    placed = None
    for radius in (150, 180, 210, 250, 300):
        for deg in range(0, 360, 15):
            rad = math.radians(deg)
            x = mhq["x"] + math.cos(rad) * radius
            y = mhq["y"] + math.sin(rad) * radius
            try:
                placed = server.place_structure(room, b["id"], "mtemple", x, y, free=True)
                break
            except ValueError:
                continue
        if placed:
            break
    assert placed is not None and placed["kind"] == "mtemple", "应能在魔法主堡旁放下奥术圣殿"
    print("  place_structure mtemple 靠近 mhq: PASS")

    # 队列就绪后 AI 也必须能落地，否则魔法电脑永远卡在「建筑已就绪」
    b["isBot"] = True
    b["buildQueue"] = [{
        "id": "c-ready", "kind": "mtower",
        "remaining": 0.0, "total": 12.0, "ready": True,
    }]
    assert server.bot_place_prepared(room, b, "mtower"), "魔法 AI 应按 role 找到锚点并放置奥术塔"
    assert any(s["owner"] == b["id"] and s["kind"] == "mtower" for s in game["structures"])
    print("  bot_place_prepared mtower: PASS")

    server.handle_game_command(room, b, {
        "command": "setRally", "structureId": placed["id"],
        "x": placed["x"] + 80, "y": placed["y"] + 40,
    })
    assert placed.get("rally"), "奥术圣殿应能设集结点"
    print("  圣殿集结点: PASS")

    print("\n=== Test 9: 摧毁总部即淘汰（折叠基地车除外）===")
    room, a, b = make_room("FAC09", magic_b=True)
    game = room["game"]
    leftover = [s for s in game["structures"] if s["owner"] == b["id"] and s["kind"] != "mhq"]
    assert leftover, "开局除主堡外应还有法力塔/精炼所"
    for s in game["structures"]:
        if s["owner"] == b["id"] and s["kind"] == "mhq":
            s["hp"] = 0
    server.remove_destroyed_and_check(room)
    assert b["eliminated"] is True, "只拆主堡、留下其他建筑也应淘汰"
    assert not a["eliminated"]
    print("  拆 mhq 即淘汰（留下 mpower/mrefinery）: PASS")

    room, a, b = make_room("FAC10", magic_b=True)
    game = room["game"]
    mhq = next(s for s in game["structures"] if s["owner"] == b["id"] and s["kind"] == "mhq")
    server.issue_undeploy(game, b["id"], mhq["id"])
    assert any(u["owner"] == b["id"] and u["kind"] == "mmcv" and u["hp"] > 0 for u in game["units"])
    server.remove_destroyed_and_check(room)
    assert b["eliminated"] is False, "折叠主堡成迁徙法阵不应立刻战败"
    for u in game["units"]:
        if u["owner"] == b["id"] and server.unit_role(u["kind"]) == "mcv":
            u["hp"] = 0
    server.remove_destroyed_and_check(room)
    assert b["eliminated"] is True, "主堡与迁徙法阵都没了才淘汰"
    print("  折叠保命 / 再拆迁徙法阵才淘汰: PASS")

    print("\n=== 阵营对抗测试全部通过 ===")


if __name__ == "__main__":
    main()
