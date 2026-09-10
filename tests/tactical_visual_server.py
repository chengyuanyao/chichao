"""Loopback-only real-client fixture for mixed selection, scatter and hold.

Run py -3.13 tests/tactical_visual_server.py; open http://127.0.0.1:8877,
create a room, add an AI and start. AI is disabled; gameplay code is unchanged.
"""
import patrol_visual_server as fixture


def start_tactical_fixture(room):
    fixture.start_patrol_fixture(room)
    game = room["game"]
    game["units"] = []
    for player in room["players"].values():
        if player.get("isBot"):
            continue
        hq = next(s for s in game["structures"] if s["owner"] == player["id"]
                  and fixture.server.structure_role(s["kind"]) == "hq")
        for index, kind in enumerate(("tank","tank","dog","dog","artillery","artillery","mage","mage")):
            game["units"].append(fixture.server.make_unit(kind,player["id"],
                hq["x"]+130+index%4*55,hq["y"]+140+index//4*75))
    fixture.server.invalidate_game_snapshot(game)


if __name__ == "__main__":
    fixture.server.start_game = start_tactical_fixture
    fixture.server.tick_bots = lambda room: None
    raise SystemExit(fixture.server.main())
