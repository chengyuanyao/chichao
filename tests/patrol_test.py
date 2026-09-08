#!/usr/bin/env python3
"""Authoritative scouting loops, command priority, navigation and route privacy."""
import math
from unittest.mock import patch

from command_priority_test import make_room
import server


def setup(kind="dog"):
    room, alpha, beta = make_room()
    game = room["game"]
    unit = server.make_unit(kind, alpha["id"], 600, 600)
    game["units"] = [unit]
    return room, alpha, beta, unit


def advance(room, seconds):
    for _ in range(round(seconds / .05)):
        room["game"]["elapsed"] += .05
        server.tick_units(room, .05)


def test_loop_and_append():
    room, alpha, beta, dog = setup()
    game = room["game"]
    enemy = server.make_unit("rifle", beta["id"], 700, 630)
    game["units"].append(enemy)
    dog["order"], dog["targetId"] = "attack", enemy["id"]
    server.handle_game_command(room, alpha, {"command":"patrol", "unitIds":[dog["id"]], "x":1000,"y":600})
    assert dog["_patrolPoints"] == [(600,600),(1000,600)]
    assert dog["targetId"] is None and dog["order"] == "patrol"
    advance(room,.25)
    old_destination = dog["destX"], dog["destY"]
    server.issue_patrol(game,alpha["id"],{dog["id"]},1000,1000)
    server.issue_patrol(game,alpha["id"],{dog["id"]},600,1000)
    assert (dog["destX"],dog["destY"]) == old_destination, "append must not interrupt current leg"
    game["units"].remove(enemy)  # Preserve the attack-interruption check, no battle damage below.
    visited=[]
    for _ in range(1500):
        old=dog["_patrolIndex"]
        advance(room,.05)
        if old!=dog["_patrolIndex"]:
            visited.append(old)
        assert dog["targetId"] is None and dog["order"] == "patrol"
    assert visited[:8] == [1,2,3,0,1,2,3,0], visited
    assert not any(p["owner"]==alpha["id"] for p in game["projectiles"]), "patrol must not chase/fire"
    print("PASS: ordered append, repeated closed circuits, no auto-aggro")


def test_stop_and_reassign():
    room, alpha, beta, dog = setup()
    game=room["game"]
    server.issue_patrol(game,alpha["id"],{dog["id"]},1000,600)
    advance(room,.5)
    server.issue_stop(game,alpha["id"],{dog["id"]})
    position=dog["x"],dog["y"]
    advance(room,2)
    assert (dog["x"],dog["y"])==position and "_patrolPoints" not in dog
    server.issue_patrol(game,alpha["id"],{dog["id"]},1000,900)
    assert dog["_patrolPoints"][0] == position
    server.issue_move(game,alpha["id"],{dog["id"]},900,600)
    assert dog["order"]=="move" and "_patrolPoints" not in dog
    enemy=server.make_unit("rifle",beta["id"],1000,700)
    game["units"].append(enemy)
    server.issue_patrol(game,alpha["id"],{dog["id"]},1300,600)
    server.issue_attack(game,alpha["id"],{dog["id"]},enemy["id"])
    assert dog["order"]=="attack" and "_patrolPoints" not in dog
    print("PASS: H, normal move and explicit attack replace patrol")


def test_harvesters_and_vehicles():
    for kind in ("harvester","mharvester","tank","dragon","mcv","mmcv"):
        room,alpha,beta,unit=setup(kind)
        game=room["game"]
        game["resources"]=[{"id":"mine","x":650,"y":600,"radius":48,
                            "amount":9000,"maxAmount":9000,"guarded":False}]
        server.issue_patrol(game,alpha["id"],{unit["id"]},1000,600)
        advance(room,1)
        assert unit["x"]>610 and unit["order"]=="patrol",kind
        if server.unit_role(kind)=="harvester":
            assert unit["cargo"]==0 and unit["harvestPaused"]
            server.issue_harvest(game,alpha["id"],{unit["id"]},"mine")
            assert unit["order"]=="harvest" and "_patrolPoints" not in unit
            assert unit["preferredResourceId"]=="mine"
        if kind=="tank":
            bay=server.make_structure("repair",alpha["id"],800,800,True)
            game["structures"].append(bay);unit["hp"]-=100
            server.issue_repair(game,alpha["id"],{unit["id"]},bay["id"])
            assert unit["order"]=="repair" and "_patrolPoints" not in unit
    print("PASS: all mobile roles, no accidental mining, explicit harvest/repair cancel")


def test_bridge_and_blocked_points():
    room,alpha,beta,dog=setup()
    game=room["game"]
    terrain=server.Terrain(
        [{"x1":1200,"y1":0,"x2":1200,"y2":2400,"width":140}],
        [{"x":1200,"y":900,"w":190,"h":180}],2400,2400)
    game["terrainCtx"]=terrain
    server.issue_patrol(game,alpha["id"],{dog["id"]},1800,600)
    crossings=0;last_side=False
    for _ in range(1900):
        advance(room,.05)
        assert not terrain.blocked(dog["x"],dog["y"],dog["size"]*.5), (dog["x"],dog["y"])
        side=dog["x"]>1200
        if side!=last_side:
            crossings+=1;last_side=side
            assert abs(dog["y"]-900)<90, "water crossing must use bridge"
    assert crossings>=4,crossings
    server.issue_patrol(game,alpha["id"],{dog["id"]},1200,500)
    assert not terrain.blocked(*dog["_patrolPoints"][-1],dog["size"]*.5)
    before=dog["_patrolIndex"]
    with patch.object(server,"move_toward",return_value=False):
        advance(room,server.PATROL_STALL_SECONDS+.1)
    assert dog["_patrolIndex"] == (before+1)%len(dog["_patrolPoints"])
    print("PASS: repeated bridge crossings without clipping, safe projection and stalled-leg skip")


def test_validation_and_privacy():
    room,alpha,beta,dog=setup()
    game=room["game"]
    enemy=server.make_unit("dog",beta["id"],680,600)
    dead=server.make_unit("dog",alpha["id"],600,800);dead["hp"]=0
    game["units"].extend([enemy,dead])
    for invalid in (None, [], "not-a-point", math.nan, math.inf):
        try:
            server.issue_patrol(game,alpha["id"],{dog["id"]},invalid,1000)
            raise AssertionError("invalid coordinate accepted")
        except ValueError:
            pass
    assert "_patrolPoints" not in dog
    server.handle_game_command(room,alpha,{"command":"patrol","x":1000,"y":600})
    assert "_patrolPoints" not in dog, "missing selection cannot order every unit"
    server.issue_patrol(game,alpha["id"],{dog["id"],enemy["id"],dead["id"]},1000,600)
    assert "_patrolPoints" not in enemy and "_patrolPoints" not in dead
    own=server.public_game(game,alpha["id"])
    other=server.public_game(game,beta["id"])
    assert len(own["patrols"])==1 and not other["patrols"]
    assert dog["id"] in {u["id"] for u in other["units"]}, "enemy is visible but route stays private"
    assert len(server.public_game(game,None)["patrols"])==1
    game["playerTeams"]={alpha["id"]:1,beta["id"]:1};server.invalidate_game_snapshot(game)
    assert len(server.public_game(game,beta["id"],full=False)["patrols"])==1
    for i in range(server.PATROL_MAX_POINTS-2):
        server.issue_patrol(game,alpha["id"],{dog["id"]},1200+(i%2)*200,700+i*22)
    assert len(dog["_patrolPoints"])==server.PATROL_MAX_POINTS
    before=list(dog["_patrolPoints"])
    try:
        server.issue_patrol(game,alpha["id"],{dog["id"]},500,500)
        raise AssertionError("unbounded route accepted")
    except ValueError:
        pass
    assert dog["_patrolPoints"]==before
    print("PASS: finite coordinates, ownership, bounded routes, private snapshots and ally sharing")


if __name__ == "__main__":
    test_loop_and_append()
    test_stop_and_reassign()
    test_harvesters_and_vehicles()
    test_bridge_and_blocked_points()
    test_validation_and_privacy()
