#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Building death must not cripple remaining combat.

「建筑被打掉后不影响作战」:
  - 电厂/兵营/工厂/精炼厂/圣泉被拆后，已出场部队仍全速全伤
  - 残骸不挡作战走位
  - 失去生产建筑不会冻住或删掉现有部队、也不会取消作战指令
  - 拆掉指挥中心/魔法主堡仍按 PR #3 淘汰该玩家
  - 死掉的生产建筑不能再训练；没被拆的炮塔继续开火
"""

from __future__ import print_function

import os
import random
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import server


def make_room(tag, teams=None, magic_b=False):
    random.seed(hash(tag) % 100000)
    alpha = server.create_human("甲", server.COLORS[0], team=(teams[0] if teams else 0))
    beta = server.create_human("乙", server.COLORS[1], team=(teams[1] if teams else 0))
    if magic_b:
        beta["faction"] = "magic"
    room = {
        "id": tag, "name": "death-combat", "status": "lobby",
        "hostId": alpha["id"],
        "players": {alpha["id"]: alpha, beta["id"]: beta},
        "chat": [], "game": None, "createdAt": time.time(),
    }
    server.start_game(room)
    game = room["game"]
    game["terrainCtx"] = server.FLAT_TERRAIN
    game["victoryClock"] = 999.0
    game["botClock"] = 999.0
    return room, alpha, beta


def tick_for(room, seconds, step=0.05):
    for _ in range(int(round(seconds / step))):
        server.tick_game(room, step)


def kill_role(game, owner_id, role):
    for structure in game["structures"]:
        if (structure["owner"] == owner_id
                and server.structure_role(structure["kind"]) == role):
            structure["hp"] = 0


def strip_starting_army(game):
    game["units"] = []
    game["projectiles"] = []
    game["effects"] = []


def expected_hit(attacker_kind, target):
    definition = server.UNIT_TYPES[attacker_kind]
    if target["id"].startswith("u"):
        armor = server.UNIT_TYPES[target["kind"]].get("armor", "structure")
    else:
        armor = server.STRUCTURE_TYPES[target["kind"]].get("armor", "structure")
    return definition["damage"] * server.damage_armor_multiplier(
        definition.get("damageType"), armor)


def fire_until_hit(room, attacker, victim, seconds=1.5):
    """Tick until the attacker lands one shot; return damage dealt."""
    game = room["game"]
    attacker["cooldown"] = 0.0
    attacker["scan"] = 0.0
    attacker["order"] = "attack"
    attacker["targetId"] = victim["id"]
    attacker["destX"] = None
    attacker["destY"] = None
    hp_before = victim["hp"]
    for _ in range(int(seconds / 0.05)):
        server.tick_game(room, 0.05)
        if victim["hp"] < hp_before - 0.05:
            return hp_before - victim["hp"]
        if not any(p.get("sourceId") == attacker["id"] for p in game["projectiles"]):
            attacker["cooldown"] = 0.0
    return hp_before - victim["hp"]


def force_brownout(room, player):
    """Leave HQ plus hungry consumers and no plants so supply < usage."""
    game = room["game"]
    hq = next(s for s in game["structures"]
              if s["owner"] == player["id"] and server.structure_role(s["kind"]) == "hq")
    game["structures"] = [hq]
    for kind, x, y in (("factory", hq["x"] + 180, hq["y"]),
                       ("barracks", hq["x"] - 180, hq["y"]),
                       ("turret", hq["x"], hq["y"] + 180)):
        game["structures"].append(server.make_structure(kind, player["id"], x, y, True))
    server.invalidate_game_snapshot(game)
    supply, usage = server.player_power(room, player["id"])
    assert supply < usage, (supply, usage)
    return supply, usage


def main():
    print("=== Test 1: combat multiplier ignores brownout ===")
    room, alpha, beta = make_room("DC01")
    force_brownout(room, alpha)
    assert server.fielded_combat_multiplier(room, alpha["id"]) == 1.0
    assert server.production_power_factor(room, alpha["id"], 0.35) == 0.35
    print("  fielded 1.0 / production brownout 0.35: PASS")

    print("\n=== Test 2: kill power + factory, tank still moves and deals full damage ===")
    room, alpha, beta = make_room("DC02")
    game = room["game"]
    strip_starting_army(game)
    tank = server.make_unit("tank", alpha["id"], 900, 800)
    dummy = server.make_unit("tank", beta["id"], 1040, 800)
    dummy["hp"] = 4000
    dummy["maxHp"] = 4000
    game["units"].extend([tank, dummy])
    tank["kills"] = 0

    full_hit = fire_until_hit(room, tank, dummy)
    catalog = expected_hit("tank", dummy)
    assert abs(full_hit - catalog) < 0.6, (full_hit, catalog)

    start_x = 400.0
    tank["x"] = start_x
    tank["y"] = 800.0
    tank["targetId"] = None
    tank["order"] = "move"
    tank["destX"] = 1200.0
    tank["destY"] = 800.0
    tank["_path"] = None
    tick_for(room, 1.0)
    powered_travel = tank["x"] - start_x
    assert powered_travel > 50, powered_travel

    kill_role(game, alpha["id"], "power")
    kill_role(game, alpha["id"], "factory")
    kill_role(game, alpha["id"], "refinery")
    tick_for(room, 0.2)
    assert tank["hp"] > 0
    assert tank["id"] in [u["id"] for u in game["units"]]
    assert not alpha.get("eliminated")

    dummy["hp"] = 4000
    tank["x"] = 900
    tank["y"] = 800
    tank["kills"] = 0
    after_hit = fire_until_hit(room, tank, dummy)
    assert abs(after_hit - catalog) < 0.6, (after_hit, catalog, full_hit)

    tank["x"] = start_x
    tank["y"] = 800.0
    tank["targetId"] = None
    tank["order"] = "move"
    tank["destX"] = 1200.0
    tank["destY"] = 800.0
    tank["_path"] = None
    order_before = tank["order"]
    tick_for(room, 1.0)
    brownout_travel = tank["x"] - start_x
    assert tank["order"] in ("move", "guard"), tank["order"]
    assert brownout_travel > powered_travel * 0.92, (brownout_travel, powered_travel)
    assert order_before == "move"
    print("  tank damage %.1f==%.1f, travel %.1f~%.1f: PASS" % (
        after_hit, catalog, brownout_travel, powered_travel))

    print("\n=== Test 3: losing producer does not freeze or delete units / cancel attack ===")
    room, alpha, beta = make_room("DC03")
    game = room["game"]
    strip_starting_army(game)
    factory = server.make_structure("factory", alpha["id"], 700, 700, True)
    barracks = server.make_structure("barracks", alpha["id"], 760, 700, True)
    game["structures"].extend([factory, barracks])
    tank = server.make_unit("tank", alpha["id"], 900, 900)
    rifle = server.make_unit("rifle", alpha["id"], 920, 900)
    foe = server.make_unit("harvester", beta["id"], 1100, 900)
    game["units"].extend([tank, rifle, foe])
    server.issue_attack(game, alpha["id"], {tank["id"], rifle["id"]}, foe["id"])
    assert tank["order"] == "attack"
    factory["hp"] = 0
    barracks["hp"] = 0
    tick_for(room, 0.15)
    live_ids = set(u["id"] for u in game["units"])
    assert tank["id"] in live_ids and rifle["id"] in live_ids
    assert tank["order"] == "attack"
    assert tank["targetId"] == foe["id"]
    assert rifle["order"] == "attack"
    try:
        server.queue_unit(room, alpha["id"], "tank")
        raise AssertionError("dead factory must not train")
    except ValueError as error:
        assert "生产建筑" in str(error)
    print("  attack orders kept; train refused: PASS")

    print("\n=== Test 4: wreck / dead footprint does not block a path that was open ===")
    room, alpha, beta = make_room("DC04")
    game = room["game"]
    strip_starting_army(game)
    wreck = server.make_structure("factory", beta["id"], 800, 600, True)
    game["structures"].append(wreck)
    assert server.structure_blocks_combat_movement(wreck) is False
    tank = server.make_unit("tank", alpha["id"], 400, 600)
    game["units"].append(tank)
    server.issue_move(game, alpha["id"], {tank["id"]}, 1200, 600)
    tick_for(room, 0.3)
    x_before_kill = tank["x"]
    assert x_before_kill > 400
    wreck["hp"] = 0
    assert server.structure_blocks_combat_movement(wreck) is False
    # hp=0 wreck still sitting in the list must not stall the move.
    server.move_toward(
        server.FLAT_TERRAIN, tank, 1200, 600,
        server.UNIT_TYPES["tank"]["speed"], 0.25)
    assert tank["x"] > x_before_kill, (tank["x"], x_before_kill)
    tick_for(room, 8.0)
    assert not any(s["id"] == wreck["id"] for s in game["structures"]), "wreck should be removed"
    assert tank["x"] > 1000, tank["x"]
    print("  walked through dead factory footprint to x=%.0f: PASS" % tank["x"])

    print("\n=== Test 5: other turrets keep firing after one turret and the plant die ===")
    room, alpha, beta = make_room("DC05")
    game = room["game"]
    strip_starting_army(game)
    kill_role(game, alpha["id"], "power")
    turret_a = server.make_structure("turret", alpha["id"], 1000, 1000, True)
    turret_b = server.make_structure("turret", alpha["id"], 1060, 1000, True)
    game["structures"].extend([turret_a, turret_b])
    prey = server.make_unit("harvester", beta["id"], 1180, 1000)
    prey["hp"] = 5000
    game["units"].append(prey)
    turret_a["cooldown"] = 0.0
    turret_b["cooldown"] = 0.0
    tick_for(room, 0.8)
    shots_before = sum(1 for p in game["projectiles"] if p["owner"] == alpha["id"])
    hp_after_both = prey["hp"]
    assert hp_after_both < 5000 or shots_before > 0
    turret_a["hp"] = 0
    tick_for(room, 0.15)
    assert turret_a["id"] not in [s["id"] for s in game["structures"]]
    prey["hp"] = 5000
    turret_b["cooldown"] = 0.0
    tick_for(room, 1.0)
    assert prey["hp"] < 5000, "surviving turret should still fire"
    print("  leftover turret fired (prey hp %.0f): PASS" % prey["hp"])

    print("\n=== Test 6: HQ / 魔法主堡 still eliminates; leftover queue does not spawn ===")
    room, alpha, beta = make_room("DC06")
    game = room["game"]
    factory = server.make_structure("factory", beta["id"], 2000, 2000, True)
    factory["queue"] = [{"kind": "tank", "remaining": 0.05, "total": 8.0}]
    game["structures"].append(factory)
    beta_units_before = [u["id"] for u in game["units"] if u["owner"] == beta["id"]]
    kill_role(game, beta["id"], "hq")
    game["elapsed"] = 20.0
    game["victoryClock"] = 0.0
    tick_for(room, 1.2)
    assert beta["eliminated"] is True
    assert not alpha["eliminated"]
    assert room["status"] == "finished"
    assert game["winnerId"] == alpha["id"]
    leftover = [u for u in game["units"] if u["owner"] == beta["id"]]
    assert leftover == [], leftover
    assert factory["queue"] == []
    print("  HQ loss ends player, no ghost tank: PASS")

    print("\n=== Test 7: team HQ loss clears queues but does not wipe the teammate ===")
    a1 = server.create_human("队甲1", server.COLORS[0], team=1)
    a2 = server.create_human("队甲2", server.COLORS[1], team=1)
    b1 = server.create_human("队乙1", server.COLORS[2], team=2)
    b2 = server.create_human("队乙2", server.COLORS[3], team=2)
    room = {
        "id": "DC07", "name": "team-death", "status": "lobby",
        "hostId": a1["id"],
        "players": {p["id"]: p for p in (a1, a2, b1, b2)},
        "chat": [], "game": None, "createdAt": time.time(),
    }
    server.start_game(room)
    game = room["game"]
    game["elapsed"] = 20.0
    game["victoryClock"] = 0.0
    factory = server.make_structure("factory", b1["id"], 2500, 2500, True)
    factory["queue"] = [{"kind": "tank", "remaining": 0.02, "total": 8.0}]
    game["structures"].append(factory)
    kill_role(game, b1["id"], "hq")
    tick_for(room, 1.2)
    assert b1["eliminated"] is True
    assert b2["eliminated"] is False
    assert room["status"] != "finished"
    assert factory["queue"] == []
    assert not any(u["owner"] == b1["id"] for u in game["units"])
    print("  teammate lives; leftover factory queue emptied: PASS")

    print("\n=== Test 8: 圣泉 / 法力塔 down, existing golem still fights ===")
    room, alpha, beta = make_room("DC08", magic_b=True)
    game = room["game"]
    strip_starting_army(game)
    spring = server.make_structure("mspring", beta["id"], 3000, 800, True)
    plant = next(s for s in game["structures"]
                 if s["owner"] == beta["id"] and s["kind"] == "mpower")
    game["structures"].append(spring)
    golem = server.make_unit("golem", beta["id"], 900, 900)
    prey = server.make_unit("tank", alpha["id"], 980, 900)
    prey["hp"] = 4000
    game["units"].extend([golem, prey])
    hit_full = fire_until_hit(room, golem, prey)
    spring["hp"] = 0
    plant["hp"] = 0
    tick_for(room, 0.2)
    assert golem["id"] in [u["id"] for u in game["units"]]
    assert not beta.get("eliminated")
    prey["hp"] = 4000
    hit_after = fire_until_hit(room, golem, prey)
    catalog = expected_hit("golem", prey)
    assert abs(hit_after - catalog) < 0.6, (hit_after, catalog)
    assert abs(hit_after - hit_full) < 0.6, (hit_after, hit_full)
    print("  golem full damage after 圣泉/法力塔 lost: PASS")

    print("\n=== 建筑死亡不瘫痪作战：全部通过 ===")


if __name__ == "__main__":
    main()
