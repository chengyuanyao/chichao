"""Post-game aggregates, honest loss accounting, privacy and bounded sampling."""
import json
import threading
import time
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from command_priority_test import make_room
import battle_report
import server


def setup():
    room, alpha, beta = make_room()
    battle_report.start(room, "测试战区")
    return room, alpha, beta


def row(room, player):
    return room["game"]["_battleReport"]["players"][player["id"]]


def test_combat_accounting():
    room, alpha, beta = setup()
    game = room["game"]
    tank = server.make_unit("tank", beta["id"], 500, 500)
    game["units"].append(tank)
    game["elapsed"] = 4
    server.apply_damage(room, tank, 0, alpha["id"], game=game)
    server.apply_damage(room, tank, 10, "neutral", game=game)
    assert game["_battleReport"]["firstCombatAt"] is None
    game["elapsed"] = 12.5
    server.apply_damage(room, tank, 1, alpha["id"], game=game)
    assert row(room, alpha)["firstCombatAt"] == 12.5
    assert row(room, beta)["firstCombatAt"] == 12.5
    game["elapsed"] = 14
    server.apply_damage(room, tank, 999999, alpha["id"], game=game)
    server.apply_damage(room, tank, 999999, alpha["id"], game=game)
    cost = server.UNIT_TYPES["tank"]["cost"]
    assert row(room, alpha)["unitsDestroyed"] == 1
    assert row(room, alpha)["destroyedValue"] == cost
    assert row(room, beta)["lostValue"] == cost

    # Neutral kills and friendly fire cannot inflate enemy trade value.
    neutral = server.make_unit("dog", "neutral", 600, 600)
    server.apply_damage(room, neutral, 99999, alpha["id"], game=game)
    ally = server.make_unit("dog", beta["id"], 600, 600)
    game["playerTeams"] = {alpha["id"]: 1, beta["id"]: 1}
    server.apply_damage(room, ally, 99999, alpha["id"], game=game)
    assert row(room, alpha)["destroyedValue"] == cost
    assert row(room, beta)["unitsLost"] == 2
    # Dynamic alliances are evaluated at damage time, not at final team state.
    game["playerTeams"] = {alpha["id"]: 0, beta["id"]: 0}
    power = server.make_structure("mpower", beta["id"], 1000, 1000, True)
    server.apply_damage(room, power, 99999, alpha["id"], game=game)
    assert row(room, alpha)["structuresDestroyed"] == 1
    event = game["_battleReport"]["events"][-1]
    assert event["type"] == "structureDestroyed" and event["name"] == server.STRUCTURE_TYPES["mpower"]["name"]
    print("PASS: exact costs, separate unit/building counts, first PvP contact, neutral/friendly exclusions")


def test_suicide_and_transform():
    room, alpha, beta = setup()
    game = room["game"]
    bomb = server.make_unit("bomb_truck", alpha["id"], 900, 900)
    game["units"].append(bomb)
    server.trigger_death_explosion(room, bomb, game)
    server.trigger_death_explosion(room, bomb, game)
    cost = server.UNIT_TYPES["bomb_truck"]["cost"]
    assert row(room, alpha)["lostValue"] == cost
    assert row(room, alpha)["selfConsumedValue"] == cost
    bomb2 = server.make_unit("bomb_truck", alpha["id"], 1300, 1300)
    game["units"].append(bomb2)
    server.apply_damage(room, bomb2, 99999, beta["id"], game=game)
    assert row(room, alpha)["lostValue"] == 2 * cost
    assert row(room, alpha)["selfConsumedValue"] == cost, "shot-down bomb is not also self-consumption"
    assert row(room, beta)["destroyedValue"] == cost
    before = row(room, alpha)["lostValue"]
    hq = next(s for s in game["structures"] if s["owner"] == alpha["id"] and server.structure_role(s["kind"]) == "hq")
    server.issue_undeploy(game, alpha["id"], hq["id"])
    battle_report.sample(room, force=True)
    assert row(room, alpha)["lostValue"] == before, "folding is not a combat loss"
    print("PASS: self-detonation once, enemy-triggered explosion once, folding excluded")


def test_sampling_privacy_and_finish():
    room, alpha, beta = setup()
    game = room["game"]
    game["units"] = [server.make_unit(kind, beta["id"], 800 + i * 100, 800)
                     for i, kind in enumerate(("tank", "dog", "harvester", "mcv"))]
    # Remove the MCV before defeat below; it legitimately prevents elimination.
    alpha["harvested"] = 2300
    alpha["cash"] = 9000
    alpha["combatRewardsEarned"] = 100
    game["elapsed"] = 5
    battle_report.sample(room)
    state = game["_battleReport"]
    assert state["samples"][-1]["players"][alpha["id"]] == [2300, 9000, 0]
    army = server.UNIT_TYPES["tank"]["cost"] + server.UNIT_TYPES["dog"]["cost"]
    assert row(room, beta)["peakArmyValue"] == army
    samples = len(state["samples"])
    for _ in range(100):
        battle_report.sample(room)
    assert len(state["samples"]) == samples, "no per-tick curve growth"
    for full in (False, True):
        packet = json.dumps(server.public_room(room, viewer_id=alpha["id"], full=full))
        assert "_battleReport" not in packet and "destroyedValue" not in packet and '"samples"' not in packet
    try:
        battle_report.published(room, game["uid"])
        assert False, "live report leaked"
    except ValueError:
        pass
    beta["eliminated"] = True  # Spectators must wait for match end, too.
    try:
        battle_report.published(room, game["uid"])
        assert False
    except ValueError:
        pass
    beta["eliminated"] = False
    game["units"] = [u for u in game["units"] if server.unit_role(u["kind"]) != "mcv"]
    game["elapsed"] = 21.25
    hq = next(s for s in game["structures"] if s["owner"] == beta["id"] and server.structure_role(s["kind"]) == "hq")
    server.apply_damage(room, hq, 99999, alpha["id"], game=game)
    server.check_elimination_and_victory(room, force=True)
    assert room["status"] == "finished"
    report = battle_report.published(room, game["uid"])
    loser = next(p for p in report["players"] if p["id"] == beta["id"])
    assert loser["endingArmyValue"] == 0 and loser["unitsLost"] == 0
    assert loser["lostValue"] == server.STRUCTURE_TYPES[hq["kind"]]["cost"]
    assert loser["eliminatedAt"] == 21.25
    assert report["samples"][-1]["time"] == 21.25
    frozen = json.dumps(report, sort_keys=True)
    alpha["cash"] += 10000
    battle_report.finish(room)
    battle_report.sample(room, force=True)
    assert json.dumps(battle_report.published(room, game["uid"]), sort_keys=True) == frozen
    try:
        battle_report.published(room, "old-match")
        assert False
    except ValueError:
        pass
    old_id = game["uid"]
    server.start_game(room)
    assert room["game"]["uid"] != old_id
    assert not room["game"]["_battleReport"]["events"]
    assert row(room, alpha)["destroyedValue"] == 0 and row(room, alpha)["harvested"] == 0
    print("PASS: sampling, army definition, no live leakage, real victory finalization, immutable report and next-match reset")


def test_bounds_and_teams():
    room, alpha, beta = setup()
    state = room["game"]["_battleReport"]
    with patch.object(battle_report, "MAX_SAMPLES", 20), patch.object(battle_report, "MAX_EVENTS", 10):
        for index in range(150):
            room["game"]["elapsed"] = index * 10
            battle_report.sample(room, force=True)
            battle_report._event(state, {"type": "structureDestroyed", "time": index})
        battle_report.eliminate(room, beta["id"], "left")
        assert len(state["samples"]) <= 20 and state["samples"][0]["time"] == 0
        assert len(state["events"]) <= 10 and state["droppedEvents"] > 0
        assert state["events"][-1]["reason"] == "left"
    victim = server.make_structure("refinery", beta["id"], 800, 800, True)
    server.apply_damage(room, victim, 99999, alpha["id"], game=room["game"])
    assert row(room, alpha)["destroyedValue"] == 0 and row(room, beta)["lostValue"] == 0
    # The authoritative winner list includes a previously eliminated teammate.
    room["game"]["winnerIds"] = [alpha["id"], beta["id"]]
    room["status"] = "finished"
    battle_report.finish(room)
    assert all(p["won"] for p in battle_report.published(room, room["game"]["uid"])["players"])
    print("PASS: bounded long-game data, departure reason, authoritative team result")


def test_sampler_cost():
    room, alpha, beta = setup()
    room["game"]["units"] = [server.make_unit("tank", alpha["id"], 800, 800) for _ in range(1000)]
    started = time.perf_counter()
    for _ in range(100):
        battle_report.sample(room, force=True)
    average = (time.perf_counter() - started) * 1000 / 100
    assert average < 10, average
    print("PASS: 1000-unit aggregate sample %.3f ms; normally once per 5 seconds" % average)


def test_authenticated_endpoint():
    room, alpha, beta = setup()
    server.ROOMS[room["id"]] = room

    class QuietHandler(server.GameHandler):
        def log_message(self, *_args):
            pass

    httpd = server.ThreadedHTTPServer(("127.0.0.1", 0), QuietHandler)
    thread = threading.Thread(target=lambda: httpd.serve_forever(poll_interval=.02))
    thread.daemon = True
    thread.start()
    base = "http://127.0.0.1:%d" % httpd.server_address[1]

    def call(path, expected, data=None):
        request = Request(base + path, data=json.dumps(data).encode("utf-8") if data else None,
                          headers={"Content-Type": "application/json"})
        try:
            with urlopen(request, timeout=3) as response:
                status, body = response.status, response.read()
        except HTTPError as error:
            status, body = error.code, error.read()
        assert status == expected, (status, expected)
        return json.loads(body.decode("utf-8"))

    query = {"roomId": room["id"], "playerId": alpha["id"], "token": alpha["token"], "matchId": room["game"]["uid"]}
    try:
        call("/api/report?" + urlencode(dict(query, token="invalid")), 403)
        call("/api/report?" + urlencode(query), 409)
        room["game"]["elapsed"] = 32
        call("/api/action", 200, {"roomId": room["id"], "playerId": beta["id"], "token": beta["token"], "action": "leave"})
        report = call("/api/report?" + urlencode(query), 200)["report"]
        loser = next(p for p in report["players"] if p["id"] == beta["id"])
        assert loser["exitReason"] == "left" and loser["eliminatedAt"] == 32
        assert loser["lostValue"] == 0, "leaving is not an enemy kill"
        call("/api/report?" + urlencode(dict(query, matchId="stale")), 409)
        snapshot = call("/api/state?" + urlencode(query), 200)
        assert "samples" not in json.dumps(snapshot) and "_battleReport" not in json.dumps(snapshot)
    finally:
        httpd.shutdown()
        httpd.server_close()
        thread.join(timeout=2)
        server.ROOMS.pop(room["id"], None)
    print("PASS: real HTTP authentication, live-match denial, explicit departure, stale match and snapshot isolation")


if __name__ == "__main__":
    test_combat_accounting()
    test_suicide_and_transform()
    test_sampling_privacy_and_finish()
    test_bounds_and_teams()
    test_sampler_cost()
    test_authenticated_endpoint()
