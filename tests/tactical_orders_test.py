"""Player-only tactical orders, safe scatter and bounded cost."""
import math
import time
from command_priority_test import make_room
import server
from tactical_orders import scatter_destinations


def main():
    room, me, foe = make_room()
    game = room["game"]
    game["structures"] = []
    cannon = server.make_unit("artillery", me["id"], 1600, 1200)
    target = server.make_unit("tank", foe["id"], 1600+server.UNIT_TYPES["artillery"]["range"]-5, 1200)
    miner = server.make_unit("harvester", me["id"], 1400, 900)
    game["units"] = [cannon,target,miner]
    server.issue_stop(game, foe["id"], {target["id"]})
    target["scan"] = 999
    miner_order = miner["order"]
    server.handle_game_command(room,me,{"command":"hold","unitIds":[cannon["id"],target["id"],miner["id"]]})
    assert miner["order"] == miner_order and not miner["harvestPaused"]
    assert target["order"] == "guard" and cannon["order"] == "hold"
    game["units"].remove(miner)
    cannon["cooldown"] = 0
    server.tick_units(room,.05)
    assert any(p["sourceId"] == cannon["id"] for p in game["projectiles"]), "long-range hold must use weapon range, not old aggro radius"
    assert (cannon["x"],cannon["y"]) == (1600,1200)
    target["x"] += 500
    server.tick_units(room,.05)
    assert cannon["targetId"] is None and (cannon["x"],cannon["y"]) == (1600,1200), cannon
    assert server.public_unit(cannon)["tacticalOrder"] == "hold"
    server.issue_move(game,me["id"],{cannon["id"]},1300,1200)
    server.tick_units(room,.05)
    assert cannon["x"] < 1600 and cannon["order"] == "move"
    server.issue_tactical_order(game,me["id"],{cannon["id"]},"hold")
    server.issue_stop(game,me["id"],{cannon["id"]})
    assert cannon["order"] == "guard" and "tacticalOrder" not in server.public_unit(cannon)

    dog = server.make_unit("dog",me["id"],800,800)
    tank = server.make_unit("tank",foe["id"],815,800)
    rifle = server.make_unit("rifle",foe["id"],818,800)
    game["units"] = [dog,tank,rifle]
    assert server.nearest_hold_target(game,dog) is rifle
    rifle["hp"] = 0
    assert server.nearest_hold_target(game,dog) is None

    units = [server.make_unit("tank",me["id"],700+i%5*34,700+i//5*34) for i in range(25)]
    terrain = server.Terrain([],[],2000,1600,[{"x":1100,"y":800,"r":170}],[])
    game["terrainCtx"] = terrain
    game["units"] = units
    game["structures"] = []
    original = [(u["x"],u["y"]) for u in units]
    server.handle_game_command(room,me,{"command":"scatter","unitIds":[u["id"] for u in units]})
    assert any(u["order"] == "scatter" for u in units)
    assert [(u["x"],u["y"]) for u in units] == original, "scatter is movement, never teleportation"
    for unit in units:
        if unit["destX"] is not None:
            assert not terrain.blocked(unit["destX"],unit["destY"],unit["size"]*.55)
            assert not terrain.segment_blocked(unit["x"],unit["y"],unit["destX"],unit["destY"],padding=unit["size"]*.55)
    for _ in range(800):
        server.tick_units(room,.05)
    assert all(u["order"] == "hold" for u in units), "actual scatter arrivals must not chase and clump again"
    server.issue_patrol(game,me["id"],{units[0]["id"]},400,400)
    assert units[0]["order"] == "patrol"

    large = [server.make_unit("tank",me["id"],1000+i%20*34,1000+i//20*34) for i in range(400)]
    start = time.perf_counter()
    destinations = scatter_destinations(large,server.FLAT_TERRAIN)
    elapsed = (time.perf_counter()-start)*1000
    assert len(destinations) == 400
    assert destinations == scatter_destinations(large,server.FLAT_TERRAIN)
    changed = sum(math.hypot(destinations[u["id"]][0]-u["x"],destinations[u["id"]][1]-u["y"]) > 1 for u in large)
    assert changed > 200, changed
    # Each shipped map uses its own real topology. Bridge-edge scatter must
    # stay on the deck/bank, not choose a disconnected point across the river.
    for map_def in server.MAPS.values():
        terrain = server.terrain_for_match(map_def)
        anchors = [(map_def["width"]*.5,map_def["height"]*.5)]
        for bridge in map_def.get("bridges",[]):
            if "x1" in bridge:
                anchors.append(((bridge["x1"]+bridge["x2"])*.5,(bridge["y1"]+bridge["y2"])*.5))
            else:
                anchors.append((bridge["x"],bridge["y"]))
        for x,y in anchors:
            group=[]
            for i in range(9):
                px,py=x+(i%3-1)*28,y+(i//3-1)*28
                if not terrain.blocked(px,py,12.1):
                    group.append(server.make_unit("tank",me["id"],px,py))
            placed=scatter_destinations(group,terrain)
            for u in group:
                dx,dy=placed[u["id"]]
                assert not terrain.blocked(dx,dy,u["size"]*.55), map_def["id"]
                assert not terrain.segment_blocked(u["x"],u["y"],dx,dy,padding=u["size"]*.55), map_def["id"]
    print("Tactics passed: owners, economy exclusions, range-only hold, dog targets, immediate override, safe scatter, arrival hold; 400-unit plan %.2f ms" % elapsed)


if __name__ == "__main__":
    main()
