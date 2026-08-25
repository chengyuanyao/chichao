#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""可选模式「战斗奖励」：大厅锁定、敌方最后一击奖励与防刷钱规则。"""

from __future__ import print_function

import math
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import server


def make_lobby(tag="REWARD"):
    alpha = server.create_human("奖励甲", server.COLORS[0])
    beta = server.create_human("奖励乙", server.COLORS[1])
    room = {
        "id": tag, "name": "combat reward test", "status": "lobby",
        "hostId": alpha["id"],
        "players": {alpha["id"]: alpha, beta["id"]: beta},
        "chat": [], "game": None, "createdAt": time.time(),
        "selectedMap": "narrow_standoff", "combatRewards": False,
    }
    return room, alpha, beta


def make_damage_room(enabled=True, teamed=False):
    room, alpha, beta = make_lobby("DAMAGE")
    alpha["cash"] = 1000
    beta["cash"] = 1000
    alpha["combatRewardsEarned"] = 0
    beta["combatRewardsEarned"] = 0
    if teamed:
        alpha["team"] = beta["team"] = 1
    game = {
        "combatRewards": bool(enabled),
        "playerTeams": {
            alpha["id"]: alpha.get("team", 0),
            beta["id"]: beta.get("team", 0),
        },
        "units": [], "structures": [], "effects": [],
    }
    room["status"] = "playing"
    room["game"] = game
    return room, game, alpha, beta


def kill(room, game, target, attacker):
    server.apply_damage(
        room, target, target["maxHp"] + 1, attacker["id"], game=game)


def expected_reward(kind, structure=False):
    catalog = server.STRUCTURE_TYPES if structure else server.UNIT_TYPES
    rate = (server.COMBAT_REWARD_STRUCTURE_RATE if structure
            else server.COMBAT_REWARD_UNIT_RATE)
    return int(math.floor(float(catalog[kind]["cost"]) * rate))


def main():
    print("=== Test 1: 大厅默认关闭，只有房主可改，开战后锁定 ===")
    room, host, guest = make_lobby()
    assert server.public_room(room, viewer_id=guest["id"])["combatRewards"] is False
    try:
        server.set_combat_rewards(room, guest, True)
        raise AssertionError("访客不该能开启战斗奖励")
    except ValueError as exc:
        assert "房主" in str(exc)
    server.set_combat_rewards(room, host, True)
    assert room["combatRewards"] is True
    assert server.public_room(room, viewer_id=guest["id"])["combatRewards"] is True
    server.start_game(room)
    assert room["game"]["combatRewards"] is True
    assert host["combatRewardsEarned"] == 0
    assert server.public_player(room, host, host["id"])["combatRewardsEarned"] == 0
    try:
        server.set_combat_rewards(room, host, False)
        raise AssertionError("开战后不该还能关闭战斗奖励")
    except ValueError as exc:
        assert "开始" in str(exc)
    print("  默认关 / 房主开关 / 旁观可见 / 开战锁定: PASS")

    print("\n=== Test 2: 敌方单位返还8%，建筑返还5% ===")
    room, game, alpha, beta = make_damage_room(True)
    rifle = server.make_unit("rifle", beta["id"], 100, 100)
    power = server.make_structure("power", beta["id"], 200, 100, True)
    game["units"].append(rifle)
    game["structures"].append(power)
    start_cash = alpha["cash"]
    kill(room, game, rifle, alpha)
    unit_reward = expected_reward("rifle")
    assert alpha["cash"] == start_cash + unit_reward
    assert alpha["combatRewardsEarned"] == unit_reward
    kill(room, game, power, alpha)
    structure_reward = expected_reward("power", structure=True)
    assert alpha["cash"] == start_cash + unit_reward + structure_reward
    assert alpha["combatRewardsEarned"] == unit_reward + structure_reward
    print("  单位 +$%d / 建筑 +$%d: PASS" % (unit_reward, structure_reward))

    print("\n=== Test 3: 模式关闭不改变原经济 ===")
    room, game, alpha, beta = make_damage_room(False)
    target = server.make_unit("tank", beta["id"], 100, 100)
    game["units"].append(target)
    before = alpha["cash"]
    kill(room, game, target, alpha)
    assert alpha["cash"] == before
    assert alpha["combatRewardsEarned"] == 0
    print("  击毁敌军但资金不变: PASS")

    print("\n=== Test 4: 友军、自毁和中立目标不能刷奖励 ===")
    room, game, alpha, beta = make_damage_room(True, teamed=True)
    ally = server.make_unit("tank", beta["id"], 100, 100)
    game["units"].append(ally)
    before = alpha["cash"]
    kill(room, game, ally, alpha)
    assert alpha["cash"] == before

    own = server.make_unit("tank", alpha["id"], 200, 100)
    game["units"].append(own)
    kill(room, game, own, alpha)
    assert alpha["cash"] == before

    neutral = server.make_unit("tank", server.NEUTRAL_OWNER, 300, 100)
    game["units"].append(neutral)
    kill(room, game, neutral, alpha)
    assert alpha["cash"] == before
    assert alpha["combatRewardsEarned"] == 0
    print("  同队 / 自己 / 中立均为 $0: PASS")

    print("\n=== Test 5: 大厅控件、对局徽章和操作入口存在 ===")
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    with open(os.path.join(root, "public", "index.html"), "r", encoding="utf-8") as handle:
        index = handle.read()
    with open(os.path.join(root, "public", "app.js"), "r", encoding="utf-8") as handle:
        app = handle.read()
    with open(os.path.join(root, "server.py"), "r", encoding="utf-8") as handle:
        source = handle.read()
    assert "combatRewardsToggle" in index
    assert "击毁单位返还8%，建筑返还5%，默认关" in index
    assert "combatRewardsBadge" in index
    assert "setCombatRewards" in app and "setCombatRewards" in source
    assert "战利资金" in app
    print("  大厅开关 / 模式徽章 / 奖励提示 / 结算统计: PASS")

    print("\n=== 战斗奖励测试全部通过 ===")


if __name__ == "__main__":
    main()
