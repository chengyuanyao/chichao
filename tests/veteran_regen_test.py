#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Veteran regen is percentage based and starts only after six quiet seconds."""

from __future__ import print_function

import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import server


def make_room():
    alpha = server.create_human("A", server.COLORS[0])
    beta = server.create_human("B", server.COLORS[1])
    room = {
        "id": "REGEN1", "name": "regen test", "status": "lobby",
        "hostId": alpha["id"],
        "players": {alpha["id"]: alpha, beta["id"]: beta},
        "chat": [], "game": None, "createdAt": time.time(),
    }
    server.start_game(room)
    room["game"]["units"] = []
    room["game"]["structures"] = []
    return room, alpha, beta


def tick_at(room, elapsed, seconds=1.0):
    room["game"]["elapsed"] = elapsed
    server.tick_units(room, seconds)


def main():
    room, alpha, beta = make_room()
    game = room["game"]
    tank = server.make_unit("tank", alpha["id"], 500, 500)
    tank["kills"] = 8
    tank["hp"] = 300.0
    tank["_lastCombatAt"] = 0.0
    game["units"].append(tank)

    # 5.99 秒仍完全不回；到第 6 秒后按最大生命值的 0.25%/秒恢复。
    tick_at(room, 5.99)
    assert tank["hp"] == 300.0
    tick_at(room, 6.0)
    elite_gain = tank["maxHp"] * 0.0025
    assert abs(tank["hp"] - (300.0 + elite_gain)) < 0.0001

    # 王牌使用 0.50%/秒；同一比例会随单位最大生命值变化，而不是固定点数。
    tank["kills"] = 16
    tank["hp"] = 300.0
    tick_at(room, 12.0)
    ace_gain = tank["maxHp"] * 0.005
    assert abs(tank["hp"] - (300.0 + ace_gain)) < 0.0001

    # 受到伤害和造成伤害都会刷新双方的脱战时间。
    enemy = server.make_unit("rifle", beta["id"], 900, 900)
    game["units"].append(enemy)
    game["elapsed"] = 20.0
    before = tank["hp"]
    server.apply_damage(room, enemy, 1.0, alpha["id"], "bullet",
                        game, tank["id"], tank)
    assert tank["_lastCombatAt"] == 20.0
    assert enemy["_lastCombatAt"] == 20.0
    tick_at(room, 25.99)
    assert tank["hp"] == before

    # 弹丸未命中时，开火本身也应阻止边打边回。
    game["elapsed"] = 30.0
    server.launch_projectile(game, tank, enemy, server.UNIT_TYPES["tank"])
    assert tank["_lastCombatAt"] == 30.0

    # 老兵只有战斗增益，不应获得额外回血。
    tank["kills"] = 3
    tank["hp"] = 300.0
    tick_at(room, 100.0)
    assert tank["hp"] == 300.0

    catalog = server.public_catalog()["veterancy"]
    assert catalog["regenDelay"] == 6.0
    assert [rank["minKills"] for rank in catalog["ranks"]] == [0, 3, 8, 16]
    assert catalog["ranks"][2]["regenMaxHpPerSecond"] == 0.0025
    assert catalog["ranks"][3]["regenMaxHpPerSecond"] == 0.005
    print("OK: 脱战6秒后按最大生命百分比回血，攻防都会重置计时")


if __name__ == "__main__":
    main()
