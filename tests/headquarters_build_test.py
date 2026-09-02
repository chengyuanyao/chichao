#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""总部折叠后暂停建筑生产/部署，但单位生产和多总部保持正常。"""

from __future__ import print_function

import math
import os
import random
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import server


def make_room(seed):
    random.seed(seed)
    alpha = server.create_human("迁移甲", server.COLORS[0])
    beta = server.create_human("迁移乙", server.COLORS[1])
    room = {
        "id": "HQBUILD", "name": "headquarters build test",
        "status": "lobby", "hostId": alpha["id"],
        "players": {alpha["id"]: alpha, beta["id"]: beta},
        "chat": [], "game": None, "createdAt": time.time(),
        "selectedMap": "narrow_standoff",
    }
    server.start_game(room)
    alpha["cash"] = 50000
    return room, alpha, beta


def own_hq(game, player_id):
    return next(structure for structure in game["structures"]
                if structure["owner"] == player_id and structure["hp"] > 0
                and server.structure_role(structure["kind"]) == "hq")


def own_mcv(game, player_id):
    return next(unit for unit in game["units"]
                if unit["owner"] == player_id and unit["hp"] > 0
                and server.unit_role(unit["kind"]) == "mcv")


def open_build_spot(game, player_id, kind):
    size = server.STRUCTURE_TYPES[kind]["size"]
    anchors = [structure for structure in game["structures"]
               if structure["owner"] == player_id and structure["hp"] > 0
               and structure.get("active")
               and server.structure_role(structure["kind"])
               in server.BUILD_ANCHOR_RANGES]
    for anchor in anchors:
        for radius in (145, 175, 205):
            for index in range(16):
                angle = index * math.pi / 8.0
                x = anchor["x"] + math.cos(angle) * radius
                y = anchor["y"] + math.sin(angle) * radius
                if (server.construction_anchor_near(game, player_id, x, y)
                        and server.position_clear(game, x, y, size)):
                    return x, y
    raise AssertionError("no open build spot")


def main():
    room, alpha, _beta = make_room(20260903)
    game = room["game"]
    assert server.player_has_active_headquarters(game, alpha["id"])

    # 正在生产的建筑在折叠后原地暂停，重新展开后继续倒计时。
    server.queue_structure(room, alpha["id"], "turret")
    server.tick_build_queues(room, 1.0)
    hq = own_hq(game, alpha["id"])
    server.issue_undeploy(game, alpha["id"], hq["id"])
    paused_at = alpha["buildQueue"][0]["remaining"]
    server.tick_build_queues(room, 5.0)
    assert alpha["buildQueue"][0]["remaining"] == paused_at
    assert not server.player_has_active_headquarters(game, alpha["id"])

    # 折叠时可以取消退款，但不能新开任何建筑队列。
    server.cancel_structure_queue(room, alpha["id"])
    try:
        server.queue_structure(room, alpha["id"], "turret")
    except ValueError as error:
        assert "展开基地车" in str(error)
    else:
        raise AssertionError("总部折叠时不应能生产新建筑")

    # 兵营/工厂是独立生产建筑，总部迁移时单位队列照常运转。
    barracks = server.make_structure("barracks", alpha["id"], 1200, 1200, True)
    game["structures"].append(barracks)
    server.queue_unit(room, alpha["id"], "rifle")
    unit_remaining = barracks["queue"][0]["remaining"]
    server.tick_structures(room, 1.0)
    assert barracks["queue"][0]["remaining"] < unit_remaining

    # 展开后建筑队列恢复；已造好的建筑在下次折叠时保留但禁止部署。
    server.issue_deploy(game, alpha["id"], {own_mcv(game, alpha["id"])["id"]})
    server.queue_structure(room, alpha["id"], "turret")
    server.tick_build_queues(room, 1.0)
    assert alpha["buildQueue"][0]["remaining"] < server.STRUCTURE_TYPES["turret"]["build"]
    alpha["buildQueue"][0]["remaining"] = 0.0
    alpha["buildQueue"][0]["ready"] = True
    hq = own_hq(game, alpha["id"])
    server.issue_undeploy(game, alpha["id"], hq["id"])
    try:
        server.place_prepared_structure(room, alpha["id"], "turret", 1200, 1200)
    except ValueError as error:
        assert "展开基地车" in str(error)
    else:
        raise AssertionError("总部折叠时不应能部署已完工建筑")
    assert alpha["buildQueue"][0]["ready"] is True
    server.issue_deploy(game, alpha["id"], {own_mcv(game, alpha["id"])["id"]})
    x, y = open_build_spot(game, alpha["id"], "turret")
    placed = server.place_prepared_structure(
        room, alpha["id"], "turret", x, y)
    assert placed["kind"] == "turret" and not alpha["buildQueue"]

    # 折叠其中一座总部时，另一座展开总部仍能授权建筑生产。
    room2, alpha2, _beta2 = make_room(20260904)
    game2 = room2["game"]
    first_hq = own_hq(game2, alpha2["id"])
    second_hq = server.make_structure(
        first_hq["kind"], alpha2["id"], first_hq["x"] + 500, first_hq["y"], True)
    second_hq["packable"] = True
    game2["structures"].append(second_hq)
    server.queue_structure(room2, alpha2["id"], "turret")
    server.issue_undeploy(game2, alpha2["id"], first_hq["id"])
    before = alpha2["buildQueue"][0]["remaining"]
    server.tick_build_queues(room2, 1.0)
    assert alpha2["buildQueue"][0]["remaining"] < before
    print("OK: 总部折叠暂停建筑，重新展开续造；单位生产/多总部不受影响")


if __name__ == "__main__":
    main()
