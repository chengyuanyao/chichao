#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Team mechanics tests: vision sharing, friendly fire, build zones, victory."""

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


def main():
    random.seed(20260721)
    print("=== Test 1: Backward compatibility (no teams) ===")
    # Players with team=0 should behave exactly as before
    solo_a = server.create_human("独狼A", server.COLORS[0], team=0)
    solo_b = server.create_human("独狼B", server.COLORS[1], team=0)
    room = {
        "id": "TEAM01", "name": "team test", "status": "lobby",
        "hostId": solo_a["id"],
        "players": {solo_a["id"]: solo_a, solo_b["id"]: solo_b},
        "chat": [], "game": None, "createdAt": time.time(),
    }
    server.start_game(room)
    game = room["game"]

    # Vision: solo player only sees own units directly
    view_a = server.public_game(game, solo_a["id"])
    own_structures_directly_visible = [s for s in view_a["structures"] if s["owner"] == solo_a["id"]]
    enemy_structures_directly = [s for s in view_a["structures"] if s["owner"] == solo_b["id"]]
    assert len(own_structures_directly_visible) == 3, len(own_structures_directly_visible)
    # Enemy structures not DIRECTLY visible (may be in fog if they spawned close)
    # The key assertion: enemy with team=0 is NOT friendly
    assert not server.is_friendly(game, solo_b["id"], solo_a["id"])

    # Attack: block self-attack, allow enemy attack
    own_unit = next(u for u in game["units"] if u["owner"] == solo_a["id"] and u["kind"] == "tank")
    try:
        server.issue_attack(game, solo_a["id"], {own_unit["id"]}, own_unit["id"])
        raise AssertionError("should block self-attack")
    except ValueError:
        pass

    # nearest_enemy: finds enemy when teams=0
    enemy_hq = next(s for s in game["structures"] if s["owner"] == solo_b["id"] and s["kind"] == "hq")
    found = server.nearest_enemy(game, solo_a["id"], enemy_hq["x"] + 50, enemy_hq["y"], 200)
    assert found is not None and found["owner"] == solo_b["id"]

    # nearest_enemy: does NOT find own
    own_hq = next(s for s in game["structures"] if s["owner"] == solo_a["id"] and s["kind"] == "hq")
    not_found = server.nearest_enemy(game, solo_a["id"], own_hq["x"], own_hq["y"], 50)
    assert not_found is None, "should not find own structures"

    print("  Backward compatibility: PASS")

    print("\n=== Test 2: Team vision sharing ===")
    # Create a 2v2 setup
    team_a1 = server.create_human("红队A", server.COLORS[0], team=1)
    team_a2 = server.create_human("红队B", server.COLORS[1], team=1)
    team_b1 = server.create_human("蓝队A", server.COLORS[2], team=2)
    team_b2 = server.create_human("蓝队B", server.COLORS[3], team=2)
    room2 = {
        "id": "TEAM02", "name": "2v2 test", "status": "lobby",
        "hostId": team_a1["id"],
        "players": {p["id"]: p for p in [team_a1, team_a2, team_b1, team_b2]},
        "chat": [], "game": None, "createdAt": time.time(),
    }
    server.start_game(room2)
    game2 = room2["game"]

    assert server.is_friendly(game2, team_a1["id"], team_a2["id"])
    assert server.is_friendly(game2, team_b1["id"], team_b2["id"])
    assert not server.is_friendly(game2, team_a1["id"], team_b1["id"])
    assert not server.is_friendly(game2, team_a2["id"], team_b2["id"])

    # Vision: teammates share all sight
    view_a1 = server.public_game(game2, team_a1["id"])
    teammate_structures = [s for s in view_a1["structures"] if s["owner"] == team_a2["id"]]
    assert len(teammate_structures) == 3, "teammate structures should be visible: %d" % len(teammate_structures)
    teammate_units = [u for u in view_a1["units"] if u["owner"] == team_a2["id"]]
    assert len(teammate_units) == 5, "teammate units should be visible: %d" % len(teammate_units)

    # Vision sources include teammates
    sources = server.player_vision_sources(game2, team_a1["id"])
    teammate_source_count = sum(1 for s in game2["units"] if s["owner"] == team_a2["id"] and s["hp"] > 0)
    teammate_source_count += sum(1 for s in game2["structures"] if s["owner"] == team_a2["id"] and s["hp"] > 0)
    total_expected = sum(1 for u in game2["units"] if u["owner"] in (team_a1["id"], team_a2["id"]) and u["hp"] > 0)
    total_expected += sum(1 for s in game2["structures"] if s["owner"] in (team_a1["id"], team_a2["id"]) and s["hp"] > 0)
    assert len(sources) == total_expected, "vision sources: %d vs %d" % (len(sources), total_expected)

    # Pings: teammates can see each other's pings
    game2["pings"].append({"id": "ping1", "owner": team_a2["id"], "x": 500, "y": 500, "ttl": 4.0})
    view_a1_with_ping = server.public_game(game2, team_a1["id"])
    assert any(p["owner"] == team_a2["id"] for p in view_a1_with_ping["pings"]), "teammate pings should be visible"

    print("  Team vision sharing: PASS")

    print("\n=== Test 3: Friendly fire disabled ===")
    # Cannot attack teammate
    teammate_unit = next(u for u in game2["units"] if u["owner"] == team_a2["id"] and u["kind"] == "tank")
    try:
        server.issue_attack(game2, team_a1["id"], {teammate_unit["id"]}, teammate_unit["id"])
        raise AssertionError("should block attacking teammate")
    except ValueError as exc:
        assert "无效目标" in str(exc)

    # nearest_enemy: does NOT find teammate
    teammate_hq = next(s for s in game2["structures"] if s["owner"] == team_a2["id"] and s["kind"] == "hq")
    found_teammate = server.nearest_enemy(game2, team_a1["id"], teammate_hq["x"], teammate_hq["y"], 200)
    assert found_teammate is None, "nearest_enemy should skip teammates"

    # nearest_enemy: finds enemy team
    enemy_structures = [s for s in game2.get("structures", []) if s.get("owner") == team_b1.get("id") and s.get("kind") == "hq"]
    assert len(enemy_structures) == 1
    enemy = enemy_structures[0]
    found_enemy = server.nearest_enemy(game2, team_a1["id"], enemy["x"] + 50, enemy["y"], 200)
    assert found_enemy is not None and found_enemy["owner"] == team_b1["id"]

    # Tick units: target validation clears teammate targets
    my_unit = next(u for u in game2["units"] if u["owner"] == team_a1["id"] and u["kind"] == "tank")
    my_unit["targetId"] = teammate_unit["id"]  # incorrectly targeting teammate
    tick_for(room2, 0.6)
    assert my_unit["targetId"] is None, "target of teammate should be cleared"

    print("  Friendly fire disabled: PASS")

    print("\n=== Test 4: Build zone sharing ===")
    hq_a1 = next(s for s in game2["structures"] if s["owner"] == team_a1["id"] and s["kind"] == "hq")
    # construction_anchor_near: teammate buildings provide anchor
    anchor_from_teammate = server.construction_anchor_near(
        game2, team_a1["id"], teammate_hq["x"] + 100, teammate_hq["y"] + 100)
    assert anchor_from_teammate is True, "teammate HQ should provide build anchor"

    # Enemy proximity must not override a valid friendly construction anchor.
    # This is important on central-scramble starts where several MCVs deploy together.
    power_size = server.STRUCTURE_TYPES["power"]["size"]
    build_spot = None
    for distance in (180, 220, 260, 300, 340):
        for dx, dy in ((distance, 0), (-distance, 0), (0, distance), (0, -distance)):
            x, y = hq_a1["x"] + dx, hq_a1["y"] + dy
            if server.position_clear(game2, x, y, power_size):
                build_spot = (x, y, dx, dy)
                break
        if build_spot:
            break
    assert build_spot is not None, "need a clear build spot near the friendly HQ"
    x, y, dx, dy = build_spot
    length = max(1.0, (dx * dx + dy * dy) ** 0.5)
    enemy_hq_close = server.make_structure(
        "hq", team_b1["id"], x + dx / length * 220, y + dy / length * 220, True)
    game2["structures"].append(enemy_hq_close)
    placed = server.place_structure(room2, team_a1["id"], "power", x, y, free=True)
    assert placed["owner"] == team_a1["id"], "enemy proximity should not cancel a friendly anchor"
    game2["structures"].remove(placed)
    game2["structures"].remove(enemy_hq_close)

    print("  Build zone sharing: PASS")

    print("\n=== Test 5: Splash damage exempts teammates ===")
    # Place a tank from team A1 next to a friendly structure
    splash_tank = server.make_unit("tank", team_a1["id"], teammate_hq["x"] + 50, teammate_hq["y"])
    splash_tank["cooldown"] = 0
    splash_tank["scan"] = 0
    game2["units"].append(splash_tank)

    # Place enemy nearby
    enemy_target = server.make_unit("harvester", team_b1["id"], teammate_hq["x"] + 55, teammate_hq["y"] - 5)
    game2["units"].append(enemy_target)

    teammate_hp_before = teammate_hq["hp"]
    server.launch_projectile(game2, splash_tank, enemy_target, server.UNIT_TYPES["tank"])
    tick_for(room2, 0.5)
    # Teammate structure should NOT have taken splash damage
    assert teammate_hq["hp"] == teammate_hp_before, \
        "teammate should not take splash: %s -> %s" % (teammate_hp_before, teammate_hq["hp"])

    print("  Splash damage: PASS")

    print("\n=== Test 6: Team victory condition ===")
    # 2v2: team A (a1, a2), team B (b1, b2)
    # Eliminate b1 by destroying the HQ (leftover buildings do not keep them alive)
    game2["elapsed"] = 20  # satisfy the elapsed > 15 victory check
    for s in game2["structures"]:
        if s["owner"] == team_b1["id"] and server.structure_role(s["kind"]) == "hq":
            s["hp"] = 0

    # Also need to eliminate a1/a2's structures for clean test
    # Wait - the existing test already has a1's HQ which is fine

    tick_for(room2, 1.0)
    assert team_b1["eliminated"] is True, "b1 should be eliminated"
    assert team_b2["eliminated"] is False, "b2 should still be alive"
    assert room2["status"] != "finished", "game should continue (b2 alive)"

    # Eliminate b2 by destroying the HQ
    for s in game2["structures"]:
        if s["owner"] == team_b2["id"] and server.structure_role(s["kind"]) == "hq":
            s["hp"] = 0
    tick_for(room2, 1.0)
    assert team_b2["eliminated"] is True, "b2 should be eliminated"
    assert room2["status"] == "finished", "game should end (all team B eliminated)"
    assert game2["winnerId"] in (team_a1["id"], team_a2["id"])
    assert game2["winnerTeam"] == 1
    assert set(game2["winnerIds"]) == set((team_a1["id"], team_a2["id"]))
    for teammate in (team_a1, team_a2):
        public = server.public_game(game2, teammate["id"])
        assert set(public["winnerIds"]) == set((team_a1["id"], team_a2["id"]))

    print("  Team victory: PASS")

    print("\n=== Test 7: Solo + Team mix ===")
    mix_a = server.create_human("混合A", server.COLORS[0], team=1)
    mix_b = server.create_human("混合B", server.COLORS[1], team=1)
    mix_c = server.create_human("混合C", server.COLORS[2], team=0)  # solo player
    room3 = {
        "id": "TEAM03", "name": "mixed", "status": "lobby",
        "hostId": mix_a["id"],
        "players": {p["id"]: p for p in [mix_a, mix_b, mix_c]},
        "chat": [], "game": None, "createdAt": time.time(),
    }
    server.start_game(room3)
    game3 = room3["game"]

    assert server.is_friendly(game3, mix_a["id"], mix_b["id"])
    assert not server.is_friendly(game3, mix_a["id"], mix_c["id"])
    assert not server.is_friendly(game3, mix_b["id"], mix_c["id"])

    # 即使一名队友先被淘汰，最后队伍获胜时也应拿到相同的胜利结果。
    game3["elapsed"] = 20
    for s in game3["structures"]:
        if s["owner"] == mix_b["id"] and server.structure_role(s["kind"]) == "hq":
            s["hp"] = 0
    tick_for(room3, 1.0)
    assert mix_b["eliminated"] is True
    assert room3["status"] != "finished"

    # Solo player eliminated by HQ loss -> team should win
    for s in game3["structures"]:
        if s["owner"] == mix_c["id"] and server.structure_role(s["kind"]) == "hq":
            s["hp"] = 0
    tick_for(room3, 1.0)
    assert mix_c["eliminated"] is True
    assert room3["status"] == "finished", "game should end with team victory"
    assert not mix_a["eliminated"] and mix_b["eliminated"]
    assert set(game3["winnerIds"]) == set((mix_a["id"], mix_b["id"]))

    print("  Solo + Team mix: PASS")

    print("\n=== Test 8: setTeam clamp ===")
    assert server.clamp_team(-3) == 0
    assert server.clamp_team(0) == 0
    assert server.clamp_team(4) == 4
    assert server.clamp_team(99) == 4
    assert server.clamp_team("2") == 2
    assert server.clamp_team("nope") == 0
    assert server.clamp_team(None) == 0
    print("  clamp_team 0-4: PASS")

    print("\n=== All team tests passed! ===")


if __name__ == "__main__":
    main()
