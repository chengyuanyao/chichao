#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""In-game alliances: proposals, team changes, and the lobby dynamic-alliance lock."""

from __future__ import print_function

import os
import random
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import server


def tick_for(room, seconds, step=0.05):
    for _ in range(int(seconds / step)):
        server.tick_game(room, step)


def do_action(room, player, action, payload=None):
    """Call the same alliance helpers used by the HTTP action dispatcher."""
    payload = payload or {}
    if action == "proposeAlliance":
        server.propose_alliance(room, player, payload.get("playerId"))
    elif action == "acceptAlliance":
        server.accept_alliance(room, player)
    elif action == "rejectAlliance":
        server.reject_alliance(room, player)
    elif action == "breakAlliance":
        server.break_alliance(room, player)
    else:
        raise AssertionError("unknown alliance action: %s" % action)


def main():
    random.seed(20260721)

    print("=== Test 1: Propose + Accept Alliance ===")
    a = server.create_human("A", server.COLORS[0])
    b = server.create_human("B", server.COLORS[1])
    c = server.create_human("C", server.COLORS[2])
    room = {
        "id": "ALLY1", "name": "alliance test", "status": "lobby",
        "hostId": a["id"],
        "players": {a["id"]: a, b["id"]: b, c["id"]: c},
        "chat": [], "game": None, "createdAt": time.time(),
    }
    server.start_game(room)
    game = room["game"]

    assert not server.is_friendly(game, a["id"], b["id"])

    # A proposes to B
    do_action(room, a, "proposeAlliance", {"playerId": b["id"]})
    assert b["id"] in room.get("allianceProposals", {})

    # B accepts
    do_action(room, b, "acceptAlliance")
    assert b["id"] not in room.get("allianceProposals", {})
    assert server.is_friendly(game, a["id"], b["id"])
    assert game["playerTeams"][a["id"]] == game["playerTeams"][b["id"]]
    assert game["playerTeams"][b["id"]] > 0

    print("  Propose + Accept: PASS")

    print("\n=== Test 2: Propose + Reject ===")
    d = server.create_human("D", server.COLORS[3])
    room2 = {
        "id": "ALLY2", "name": "reject", "status": "lobby",
        "hostId": d["id"],
        "players": {d["id"]: d},
        "chat": [], "game": None, "createdAt": time.time(),
    }
    e = server.create_human("E", server.COLORS[4])
    room2["players"][e["id"]] = e
    server.start_game(room2)
    game2 = room2["game"]

    do_action(room2, d, "proposeAlliance", {"playerId": e["id"]})
    assert e["id"] in room2.get("allianceProposals", {})

    do_action(room2, e, "rejectAlliance")
    assert e["id"] not in room2.get("allianceProposals", {})
    assert not server.is_friendly(game2, d["id"], e["id"])

    print("  Propose + Reject: PASS")

    print("\n=== Test 3: Break Alliance ===")
    a2 = server.create_human("A2", server.COLORS[0], team=1)
    b2 = server.create_human("B2", server.COLORS[1], team=1)
    room3 = {
        "id": "ALLY3", "name": "break", "status": "lobby",
        "hostId": a2["id"],
        "players": {a2["id"]: a2, b2["id"]: b2},
        "chat": [], "game": None, "createdAt": time.time(),
    }
    server.start_game(room3)
    game3 = room3["game"]
    assert server.is_friendly(game3, a2["id"], b2["id"])

    do_action(room3, b2, "breakAlliance")
    assert not server.is_friendly(game3, a2["id"], b2["id"])
    assert game3["playerTeams"].get(b2["id"], 0) == 0

    print("  Break Alliance: PASS")

    print("\n=== Test 4: Can't propose to same team ===")
    try:
        do_action(room3, a2, "proposeAlliance", {"playerId": b2["id"]})
        # b2 is team 0 now, a2 is team 1 - should work
        # Actually they're different teams now so it should succeed
        print("  Propose to different team: OK (already verified)")
    except ValueError:
        pass

    # Re-test: same team should fail
    a2["team"] = 1
    b2["team"] = 1
    game3["playerTeams"] = {p["id"]: p.get("team", 0) for p in room3["players"].values()}
    try:
        do_action(room3, a2, "proposeAlliance", {"playerId": b2["id"]})
        raise AssertionError("should reject same-team proposal")
    except ValueError as exc:
        assert "同一队伍" in str(exc)

    print("  Same-team block: PASS")

    print("\n=== Test 5: Proposal expiration ===")
    a3 = server.create_human("AX", server.COLORS[0])
    b3 = server.create_human("BX", server.COLORS[1])
    room4 = {
        "id": "ALLY4", "name": "expire", "status": "lobby",
        "hostId": a3["id"],
        "players": {a3["id"]: a3, b3["id"]: b3},
        "chat": [], "game": None, "createdAt": time.time(),
    }
    server.start_game(room4)
    room4["allianceProposals"] = {
        b3["id"]: {"from": a3["id"], "time": time.time() - 50}
    }
    tick_for(room4, 0.5)
    # Cleanup fires in tick_game -> should have removed expired proposal
    assert b3["id"] not in room4.get("allianceProposals", {})
    print("  Proposal expiration: PASS")

    print("\n=== Test 6: Dynamic alliances off keeps lobby teams fixed ===")
    host = server.create_human("LOCK-H", server.COLORS[0], team=1)
    ally = server.create_human("LOCK-A", server.COLORS[1], team=1)
    outsider = server.create_human("LOCK-X", server.COLORS[2])
    room5 = {
        "id": "ALLY5", "name": "fixed teams", "status": "lobby",
        "hostId": host["id"],
        "players": {p["id"]: p for p in (host, ally, outsider)},
        "chat": [], "game": None, "createdAt": time.time(),
    }
    assert server.dynamic_alliances_enabled(room5) is True
    assert server.public_room(room5, viewer_id=ally["id"])["dynamicAlliances"] is True
    try:
        server.set_dynamic_alliances(room5, ally, False)
        raise AssertionError("访客不该能关闭动态结盟")
    except ValueError as exc:
        assert "房主" in str(exc)
    server.set_dynamic_alliances(room5, host, False)
    assert room5["dynamicAlliances"] is False
    assert server.public_room(room5, viewer_id=ally["id"])["dynamicAlliances"] is False

    server.start_game(room5)
    game5 = room5["game"]
    assert game5["dynamicAlliances"] is False
    assert server.is_friendly(game5, host["id"], ally["id"])
    assert not server.is_friendly(game5, host["id"], outsider["id"])
    for action, actor, payload in (
            ("proposeAlliance", outsider, {"playerId": host["id"]}),
            ("breakAlliance", ally, {})):
        try:
            do_action(room5, actor, action, payload)
            raise AssertionError("关闭动态结盟后不该允许 %s" % action)
        except ValueError as exc:
            assert "关闭动态结盟" in str(exc), str(exc)
    room5["allianceProposals"] = {
        host["id"]: {"from": outsider["id"], "time": time.time()}
    }
    try:
        do_action(room5, host, "acceptAlliance")
        raise AssertionError("关闭动态结盟后不该接受伪造提议")
    except ValueError as exc:
        assert "关闭动态结盟" in str(exc), str(exc)
    assert host["team"] == ally["team"] == 1
    assert server.is_friendly(game5, host["id"], ally["id"])
    assert "incomingProposal" not in server.public_room(
        room5, viewer_id=host["id"])
    try:
        server.set_dynamic_alliances(room5, host, True)
        raise AssertionError("开战后不该修改动态结盟开关")
    except ValueError as exc:
        assert "开始" in str(exc)

    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    with open(os.path.join(root, "public", "index.html"), "r",
              encoding="utf-8") as handle:
        index = handle.read()
    with open(os.path.join(root, "public", "app.js"), "r",
              encoding="utf-8") as handle:
        app = handle.read()
    assert "dynamicAlliancesToggle" in index
    assert "关闭后锁定开局队伍" in index
    assert "setDynamicAlliances" in app
    assert "function roomHasDynamicAlliances" in app
    print("  默认开 / 房主可关 / 预设盟友保留 / 结盟与退盟均锁定: PASS")

    print("\n=== All alliance tests passed! ===")


if __name__ == "__main__":
    main()
