"""Bounded, match-local post-game statistics; never a replay or live radar.

The simulation calls the event hooks, and samples aggregates at low frequency.
Only a finished match may publish this data. No entity positions are recorded.
"""
from copy import deepcopy

from catalog import STRUCTURE_TYPES, UNIT_TYPES, structure_role, unit_role

SAMPLE_SECONDS = 5.0
MAX_SAMPLES = 720
MAX_EVENTS = 160
INCOME_GAP_SECONDS = 30.0
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
            "byKind": {}, "techTimes": {}, "harvestersLost": 0,
            "incomeGapCount": 0, "incomeGapSeconds": 0.0, "longestIncomeGap": 0.0,
            "_lastIncomeAt": None,
        }
    game["_battleReport"] = {
        "version": 2, "matchId": game["uid"], "mapName": map_name,
        "mapId": game["map"]["id"], "players": rows, "firstCombatAt": None,
        "samples": [], "events": [], "droppedEvents": 0,
        "sampleInterval": SAMPLE_SECONDS, "nextSampleAt": 0,
        "finished": False,
    }
    for unit in game["units"]:
        if unit.get("hp", 0) > 0:
            unit_created(room, unit, "initial")
    for structure in game["structures"]:
        if structure.get("active") and structure.get("hp", 0) > 0:
            structure_completed(room, structure, initial=True)
    sample(room, force=True)


def kind_row(row, kind):
    if kind not in UNIT_TYPES and kind not in STRUCTURE_TYPES:
        kind = "support"
    if kind not in row["byKind"]:
        definition = UNIT_TYPES.get(kind, STRUCTURE_TYPES.get(kind, {}))
        row["byKind"][kind] = {
            "kind": kind, "name": definition.get("name", "轨道 / 其他来源"),
            "category": "unit" if kind in UNIT_TYPES else "structure" if kind in STRUCTURE_TYPES else "support",
            "produced": 0, "initial": 0, "gifted": 0, "lost": 0,
            "lostValue": 0, "destroyed": 0, "destroyedValue": 0,
        }
    return row["byKind"][kind]


def unit_created(room, unit, origin="produced"):
    state = _state(room)
    if not state or state["finished"] or unit.get("_reportCreated"):
        return
    row = state["players"].get(unit["owner"])
    if row is None or row["eliminatedAt"] is not None:
        return
    unit["_reportCreated"] = True
    kind_row(row, unit["kind"])[origin if origin in ("initial", "gifted") else "produced"] += 1


def structure_completed(room, structure, initial=False):
    state = _state(room)
    if not state or state["finished"]:
        return
    row = state["players"].get(structure["owner"])
    kind = structure["kind"]
    if (row is None or row["eliminatedAt"] is not None or kind in row["techTimes"]
            or structure_role(kind) not in KEY_STRUCTURE_ROLES):
        return
    stamp = 0.0 if initial else _time(room)
    row["techTimes"][kind] = {"time": stamp, "name": STRUCTURE_TYPES[kind]["name"], "initial": initial}
    if not initial:
        _event(state, {"time": stamp, "type": "techCompleted", "playerId": structure["owner"],
                       "kind": kind, "name": STRUCTURE_TYPES[kind]["name"]})


def _close_income_gap(room, player_id):
    state = _state(room)
    row = state["players"][player_id]
    last = row["_lastIncomeAt"]
    if last is None:
        return
    start = last + INCOME_GAP_SECONDS
    duration = round(_time(room) - start, 2)
    if duration <= 0:
        return
    row["incomeGapCount"] += 1
    row["incomeGapSeconds"] = round(row["incomeGapSeconds"] + duration, 2)
    row["longestIncomeGap"] = max(row["longestIncomeGap"], duration)
    _event(state, {"time": _time(room), "type": "incomeGap", "playerId": player_id,
                   "startedAt": start, "duration": duration})


def income(room, player_id, amount):
    state = _state(room)
    if not state or state["finished"] or amount <= 0:
        return
    row = state["players"].get(player_id)
    if row is None or row["eliminatedAt"] is not None:
        return
    _close_income_gap(room, player_id)
    row["_lastIncomeAt"] = _time(room)


def _event(state, event):
    # Preserve first-contact and elimination events even after a long siege.
    if len(state["events"]) >= MAX_EVENTS:
        index = next((i for i, row in enumerate(state["events"])
                      if row["type"] in ("structureDestroyed", "techCompleted", "incomeGap", "harvesterLost")), None)
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


def loss(room, target, source_owner=None, hostile=False, self_consumed=False, source_kind=None):
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
    kind_stats = kind_row(row, target.get("kind"))
    kind_stats["lost"] += 1
    kind_stats["lostValue"] += value
    if self_consumed:
        row["selfConsumedValue"] += value
    attacker = state["players"].get(source_owner) if hostile else None
    if attacker is not None and source_owner != owner:
        attacker["destroyedValue"] += value
        attacker["structuresDestroyed" if is_structure else "unitsDestroyed"] += 1
        source_stats = kind_row(attacker, source_kind)
        source_stats["destroyed"] += 1
        source_stats["destroyedValue"] += value
    if not is_structure and unit_role(target["kind"]) == "harvester":
        row["harvestersLost"] += 1
        _event(state, {"time": _time(room), "type": "harvesterLost", "playerId": owner,
                       "name": definition.get("name", target["kind"]),
                       "sourceId": source_owner if attacker else None})
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
    _close_income_gap(room, player_id)
    row["_lastIncomeAt"] = None
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
        if row["eliminatedAt"] is None:
            _close_income_gap(room, player_id)
            row["_lastIncomeAt"] = None
    state["duration"] = _time(room)
    state["finished"] = True
    state["public"] = {
        key: deepcopy(state[key]) for key in
        ("version", "matchId", "mapName", "mapId", "duration", "firstCombatAt",
         "samples", "events", "droppedEvents", "sampleInterval")
    }
    state["public"]["players"] = [deepcopy({k: v for k, v in row.items() if not k.startswith("_")})
                                   for row in state["players"].values()]


def published(room, match_id):
    state = _state(room)
    if room.get("status") != "finished":
        raise ValueError("整局结束后才能查看战报")
    if not state or not state["finished"]:
        raise ValueError("本局未记录战报，请更新服务后开启新对局")
    if not match_id or match_id != state["matchId"]:
        raise ValueError("战报不属于当前对局，请刷新页面")
    return state["public"]
