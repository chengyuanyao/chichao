"""Version 3 contribution accounting through real damage and bounded hooks."""
import json
from command_priority_test import make_room
import battle_report
import server


def main():
    room, me, foe = make_room()
    game = room["game"]
    state = game["_battleReport"]
    mine, theirs = (state["players"][p["id"]] for p in (me, foe))
    tank = server.make_unit("tank", me["id"], 1000, 1000)
    victim = server.make_unit("harvester", foe["id"], 1100, 1000)
    victim["hp"], victim["cargo"] = 73, 123.5
    game["units"] = [tank, victim]
    game["elapsed"] = 10
    battle_report.unit_created(room, tank)
    battle_report.unit_created(room, tank)
    stats = mine["byKind"]["tank"]
    assert stats["produced"] == 1
    assert stats["producedValue"] == server.UNIT_TYPES["tank"]["cost"]
    assert stats["firstProducedAt"] == stats["lastProducedAt"] == 10
    server.apply_damage(room, victim, 99999, me["id"], game=game, source_unit=tank)
    server.apply_damage(room, victim, 99999, me["id"], game=game, source_unit=tank)
    assert stats["damageDealt"] == stats["unitDamage"] == 73
    assert mine["damageDealt"] == theirs["damageTaken"] == 73
    assert theirs["cargoLost"] == 123.5
    pair = mine["opponents"][foe["id"]]
    assert pair["harvestersDestroyed"] == pair["unitsDestroyed"] == 1
    assert pair["destroyedValue"] == theirs["opponents"][me["id"]]["lostValue"]

    # Posthumous projectile attribution, structure damage and unknown support.
    tower = server.make_structure("power", foe["id"], 1500, 1500, True)
    tower["hp"] = 29
    server.apply_damage(room, tower, 99999, me["id"], game=game, source_kind="tank")
    assert stats["structureDamage"] == 29
    assert pair["structuresDestroyed"] == 1
    target = server.make_unit("dog", foe["id"], 1400, 1400)
    battle_report.damage(room, target, 3, me["id"], True)
    assert mine["byKind"]["support"]["damageDealt"] == 3
    before = mine["damageDealt"]
    battle_report.damage(room, target, 5, me["id"], False)
    battle_report.damage(room, target, 5, "neutral", True)
    assert mine["damageDealt"] == before

    # Independent loss categories and cargo; no log entry per hit.
    bomb = server.make_unit("bomb_truck", me["id"], 2000, 2000)
    battle_report.loss(room, bomb, self_consumed=True)
    dog = server.make_unit("dog", me["id"], 2200, 2200)
    battle_report.loss(room, dog)
    assert mine["lossCauses"]["self"]["units"] == 1
    assert mine["lossCauses"]["other"]["units"] == 1
    assert theirs["lossCauses"]["enemy"]["units"] == 1
    events = len(state["events"])
    for _ in range(10000):
        battle_report.damage(room, target, 1, me["id"], True, "tank")
    assert len(state["events"]) == events and len(mine["opponents"]) == 1

    factory = server.make_structure("factory", me["id"], 2400, 2400, True)
    game["structures"].append(factory)
    game["elapsed"] = 20
    battle_report.structure_completed(room, factory)
    battle_report.structure_completed(room, factory)
    assert mine["byKind"]["factory"]["produced"] == 1
    assert mine["byKind"]["factory"]["firstProducedAt"] == 20
    hq = server.make_structure("hq", me["id"], 2700, 2700, True)
    initial_hq_count = mine["byKind"]["hq"]["initial"]
    battle_report.structure_completed(room, hq, transformed=True)
    assert mine["byKind"]["hq"]["produced"] == 0
    assert mine["byKind"]["hq"]["initial"] == initial_hq_count
    unfinished = server.make_structure("factory", me["id"], 3000, 3000, False)
    game["structures"].append(unfinished)
    battle_report.eliminate(room, foe["id"])
    before = mine["damageDealt"]
    battle_report.damage(room, target, 4, me["id"], True, "tank")
    assert mine["damageDealt"] == before
    room["status"] = "finished"
    game["winnerIds"] = [me["id"]]
    battle_report.finish(room)
    assert stats["remaining"] == 1
    assert mine["byKind"]["factory"]["remaining"] == 1
    assert all(k["remaining"] == 0 for k in theirs["byKind"].values())
    report = battle_report.published(room, game["uid"])
    frozen = json.dumps(report, sort_keys=True)
    battle_report.finish(room)
    battle_report.damage(room, tank, 4, foe["id"], True, "tank")
    assert json.dumps(report, sort_keys=True) == frozen
    assert sum(k["damageDealt"] for k in mine["byKind"].values()) == mine["damageDealt"]
    assert sum(k["value"] for k in mine["lossCauses"].values()) == mine["lostValue"]
    assert len(frozen) < 50000
    print("Detailed report passed: damage, overkill, opponents, cargo, causes, production, transformations, survivors, bounded storage and freeze.")


if __name__ == "__main__":
    main()
