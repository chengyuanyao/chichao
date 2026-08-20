#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""地图数据校验。

一张地形写错的地图不会报错，只会让对局变成死局：出生点被山围死、山谷被封、
某个出生点跟别人不连通、矿区落在山里采不到。这些都靠肉眼看不出来，
所以逐条断言。
"""

from __future__ import print_function

import math
import os
import random
import sys
import time
from collections import deque

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import server


SPAWN_CLEAR_RADIUS = 420.0     # 出生点周围必须留出的空地半径


def flood_reachable(terrain, start_cell):
    """从某格出发，在寻路网格上做四邻域洪水填充。"""
    grid = terrain._ensure_grid()
    gw = terrain._grid_w
    gh = terrain._grid_h
    seen = set([start_cell])
    queue = deque([start_cell])
    while queue:
        cx, cy = queue.popleft()
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            nx, ny = cx + dx, cy + dy
            if not (0 <= nx < gw and 0 <= ny < gh):
                continue
            if (nx, ny) in seen or not grid[nx][ny]:
                continue
            seen.add((nx, ny))
            queue.append((nx, ny))
    return seen


def cell_of(terrain, x, y):
    gw = terrain._grid_w
    gh = terrain._grid_h
    return (max(0, min(gw - 1, int(x / server.PATH_CELL_SIZE))),
            max(0, min(gh - 1, int(y / server.PATH_CELL_SIZE))))


def check_map(map_id, map_def):
    terrain = server.terrain_for_map(map_def)
    terrain._ensure_grid()
    width = map_def["width"]
    height = map_def["height"]
    spawns = map_def["spawnPoints"]

    assert len(spawns) == map_def["maxPlayers"], \
        "%s: 出生点数量与 maxPlayers 不符" % map_id
    assert len(map_def["spawnLabels"]) == len(spawns), \
        "%s: 出生点标签数量不符" % map_id

    # --- 出生点必须在地图内、且周围有足够空地 ---
    for index, (sx, sy) in enumerate(spawns):
        assert 0 < sx < width and 0 < sy < height, \
            "%s: 出生点 %d 在地图外" % (map_id, index)
        for angle_step in range(12):
            angle = angle_step * math.pi / 6.0
            for dist in (140, 260, SPAWN_CLEAR_RADIUS):
                px = sx + math.cos(angle) * dist
                py = sy + math.sin(angle) * dist
                if not (0 <= px <= width and 0 <= py <= height):
                    continue
                assert not terrain.blocked(px, py), \
                    "%s: 出生点 %d 周围 %d 处被地形阻挡" % (map_id, index, dist)

    # --- 新地图只允许山地分区，彻底禁用河流/桥梁瓶颈 ---
    assert not map_def.get("rivers"), "%s: 不应再包含河流" % map_id
    assert not map_def.get("bridges"), "%s: 不应再包含桥梁" % map_id

    # 锁住恢复后的大战场尺寸，防止后续改地形时又意外缩图。
    expected_sizes = {
        "north_conflict": (9600, 6000),
        "cliff_assault": (9600, 6000),
        "island_hop": (7200, 6000),
        "urban_siege": (6400, 6400),
        "narrow_standoff": (4800, 3200),
        "triple_pass": (5400, 4200),
        "valley_clash": (6400, 4800),
        "gold_crater": (10000, 6400),
    }
    assert (width, height) == expected_sizes[map_id], \
        "%s: 地图尺寸意外变化 (%dx%d)" % (map_id, width, height)

    # --- 所有出生点必须互相连通 ---
    reachable = flood_reachable(terrain, cell_of(terrain, spawns[0][0], spawns[0][1]))
    for index, (sx, sy) in enumerate(spawns[1:], start=1):
        assert cell_of(terrain, sx, sy) in reachable, \
            "%s: 出生点 %d 与出生点 0 不连通" % (map_id, index)

    # --- 道路必须可通行（画在山里/河里的路是误导） ---
    for index, road in enumerate(map_def.get("roads", [])):
        for step in range(0, 21):
            t = step / 20.0
            px = road["x1"] + (road["x2"] - road["x1"]) * t
            py = road["y1"] + (road["y2"] - road["y1"]) * t
            assert not terrain.point_in_mountain(px, py), \
                "%s: 道路 %d 从山体中穿过（%.0f,%.0f）" % (map_id, index, px, py)

    # --- 实际开一局，检查矿区可达 ---
    players = [server.create_human("校验%d" % i, server.COLORS[i])
               for i in range(map_def["maxPlayers"])]
    room = {
        "id": "MAPCHK", "name": map_id, "status": "lobby",
        "hostId": players[0]["id"],
        "players": {p["id"]: p for p in players},
        "chat": [], "game": None, "createdAt": time.time(),
        "selectedMap": map_id,
    }
    server.start_game(room)
    game = room["game"]

    for resource in game["resources"]:
        assert not terrain.blocked(resource["x"], resource["y"], resource["radius"]), \
            "%s: 矿脉 (%.0f,%.0f) 落在阻挡地形里" % (map_id, resource["x"], resource["y"])
        assert cell_of(terrain, resource["x"], resource["y"]) in reachable, \
            "%s: 矿脉 (%.0f,%.0f) 与出生点不连通" % (map_id, resource["x"], resource["y"])

    # --- 初始建筑与单位不能卡在地形里 ---
    for structure in game["structures"]:
        assert not terrain.blocked(structure["x"], structure["y"]), \
            "%s: 初始建筑 %s 落在阻挡地形里" % (map_id, structure["kind"])
    for unit in game["units"]:
        assert not terrain.blocked(unit["x"], unit["y"]), \
            "%s: 初始单位 %s 落在阻挡地形里" % (map_id, unit["kind"])

    # --- 跑一段模拟，确认没有单位被挤进山里卡死 ---
    for _ in range(60):
        server.tick_game(room, 0.05)
    stuck = [u for u in game["units"] if terrain.blocked(u["x"], u["y"])]
    assert not stuck, "%s: %d 个单位被挤进了阻挡地形" % (map_id, len(stuck))

    roads = len(map_def.get("roads", []))
    mountains = len(map_def.get("mountains", []))
    print("  %-16s %5dx%-5d 出生%d 山谷地形%d 路%d 矿%d  OK" % (
        map_id, width, height, len(spawns),
        mountains, roads, len(game["resources"])))


def main():
    random.seed(20260726)
    print("=== 地图数据校验 ===")
    for map_id in sorted(server.MAPS):
        check_map(map_id, server.MAPS[map_id])

    # --- 道路确实影响寻路与速度 ---
    road_map = server.MAPS["north_conflict"]
    terrain = server.terrain_for_map(road_map)
    on = terrain.speed_scale(3000, 1636)      # 北侧主干道上
    off = terrain.speed_scale(3000, 1900)     # 主干道旁的旷野
    assert on > off, "道路应当提供行军加成 (%.2f vs %.2f)" % (on, off)
    assert abs(off - 1.0) < 1e-6, "非道路区域不应有加成"
    print("  道路加成 %.2fx（旷野 %.2fx）" % (on, off))

    # 同样距离下，沿路的路径代价应低于横穿旷野
    path_along_road = terrain.find_path(700, 1636, 8900, 1636)
    assert len(path_along_road) > 1, "沿路路径应当存在"
    print("  沿主干道寻路 %d 个航点" % len(path_along_road))

    crater = server.MAPS["gold_crater"]
    assert crater["maxPlayers"] == 5
    assert len(crater["spawnPoints"]) == 5
    assert crater["theme"] == "crater"
    assert crater.get("publicOreCount", 4) > 4
    assert crater["homeOreAmounts"] == (26000, 19000, 17000, 21000)
    bonuses = list(crater.get("bonusResources") or [])
    assert len(bonuses) >= 10
    crater_cx, crater_cy = crater["width"] / 2.0, crater["height"] / 2.0
    center_ores = [r for r in bonuses
                   if math.hypot(r["x"] - crater_cx, r["y"] - crater_cy) < 700]
    pocket_ores = [r for r in bonuses
                   if math.hypot(r["x"] - crater_cx, r["y"] - crater_cy) > 2000]
    # 中庭金库围核至少五处，且比初版三处头奖（5万+3.8万+3.8万）更肥。
    assert len(center_ores) >= 5, len(center_ores)
    assert sum(r["amount"] for r in center_ores) >= 220000
    assert min(r["amount"] for r in center_ores) >= 44000
    # 外环口袋矿与家矿保持原量，多出来的全在正中争夺区。
    assert len(pocket_ores) == 5
    assert all(r["amount"] == 26000 for r in pocket_ores)

    def ore_payload(map_id, n_players):
        random.seed(88001)
        players = [server.create_human("比%d" % i, server.COLORS[i % 6])
                   for i in range(n_players)]
        room = {
            "id": "ORECMP", "name": map_id, "status": "lobby",
            "hostId": players[0]["id"],
            "players": {p["id"]: p for p in players},
            "chat": [], "game": None, "createdAt": time.time(),
            "selectedMap": map_id,
        }
        server.start_game(room)
        resources = room["game"]["resources"]
        return resources

    north_ores = ore_payload("north_conflict", 5)
    crater_ores = ore_payload("gold_crater", 5)
    north_n, north_amt = len(north_ores), sum(r["amount"] for r in north_ores)
    crater_n, crater_amt = len(crater_ores), sum(r["amount"] for r in crater_ores)
    assert crater_n > north_n, (crater_n, north_n)
    assert crater_amt > north_amt, (crater_amt, north_amt)
    live_center = [r for r in crater_ores
                   if math.hypot(r["x"] - crater_cx, r["y"] - crater_cy) < 700]
    assert len(live_center) >= 5, len(live_center)
    for planned in center_ores:
        nearest = min(math.hypot(r["x"] - planned["x"], r["y"] - planned["y"])
                      for r in live_center)
        assert nearest < 80, (planned["x"], planned["y"], nearest)
    print("  赤金陨坑 5人矿点 %d / 储量 %.0f  vs 北境 %d / %.0f" % (
        crater_n, crater_amt, north_n, north_amt))
    print("  中庭金库 %d 处 / 储量 %.0f" % (
        len(live_center), sum(r["amount"] for r in live_center)))

    print("map tests ok: %d 张地图通过" % len(server.MAPS))


if __name__ == "__main__":
    main()
