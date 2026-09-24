"""Two authoritative construction lanes, one slot each; no gameplay balance changes."""
from unittest.mock import patch
from headquarters_build_test import make_room, own_hq
import server


def rejects(fn):
    try:
        fn()
    except ValueError:
        return
    raise AssertionError("expected rejection")


def main():
    assert all(server.structure_queue_key(k)=="defenseQueue" for k in (
        "turret", "missile", "mtower", "mstorm", "tspiketower", "ttoxtower"))
    assert all(server.structure_queue_key(k)=="buildQueue" for k in ("ttrap", "tpit"))
    for magic in (False, True):
        room, p, enemy = make_room(789)
        game = room["game"]
        game["terrainCtx"] = server.FLAT_TERRAIN
        if magic:
            p["faction"] = "magic"
            for s in game["structures"]:
                if s["owner"] == p["id"]:
                    s["kind"] = "mhq" if server.structure_role(s["kind"]) == "hq" else server.faction_buildings("magic")[server.structure_role(s["kind"])]
        power, defense = ("mpower", "mtower") if magic else ("power", "turret")
        game["structures"].append(server.make_structure(power,p["id"],1200,1300,True))
        before = p["cash"]
        a = server.queue_structure(room,p["id"],power)
        b = server.queue_structure(room,p["id"],defense)
        rejects(lambda: server.queue_structure(room,p["id"],"turret" if magic else "mtower"))
        assert p["buildQueue"] == [a] and p["defenseQueue"] == [b]
        assert p["cash"] == before-server.STRUCTURE_TYPES[power]["cost"]-server.STRUCTURE_TYPES[defense]["cost"]
        rejects(lambda: server.queue_structure(room,p["id"],defense))
        rejects(lambda: server.queue_structure(room,p["id"],power))
        rejects(lambda: server.cancel_structure_queue(room,p["id"]))
        rejects(lambda: server.cancel_structure_queue(room,p["id"],defense,"old-task"))
        mine=server.public_player(room,p,viewer_id=p["id"])
        other=server.public_player(room,p,viewer_id=enemy["id"])
        assert mine["defenseQueue"] and mine["buildQueue"]
        assert not other["defenseQueue"] and not other["buildQueue"]
        mine["defenseQueue"][0]["remaining"]=999
        assert b["remaining"] != 999
        server.tick_build_queues(room,1)
        assert a["remaining"] == a["total"]-1 and b["remaining"] == b["total"]-1
        with patch.object(server,"production_power_factor",return_value=.4):
            server.tick_build_queues(room,1)
        assert abs(a["remaining"]-(a["total"]-1.4))<.001
        assert abs(b["remaining"]-(b["total"]-1.4))<.001
        room["mobileConstruction"]=False;game["mobileConstruction"]=False
        hq=own_hq(game,p["id"])
        server.issue_undeploy(game,p["id"],hq["id"])
        remaining=(a["remaining"],b["remaining"])
        server.tick_build_queues(room,1)
        assert remaining==(a["remaining"],b["remaining"])
        room["mobileConstruction"]=True;game["mobileConstruction"]=True
        server.tick_build_queues(room,1)
        assert a["remaining"]<remaining[0] and b["remaining"]<remaining[1]
        a["ready"]=True;a["remaining"]=0
        before_b=b["remaining"]
        server.tick_build_queues(room,1)
        assert b["remaining"]<before_b, "ready economy lane cannot block defenses"
        b["ready"]=True;b["remaining"]=0
        # A failed placement consumes neither ready building nor money.
        with patch.object(server,"place_structure",side_effect=ValueError("blocked")):
            rejects(lambda: server.place_prepared_structure(room,p["id"],defense,0,0))
        assert p["buildQueue"] and p["defenseQueue"]
        with patch.object(server,"place_structure",return_value={"kind":defense}) as place:
            server.place_prepared_structure(room,p["id"],defense,0,0)
            assert place.call_args[1]=={"free":True,"requirements_locked":True}
        assert p["buildQueue"] and not p["defenseQueue"]
        b=server.queue_structure(room,p["id"],defense)
        server.handle_game_command(room,p,{"command":"cancelBuild","structureType":power,"queueId":a["id"]})
        assert not p["buildQueue"] and p["defenseQueue"]==[b]
        assert p["cash"]==before-2*server.STRUCTURE_TYPES[defense]["cost"]
        rejects(lambda: server.cancel_structure_queue(room,p["id"],power,a["id"]))
        p["eliminated"]=True
        remaining=b["remaining"];server.tick_build_queues(room,1)
        assert b["remaining"]==remaining
        p["eliminated"]=False
        server.start_game(room)
        assert not p["buildQueue"] and not p["defenseQueue"], "rematch clears both lanes"

    # Built-in AI defends while economy production is occupied, even before factory tech.
    room,p,e=make_room(456);p["isBot"]=True;p["cash"]=50000
    server.queue_structure(room,p["id"],"power")
    own_hq(room["game"],p["id"])["hp"]=1000
    with patch.object(server,"bot_needs_defense",return_value=True):
        server.tick_bots(room)
    assert p["buildQueue"][0]["kind"]=="power" and p["defenseQueue"][0]["kind"]=="turret"
    # Optional strategic AI likewise builds defenses while development is occupied.
    from ai_commander.commander import Commander
    from ai_commander.config import Settings
    strategist=Commander(Settings(),log=lambda *args:None)
    server.cancel_structure_queue(room,p["id"],"turret")
    plan={"build":["power","turret"],"max_turrets":1,"mix":{}}
    structures=[s for s in room["game"]["structures"] if s["owner"]==p["id"]]
    strategist._build(room,p,plan,structures,155,30)
    assert p["defenseQueue"][0]["kind"]=="turret"
    print("Build lanes passed: parallel timers, shared costs/power, one slot, ready independence, scoped refund, stale rejection, authority, privacy, rematch and AI defense.")


if __name__=="__main__":
    main()
