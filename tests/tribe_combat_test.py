#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""固定种子交战；--measure 输出实测与设计差异，数值仍以 catalog 为准。"""
from __future__ import print_function

import json
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from tribe_redesign_test import make_room
import server

SEEDS = (11, 23, 37, 41, 53)
EARLY = ["spear"] * 3 + ["javelin"] * 2 + ["wolf"] * 2
MIXED = ["javelin"] * 2 + ["spear"] * 2 + ["scorpion"] * 2 + ["tamer"]
# (名称、双方编制、决定性胜方；None 表示均势、均势上限)
SCENARIOS = (
    ("four_javelins", ["javelin"] * 4, ["tank"], "a", None),
    ("two_javelins", ["javelin"] * 2, ["tank"], None, .30),
    ("spike_one_tank", ["tspiketower"], ["tank"], "a", None),
    ("spike_two_tanks", ["tspiketower"], ["tank"] * 2, "b", None),
    ("toxin_six_rifles", ["ttoxtower"], ["rifle"] * 6, "a", None),
    ("toxin_one_tank", ["ttoxtower"], ["tank"], "a", None),
    ("scorpion_tank", ["scorpion"], ["tank"], None, .30),
    ("scorpion_spear", ["scorpion", "spear"], ["tank"], "a", None),
    ("early_tech", EARLY, ["rifle"] * 3 + ["rocket"] * 2 + ["tank"], "a", None),
    ("early_magic", EARLY, ["imp"] * 3 + ["mage", "golem"], "a", None),
    ("mixed", MIXED, ["tank"] * 3 + ["rifle"] * 2, None, .60),
    ("garrison", ["spear"] * 3 + ["javelin", "wolf"], ["rifle"] * 3 + ["tank"], "a", None),
    ("catapult_turret", ["catapult"], ["turret"], "a", None),
    ("catapult_mtower", ["catapult"], ["mtower"], "b", None),
)


# 2026-10-03：对称单列、28 间距、5 种子实测均值 ±0.15。
INTERVALS = {'four_javelins': (0.593496, 0.893496), 'spike_one_tank': (0.461429, 0.761429), 'spike_two_tanks': (0.15, 0.45), 'toxin_six_rifles': (0.61054, 0.91054), 'toxin_one_tank': (0.442, 0.742), 'scorpion_spear': (0.633699, 0.933699), 'early_tech': (0.326565, 0.626565), 'early_magic': (0.356009, 0.656009), 'garrison': (0.187011, 0.487011), 'catapult_turret': (0.85, 1), 'catapult_mtower': (0.718462, 1)}


def combat(scenario, seed, hunt_bonus=None):
    name, kinds_a, kinds_b, _, _ = scenario
    faction_b = "magic" if any(server.kind_faction(k) == "magic" for k in kinds_b) else "tech"
    room, a, b = make_room("COMBAT", faction_b=faction_b)
    game = room["game"]
    for key in ("units", "structures", "neutralCamps", "projectiles", "effects", "crates"):
        game[key] = []
    for key in ("nextCrateAt", "victoryClock", "botClock"):
        game[key] = 1e9
    room["neutrals"] = game["neutrals"] = False
    random.seed(seed)
    sides = []
    for player, kinds, x in ((a, kinds_a, 1800.0), (b, kinds_b, 2220.0)):
        army = []
        for index, kind in enumerate(kinds):
            # 对称单列，28 间距，编制顺序固定；双方中心距离 420。
            y = 1600.0 + (index - (len(kinds) - 1) / 2.0) * 28.0
            structure = kind in server.STRUCTURE_TYPES
            entity = (server.make_structure(kind, player["id"], x, y)
                      if structure else server.make_unit(kind, player["id"], x, y))
            game["structures" if structure else "units"].append(entity)
            army.append(entity)
        sides.append(army)
    for player, own, enemy in ((a, sides[0], sides[1]), (b, sides[1], sides[0])):
        ids = [u["id"] for u in own if u["id"].startswith("u")]
        if not ids:
            continue
        if any(e["id"].startswith("s") for e in enemy):
            server.issue_attack(game, player["id"], ids, enemy[0]["id"])
        else:
            server.issue_move(game, player["id"], ids, enemy[0]["x"], 1600, attack_move=True)
    original = server.HUNT_MARK_BONUS
    try:
        if hunt_bonus is not None:
            server.HUNT_MARK_BONUS = hunt_bonus
        for _ in range(1800):
            server.tick_game(room, .05)
            if any(not any(e["hp"] > 0 for e in army) for army in sides):
                break
    finally:
        server.HUNT_MARK_BONUS = original
    ratios = []
    for army in sides:
        def cost(e):
            return (server.STRUCTURE_TYPES if e["id"].startswith("s") else server.UNIT_TYPES)[e["kind"]]["cost"]
        total = sum(cost(e) for e in army)
        ratios.append(sum(cost(e) * max(0.0, e["hp"]) / e["maxHp"] for e in army) / total)
    alive = [any(e["hp"] > 0 for e in army) for army in sides]
    winner = "a" if alive == [True, False] else "b" if alive == [False, True] else "draw"
    return {"seed": seed, "a": ratios[0], "b": ratios[1],
            "margin": ratios[0] - ratios[1], "winner": winner,
            "seconds": game["elapsed"]}


def main():
    print("Feature: tribe-faction-redesign, Property 10: 固定种子交战回归")
    measured = {}
    differences = []
    for scenario in SCENARIOS:
        name, _, _, winner, limit = scenario
        rows = [combat(scenario, seed) for seed in SEEDS]
        measured[name] = rows
        for row in rows:
            if winner is not None and row["winner"] != winner:
                differences.append((name, row["seed"], "胜负方向", winner, row["winner"]))
            if winner is not None:
                low, high = INTERVALS[name]
                assert low <= row[winner] <= high, (name, row)
            if limit is not None and abs(row["margin"]) > limit:
                differences.append((name, row["seed"], "均势上限", limit, row["margin"]))
            if name == "catapult_turret" and (row["seconds"] > 30 or row["a"] < .99):
                differences.append((name, row["seed"], "无损攻城", 30, row))
        print("%s: %s" % (name, [(r["seed"], r["winner"], round(r["margin"], 4)) for r in rows]))
    no_mark = [combat(SCENARIOS[10], seed, 1.0) for seed in SEEDS]
    if sum(r["a"] for r in measured["mixed"]) + 1e-9 < sum(r["a"] for r in no_mark):
        differences.append(("mixed", "猎印 A/B", measured["mixed"], no_mark))
    if "--measure" in sys.argv:
        print(json.dumps({"scenarios": measured, "noMark": no_mark, "differences": differences}, ensure_ascii=False))
    assert not differences, "设计交战类别或胜负与实测不同，保留目录数值待复核：%r" % differences
    print("固定种子交战通过")


if __name__ == "__main__":
    main()
