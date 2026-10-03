#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""原始部落进阶：蛛网巨蛛。
   1) 目录 / 阵营 / 血祭坛门槛
   2) 吐丝命中定身（slow.mult 0），仍可开火；控制规则 H：定身中不续时，
      到期后 1 s 抗性内再中定身降为 ×0.5 减速，冰霜也解不了定身
   3) 可复用 DoT：刷新只续时，击杀记给巨蛛
   4) 建筑免疫；跨阵营不能产
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
        "id": tag, "name": "spider test", "status": "lobby",
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


def give(game, pid, kind):
    structure = server.make_structure(kind, pid, 900, 900, True)
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


def queued_kinds(game, pid):
    return [item["kind"] for structure in game["structures"]
            if structure["owner"] == pid for item in structure["queue"]]


def run_out_slow(unit, dt=0.05, limit=10.0):
    """按固定步长推进状态计时，直到减速/定身计时走完。

    0.05 步长累减可能残留 ~1e-17 的正余量，不能按「时长 / 步长」算步数，
    所以推进到 slowTimer <= 0 为止。
    """
    elapsed = 0.0
    while unit["slowTimer"] > 0.0:
        assert elapsed < limit, ("减速计时未走完", unit["slowTimer"])
        server.tick_status_timers(unit, dt)
        elapsed += dt
    return elapsed


def main():
    print("=== Test 1: 目录 / 阵营 / 血祭坛门槛字段 ===")
    spider = server.UNIT_TYPES["spider"]
    wolf = server.UNIT_TYPES["wolf"]
    frost = server.UNIT_TYPES["frost"]
    for field in ("name", "cost", "hp", "speed", "damage", "range",
                  "cooldown", "size", "build", "producer", "projectile",
                  "projectileSpeed", "splash", "sight", "armor",
                  "damageType", "requires", "slow", "dot"):
        assert field in spider, "spider 缺字段 %s" % field
    assert spider["name"] == "蛛网巨蛛"
    assert spider["producer"] == "tpen"
    assert spider["requires"] == ["taltar"]
    assert spider["faction"] == "tribe"
    assert spider["cost"] == 720
    assert 600 <= spider["cost"] <= 800
    assert spider["hp"] == 340
    assert 280 <= spider["hp"] <= 400
    assert spider["speed"] == 108.0
    assert spider["speed"] < wolf["speed"]
    assert spider["damage"] == 18.0
    assert spider["range"] == 170.0
    assert spider["cooldown"] == 1.45
    assert spider["size"] == 14.0
    assert spider["build"] == 8.0
    assert spider["splash"] == 0.0
    assert spider["sight"] == 400.0
    assert spider["projectile"] == "web"
    assert spider["projectileSpeed"] == 520.0
    assert spider["armor"] == "beast"
    assert spider["damageType"] == "venom"
    assert spider["slow"] == {"mult": 0.0, "duration": 2.2}
    assert spider["dot"] == {"dps": 14.0, "duration": 3.0, "damageType": "venom"}
    assert "spider" in server.TRIBE_UNITS
    assert "spider" not in server.VEHICLE_KINDS
    assert "spider" not in server.SUICIDE_KINDS
    assert not server.is_dog_prey("spider")
    assert spider["cost"] > frost["cost"]
    assert spider["hp"] > frost["hp"]
    assert spider["range"] < frost["range"]
    catalog = server.public_catalog()
    entry = catalog["units"]["spider"]
    assert entry["name"] == "蛛网巨蛛"
    assert entry["cost"] == 720
    assert entry["faction"] == "tribe"
    assert entry["producer"] == "tpen"
    assert entry["requires"] == ["taltar"]
    assert entry["repairable"] is True
    assert entry["canVeteran"] is True
    assert server.unit_move_slow({"slowMult": 0.0}) == 0.0
    assert server.unit_move_slow({}) == 1.0
    print("  定义/阵营/目录 requires: PASS")

    print("\n=== Test 2: 只有围栏不能出巨蛛；补血祭坛放行 ===")
    room, a, b = make_room("SPIDER01")
    game = room["game"]
    a["cash"] = 99999
    give(game, a["id"], "tpen")
    try:
        server.queue_unit(room, a["id"], "spider")
        raise AssertionError("无血祭坛时不该能出蛛网巨蛛")
    except ValueError as exc:
        assert "前置建筑" in str(exc), str(exc)
    give(game, a["id"], "taltar")
    server.queue_unit(room, a["id"], "spider")
    assert "spider" in queued_kinds(game, a["id"])
    print("  缺祭坛拒绝 / 补祭坛放行: PASS")

    print("\n=== Test 3: 跨阵营不能产巨蛛 ===")
    room, a, b = make_room("SPIDER02", tribe_a=False, magic_b=True)
    game = room["game"]
    a["cash"] = b["cash"] = 99999
    give(game, a["id"], "factory")
    give(game, a["id"], "repair")
    give(game, b["id"], "mcircle")
    give(game, b["id"], "mspring")
    for pid in (a["id"], b["id"]):
        try:
            server.queue_unit(room, pid, "spider")
            raise AssertionError("非部落不该能产蛛网巨蛛")
        except ValueError as exc:
            assert "阵营" in str(exc), str(exc)
    print("  钢铁/秘法拦截: PASS")

    print("\n=== Test 4: 定身锁位移，定身中不续时，仍可开火；到期进入抗性 ===")
    room, a, b = make_room("SPIDER03")
    game = room["game"]
    spider_u = server.make_unit("spider", a["id"], 1000, 1000)
    rifle = server.make_unit("rifle", b["id"], 1120, 1000)
    isolate(game, spider_u, rifle)
    terrain = server.game_terrain(game)
    server.apply_slow({"slow": spider["slow"]}, rifle)
    assert abs(rifle["slowMult"] - 0.0) < 1e-9
    assert abs(rifle["slowTimer"] - 2.2) < 1e-9
    pub = server.public_unit(rifle)
    assert pub.get("slow") is True
    assert pub.get("rooted") is True
    rifle["destX"], rifle["destY"] = 1400.0, 1000.0
    x0, y0 = rifle["x"], rifle["y"]
    server.move_toward(terrain, rifle, rifle["destX"], rifle["destY"],
                       server.UNIT_TYPES["rifle"]["speed"], 0.05)
    assert abs(rifle["x"] - x0) < 1e-9 and abs(rifle["y"] - y0) < 1e-9
    # 控制规则 H：定身期间再中定身不续时，剩余时长保持
    rifle["slowTimer"] = 0.4
    server.apply_slow({"slow": spider["slow"]}, rifle)
    assert abs(rifle["slowMult"] - 0.0) < 1e-9
    assert abs(rifle["slowTimer"] - 0.4) < 1e-9, rifle["slowTimer"]
    hq = next(structure for structure in game["structures"]
              if structure["owner"] == a["id"]
              and server.structure_role(structure["kind"]) == "hq")
    hq["slowMult"] = 1.0
    hq["slowTimer"] = 0.0
    server.apply_slow({"slow": spider["slow"]}, hq)
    assert hq.get("slowMult", 1.0) == 1.0
    rifle["order"] = "attack"
    rifle["targetId"] = spider_u["id"]
    rifle["cooldown"] = 0.0
    rifle["destX"] = rifle["destY"] = None
    server.tick_units(room, 0.05)
    assert game["projectiles"], "定身单位在射程内仍应开火"
    assert abs(rifle["x"] - x0) < 1e-9
    # 定身计时走完：恢复满速，并写入 1.0 s 定身抗性
    run_out_slow(rifle)
    assert rifle["slowMult"] == 1.0, rifle["slowMult"]
    assert abs(rifle["rootResist"] - 1.0) < 1e-9, rifle["rootResist"]
    pub = server.public_unit(rifle)
    assert pub.get("rootResist") is True
    assert pub.get("slow") is None and pub.get("rooted") is None
    # 抗性期内再中蛛网：定身降为 ×0.5 减速，时长不变
    server.apply_slow({"slow": spider["slow"]}, rifle)
    assert abs(rifle["slowMult"] - 0.5) < 1e-9, rifle["slowMult"]
    assert abs(rifle["slowTimer"] - 2.2) < 1e-9, rifle["slowTimer"]
    pub = server.public_unit(rifle)
    assert pub.get("slow") is True and pub.get("rooted") is None
    print("  定身锁位移 / 定身不续时 / 建筑免疫 / 仍可开火 / 抗性期降为 ×0.5: PASS")

    print("\n=== Test 5: 吐丝弹丸挂定身+DoT，刷新只续时 ===")
    room, a, b = make_room("SPIDER04")
    game = room["game"]
    spider_u = server.make_unit("spider", a["id"], 2000, 2000)
    rifle = server.make_unit("rifle", b["id"], 2080, 2000)
    isolate(game, spider_u, rifle)
    rifle["hp"] = 1000.0
    server.launch_projectile(game, spider_u, rifle, spider)
    shot = game["projectiles"][-1]
    assert shot["kind"] == "web"
    assert shot.get("slow") == spider["slow"]
    assert shot.get("dot") == spider["dot"]
    assert shot.get("damageType") == "venom"
    index = {spider_u["id"]: spider_u, rifle["id"]: rifle}
    for _ in range(20):
        server.tick_projectiles(room, 0.05, index)
        if not game["projectiles"]:
            break
    assert not game["projectiles"]
    assert abs(rifle["slowMult"] - 0.0) < 1e-9
    assert abs(rifle["slowTimer"] - 2.2) < 1e-6
    assert abs(rifle["dotDps"] - 14.0) < 1e-6
    assert abs(rifle["dotTimer"] - 3.0) < 1e-6
    assert rifle["dotOwner"] == a["id"]
    assert rifle["dotSourceId"] == spider_u["id"]
    assert rifle["dotSourceKind"] == "spider"
    assert rifle["dotDamageType"] == "venom"
    assert server.public_unit(rifle).get("dot") is True
    rifle["dotTimer"] = 0.6
    rifle["dotDps"] = 14.0
    server.apply_dot({"dot": spider["dot"], "owner": a["id"],
                      "sourceId": spider_u["id"], "sourceKind": "spider"}, rifle)
    assert abs(rifle["dotTimer"] - 3.0) < 1e-6
    assert abs(rifle["dotDps"] - 14.0) < 1e-6
    structure = next(s for s in game["structures"] if s["owner"] == a["id"])
    before_hp = structure["hp"]
    server.apply_dot({"dot": spider["dot"], "owner": b["id"]}, structure)
    assert not structure.get("dotTimer")
    assert abs(structure["hp"] - before_hp) < 1e-9
    print("  弹丸复制状态 / 刷新不叠乘 / 建筑无 DoT: PASS")

    print("\n=== Test 6: DoT 结算与击杀归属 ===")
    room, a, b = make_room("SPIDER05")
    game = room["game"]
    spider_u = server.make_unit("spider", a["id"], 3000, 3000)
    rifle = server.make_unit("rifle", b["id"], 3080, 3000)
    isolate(game, spider_u, rifle)
    rifle["hp"] = 8.0
    kills0 = a["kills"]
    spider_kills0 = spider_u.get("kills", 0)
    server.apply_dot({
        "dot": spider["dot"],
        "owner": a["id"],
        "sourceId": spider_u["id"],
        "sourceKind": "spider",
    }, rifle)
    index = {spider_u["id"]: spider_u, rifle["id"]: rifle}
    elapsed = 0.0
    while rifle["hp"] > 0 and elapsed < 3.0:
        server.tick_dot(room, rifle, 0.05, index)
        elapsed += 0.05
    assert rifle["hp"] <= 0, rifle["hp"]
    assert a["kills"] == kills0 + 1
    assert spider_u["kills"] == spider_kills0 + 1
    # venom vs 步甲 ×1.15：0.05s * 14 * 1.15 ≈ 0.805，8 血大约 0.5s 内死
    assert elapsed <= 1.0
    print("  DoT 击杀掉血/击杀/军衔归属: PASS")

    print("\n=== Test 7: 毒丝克制；冰霜解不了定身 ===")
    room, a, b = make_room("SPIDER06")
    game = room["game"]
    rifle = server.make_unit("rifle", b["id"], 4000, 4000)
    tank = server.make_unit("tank", b["id"], 4100, 4000)
    rifle["hp"] = tank["hp"] = 1000.0
    game["units"].extend((rifle, tank))
    before = rifle["hp"]
    server.apply_damage(room, rifle, 100, a["id"], "venom", game)
    assert abs((before - rifle["hp"]) - 115.0) < 0.1, before - rifle["hp"]
    before = tank["hp"]
    server.apply_damage(room, tank, 100, a["id"], "venom", game)
    assert abs((before - tank["hp"]) - 55.0) < 0.1, before - tank["hp"]
    # 控制规则 H：冰霜 0.45 弱于定身，命中已定身目标被忽略，定身与剩余时长保持
    server.apply_slow({"slow": spider["slow"]}, tank)
    server.apply_slow({"slow": frost["slow"]}, tank)
    assert tank["slowMult"] == 0.0, tank["slowMult"]
    assert abs(tank["slowTimer"] - 2.2) < 1e-9, tank["slowTimer"]
    assert server.public_unit(tank).get("rooted") is True
    # 定身到期后冰霜正常生效：冰霜是普通减速，定身抗性不影响它
    run_out_slow(tank)
    assert tank["slowMult"] == 1.0, tank["slowMult"]
    assert abs(tank["rootResist"] - 1.0) < 1e-9, tank["rootResist"]
    server.apply_slow({"slow": frost["slow"]}, tank)
    assert abs(tank["slowMult"] - 0.45) < 1e-6
    assert abs(tank["slowTimer"] - 2.5) < 1e-6
    assert server.public_unit(tank).get("rooted") is None
    print("  venom 克制 / 冰霜命中已定身目标仍定身 / 定身到期后冰霜生效: PASS")

    print("\n=== Test 8: 机器人在祭坛后才偏好转巨蛛 ===")
    scout = server.bot_empty_scout()
    with_altar = server.bot_support_choices(
        "tribe", set(["factory", "repair"]), False, False, True, 2)
    assert "spider" in with_altar, with_altar
    assert "wolf" in with_altar, with_altar
    no_altar = server.bot_support_choices(
        "tribe", set(["factory"]), False, False, True, 2)
    assert "spider" not in no_altar, no_altar
    late = server.bot_unit_choices(
        "tribe", set(["factory", "repair"]), server.BOT_PHASE_CLOSE,
        scout, False, True, 2, False)
    assert "spider" in late, late
    print("  围栏+祭坛才排巨蛛: PASS")

    print("\n=== 蛛网巨蛛测试全部通过 ===")


if __name__ == "__main__":
    main()
