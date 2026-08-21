#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""4/5 人开局：每名入座玩家都必须带着活着的总部，不能一进图就彻底战败。"""

from __future__ import print_function

import os
import random
import re
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import server


MAPS_4P = ("island_hop", "urban_siege", "valley_clash")
MAPS_LARGER = ("north_conflict", "gold_crater")
TICKS = 24


def make_players(n, factions, spawns=None, teams=None):
    players = []
    for index in range(n):
        player = server.create_human("P%d" % (index + 1), server.COLORS[index % len(server.COLORS)])
        player["faction"] = factions[index % len(factions)]
        player["ready"] = True
        if spawns is not None:
            player["spawn"] = spawns[index]
        if teams is not None:
            player["team"] = teams[index]
        players.append(player)
    return players


def make_room(map_id, players, tag="4P"):
    return {
        "id": tag,
        "name": map_id,
        "status": "lobby",
        "hostId": players[0]["id"],
        "players": {player["id"]: player for player in players},
        "chat": [],
        "game": None,
        "createdAt": time.time(),
        "selectedMap": map_id,
    }


def defeat_chats(room):
    return [line["message"] for line in room["chat"]
            if "彻底战败" in line.get("message", "")]


def living_command(game, player_id):
    hqs = [structure for structure in game["structures"]
           if (structure["owner"] == player_id and structure["hp"] > 0
               and server.structure_role(structure["kind"]) == "hq")]
    mcvs = [unit for unit in game["units"]
            if (unit["owner"] == player_id and unit["hp"] > 0
                and server.unit_role(unit["kind"]) == "mcv")]
    return hqs, mcvs


def assert_seated_alive(room, label):
    game = room["game"]
    assert game is not None, "%s: 对局未开始" % label
    seated = list(room["players"].values())
    assert len(seated) >= 2, label
    hq_cells = []
    for player in seated:
        hqs, mcvs = living_command(game, player["id"])
        has_command = server.player_has_command(game, player["id"])
        assert player.get("eliminated") is False, \
            "%s: %s 已被标记淘汰" % (label, player["name"])
        assert has_command, \
            "%s: %s 没有活着的总部/基地车 hq=%s mcv=%s" % (
                label, player["name"],
                [(s["kind"], s["hp"], s["x"], s["y"]) for s in hqs],
                [(u["kind"], u["hp"], u["x"], u["y"]) for u in mcvs])
        assert hqs or mcvs, "%s: %s 指挥建筑为空" % (label, player["name"])
        if hqs:
            hq_cells.append((round(hqs[0]["x"], 1), round(hqs[0]["y"], 1)))
    chats = defeat_chats(room)
    assert not chats, "%s: 出现战败提示 %s" % (label, chats)
    return hq_cells


def start_and_check(map_id, factions, seed=20260821, spawns=None, teams=None, n=4):
    random.seed(seed)
    players = make_players(n, factions, spawns=spawns, teams=teams)
    room = make_room(map_id, players, tag="%s-%s" % (map_id, "-".join(factions)))
    server.start_game(room)
    label0 = "%s %s t=0" % (map_id, factions)
    cells = assert_seated_alive(room, label0)
    server.check_elimination_and_victory(room)
    assert_seated_alive(room, label0 + " after victory scan")
    for _ in range(TICKS):
        server.tick_game(room, 0.05)
    assert_seated_alive(room, "%s %s after %d ticks" % (map_id, factions, TICKS))
    return room, cells


def builtin_maps_from_client():
    app_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                            "public", "app.js")
    with open(app_path, "r", encoding="utf-8") as handle:
        source = handle.read()
    block = re.search(r"var BUILTIN_MAPS = \{([\s\S]*?)\n  \};", source)
    assert block, "public/app.js 缺少 BUILTIN_MAPS"
    return block.group(1)


def main():
    print("=== 4 人图：科技 / 魔法开局都要有指挥 ===")
    for map_id in MAPS_4P:
        for factions in (("tech", "tech", "tech", "tech"),
                         ("magic", "magic", "magic", "magic"),
                         ("tech", "magic", "tech", "magic")):
            room, cells = start_and_check(map_id, factions)
            assert len(set(cells)) == 4, \
                "%s %s 出生点重叠 %s" % (map_id, factions, cells)
            print("  %s %s: 4 座总部分散，无战败" % (map_id, factions))

    print("\n=== 大战场坐满 4 人 ===")
    for map_id in MAPS_LARGER:
        for factions in (("tech",) * 4, ("magic",) * 4):
            room, cells = start_and_check(map_id, factions, seed=77)
            assert len(set(cells)) == 4, (map_id, cells)
            print("  %s %s: 4 人入座均有总部" % (map_id, factions))

    print("\n=== 赤金陨坑满 5 人 ===")
    for factions in (("tech",) * 5,
                     ("magic",) * 5,
                     ("tech", "magic", "tech", "magic", "tech")):
        room, cells = start_and_check(
            "gold_crater", factions, seed=88, n=5)
        assert len(set(cells)) == 5, ("gold_crater", factions, cells)
        print("  gold_crater %s: 5 座总部分散，无战败" % (factions,))

    print("\n=== 大厅复用同一出生点时必须拆开 ===")
    for map_id in MAPS_4P:
        room, cells = start_and_check(
            map_id, ("tech", "magic", "tech", "magic"),
            seed=3, spawns=(0, 0, 0, 0))
        assert len(set(cells)) == 4, \
            "%s 四个 spawn=0 仍叠在一起 %s" % (map_id, cells)
        print("  %s 重复出生点已拆成 4 席" % map_id)
    room, cells = start_and_check(
        "gold_crater", ("tech", "magic", "tech", "magic", "tech"),
        seed=4, spawns=(0, 0, 0, 0, 0), n=5)
    assert len(set(cells)) == 5, \
        "gold_crater 五个 spawn=0 仍叠在一起 %s" % (cells,)
    print("  gold_crater 重复出生点已拆成 5 席")

    print("\n=== 6 人图残留的出生下标不能让 4 人图开局崩掉 ===")
    room, cells = start_and_check(
        "island_hop", ("tech",) * 4, seed=11, spawns=(0, 1, 2, 5))
    assert len(set(cells)) == 4, cells
    print("  island_hop spawn=5 回落到空席")

    print("\n=== 客户端内置目录必须带上三张 4 人图 ===")
    builtin = builtin_maps_from_client()
    for map_id in MAPS_4P:
        assert ("%s:" % map_id) in builtin, \
            "BUILTIN_MAPS 缺少 %s，大厅回退会按 6 个出生点发出无效 setSpawn" % map_id
    assert "function lobbySpawnCount" in open(
        os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                     "public", "app.js"), encoding="utf-8").read()
    print("  BUILTIN_MAPS 含 island_hop / urban_siege / valley_clash")

    print("\nfour-player start tests ok")


if __name__ == "__main__":
    main()
