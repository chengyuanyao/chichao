#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""机动建造开关、成品资格锁定、单位生产和多总部回归测试。"""

from __future__ import print_function

import math
import os
import random
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import server


def make_room(seed, mobile_construction=True):
    random.seed(seed)
    alpha = server.create_human("迁移甲", server.COLORS[0])
    beta = server.create_human("迁移乙", server.COLORS[1])
    room = {
        "id": "HQBUILD", "name": "headquarters build test",
        "status": "lobby", "hostId": alpha["id"],
        "players": {alpha["id"]: alpha, beta["id"]: beta},
        "chat": [], "game": None, "createdAt": time.time(),
        "selectedMap": "iron_river_duel",
        "mobileConstruction": bool(mobile_construction),
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


def check_lobby_toggle():
    host = server.create_human("机动房主", server.COLORS[0])
    guest = server.create_human("机动访客", server.COLORS[1])
    room = {
        "id": "MOBILE", "name": "机动建造开关", "status": "lobby",
        "hostId": host["id"],
        "players": {host["id"]: host, guest["id"]: guest},
        "chat": [], "game": None, "createdAt": time.time(),
        "selectedMap": "iron_river_duel",
    }
    assert server.mobile_construction_enabled(room) is True
    assert server.public_room(room, viewer_id=guest["id"])["mobileConstruction"] is True
    server.set_mobile_construction(room, host, False)
    assert room["mobileConstruction"] is False
    assert server.public_room(room, viewer_id=guest["id"])["mobileConstruction"] is False
    try:
        server.set_mobile_construction(room, guest, True)
    except ValueError as error:
        assert "房主" in str(error)
    else:
        raise AssertionError("非房主不应修改机动建造")
    with open(os.path.join(ROOT, "public", "index.html"), "r", encoding="utf-8") as handle:
        index = handle.read()
    with open(os.path.join(ROOT, "public", "app.js"), "r", encoding="utf-8") as handle:
        app = handle.read()
    assert 'id="mobileConstructionToggle" checked' in index
    assert "sendAction('setMobileConstruction'" in app
    assert "function hasConstructionAuthority()" in app


def main():
    check_lobby_toggle()
    room, alpha, _beta = make_room(20260903)
    game = room["game"]
    assert server.player_has_active_headquarters(game, alpha["id"])
    assert server.mobile_construction_enabled(room, game)
    assert server.public_room(room, viewer_id=alpha["id"])["mobileConstruction"] is True
    assert server.public_game(game, alpha["id"], full=True)["mobileConstruction"] is True

    # 默认开启：建筑在总部折叠成基地车后继续生产。
    server.queue_structure(room, alpha["id"], "turret")
    server.tick_build_queues(room, 1.0)
    hq = own_hq(game, alpha["id"])
    server.issue_undeploy(game, alpha["id"], hq["id"])
    moving_at = alpha["buildQueue"][0]["remaining"]
    server.tick_build_queues(room, 5.0)
    assert alpha["buildQueue"][0]["remaining"] < moving_at
    assert not server.player_has_active_headquarters(game, alpha["id"])
    assert server.player_has_mobile_headquarters(game, alpha["id"])

    # 移动时可以取消退款，也能在现有前置仍满足时开新建筑队列。
    server.cancel_structure_queue(room, alpha["id"])
    server.queue_structure(room, alpha["id"], "turret")
    assert alpha["buildQueue"][0]["kind"] == "turret"
    server.cancel_structure_queue(room, alpha["id"])

    # 兵营/工厂是独立生产建筑，总部迁移时单位队列照常运转。
    barracks = server.make_structure("barracks", alpha["id"], 1200, 1200, True)
    game["structures"].append(barracks)
    server.queue_unit(room, alpha["id"], "rifle")
    unit_remaining = barracks["queue"][0]["remaining"]
    server.tick_structures(room, 1.0)
    assert barracks["queue"][0]["remaining"] < unit_remaining

    # 已付费成品锁定排队时的资格：电站造好后，即使总部折叠导致 hq
    # 前置消失，也仍能在现有基地控制区内部署。
    server.issue_deploy(game, alpha["id"], {own_mcv(game, alpha["id"])["id"]})
    server.queue_structure(room, alpha["id"], "power")
    alpha["buildQueue"][0]["remaining"] = 0.0
    alpha["buildQueue"][0]["ready"] = True
    hq = own_hq(game, alpha["id"])
    server.issue_undeploy(game, alpha["id"], hq["id"])
    assert alpha["buildQueue"][0]["ready"] is True
    assert not server.has_active_structure(game, alpha["id"], "hq")
    x, y = open_build_spot(game, alpha["id"], "power")
    placed = server.place_prepared_structure(
        room, alpha["id"], "power", x, y)
    assert placed["kind"] == "power" and not alpha["buildQueue"]

    # 关闭选项时恢复暂停规则，且折叠期间不能部署成品。
    room2, alpha2, _beta2 = make_room(20260904, mobile_construction=False)
    game2 = room2["game"]
    assert not server.mobile_construction_enabled(room2, game2)
    server.queue_structure(room2, alpha2["id"], "turret")
    server.tick_build_queues(room2, 1.0)
    first_hq = own_hq(game2, alpha2["id"])
    server.issue_undeploy(game2, alpha2["id"], first_hq["id"])
    paused_at = alpha2["buildQueue"][0]["remaining"]
    server.tick_build_queues(room2, 5.0)
    assert alpha2["buildQueue"][0]["remaining"] == paused_at
    alpha2["buildQueue"][0]["remaining"] = 0.0
    alpha2["buildQueue"][0]["ready"] = True
    try:
        server.place_prepared_structure(room2, alpha2["id"], "turret", 1200, 1200)
    except ValueError as error:
        assert "机动建造" in str(error)
    else:
        raise AssertionError("关闭机动建造后，总部折叠时不应部署成品")

    # 折叠其中一座总部时，另一座展开总部仍能授权建筑生产。
    room3, alpha3, _beta3 = make_room(20260905, mobile_construction=False)
    game3 = room3["game"]
    first_hq = own_hq(game3, alpha3["id"])
    second_hq = server.make_structure(
        first_hq["kind"], alpha3["id"], first_hq["x"] + 500, first_hq["y"], True)
    second_hq["packable"] = True
    game3["structures"].append(second_hq)
    server.queue_structure(room3, alpha3["id"], "turret")
    server.issue_undeploy(game3, alpha3["id"], first_hq["id"])
    before = alpha3["buildQueue"][0]["remaining"]
    server.tick_build_queues(room3, 1.0)
    assert alpha3["buildQueue"][0]["remaining"] < before
    print("OK: 机动建造默认开启并可关闭；成品资格锁定；单位生产/多总部不受影响")


if __name__ == "__main__":
    main()
