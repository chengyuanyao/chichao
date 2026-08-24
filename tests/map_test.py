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

    # 赤金陨坑大图 / 紧凑版用外环河+桥做邻里卡口；其余图仍只靠山地分区。
    if map_id in ("gold_crater", "gold_crater_small"):
        assert map_def.get("rivers"), "%s: 外环卡口需要河流" % map_id
        assert map_def.get("bridges"), "%s: 外环卡口需要桥梁" % map_id
    else:
        assert not map_def.get("rivers"), "%s: 不应再包含河流" % map_id
        assert not map_def.get("bridges"), "%s: 不应再包含桥梁" % map_id

    # 锁住恢复后的大战场尺寸，防止后续改地形时又意外缩图。
    expected_sizes = {
        "north_conflict": (9600, 6000),
        "island_hop": (7200, 6000),
        "urban_siege": (6400, 6400),
        "narrow_standoff": (4800, 3200),
        "triple_pass": (5400, 4200),
        "valley_clash": (6400, 4800),
        "gold_crater": (10000, 6400),
        "gold_crater_small": (6400, 6400),
    }
    assert (width, height) == expected_sizes[map_id], \
        "%s: 地图尺寸意外变化 (%dx%d)" % (map_id, width, height)

    # --- 所有出生点必须互相连通 ---
    reachable = flood_reachable(terrain, cell_of(terrain, spawns[0][0], spawns[0][1]))
    for index, (sx, sy) in enumerate(spawns[1:], start=1):
        assert cell_of(terrain, sx, sy) in reachable, \
            "%s: 出生点 %d 与出生点 0 不连通" % (map_id, index)

    # --- 道路必须可通行（画在山里/没桥的河里是误导） ---
    for index, road in enumerate(map_def.get("roads", [])):
        for step in range(0, 21):
            t = step / 20.0
            px = road["x1"] + (road["x2"] - road["x1"]) * t
            py = road["y1"] + (road["y2"] - road["y1"]) * t
            assert not terrain.point_in_mountain(px, py), \
                "%s: 道路 %d 从山体中穿过（%.0f,%.0f）" % (map_id, index, px, py)
            assert not terrain.point_in_water(px, py), \
                "%s: 道路 %d 落入无桥水面（%.0f,%.0f）" % (map_id, index, px, py)

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

    for map_id in ("gold_crater", "gold_crater_small"):
        crater = server.MAPS[map_id]
        pub = server.PUBLIC_MAPS[map_id]
        assert pub.get("rivers") and pub.get("bridges")
        assert crater["maxPlayers"] == 5
        assert len(crater["spawnPoints"]) == 5
        assert crater["theme"] == "crater"
        assert not crater.get("landmarks")
        assert not pub.get("landmarks")
        assert crater.get("publicOreCount", 4) > 4
        assert crater["homeOreAmounts"] == (26000, 19000, 17000, 21000)
        assert crater.get("homeOreBehind") is True
        assert crater.get("homeOreDistance") == 450
        bonuses = list(crater.get("bonusResources") or [])
        assert len(bonuses) >= 15
        crater_cx, crater_cy = crater["width"] / 2.0, crater["height"] / 2.0
        center_ores = [r for r in bonuses
                       if math.hypot(r["x"] - crater_cx, r["y"] - crater_cy) < 700]
        pocket_ores = [r for r in bonuses
                       if math.hypot(r["x"] - crater_cx, r["y"] - crater_cy) > 1280]
        # 中庭金库围核至少五处，且比初版三处头奖（5万+3.8万+3.8万）更肥。
        assert len(center_ores) >= 5, len(center_ores)
        assert sum(r["amount"] for r in center_ores) >= 220000
        assert min(r["amount"] for r in center_ores) >= 44000
        # 五条悠长林道两端各有一矿；总储量仍与原先 5×26000 相同。
        assert len(pocket_ores) == 10, map_id
        assert all(r["amount"] == 13000 for r in pocket_ores)
        assert sum(r["amount"] for r in pocket_ores) == 130000

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
    small_ores = ore_payload("gold_crater_small", 5)
    north_n, north_amt = len(north_ores), sum(r["amount"] for r in north_ores)
    crater_n, crater_amt = len(crater_ores), sum(r["amount"] for r in crater_ores)
    assert crater_n > north_n, (crater_n, north_n)
    assert crater_amt > north_amt, (crater_amt, north_amt)
    crater = server.MAPS["gold_crater"]
    crater_cx, crater_cy = crater["width"] / 2.0, crater["height"] / 2.0
    live_center = [r for r in crater_ores
                   if math.hypot(r["x"] - crater_cx, r["y"] - crater_cy) < 700]
    assert len(live_center) >= 5, len(live_center)
    for planned in [r for r in crater.get("bonusResources") or []
                    if math.hypot(r["x"] - crater_cx, r["y"] - crater_cy) < 700]:
        nearest = min(math.hypot(r["x"] - planned["x"], r["y"] - planned["y"])
                      for r in live_center)
        assert nearest < 80, (planned["x"], planned["y"], nearest)
    print("  赤金陨坑 5人矿点 %d / 储量 %.0f  vs 北境 %d / %.0f" % (
        crater_n, crater_amt, north_n, north_amt))
    print("  中庭金库 %d 处 / 储量 %.0f" % (
        len(live_center), sum(r["amount"] for r in live_center)))

    check_gold_crater_chokepoints(crater, crater_ores, CRATER_LAYOUTS["gold_crater"])
    small = server.MAPS["gold_crater_small"]
    check_gold_crater_chokepoints(small, small_ores, CRATER_LAYOUTS["gold_crater_small"])

    print("map tests ok: %d 张地图通过" % len(server.MAPS))


# 外环五处邻里卡口：北岗-东北、东北-东南、东南-西南、西南-西北、西北-北岗。
# 每道熔水河沿五边形角平分线从陨坑外壁拉到地图边，只在外环公路留桥。
# 大图 / 紧凑版各自有独立的中心、桥位与金库。
CRATER_LAYOUTS = {
    "gold_crater": {
        "cx": 5000.0, "cy": 3200.0,
        "links": (
            {"name": "北岗-东北", "bridge": (6575, 1032)},
            {"name": "东北-东南", "bridge": (7549, 4028)},
            {"name": "东南-西南", "bridge": (5000, 5880)},
            {"name": "西南-西北", "bridge": (2451, 4028)},
            {"name": "西北-北岗", "bridge": (3425, 1032)},
        ),
        "vault": (5000.0, 2740.0),
    },
    "gold_crater_small": {
        "cx": 3200.0, "cy": 3200.0,
        "links": (
            {"name": "北岗-东北", "bridge": (4775, 1032)},
            {"name": "东北-东南", "bridge": (5749, 4028)},
            {"name": "东南-西南", "bridge": (3200, 5880)},
            {"name": "西南-西北", "bridge": (651, 4028)},
            {"name": "西北-北岗", "bridge": (1625, 1032)},
        ),
        "vault": (3200.0, 2740.0),
    },
}
# 坦克 / 攻城炮 / 裂地晶兽半径约 20–24，林道宽度必须留出并排余量。
CRATER_BRIDGE_MIN = 110.0
CRATER_TRAIL_LENGTH_MIN = 1200.0


def check_gold_crater_chokepoints(crater, live_ores, layout):
    terrain = server.terrain_for_map(crater)
    terrain._ensure_grid()
    cx, cy = layout["cx"], layout["cy"]
    rivers = list(crater.get("rivers") or [])
    bridges = list(crater.get("bridges") or [])
    spawns = crater["spawnPoints"]
    assert len(rivers) == 5, len(rivers)
    assert len(bridges) == 5, len(bridges)

    # 五个出生点落在同一圆周上，按 72° 严格等分；紧凑版不得横向挤压。
    spawn_radii = [math.hypot(sx - cx, sy - cy) for sx, sy in spawns]
    assert max(spawn_radii) - min(spawn_radii) < 2.0, spawn_radii
    spawn_angles = sorted(math.atan2(sy - cy, sx - cx) % (math.pi * 2)
                          for sx, sy in spawns)
    angle_gaps = [((spawn_angles[(i + 1) % 5] - spawn_angles[i]) % (math.pi * 2))
                  for i in range(5)]
    expected_gap = math.pi * 2 / 5
    assert max(abs(gap - expected_gap) for gap in angle_gaps) < 0.002, angle_gaps
    assert all(river["width"] >= 800 for river in rivers)
    inner_radii = [math.hypot(river["x1"] - cx, river["y1"] - cy)
                   for river in rivers]
    assert max(inner_radii) - min(inner_radii) < 2.0, inner_radii
    assert all(1448 <= radius <= 1452 for radius in inner_radii), inner_radii

    # 收窄入口后仍须保住中央开放圈：半径 1000 的整圈均为干地。
    for angle_step in range(72):
        angle = angle_step * math.pi * 2 / 72
        open_x = cx + math.cos(angle) * 1000
        open_y = cy + math.sin(angle) * 1000
        assert not terrain.point_in_water(open_x, open_y), (angle_step, open_x, open_y)
        assert not terrain.point_in_mountain(open_x, open_y), (angle_step, open_x, open_y)

    # 四片初始家矿必须全部在总部背向中央的一侧，且保持合理采矿距离。
    home_ores = [ore for ore in live_ores if not ore.get("public")]
    expected_home_count = len(spawns) * len(crater["homeOreAmounts"])
    assert len(home_ores) == expected_home_count, len(home_ores)
    ores_by_spawn = [[] for _ in spawns]
    for ore in home_ores:
        spawn_index = min(
            range(len(spawns)),
            key=lambda i: math.hypot(ore["x"] - spawns[i][0],
                                     ore["y"] - spawns[i][1]))
        sx, sy = spawns[spawn_index]
        outward_x, outward_y = sx - cx, sy - cy
        outward_length = math.hypot(outward_x, outward_y)
        outward_x /= outward_length
        outward_y /= outward_length
        rel_x, rel_y = ore["x"] - sx, ore["y"] - sy
        outward_projection = rel_x * outward_x + rel_y * outward_y
        lateral_projection = abs(rel_x * -outward_y + rel_y * outward_x)
        assert 350 <= outward_projection <= 580, \
            (spawn_index, ore["x"], ore["y"], outward_projection)
        assert lateral_projection <= 130, \
            (spawn_index, ore["x"], ore["y"], lateral_projection)
        ores_by_spawn[spawn_index].append(ore)
    for spawn_index, ores in enumerate(ores_by_spawn):
        assert len(ores) == len(crater["homeOreAmounts"]), spawn_index
        assert sorted(ore["amount"] for ore in ores) == \
            sorted(float(amount) for amount in crater["homeOreAmounts"])

    dry = server.Terrain(rivers, [], crater["width"], crater["height"],
                         crater.get("mountains"), crater.get("roads"))
    for index, link in enumerate(layout["links"]):
        bridge = bridges[index]
        bx, by = link["bridge"]
        assert abs(bridge["x"] - bx) < 2 and abs(bridge["y"] - by) < 2, link["name"]
        assert all(key in bridge for key in ("x1", "y1", "x2", "y2", "width"))
        assert bridge["width"] >= CRATER_BRIDGE_MIN, link["name"]
        trail_length = math.hypot(
            bridge["x2"] - bridge["x1"], bridge["y2"] - bridge["y1"])
        assert trail_length >= CRATER_TRAIL_LENGTH_MIN, (link["name"], trail_length)
        assert trail_length > rivers[index]["width"] * 1.45, link["name"]
        assert dry.point_in_water(bridge["x"], bridge["y"]), \
            "%s: 桥心必须压在河面上" % link["name"]
        assert not terrain.blocked(bridge["x"], bridge["y"]), \
            "%s: 桥面被标成阻挡格" % link["name"]
        assert terrain.cell_open(bridge["x"], bridge["y"]), \
            "%s: 寻路网格把桥面封了" % link["name"]
        # 攻城炮 / 晶兽中心踩在桥上不能落水。
        assert not terrain.blocked(bridge["x"], bridge["y"], 24), \
            "%s: 桥面不够大单位落脚" % link["name"]
        # 小道两端都伸出密林，端点金矿在相邻玩家各自一侧，且可安全采集。
        for endpoint in ((bridge["x1"], bridge["y1"]),
                         (bridge["x2"], bridge["y2"])):
            assert not terrain.blocked(endpoint[0], endpoint[1], 48), \
                (link["name"], endpoint)
            nearest_planned = min(
                math.hypot(ore[0] - endpoint[0], ore[1] - endpoint[1])
                for ore in pocket_ores_of(crater))
            assert nearest_planned < 2, (link["name"], endpoint, nearest_planned)

        # 把同样的横穿线沿森林中心线平移 320px 后便离开小道：两端仍是
        # 旷地，但直穿会撞上密林，只能回到唯一通道绕行。
        river = rivers[index]
        rdx = river["x2"] - river["x1"]
        rdy = river["y2"] - river["y1"]
        river_length = math.hypot(rdx, rdy)
        shift_x = rdx / river_length * 320
        shift_y = rdy / river_length * 320
        left = (bridge["x1"] - shift_x, bridge["y1"] - shift_y)
        right = (bridge["x2"] - shift_x, bridge["y2"] - shift_y)
        assert not terrain.blocked(left[0], left[1]), (link["name"], left)
        assert not terrain.blocked(right[0], right[1]), (link["name"], right)
        assert terrain.segment_blocked(left[0], left[1], right[0], right[1]), \
            "%s: 外环旷野仍能直线穿过卡口" % link["name"]
        via = terrain.find_path(left[0], left[1], right[0], right[1])
        assert len(via) > 1, "%s: 卡口两侧无法经桥绕行" % link["name"]

    # 每家都能走到：其他出生点、中庭金库、自家矿、最近口袋矿。
    vault = layout["vault"]
    for i, (sx, sy) in enumerate(spawns):
        assert len(terrain.find_path(sx, sy, vault[0], vault[1])) > 0, i
        cdx, cdy = cx - sx, cy - sy
        dist = max(1.0, math.hypot(cdx, cdy))
        factor = min(0.20, 650.0 / dist)
        home = (sx + cdx * factor, sy + cdy * factor)
        assert len(terrain.find_path(sx, sy, home[0], home[1])) > 0, i
        pocket = min(pocket_ores_of(crater),
                     key=lambda ore: math.hypot(ore[0] - sx, ore[1] - sy))
        assert len(terrain.find_path(sx, sy, pocket[0], pocket[1])) > 0, i
        for j, (tx, ty) in enumerate(spawns):
            if i == j:
                continue
            path = terrain.find_path(sx, sy, tx, ty)
            assert len(path) > 0, "%s -> %s" % (i, j)

    planned_pockets = pocket_ores_of(crater)
    assert len(planned_pockets) == 10
    for px, py in planned_pockets:
        assert not terrain.blocked(px, py, 48)
        nearest = min(math.hypot(r["x"] - px, r["y"] - py) for r in live_ores)
        assert nearest < 80, (px, py, nearest)
        match = min(live_ores, key=lambda r: math.hypot(r["x"] - px, r["y"] - py))
        assert match["amount"] == 13000
    print("  五等分发展区 / 5 条长林道 / 10 处端点矿 / 中央收窄入口可通行")


def pocket_ores_of(crater):
    cx, cy = crater["width"] / 2.0, crater["height"] / 2.0
    return [(r["x"], r["y"]) for r in crater.get("bonusResources") or []
            if math.hypot(r["x"] - cx, r["y"] - cy) > 1280]


if __name__ == "__main__":
    main()
