#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Facing-aware group formations and per-seat preference."""

from __future__ import print_function

import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import server
from command_priority_test import make_room
from formation import normalize_formation


def dests(units):
    return [(unit["destX"], unit["destY"]) for unit in units]


def distinct(points):
    rounded = [(round(x, 3), round(y, 3)) for x, y in points]
    return len(set(rounded)) == len(rounded)


def place_squad(game, owner, count, ox=800, oy=800, kind="tank"):
    units = []
    for index in range(count):
        units.append(server.make_unit(
            kind, owner, ox + (index % 3) * 20, oy + (index // 3) * 20))
    game["units"].extend(units)
    return units


def remain_to_target(points, tx, ty, fx, fy):
    return [((tx - x) * fx + (ty - y) * fy) for x, y in points]


def main():
    room, me, _foe = make_room()
    game = room["game"]
    game["units"] = []
    game["structures"] = []
    game["terrainCtx"] = server.FLAT_TERRAIN

    solo = server.make_unit("tank", me["id"], 400, 400)
    game["units"] = [solo]
    server.issue_move(game, me["id"], {solo["id"]}, 1200, 900)
    assert abs(solo["destX"] - 1200) < 1e-6 and abs(solo["destY"] - 900) < 1e-6

    for count in (4, 9):
        game["units"] = []
        squad = place_squad(game, me["id"], count, 600, 800)
        tx, ty = 1800.0, 1400.0
        server.issue_move(
            game, me["id"], {unit["id"] for unit in squad}, tx, ty,
            formation="box")
        points = dests(squad)
        assert distinct(points), points
        cx = sum(unit["x"] for unit in squad) / float(count)
        cy = sum(unit["y"] for unit in squad) / float(count)
        length = math.hypot(tx - cx, ty - cy)
        fx, fy = (tx - cx) / length, (ty - cy) / length
        scored = sorted(
            points, key=lambda point: (point[0] - cx) * fx + (point[1] - cy) * fy)
        half = 2 if count == 4 else 3
        back, front = scored[:half], scored[-half:]
        front_remain = sum(remain_to_target(front, tx, ty, fx, fy)) / float(half)
        back_remain = sum(remain_to_target(back, tx, ty, fx, fy)) / float(half)
        assert front_remain < back_remain - 8, (front_remain, back_remain, points)
        # 斜向行军时方阵必须旋转，不能再贴世界坐标轴铺格子。
        xs = [point[0] - tx for point in points]
        ys = [point[1] - ty for point in points]
        assert max(xs) - min(xs) > 20 and max(ys) - min(ys) > 20
        if count == 4:
            assert not all(abs(abs(x) - abs(y)) < 4 for x, y in zip(xs, ys)), points

    game["units"] = []
    squad = place_squad(game, me["id"], 5, 700, 700)
    tx, ty = 700.0, 1600.0
    server.issue_move(
        game, me["id"], {unit["id"] for unit in squad}, tx, ty, formation="line")
    points = dests(squad)
    assert distinct(points)
    xs = [point[0] for point in points]
    ys = [point[1] for point in points]
    assert max(xs) - min(xs) > max(ys) - min(ys) + 40
    for point in points:
        assert abs(point[1] - ty) < 8, points

    game["units"] = []
    squad = place_squad(game, me["id"], 6, 900, 500)
    tx, ty = 2000.0, 500.0
    server.issue_move(
        game, me["id"], {unit["id"] for unit in squad}, tx, ty, formation="wedge")
    points = dests(squad)
    assert distinct(points)
    dists = [math.hypot(point[0] - tx, point[1] - ty) for point in points]
    tip = min(points, key=lambda point: math.hypot(point[0] - tx, point[1] - ty))
    assert math.hypot(tip[0] - tx, tip[1] - ty) < 8
    assert sorted(dists)[0] + 10 < sorted(dists)[1]
    assert abs(tip[0] - max(point[0] for point in points)) < 1e-6

    game["units"] = []
    squad = place_squad(game, me["id"], 4, 500, 500)
    assert normalize_formation(me.get("formation")) == "box"
    server.handle_game_command(room, me, {"command": "setFormation", "formation": "line"})
    assert me["formation"] == "line"
    assert server.public_player(room, me, me["id"])["formation"] == "line"
    server.handle_game_command(room, me, {
        "command": "move",
        "unitIds": [unit["id"] for unit in squad],
        "x": 500, "y": 1500,
    })
    points = dests(squad)
    xs = [point[0] for point in points]
    ys = [point[1] for point in points]
    assert max(xs) - min(xs) > max(ys) - min(ys) + 40
    server.handle_game_command(room, me, {
        "command": "move",
        "unitIds": [unit["id"] for unit in squad],
        "x": 1800, "y": 500,
        "formation": "wedge",
    })
    points = dests(squad)
    tip = min(points, key=lambda point: math.hypot(point[0] - 1800, point[1] - 500))
    assert math.hypot(tip[0] - 1800, tip[1] - 500) < 8
    assert me["formation"] == "line"

    try:
        server.handle_game_command(room, me, {"command": "setFormation", "formation": "circle"})
    except ValueError as error:
        assert "阵型" in str(error)
    else:
        raise AssertionError("invalid formation must be rejected")
    assert me["formation"] == "line"

    game["units"] = []
    rifles = place_squad(game, me["id"], 4, 400, 400, "rifle")
    server.issue_move(
        game, me["id"], {unit["id"] for unit in rifles}, 400, 1200, formation="line")
    rifle_span = max(unit["destX"] for unit in rifles) - min(unit["destX"] for unit in rifles)
    game["units"] = []
    dragons = place_squad(game, me["id"], 4, 400, 400, "dragon")
    server.issue_move(
        game, me["id"], {unit["id"] for unit in dragons}, 400, 1200, formation="line")
    dragon_span = max(unit["destX"] for unit in dragons) - min(unit["destX"] for unit in dragons)
    assert dragon_span > rifle_span + 5, (rifle_span, dragon_span)

    print("formation ok: facing box, line, wedge, preference, single-unit click")


if __name__ == "__main__":
    main()
