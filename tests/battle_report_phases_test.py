"""Bounded phase totals, real cash ledger, temporal loss summaries and slowdown."""
import json
from unittest.mock import patch
from command_priority_test import make_room
import battle_report as report
import server


def finish(room):
    room["status"] = "finished"
    report.finish(room)
    return report.published(room, room["game"]["uid"])


def test_finance():
    room, me, foe = make_room()
    game = room["game"]
    row = game["_battleReport"]["players"][me["id"]]
    opening = me["cash"]
    barracks = server.make_structure("barracks", me["id"], 1000, 1000, True)
    game["structures"].append(barracks)
    game["elapsed"] = 10
    server.queue_unit(room, me["id"], "rifle")
    rifle_cost = server.UNIT_TYPES["rifle"]["cost"]
    game["elapsed"] = 20
    server.cancel_unit_queue(room, me["id"], "rifle")
    server.queue_structure(room, me["id"], "power")
    server.cancel_structure_queue(room, me["id"])
    flow = row["cashFlow"]
    assert flow["unitSpend"] == flow["unitRefund"] == rifle_cost
    assert flow["structureSpend"] == flow["structureRefund"] == server.STRUCTURE_TYPES["power"]["cost"]
    # Invalid commands must never enter the ledger.
    previous = dict(flow)
    try:
        server.cancel_unit_queue(room, me["id"], "rifle")
        raise AssertionError("empty queue accepted")
    except ValueError:
        pass
    assert flow == previous
    game["elapsed"] = 30
    report.eliminate(room, me["id"])
    game["elapsed"] = 100
    finish(room)
    assert row["cashObservedSeconds"] == 30
    assert row["highCashSeconds"] == 30
    assert abs(row["averageCash"] - (opening - rifle_cost / 3)) < 1e-6
    assert abs(row["cashReconciliation"]) < 1e-6
    assert row["closingCash"] == opening
    phases = game["_battleReport"]["phases"]
    assert abs(sum(p["players"].get(me["id"], {}).get("cashSeconds", 0) for p in phases) - row["cashSeconds"]) < 1e-6


def test_real_receipts_and_repair():
    room, me, foe = make_room()
    game = room["game"]
    game["elapsed"] = 10
    row = game["_battleReport"]["players"][me["id"]]
    server.apply_crate(room, me["id"], {"kind": "cash"})
    me["strikeCharges"] = server.STRIKE_MAX_CHARGES
    server.apply_crate(room, me["id"], {"kind": "strike"})
    assert row["cashFlow"]["crates"] == 2300
    factory = server.make_structure("factory", me["id"], 1000, 1000, True)
    factory["hp"] -= 100
    factory["repairing"] = True
    before = me["cash"]
    server.tick_structure_repair(room, factory, .1, {me["id"]: 1})
    assert abs(row["cashFlow"]["structureRepair"] - (before - me["cash"])) < 1e-6
    game["structures"].append(factory)
    server.handle_game_command(room, me, {"command": "sell", "structureId": factory["id"]})
    assert row["cashFlow"]["sales"] > 0
    bay = server.make_structure("repair", me["id"], 1600, 1600, True)
    game["structures"].append(bay)
    tank = server.make_unit("tank", me["id"], 1600, 1600)
    tank["hp"] -= 100
    tank["repairTargetId"] = bay["id"]
    before = me["cash"]
    server.tick_repair_unit(room, tank, .1, None, {me["id"]: 1}, server.FLAT_TERRAIN)
    assert row["cashFlow"]["unitRepair"] > 0
    assert abs(row["cashFlow"]["unitRepair"] - (before - me["cash"])) < 1e-6
    game["combatRewards"] = True
    victim = server.make_unit("tank", foe["id"], 1400, 1400)
    reward = server.award_combat_reward(room, game, me["id"], victim)
    assert row["cashFlow"]["rewards"] == reward > 0
    # The actual harvester delivery hook increments both income and ledger.
    refinery = server.make_structure("refinery", me["id"], 2000, 2000, True)
    game["structures"].append(refinery)
    harvester = server.make_unit("harvester", me["id"], 2000, 2000)
    harvester["cargo"], harvester["returnTarget"] = 123, refinery["id"]
    server.tick_harvester(room, harvester, .1)
    assert row["cashFlow"]["harvest"] == 123
    game["elapsed"] = 20
    finish(room)
    assert abs(row["cashReconciliation"]) < 1e-6


def test_phases_and_episodes():
    room, me, foe = make_room()
    game = room["game"]
    state = game["_battleReport"]
    for stamp, victim_owner, attacker in [(59.9, foe, me), (60, me, foe), (81, foe, me)]:
        game["elapsed"] = stamp
        victim = server.make_unit("tank", victim_owner["id"], 1000, 1000)
        report.loss(room, victim, attacker["id"], True, source_kind="tank")
    assert len(state["engagements"]) == 1
    assert state["engagements"][0]["start"] == 59.9 and state["engagements"][0]["end"] == 60
    cost = server.UNIT_TYPES["tank"]["cost"]
    assert state["phases"][0]["players"][me["id"]]["destroyedValue"] == cost
    assert state["phases"][1]["players"][me["id"]]["lostValue"] == cost
    # Many disjoint windows: episodes are capped; aggregates never discarded.
    for index in range(70):
        game["elapsed"] = 110 + index * 25
        victim = server.make_unit("dog", foe["id"], 1000, 1000)
        report.loss(room, victim, me["id"], True, source_kind="tank")
    assert len(state["engagements"]) <= report.MAX_ENGAGEMENTS
    game["elapsed"] = 100000  # Long silent tail must coarsen and stay bounded.
    published = finish(room)
    assert len(published["phases"]) <= report.MAX_PHASES
    assert published["phaseSeconds"] > 60
    assert published["phases"][-1]["time"] <= 100000 < published["phases"][-1]["time"] + published["phaseSeconds"]
    assert len(published["engagements"]) == report.MAX_ENGAGEMENTS
    assert published["omittedEngagements"] == 72 - report.MAX_ENGAGEMENTS
    for player in published["players"]:
        sums = sum(p["players"].get(player["id"], {}).get("lostValue", 0) for p in published["phases"])
        assert sums == player["lostValue"]
        seconds = sum(p["players"].get(player["id"], {}).get("cashObservedSeconds", 0) for p in published["phases"])
        assert seconds == player["cashObservedSeconds"] == 100000
        high_seconds = sum(p["players"].get(player["id"], {}).get("highCashSeconds", 0) for p in published["phases"])
        assert high_seconds == player["highCashSeconds"]
    assert published["engagements"][0]["value"] == 2 * cost
    frozen = json.dumps(published, sort_keys=True)
    report.phase_add(room, me["id"], "lostValue", 1)
    report.cash_flow(room, me["id"], "crates", 1)
    assert json.dumps(published, sort_keys=True) == frozen


def test_production_delay():
    room, me, foe = make_room()
    game = room["game"]
    row = game["_battleReport"]["players"][me["id"]]
    barracks = server.make_structure("barracks", me["id"], 1000, 1000, True)
    game["structures"].append(barracks)
    server.queue_unit(room, me["id"], "rifle")
    server.queue_structure(room, me["id"], "power")
    with patch.object(server, "production_power_factor", return_value=.4):
        server.tick_build_queues(room, .5)
        server.tick_structures(room, .5)
    assert abs(row["productionDelay"]["unitPowerLoss"] - .3) < 1e-6
    assert abs(row["productionDelay"]["buildPowerLoss"] - .3) < 1e-6
    with patch.object(server, "player_has_construction_authority", return_value=False):
        server.tick_build_queues(room, .5)
    assert row["productionDelay"]["authorityPause"] == .5
    # Finishing midway through a tick must only count actual busy time.
    barracks["queue"][0]["remaining"] = .01
    with patch.object(server, "production_power_factor", return_value=.4):
        server.tick_structures(room, .5)
    assert abs(row["productionDelay"]["unitPowerLoss"] - .315) < 1e-6


if __name__ == "__main__":
    test_finance()
    test_real_receipts_and_repair()
    test_phases_and_episodes()
    test_production_delay()
    print("Phase report passed: real cash ledger, weighted cash, exit freeze, refunds, repair, receipts, slowdown, bounded exact phase sums and ranked casualty episodes.")
