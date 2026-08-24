#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""AI co-pilot pairing codes are browser-approved, expiring and one-use."""

from __future__ import print_function

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import server


def make_room():
    player = server.create_human("配对玩家", server.COLORS[0])
    room = {
        "id": "PAIR01", "players": {player["id"]: player},
        "lock": server.threading.RLock(),
    }
    return room, player


def main():
    room, player = make_room()
    code = server.issue_agent_pair(player)
    assert len(code) == 8 and code.isalnum()
    assert server.redeem_agent_pair(room, code.lower()) is player
    assert server.redeem_agent_pair(room, code) is None, "配对码必须只能用一次"

    expired = server.issue_agent_pair(player)
    player["agentPair"]["expires"] = server.now() - 1
    assert server.redeem_agent_pair(room, expired) is None
    assert "agentPair" not in player

    other = server.issue_agent_pair(player)
    assert server.redeem_agent_pair(room, other + "X") is None
    assert server.redeem_agent_pair(room, other) is player

    # 配对码只有 8 位十六进制。没有限流的话，局域网里的人可以在这 2 分钟窗口
    # 里慢慢刷，所以连续猜错要进冷却。
    assert server.agent_pair_cooldown(room) == 0
    for _ in range(server.AGENT_PAIR_MAX_FAILS):
        assert server.redeem_agent_pair(room, "DEADBEEF") is None
        server.note_agent_pair_failure(room)
    assert server.agent_pair_cooldown(room) > 0, "连续猜错必须进冷却"

    # 冷却是给猜错的人设的：正确的码兑换成功后要立刻解除，
    # 不然玩家自己误输一次也会被关在门外一分钟。
    room["agentPairGate"]["until"] = server.now() - 1
    assert server.agent_pair_cooldown(room) == 0
    fresh = server.issue_agent_pair(player)
    server.note_agent_pair_failure(room)
    assert server.redeem_agent_pair(room, fresh) is player
    assert "agentPairGate" not in room
    print("agent pair tests passed")


if __name__ == "__main__":
    main()
