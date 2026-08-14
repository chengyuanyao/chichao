#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""升军衔(promote)特效的服务端触发测试：单位击杀数跨过 3/8/16 时，
apply_damage 应在其位置追加一个 type=promote 的特效，且只在跨档那一刻触发。"""

from __future__ import print_function

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import server


def make_room():
    a = server.create_human("A", server.COLORS[0])
    b = server.create_human("B", server.COLORS[1])
    room = {
        "id": "PROMO1", "name": "promote test", "status": "lobby",
        "hostId": a["id"],
        "players": {a["id"]: a, b["id"]: b},
        "chat": [], "game": None, "createdAt": time.time(),
    }
    server.start_game(room)
    return room, a, b


def promotes_for(game, unit):
    return [e for e in game["effects"]
            if e.get("type") == "promote"
            and e.get("x") == unit["x"] and e.get("y") == unit["y"]]


def main():
    room, a, b = make_room()
    game = room["game"]

    # A 的攻击手，B 的一串活靶。攻击手摆远处免得平 A 干扰计数。
    shooter = server.make_unit("rifle", a["id"], 500, 500)
    game["units"].append(shooter)

    # 让 shooter 从 0 杀一路点到 17 杀，逐个检查特效只在 3/8/16 触发。
    expected = {3, 8, 16}
    fired_at = []
    for kill_no in range(1, 18):
        target = server.make_unit("rifle", b["id"], 9000, 9000)
        target["hp"] = 1.0
        game["units"].append(target)
        game["effects"][:] = []  # 只看本次击杀产生的特效
        server.apply_damage(room, target, 9999.0, a["id"], "bullet",
                            game, shooter["id"])
        assert target["hp"] == 0, "target should die"
        assert shooter["kills"] == kill_no, \
            "kills=%s expected %s" % (shooter["kills"], kill_no)
        got = promotes_for(game, shooter)
        if got:
            fired_at.append(kill_no)
            assert len(got) == 1, "one promote per crossing, got %d" % len(got)
        should = kill_no in expected
        assert bool(got) == should, \
            "kill %d: promote fired=%s expected=%s" % (kill_no, bool(got), should)
        game["units"].remove(target)

    assert fired_at == [3, 8, 16], "promote fired at %s" % fired_at
    print("OK: promote 特效只在 3/8/16 杀触发，位置=单位脚下，共 %d 次" % len(fired_at))


if __name__ == "__main__":
    main()
