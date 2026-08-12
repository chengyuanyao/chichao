#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""取消生产：建筑队列与单位队列都要能撤回并全额退款。"""

from __future__ import print_function

import os
import random
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import server


def make_room():
    alpha = server.create_human("撤单甲", server.COLORS[0])
    beta = server.create_human("撤单乙", server.COLORS[1])
    room = {
        "id": "CNL001", "name": "撤单测试", "status": "lobby",
        "hostId": alpha["id"],
        "players": {alpha["id"]: alpha, beta["id"]: beta},
        "chat": [], "game": None, "createdAt": time.time(),
        "selectedMap": "narrow_standoff",
    }
    return room, alpha, beta


def main():
    random.seed(20260726)
    room, alpha, beta = make_room()
    server.start_game(room)
    game = room["game"]
    alpha["cash"] = 20000

    # --- Test 1: 取消建筑队列全额退款 ---
    before = alpha["cash"]
    server.queue_structure(room, alpha["id"], "power")
    cost = server.STRUCTURE_TYPES["power"]["cost"]
    assert alpha["cash"] == before - cost, "排队应当先扣款"
    assert alpha["buildQueue"], "建筑队列应当有内容"
    server.handle_game_command(room, alpha, {"command": "cancelBuild"})
    assert alpha["cash"] == before, "取消建筑应当全额退款"
    assert not alpha["buildQueue"], "取消后队列应当清空"
    print("  取消建筑队列: PASS")

    # --- Test 2: 没有队列时取消要报错，且不能凭空加钱 ---
    before = alpha["cash"]
    try:
        server.handle_game_command(room, alpha, {"command": "cancelBuild"})
        raise AssertionError("空队列时取消应当报错")
    except ValueError:
        pass
    assert alpha["cash"] == before, "失败的取消不能改变资金"
    print("  空队列取消被拒绝: PASS")

    # --- Test 3: 取消单位生产 ---
    barracks = server.make_structure("barracks", alpha["id"], 900, 1600, True)
    game["structures"].append(barracks)
    before = alpha["cash"]
    server.handle_game_command(room, alpha, {"command": "train", "unitType": "rifle"})
    server.handle_game_command(room, alpha, {"command": "train", "unitType": "rocket"})
    server.handle_game_command(room, alpha, {"command": "train", "unitType": "rifle"})
    rifle_cost = server.UNIT_TYPES["rifle"]["cost"]
    rocket_cost = server.UNIT_TYPES["rocket"]["cost"]
    assert alpha["cash"] == before - rifle_cost * 2 - rocket_cost
    assert len(barracks["queue"]) == 3

    server.handle_game_command(room, alpha, {"command": "cancelTrain", "unitType": "rifle"})
    assert len(barracks["queue"]) == 2, "应当撤下一个"
    assert alpha["cash"] == before - rifle_cost - rocket_cost, "取消单位应当全额退款"
    # 撤的是最后排进去的那个，队列里剩下 rifle + rocket
    kinds = [item["kind"] for item in barracks["queue"]]
    assert kinds == ["rifle", "rocket"], "应当撤走最后排入的那一个，实际剩 %s" % kinds
    print("  取消单位生产（撤最后一个）: PASS")

    # --- Test 4: 没有在生产该兵种时报错 ---
    before = alpha["cash"]
    try:
        server.handle_game_command(room, alpha, {"command": "cancelTrain", "unitType": "sniper"})
        raise AssertionError("没有该兵种在生产时应当报错")
    except ValueError:
        pass
    assert alpha["cash"] == before, "失败的取消不能改变资金"
    print("  未生产的兵种取消被拒绝: PASS")

    # --- Test 5: 只能撤自己的队列 ---
    beta_barracks = server.make_structure("barracks", beta["id"], 4100, 1600, True)
    game["structures"].append(beta_barracks)
    beta["cash"] = 5000
    server.handle_game_command(room, beta, {"command": "train", "unitType": "rifle"})
    assert len(beta_barracks["queue"]) == 1
    alpha_before = alpha["cash"]
    # alpha 队列里还有一个 rifle，取消只应影响自己那座兵营
    server.handle_game_command(room, alpha, {"command": "cancelTrain", "unitType": "rifle"})
    assert len(beta_barracks["queue"]) == 1, "不能撤别人的队列"
    assert alpha["cash"] == alpha_before + rifle_cost
    print("  只能撤自己的队列: PASS")

    # --- Test 6: 未知兵种 ---
    try:
        server.handle_game_command(room, alpha, {"command": "cancelTrain", "unitType": "nope"})
        raise AssertionError("未知兵种应当报错")
    except ValueError:
        pass
    print("  未知兵种被拒绝: PASS")

    print("cancel tests ok: 6 tests passed")


if __name__ == "__main__":
    main()
