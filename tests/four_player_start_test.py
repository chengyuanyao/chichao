#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""保留地图的 2/4/5 人开局：每名玩家都必须拥有活着的总部或基地车。"""

from __future__ import print_function

import os
import random
import re
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import server


SHIPPED_MAPS = ("central_scramble", "gold_crater_small", "narrow_standoff")
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
    command_cells = []
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
        command = hqs[0] if hqs else mcvs[0]
        command_cells.append((round(command["x"], 1), round(command["y"], 1)))
    chats = defeat_chats(room)
    assert not chats, "%s: 出现战败提示 %s" % (label, chats)
    return command_cells


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
    assert tuple(server.MAPS) == SHIPPED_MAPS
    assert server.DEFAULT_MAP == "gold_crater_small"

    print("=== 狭路对峙满 2 人 ===")
    for factions in (("tech", "tech"), ("magic", "magic"), ("tech", "magic")):
        _room, cells = start_and_check(
            "narrow_standoff", factions, seed=66, n=2)
        assert len(set(cells)) == 2, cells
        print("  narrow_standoff %s: 两席均有指挥" % (factions,))

    print("\n=== 两张 5 人图支持 4 人与满 5 人开局 ===")
    for map_id in ("gold_crater_small", "central_scramble"):
        for count in (4, 5):
            factions = tuple("tech" if i % 2 == 0 else "magic"
                             for i in range(count))
            _room, cells = start_and_check(
                map_id, factions, seed=70 + count, n=count)
            assert len(set(cells)) == count, (map_id, cells)
            print("  %s: %d 人指挥单位分散，无战败" % (map_id, count))

    print("\n=== 大厅复用同一出生点时必须拆开 ===")
    _room, cells = start_and_check(
        "gold_crater_small", ("tech", "magic", "tech", "magic", "tech"),
        seed=4, spawns=(0, 0, 0, 0, 0), n=5)
    assert len(set(cells)) == 5, \
        "五个 spawn=0 仍叠在一起 %s" % (cells,)
    print("  gold_crater_small 重复出生点已拆成 5 席")

    print("\n=== 五车争霸连续多局不得有玩家进场即败 ===")
    terrain_contexts = []
    for match_index in range(8):
        room, _cells = start_and_check(
            "central_scramble",
            ("tech", "magic", "tech", "magic", "tech"),
            seed=900 + match_index, n=5)
        terrain_contexts.append(server.game_terrain(room["game"]))
    assert all(terrain_contexts[left] is not terrain_contexts[right]
               for left in range(len(terrain_contexts))
               for right in range(left + 1, len(terrain_contexts))), \
        "连续对局复用了可变导航状态"
    print("  连续 8 局、40 个席位均有指挥单位，导航状态彼此隔离")

    print("\n=== 已删除地图的旧出生下标必须安全回落 ===")
    _room, cells = start_and_check(
        "gold_crater_small", ("tech",) * 4,
        seed=11, spawns=(0, 1, 2, 5), n=4)
    assert len(set(cells)) == 4, cells
    print("  越界 spawn=5 已回落到空席")

    print("\n=== 客户端与服务端都只发布三张地图 ===")
    builtin = builtin_maps_from_client()
    for map_id in SHIPPED_MAPS:
        assert ("%s:" % map_id) in builtin, \
            "BUILTIN_MAPS 缺少 %s" % map_id
    for retired in ("north_conflict", "gold_crater", "triple_pass",
                    "island_hop", "urban_siege", "valley_clash"):
        assert ("%s:" % retired) not in builtin, retired
    assert "function lobbySpawnCount" in open(
        os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                     "public", "app.js"), encoding="utf-8").read()
    print("  BUILTIN_MAPS 与 MAPS 均只含 central_scramble / gold_crater_small / narrow_standoff")

    print("\nretained-map start tests ok")


if __name__ == "__main__":
    main()
