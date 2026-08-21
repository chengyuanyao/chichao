#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""秘法会针对性补强：玻璃后排、轻甲经济、磁暴/狙击过伤。
   不改钢铁身份（军犬仍一口清步兵，磁暴仍克载具）。
   自爆卡车与魔仆造价/血/速/爆炸仍对齐。
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
        "id": tag, "name": "magic balance test", "status": "lobby",
        "hostId": a["id"],
        "players": {a["id"]: a, b["id"]: b},
        "chat": [], "game": None, "createdAt": time.time(),
    }
    server.start_game(room)
    return room, a, b


def bite_to(armor):
    return (server.UNIT_TYPES["dog"]["damage"]
            * server.DAMAGE_MULTIPLIER["bite"][armor])


def main():
    print("=== Test 1: 军犬一口咬不死法师/女巫，两口仍死 ===")
    bite_arcane = bite_to("arcane")
    assert abs(bite_arcane - 90.0) < 0.1, bite_arcane
    assert bite_to("infantry") >= 240.0
    for kind in ("mage", "frost"):
        hp = server.UNIT_TYPES[kind]["hp"]
        assert hp > bite_arcane, (kind, hp, bite_arcane)
        leftover = hp - bite_arcane
        assert leftover > 0
        assert leftover < hp * 0.55, leftover
        assert bite_arcane * 2 >= hp, (kind, hp)
    room, a, b = make_room("MB01")
    game = room["game"]
    bite = server.UNIT_TYPES["dog"]["damage"]
    for kind in ("mage", "frost"):
        unit = server.make_unit(kind, b["id"], 9000, 9000)
        game["units"].append(unit)
        server.apply_damage(room, unit, bite, a["id"], "bite", game)
        assert unit["hp"] > 0, "%s 一口应活，剩 %s" % (kind, unit["hp"])
        server.apply_damage(room, unit, bite, a["id"], "bite", game)
        assert unit["hp"] <= 0, "%s 两口应死" % kind
    print("  咬 90 / 血 160，一口剩 70: PASS")

    print("\n=== Test 2: 自爆卡车与爆裂魔仆战斗数值仍对齐 ===")
    truck = server.UNIT_TYPES["bomb_truck"]
    hexling = server.UNIT_TYPES["hexling"]
    for field in ("cost", "hp", "speed", "build", "damageType"):
        assert truck[field] == hexling[field], (field, truck[field], hexling[field])
    for field in ("damage", "radius", "chainRadius", "damageType"):
        assert truck["deathExplosion"][field] == hexling["deathExplosion"][field], (
            field, truck["deathExplosion"][field], hexling["deathExplosion"][field])
    assert hexling["hp"] > bite_arcane
    assert hexling["armor"] == "arcane"
    assert truck["armor"] == "light"
    assert server.is_dog_prey("hexling")
    assert not server.is_dog_prey("bomb_truck")
    room, a, b = make_room("MB02")
    game = room["game"]
    familiar = server.make_unit("hexling", b["id"], 9100, 9100)
    game["units"].append(familiar)
    before = familiar["hp"]
    dog_bite = server.UNIT_TYPES["dog"]["damage"]
    server.apply_damage(room, familiar, dog_bite, a["id"], "bite", game)
    assert familiar["hp"] > 0
    assert abs((before - familiar["hp"]) - bite_arcane) < 0.1
    print("  640/160/122.4/700/r120/连带130 对齐，魔仆一口不死: PASS")

    print("\n=== Test 3: 经济甲种与钢铁对齐，采矿仍结算 ===")
    assert server.UNIT_TYPES["mharvester"]["armor"] == "heavy"
    assert server.UNIT_TYPES["mmcv"]["armor"] == "heavy"
    assert server.UNIT_TYPES["harvester"]["armor"] == "heavy"
    assert server.UNIT_TYPES["mcv"]["armor"] == "heavy"
    for field in ("cost", "hp", "speed", "build", "capacity", "harvestRate"):
        assert (server.UNIT_TYPES["mharvester"][field]
                == server.UNIT_TYPES["harvester"][field]), field
    room, a, b = make_room("MB03")
    game = room["game"]
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
    assert b["cash"] > cash0
    rifle_vs_heavy = 100 * server.DAMAGE_MULTIPLIER["bullet"]["heavy"]
    rifle_vs_light = 100 * server.DAMAGE_MULTIPLIER["bullet"]["light"]
    crystal = server.make_unit("mharvester", b["id"], 9200, 9200)
    game["units"].append(crystal)
    before = crystal["hp"]
    server.apply_damage(room, crystal, 100, a["id"], "bullet", game)
    assert abs((before - crystal["hp"]) - rifle_vs_heavy) < 0.1
    assert rifle_vs_heavy < rifle_vs_light
    print("  晶簇/迁徙 heavy，交付资金，步枪按重甲结算: PASS")

    print("\n=== Test 4: 磁暴/狙击对魔导下调，钢铁身份不动 ===")
    tesla = server.DAMAGE_MULTIPLIER["tesla"]
    sniper = server.DAMAGE_MULTIPLIER["sniper"]
    assert abs(tesla["arcane"] - 1.60) < 1e-6
    assert abs(sniper["arcane"] - 1.60) < 1e-6
    assert tesla["arcane"] > 1.0
    assert tesla["arcane"] > tesla["infantry"]
    assert tesla["arcane"] > tesla["light"]
    assert abs(tesla["light"] - 1.40) < 1e-6
    assert abs(tesla["heavy"] - 1.30) < 1e-6
    assert abs(sniper["infantry"] - 2.20) < 1e-6
    assert abs(sniper["light"] - 0.40) < 1e-6
    tesla_hit = 26 * tesla["arcane"]
    sniper_hit = 55 * sniper["arcane"]
    mage_hp = server.UNIT_TYPES["mage"]["hp"]
    frost_hp = server.UNIT_TYPES["frost"]["hp"]
    hex_hp = server.UNIT_TYPES["hexling"]["hp"]
    assert tesla_hit < mage_hp, "磁暴不应一枪法师"
    assert tesla_hit * 2 < mage_hp, "160 血法师应吃下两发磁暴"
    assert sniper_hit < mage_hp, "狙击不应一枪法师"
    assert sniper_hit * 2 >= mage_hp
    assert tesla_hit * 2 < hex_hp
    assert sniper_hit < hex_hp
    room, a, b = make_room("MB04")
    game = room["game"]
    mage = server.make_unit("mage", b["id"], 9000, 9000)
    game["units"].append(mage)
    before = mage["hp"]
    server.apply_damage(room, mage, 26, a["id"], "tesla", game)
    assert abs((before - mage["hp"]) - tesla_hit) < 0.1
    assert mage["hp"] > 0
    print("  tesla/sniper vs arcane ×1.6；对载具/步兵表不变: PASS")

    print("\n=== Test 5: 钢铁单位本身没被砍 ===")
    dog = server.UNIT_TYPES["dog"]
    tesla_u = server.UNIT_TYPES["tesla"]
    overlord = server.UNIT_TYPES["overlord"]
    assert dog["damage"] == 60.0 and dog["hp"] == 55
    assert tesla_u["damage"] == 26.0 and tesla_u["hp"] == 190
    assert overlord["hp"] == 1500 and overlord["damage"] == 120.0
    turret = server.STRUCTURE_TYPES["turret"]
    missile = server.STRUCTURE_TYPES["missile"]
    assert turret["damage"] == 80.0 and turret["range"] == 320.0
    assert missile["damage"] == 120.0 and missile["range"] == 420.0
    print("  军犬/磁暴/天启未动；双塔 80/320 与 120/420: PASS")

    print("\n=== Test 6: 巨龙仍低于天启，奥术塔仍弱于钢铁双塔组合 ===")
    dragon = server.UNIT_TYPES["dragon"]
    mtower = server.STRUCTURE_TYPES["mtower"]
    assert dragon["hp"] == 1100
    assert dragon["hp"] < overlord["hp"]
    assert dragon["damage"] == 95.0
    assert mtower["damage"] == 80.0
    assert mtower["range"] == 360.0
    assert mtower["cooldown"] == 0.9
    assert turret["range"] < mtower["range"] < missile["range"]
    tower_dps = mtower["damage"] / mtower["cooldown"]
    turret_dps = turret["damage"] / turret["cooldown"]
    missile_dps = missile["damage"] / missile["cooldown"]
    assert tower_dps < turret_dps
    assert missile_dps < tower_dps
    print("  巨龙 1100 < 天启 1500；奥术塔 DPS/射程夹在哨戒与导弹之间: PASS")

    print("\n=== 秘法会平衡测试全部通过 ===")


if __name__ == "__main__":
    main()
