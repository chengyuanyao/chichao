"""Local-only UI fixture: real game client/server, three dogs, no attacking AI.

Run: py -3.13 tests/patrol_visual_server.py
Open http://127.0.0.1:8877, create a room, add an AI and start. The fixture uses
iron_river_duel and gives each human three dogs. No production rules are saved.
Select dogs; Shift+right-click the battlefield/minimap, then press H.
"""
import os
import sys
from pathlib import Path

os.environ["HOST"] = "127.0.0.1"
os.environ["PORT"] = "8877"
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import server


original_start = server.start_game


def start_patrol_fixture(room):
    room["selectedMap"] = "iron_river_duel"
    room["neutrals"] = False
    original_start(room)
    game = room["game"]
    game["units"] = []
    for player in room["players"].values():
        if player.get("isBot"):
            continue
        hq = next(s for s in game["structures"] if s["owner"] == player["id"]
                  and server.structure_role(s["kind"]) == "hq")
        for index in range(3):
            game["units"].append(server.make_unit(
                "dog", player["id"], hq["x"] + 180 + index * 60, hq["y"] + 190))
    server.invalidate_game_snapshot(game)


if __name__ == "__main__":
    server.start_game = start_patrol_fixture
    server.tick_bots = lambda room: None
    raise SystemExit(server.main())
