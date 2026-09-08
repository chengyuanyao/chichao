"""Bounded, match-local post-game statistics; never a replay or live radar.

The simulation calls the event hooks, and samples aggregates at low frequency.
Only a finished match may publish this data. No entity positions are recorded.
"""
from copy import deepcopy

from catalog import STRUCTURE_TYPES, UNIT_TYPES, structure_role, unit_role

SAMPLE_SECONDS = 5.0
MAX_SAMPLES = 720
MAX_EVENTS = 160
KEY_STRUCTURE_ROLES = frozenset(("hq", "power", "refinery", "barracks", "factory", "repair"))


def _state(room):
    return (room.get("game") or {}).get("_battleReport")


def _time(room):
    return round(float(room["game"].get("elapsed", 0)), 2)


def start(room, map_name):
    game = room["game"]
    rows = {}
    for player in room["players"].values():
        rows[player["id"]] = {
            "id": player["id"], "name": player["name"], "color": player["color"],
            "faction": player.get("faction", "tech"), "startTeam": player.get("team", 0),
            "firstCombatAt": None, "eliminatedAt": None, "exitReason": None,
            "unitsDestroyed": 0, "structuresDestroyed": 0,
            "unitsLost": 0, "structuresLost": 0,
            "destroyedValue": 0, "lostValue": 0, "selfConsumedValue": 0,
            "peakArmyValue": 0,
        }
    game["_battleReport"] = {
        "version": 1, "matchId": game["uid"], "mapName": map_name,
        "mapId": game["map"]["id"], "players": rows, "firstCombatAt": None,
        "samples": [], "events": [], "droppedEvents": 0,
        "sampleInterval": SAMPLE_SECONDS, "nextSampleAt": 0,
        "finished": False,
    }
    sample(room, force=True)


def _event(state, event):
    # Preserve first-contact and elimination events even after a long siege.
    if len(state["events"]) >= MAX_EVENTS:
        index = next((i for i, row in enumerate(state["events"])
                      if row["type"] == "structureDestroyed"), None)
        if index is None:
            state["droppedEvents"] += 1
            return
        state["events"].pop(index)
        state["droppedEvents"] += 1
    state["events"].append(event)


def damage(room, target, amount, source_owner, hostile):
    state = _state(room)
    if not state or state["finished"] or amount <= 0 or not hostile:
        return
    owner = target.get("owner")
    rows = state["players"]
    if owner not in rows or source_owner not in rows:
        return  # Neutral guards, friendly fire and system strikes are not PvP.
    if rows[owner]["eliminatedAt"] is not None or rows[source_owner]["eliminatedAt"] is not None:
        return
    stamp = _time(room)
    if state["firstCombatAt"] is None:
        state["firstCombatAt"] = stamp
        _event(state, {"time": stamp, "type": "firstCombat",
                       "playerId": owner, "sourceId": source_owner})
    for player_id in (owner, source_owner):
        if rows[player_id]["firstCombatAt"] is None:
            rows[player_id]["firstCombatAt"] = stamp


def loss(room, target, source_owner=None, hostile=False, self_consumed=False):
    state = _state(room)
    if not state or state["finished"] or target.get("_reportLossRecorded"):
        return
    owner = target.get("owner")
    row = state["players"].get(owner)
    if row is None or row["eliminatedAt"] is not None:
        # Remaining scenery after surrender/command loss is not a new battle.
        return
    target["_reportLossRecorded"] = True
    is_structure = target["id"].startswith("s")
    definitions = STRUCTURE_TYPES if is_structure else UNIT_TYPES
    definition = definitions.get(target.get("kind"), {})
    value = int(definition.get("cost", 0))
    row["lostValue"] += value
    row["structuresLost" if is_structure else "unitsLost"] += 1
    if self_consumed:
        row["selfConsumedValue"] += value
    attacker = state["players"].get(source_owner) if hostile else None
    if attacker is not None and source_owner != owner:
        attacker["destroyedValue"] += value
        attacker["structuresDestroyed" if is_structure else "unitsDestroyed"] += 1
    if is_structure and structure_role(target["kind"]) in KEY_STRUCTURE_ROLES:
        _event(state, {"time": _time(room), "type": "structureDestroyed",
                       "playerId": owner, "sourceId": source_owner if source_owner in state["players"] else None,
                       "kind": target["kind"], "name": definition.get("name", target["kind"]),
                       "cause": "enemy" if attacker else "other"})


def eliminate(room, player_id, reason="commandLost"):
    state = _state(room)
    if not state or state["finished"]:
        return
    row = state["players"].get(player_id)
    if row is None or row["eliminatedAt"] is not None:
        return
    row["eliminatedAt"] = _time(room)
    row["exitReason"] = reason
    _event(state, {"time": row["eliminatedAt"], "type": "eliminated",
                   "playerId": player_id, "reason": reason})


def sample(room, force=False):
    state = _state(room)
    if not state or state["finished"]:
        return
    stamp = _time(room)
    if not force and stamp < state["nextSampleAt"]:
        return
    values = {player_id: 0 for player_id in state["players"]}
    for unit in room["game"]["units"]:
        owner = unit["owner"]
        if (owner in values and unit["hp"] > 0
                and not room["players"].get(owner, {}).get("eliminated")
                and unit_role(unit["kind"]) not in ("harvester", "mcv")):
            values[owner] += int(UNIT_TYPES.get(unit["kind"], {}).get("cost", 0))
    point = {"time": stamp, "players": {}}
    for player_id, row in state["players"].items():
        player = room["players"].get(player_id, {})
        row["harvested"] = int(player.get("harvested", 0))
        row["cash"] = int(player.get("cash", 0))
        row["combatRewardsEarned"] = int(player.get("combatRewardsEarned", 0))
        row["endingArmyValue"] = values[player_id]
        row["peakArmyValue"] = max(row["peakArmyValue"], values[player_id])
        row["team"] = room["game"].get("playerTeams", {}).get(player_id, 0)
        point["players"][player_id] = [row["harvested"], row["cash"], values[player_id]]
    samples = state["samples"]
    if samples and samples[-1]["time"] == stamp:
        samples[-1] = point
    else:
        if len(samples) >= MAX_SAMPLES:
            # Keep the opening and thin older curves, not an unbounded tick log.
            samples[:] = samples[::2]
            state["sampleInterval"] *= 2
        samples.append(point)
    state["nextSampleAt"] = stamp + state["sampleInterval"]


def finish(room):
    state = _state(room)
    if not state or state["finished"] or room.get("status") != "finished":
        return
    sample(room, force=True)
    winners = set(room["game"].get("winnerIds", []))
    for player_id, row in state["players"].items():
        row["won"] = player_id in winners
    state["duration"] = _time(room)
    state["finished"] = True
    state["public"] = {
        key: deepcopy(state[key]) for key in
        ("version", "matchId", "mapName", "mapId", "duration", "firstCombatAt",
         "samples", "events", "droppedEvents", "sampleInterval")
    }
    state["public"]["players"] = deepcopy(list(state["players"].values()))


def published(room, match_id):
    state = _state(room)
    if room.get("status") != "finished":
        raise ValueError("整局结束后才能查看战报")
    if not state or not state["finished"]:
        raise ValueError("本局未记录战报，请更新服务后开启新对局")
    if not match_id or match_id != state["matchId"]:
        raise ValueError("战报不属于当前对局，请刷新页面")
    return state["public"]
