"""Local UI fixture with controlled post-match data, not a real match recording.

Run: py -3.13 tests/battle_report_visual_server.py
Open http://127.0.0.1:8878, create a room, add 4 AI and start. A deterministic
five-minute scenario populates the real report hooks and finishes immediately.
Production gameplay is unchanged; this process listens only on loopback.
"""
import os
import sys
from pathlib import Path

os.environ["HOST"] = "127.0.0.1"
os.environ["PORT"] = "8878"
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import battle_report
import server

original_start = server.start_game


def start_fixture(room):
    room["selectedMap"] = "central_scramble"
    room["neutrals"] = False
    players = list(room["players"].values())
    for index, player in enumerate(players):
        player["faction"] = "magic" if index % 2 else "tech"
    original_start(room)
    game = room["game"]
    game["units"] = []
    game["structures"] = []
    for index, player in enumerate(players):
        loadout = server.faction_loadout(player["faction"])
        x, y = 600 + index * 520, 600
        for n, role in enumerate(("hq", "power", "refinery")):
            game["structures"].append(server.make_structure(loadout[role], player["id"], x, y + n * 140, True))
    battle_report.start(room, "五车争霸 · 受控测试对局")
    for step in range(1, 31):
        game["elapsed"] = step * 10
        for index, player in enumerate(players):
            player["harvested"] += 450 + index * 90
            player["cash"] = 1000 + (step * (390 + index * 43)) % 7000
            if step % 2 == 0:
                kind = "golem" if player["faction"] == "magic" else "tank"
                game["units"].append(server.make_unit(kind, player["id"], 600 + index * 520, 1100 + step * 10))
            if step % (3 + index % 3) == 0:
                victim = next((u for u in game["units"] if u["owner"] == player["id"] and u["hp"] > 0), None)
                if victim:
                    attacker = players[(index + 1) % len(players)]
                    server.apply_damage(room, victim, 99999, attacker["id"], game=game)
        if step in (10, 17, 24):
            victim = next((s for s in game["structures"] if s["owner"] != players[0]["id"]
                           and s["hp"] > 0 and server.structure_role(s["kind"]) != "hq"), None)
            if victim:
                server.apply_damage(room, victim, 99999, players[0]["id"], game=game)
        battle_report.sample(room)
    for index, player in enumerate(players[1:]):
        game["elapsed"] = 300 + index * 8
        hq = next(s for s in game["structures"] if s["owner"] == player["id"] and server.structure_role(s["kind"]) == "hq")
        server.apply_damage(room, hq, 99999, players[0]["id"], game=game)
        server.check_elimination_and_victory(room, force=True)
    server.invalidate_game_snapshot(game)


if __name__ == "__main__":
    server.start_game = start_fixture
    raise SystemExit(server.main())
