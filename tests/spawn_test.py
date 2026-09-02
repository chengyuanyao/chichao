#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Spawn assignment tests: auto-grouping, manual override, team adjacency."""

from __future__ import print_function

import os
import random
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import server


def main():
    print("=== Test 1: 2 players, no teams - opposite corners ===")
    a = server.create_human("A", server.COLORS[0])
    b = server.create_human("B", server.COLORS[1])
    room = {
        "id": "SPN01", "name": "spawn test", "status": "lobby",
        "hostId": a["id"],
        "players": {a["id"]: a, b["id"]: b},
        "chat": [], "game": None, "createdAt": time.time(),
        "selectedMap": "gold_crater_small",
    }
    server.start_game(room)
    hq_a = next(s for s in room["game"]["structures"] if s["owner"] == a["id"] and s["kind"] == "hq")
    hq_b = next(s for s in room["game"]["structures"] if s["owner"] == b["id"] and s["kind"] == "hq")
    # Should be on opposite sides of the map
    assert abs(hq_a["x"] - hq_b["x"]) > 1500 or abs(hq_a["y"] - hq_b["y"]) > 1500
    print("  2P no-team: PASS (hq_a=(%.0f,%.0f) hq_b=(%.0f,%.0f))" % (hq_a["x"], hq_a["y"], hq_b["x"], hq_b["y"]))

    print("\n=== Test 2: 4 players, 2v2 teams - teammates on same side ===")
    t1a = server.create_human("红1", server.COLORS[0], team=1)
    t1b = server.create_human("红2", server.COLORS[1], team=1)
    t2a = server.create_human("蓝1", server.COLORS[2], team=2)
    t2b = server.create_human("蓝2", server.COLORS[3], team=2)
    room2 = {
        "id": "SPN02", "name": "2v2", "status": "lobby",
        "hostId": t1a["id"],
        "players": {p["id"]: p for p in [t1a, t1b, t2a, t2b]},
        "chat": [], "game": None, "createdAt": time.time(),
        "selectedMap": "gold_crater_small",
    }
    server.start_game(room2)
    game2 = room2["game"]

    spawn_pts = server.MAPS["gold_crater_small"]["spawnPoints"]

    def get_spawn_index(game, pid):
        s = next(s for s in game2["structures"] if s["owner"] == pid and s["kind"] == "hq")
        return min(range(len(spawn_pts)), key=lambda i: (
            (s["x"] - spawn_pts[i][0]) ** 2 + (s["y"] - spawn_pts[i][1]) ** 2))

    # 五边形地图上，同队应拿到相邻席位，两队不能占用同一席位。
    t1_positions = [get_spawn_index(game2, t1a["id"]), get_spawn_index(game2, t1b["id"])]
    t2_positions = [get_spawn_index(game2, t2a["id"]), get_spawn_index(game2, t2b["id"])]
    assert abs(t1_positions[0] - t1_positions[1]) == 1, t1_positions
    assert abs(t2_positions[0] - t2_positions[1]) == 1, t2_positions
    assert set(t1_positions).isdisjoint(t2_positions)
    print("  2v2 team adjacency: PASS")

    print("\n=== Test 3: Manual spawn override ===")
    t1a2 = server.create_human("红1", server.COLORS[0], team=1, spawn=4)  # force northwest
    t1b2 = server.create_human("红2", server.COLORS[1], team=1, spawn=3)  # force bottom-left
    t2a2 = server.create_human("蓝1", server.COLORS[2], team=2, spawn=0)  # force north
    t2b2 = server.create_human("蓝2", server.COLORS[3], team=2, spawn=1)  # force northeast
    room3 = {
        "id": "SPN03", "name": "manual", "status": "lobby",
        "hostId": t1a2["id"],
        "players": {p["id"]: p for p in [t1a2, t1b2, t2a2, t2b2]},
        "chat": [], "game": None, "createdAt": time.time(),
        "selectedMap": "gold_crater_small",
    }
    server.start_game(room3)
    game3 = room3["game"]

    spawn_pts = server.MAPS["gold_crater_small"]["spawnPoints"]
    hq = next(s for s in game3["structures"] if s["owner"] == t1a2["id"] and s["kind"] == "hq")
    assert abs(hq["x"] - spawn_pts[4][0]) < 5
    assert abs(hq["y"] - spawn_pts[4][1]) < 5
    hq = next(s for s in game3["structures"] if s["owner"] == t2a2["id"] and s["kind"] == "hq")
    assert abs(hq["x"] - spawn_pts[0][0]) < 5
    assert abs(hq["y"] - spawn_pts[0][1]) < 5
    print("  Manual spawn override: PASS")

    print("\n=== Test 4: 5 players, 3v2 teams ===")
    players = []
    for i in range(3):
        players.append(server.create_human("红%d" % (i+1), server.COLORS[i], team=1))
    for i in range(2):
        players.append(server.create_human("蓝%d" % (i+1), server.COLORS[3+i], team=2))
    room4 = {
        "id": "SPN04", "name": "3v3", "status": "lobby",
        "hostId": players[0]["id"],
        "players": {p["id"]: p for p in players},
        "chat": [], "game": None, "createdAt": time.time(),
        "selectedMap": "gold_crater_small",
    }
    server.start_game(room4)
    game4 = room4["game"]

    used = set()
    for player in players:
        structure = next(s for s in game4["structures"]
                         if s["owner"] == player["id"] and s["kind"] == "hq")
        used.add((structure["x"], structure["y"]))
    assert used == set(spawn_pts)
    print("  3v2 五席无重叠: PASS")

    print("\n=== Test 5: Mixed solo + team ===")
    s1 = server.create_human("独1", server.COLORS[0])
    s2 = server.create_human("独2", server.COLORS[1])
    t1 = server.create_human("团1", server.COLORS[2], team=1)
    t2 = server.create_human("团2", server.COLORS[3], team=1)
    room5 = {
        "id": "SPN05", "name": "mix", "status": "lobby",
        "hostId": s1["id"],
        "players": {p["id"]: p for p in [s1, s2, t1, t2]},
        "chat": [], "game": None, "createdAt": time.time(),
        "selectedMap": "gold_crater_small",
    }
    server.start_game(room5)
    game5 = room5["game"]
    team_spawns = [
        min(range(len(spawn_pts)), key=lambda i: (
            (s["x"] - spawn_pts[i][0]) ** 2 + (s["y"] - spawn_pts[i][1]) ** 2))
        for s in game5["structures"]
        if s["kind"] == "hq" and s["owner"] in (t1["id"], t2["id"])
    ]
    assert len(team_spawns) == 2 and len(set(team_spawns)) == 2, team_spawns
    assert game5["playerTeams"][t1["id"]] == 1
    assert game5["playerTeams"][t2["id"]] == 1
    print("  Mixed solo + team: PASS")

    print("\n=== Test 6: 5-player FFA on 赤金陨坑·紧凑 ===")
    crater_players = [
        server.create_human("坑%d" % (i + 1), server.COLORS[i]) for i in range(5)
    ]
    room6 = {
        "id": "SPN06", "name": "gold crater", "status": "lobby",
        "hostId": crater_players[0]["id"],
        "players": {p["id"]: p for p in crater_players},
        "chat": [], "game": None, "createdAt": time.time(),
        "selectedMap": "gold_crater_small",
    }
    server.start_game(room6)
    crater_pts = set(server.MAPS["gold_crater_small"]["spawnPoints"])
    used = set()
    for player in crater_players:
        hq = next(s for s in room6["game"]["structures"]
                  if s["owner"] == player["id"] and s["kind"] == "hq")
        used.add((hq["x"], hq["y"]))
    assert used == crater_pts, (used, crater_pts)
    print("  5P crater FFA: PASS")

    print("\n=== All spawn tests passed! ===")


if __name__ == "__main__":
    main()
