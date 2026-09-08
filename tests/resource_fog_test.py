#!/usr/bin/env python3
"""Mineral intelligence is private to live friendly vision on every map."""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import server


def assert_intel(game, viewer, target, visible):
    for full in (False, True):
        snapshot = server.public_game(game, viewer, full=full)
        intel = {r["id"]: r for r in snapshot["resourceIntel"]}
        assert (target["id"] in intel) is visible
        assert (target["id"] in {r[0] for r in snapshot["ore"]}) is visible
        if full:
            assert {r["id"] for r in snapshot["resources"]} == set(intel)
        else:
            assert "resources" not in snapshot
        if visible:
            assert intel[target["id"]]["amount"] == round(target["amount"], 1)


def main():
    for map_id in server.SHIPPED_MAP_IDS:
        alpha = server.create_human("侦察员", server.COLORS[0])
        beta = server.create_human("盟友", server.COLORS[1])
        room = {"id":"FOG", "name":"视野检查", "status":"lobby",
                "hostId":alpha["id"], "players":{p["id"]:p for p in (alpha,beta)},
                "chat":[], "createdAt":time.time(), "selectedMap":map_id, "game":None}
        server.start_game(room)
        game = room["game"]
        field = server.vision_field(game, alpha["id"])
        target = next(r for r in game["resources"] if not field.visible(r["x"],r["y"]))
        assert_intel(game, alpha["id"], target, False)
        assert not server.PUBLIC_MAPS[map_id]["resources"], "lobby leaked mineral positions"

        scout = server.make_unit("rifle",alpha["id"],target["x"],target["y"])
        game["units"].append(scout)
        server.invalidate_game_snapshot(game)
        assert_intel(game,alpha["id"],target,True)
        scout["hp"] = 0
        target["amount"] -= 777
        server.invalidate_game_snapshot(game)
        assert_intel(game,alpha["id"],target,False)

        scout["hp"] = scout["maxHp"]
        scout["owner"] = beta["id"]
        server.invalidate_game_snapshot(game)
        assert_intel(game,alpha["id"],target,False)
        game["playerTeams"] = {alpha["id"]:1,beta["id"]:1}
        server.invalidate_game_snapshot(game)
        assert_intel(game,alpha["id"],target,True)
        game["playerTeams"] = {alpha["id"]:1,beta["id"]:0}
        server.invalidate_game_snapshot(game)
        assert_intel(game,alpha["id"],target,False)

        alpha["eliminated"] = True
        observer = server.public_room(room,viewer_id=alpha["id"])["game"]
        assert len(observer["resources"]) == len(game["resources"])
        assert_intel(game,None,target,True)
        print(map_id + ': hidden / scout / dead scout / ally / break alliance / spectator PASS')


if __name__ == "__main__":
    main()
