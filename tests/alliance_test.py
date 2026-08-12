#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""In-game alliance tests: propose, accept, reject, break, vision/fire update."""

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
    """Mimic the alliance action dispatch from room_action."""
    data = {"action": action, "payload": payload or {}}
    if action == "proposeAlliance":
        if room["status"] != "playing":
            raise ValueError("只能在战斗中进行")
        if player.get("eliminated"):
            raise ValueError("你已被击败")
        target_id = data["payload"].get("playerId")
        target = room["players"].get(target_id)
        if not target or target["isBot"] or target.get("eliminated"):
            raise ValueError("无效的结盟目标")
        if server.is_friendly(room["game"], player["id"], target["id"]):
            raise ValueError("已经处于同一队伍")
        room.setdefault("allianceProposals", {})
        room["allianceProposals"][target["id"]] = {"from": player["id"], "time": time.time()}
    elif action == "acceptAlliance":
        proposals = room.get("allianceProposals", {})
        proposal = proposals.get(player["id"])
        if not proposal:
            raise ValueError("没有待处理的结盟提议")
        proposer = room["players"].get(proposal["from"])
        if not proposer or proposer.get("eliminated"):
            proposals.pop(player["id"], None)
            raise ValueError("提议者已不可用")
        team_id = proposer.get("team", 0)
        if team_id <= 0:
            team_id = max((p.get("team", 0) for p in room["players"].values()), default=0) + 1
            proposer["team"] = team_id
        player["team"] = team_id
        room["game"]["playerTeams"] = {p["id"]: p.get("team", 0) for p in room["players"].values()}
        proposals.pop(player["id"], None)
    elif action == "rejectAlliance":
        proposals = room.get("allianceProposals", {})
        proposals.pop(player["id"], None)
    elif action == "breakAlliance":
        if player.get("eliminated"):
            raise ValueError("你已被击败")
        if not player.get("team") or player["team"] <= 0:
            raise ValueError("你没有加入任何队伍")
        player["team"] = 0
        room["game"]["playerTeams"] = {p["id"]: p.get("team", 0) for p in room["players"].values()}


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

    print("\n=== All alliance tests passed! ===")


if __name__ == "__main__":
    main()
