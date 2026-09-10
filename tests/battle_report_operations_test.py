"""Real production/death/income hooks and bounded, honest operating metrics."""
from command_priority_test import make_room
import battle_report
import server


def main():
    room, me, foe = make_room()
    game = room["game"]
    row = game["_battleReport"]["players"][me["id"]]
    factory = server.make_structure("factory",me["id"],1000,1000,True)
    factory["queue"] = [{"kind":"tank","remaining":.001,"total":1}]
    game["structures"] = [factory]
    game["elapsed"] = 44
    server.tick_structures(room,.1)
    assert row["byKind"]["tank"]["produced"] == 1
    tank = game["units"][-1]
    battle_report.unit_created(room,tank)
    assert row["byKind"]["tank"]["produced"] == 1

    refinery = server.make_structure("refinery",me["id"],1400,1400,False)
    refinery["buildRemaining"] = .001
    factory["active"] = False
    factory["buildRemaining"] = .001
    game["structures"].append(refinery)
    game["elapsed"] = 60
    server.tick_structures(room,.1)
    assert row["byKind"]["harvester"]["gifted"] == 1
    assert row["techTimes"]["factory"]["time"] == 60
    game["elapsed"] = 70
    battle_report.structure_completed(room,factory)
    assert row["techTimes"]["factory"]["time"] == 60

    # A dead/removed shooter still gets per-kind last-hit credit.
    victim = server.make_unit("harvester",foe["id"],tank["x"]+2,tank["y"])
    victim["hp"] = 1
    game["units"].append(victim)
    server.launch_projectile(game,tank,victim,server.UNIT_TYPES["tank"])
    game["units"].remove(tank)
    server.tick_projectiles(room,.1)
    assert row["byKind"]["tank"]["destroyedValue"] == server.UNIT_TYPES["harvester"]["cost"]
    foe_row = game["_battleReport"]["players"][foe["id"]]
    assert foe_row["harvestersLost"] == 1
    assert foe_row["byKind"]["harvester"]["lost"] == 1

    # No pre-first-delivery gap, no crate/reward income, and no double counting.
    game["elapsed"] = 100
    battle_report.income(room,me["id"],100)
    assert row["incomeGapCount"] == 0
    game["elapsed"] = 130
    battle_report.income(room,me["id"],100)
    assert row["incomeGapCount"] == 0
    game["elapsed"] = 190
    battle_report.income(room,me["id"],100)
    assert row["incomeGapCount"] == 1 and row["incomeGapSeconds"] == 30
    game["elapsed"] = 235
    battle_report.eliminate(room,me["id"])
    assert row["incomeGapSeconds"] == 45 and row["longestIncomeGap"] == 30
    game["elapsed"] = 400
    battle_report.income(room,me["id"],100)
    assert row["incomeGapSeconds"] == 45
    room["status"] = "finished"
    game["winnerIds"] = [foe["id"]]
    battle_report.finish(room)
    published = battle_report.published(room,game["uid"])
    mine = next(p for p in published["players"] if p["id"] == me["id"])
    assert not any(k.startswith("_") for k in mine)
    assert published["version"] == 2 and mine["incomeGapSeconds"] == 45
    assert sum(k["destroyedValue"] for k in mine["byKind"].values()) == mine["destroyedValue"]
    before = len(published["events"])
    battle_report.finish(room)
    assert len(published["events"]) == before
    print("Report operations passed: production once, gift separation, first tech completion, posthumous attribution, harvester loss, precise 30s delivery gaps, frozen private-safe result.")


if __name__ == "__main__":
    main()
