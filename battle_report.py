"""Bounded, match-local post-game statistics; never a replay or live radar.

The simulation calls the event hooks, and samples aggregates at low frequency.
Only a finished match may publish this data. No entity positions are recorded.
"""
from copy import deepcopy
import diagnostics

from catalog import STRUCTURE_TYPES, UNIT_TYPES, structure_role, unit_role

SAMPLE_SECONDS = 5.0
MAX_SAMPLES = 720
MAX_EVENTS = 160
MAX_PHASES = 120
MAX_ENGAGEMENTS = 24
ENGAGEMENT_GAP = 20.0
HIGH_CASH = 5000
# Positive amounts; direction is defined here, not inferred from balance deltas.
CASH_DIRECTIONS = {"harvest": 1, "rewards": 1, "crates": 1,
                   "unitRefund": 1, "structureRefund": 1, "sales": 1,
                   "unitSpend": -1, "structureSpend": -1,
                   "unitRepair": -1, "structureRepair": -1, "adjustments": -1}
INCOME_GAP_SECONDS = 30.0
KEY_STRUCTURE_ROLES = frozenset(("hq", "power", "refinery", "barracks", "factory", "repair"))


def _state(room):
    return (room.get("game") or {}).get("_battleReport")


def _time(room):
    return round(float(room["game"].get("elapsed", 0)), 2)


def start(room, map_name):
    game = room["game"]
    diagnostics.start(room)
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
            "damageDealt": 0.0, "damageTaken": 0.0, "cargoLost": 0.0,
            "opponents": {}, "lossCauses": {},
            "byKind": {}, "techTimes": {}, "harvestersLost": 0,
            "incomeGapCount": 0, "incomeGapSeconds": 0.0, "longestIncomeGap": 0.0,
            "_lastIncomeAt": None,
            "cashFlow": {key: 0.0 for key in CASH_DIRECTIONS},
            "openingCash": float(player.get("cash", 0)),
            "cashSeconds": 0.0, "cashObservedSeconds": 0.0, "highCashSeconds": 0.0,
            "_cashAt": _time(room), "_cashValue": float(player.get("cash", 0)),
            "productionDelay": {},
        }
    game["_battleReport"] = {
        "version": 4, "matchId": game["uid"], "mapName": map_name,
        "mapId": game["map"]["id"], "players": rows, "firstCombatAt": None,
        "samples": [], "events": [], "droppedEvents": 0,
        "sampleInterval": SAMPLE_SECONDS, "nextSampleAt": 0,
        "finished": False,
        "phases": [], "phaseSeconds": 60, "engagements": [],
        "_activeEngagements": {}, "omittedEngagements": 0,
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
            "producedValue": 0, "firstProducedAt": None, "lastProducedAt": None,
            "damageDealt": 0.0, "damageTaken": 0.0,
            "unitDamage": 0.0, "structureDamage": 0.0,
            "remaining": 0, "remainingValue": 0,
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
    if origin not in ("initial", "gifted"):
        _production(room, row, unit["kind"])


def _production(room, row, kind):
    stats = kind_row(row, kind)
    definition = UNIT_TYPES.get(kind, STRUCTURE_TYPES.get(kind, {}))
    stats["producedValue"] += int(definition.get("cost", 0))
    if stats["firstProducedAt"] is None:
        stats["firstProducedAt"] = _time(room)
    stats["lastProducedAt"] = _time(room)
    phase_add(room, row["id"], "unitProducedValue" if kind in UNIT_TYPES else "structureProducedValue",
              int(definition.get("cost", 0)))


def phase_add(room, player_id, metric, amount, at=None):
    state = _state(room)
    if not state or state["finished"]:
        return
    stamp = float(room["game"].get("elapsed", 0)) if at is None else at
    # Coarsen the entire timeline without discarding any aggregate totals.
    while stamp >= MAX_PHASES * state["phaseSeconds"]:
        merged = []
        for index, phase in enumerate(state["phases"]):
            if index % 2 == 0:
                merged.append({"time": phase["time"], "players": {}})
            for pid, metrics in phase["players"].items():
                dest = merged[-1]["players"].setdefault(pid, {})
                for key, value in metrics.items():
                    dest[key] = dest.get(key, 0) + value
        state["phases"] = merged
        state["phaseSeconds"] *= 2
    index = int(stamp // state["phaseSeconds"])
    while len(state["phases"]) <= index:
        state["phases"].append({"time": len(state["phases"]) * state["phaseSeconds"], "players": {}})
    if amount:
        metrics = state["phases"][index]["players"].setdefault(player_id, {})
        metrics[metric] = metrics.get(metric, 0) + amount
    return state["phases"][index]


def _observe_cash(room, row):
    stamp = _time(room)
    duration = max(0, stamp - row["_cashAt"])
    row["cashSeconds"] += row["_cashValue"] * duration
    row["cashObservedSeconds"] += duration
    if row["_cashValue"] >= HIGH_CASH:
        row["highCashSeconds"] += duration
    if duration:
        # Split holding time at phase boundaries; never keep balance snapshots
        # per transaction. Coarsen before splitting, so even a long quiet gap is bounded.
        phase_add(room, None, None, 0)
        cursor = row["_cashAt"]
        interval = _state(room)["phaseSeconds"]
        while cursor < stamp:
            phase = phase_add(room, None, None, 0, at=cursor)
            end = min(stamp, phase["time"] + interval)
            span = end - cursor
            metrics = phase["players"].setdefault(row["id"], {})
            metrics["cashSeconds"] = metrics.get("cashSeconds", 0) + row["_cashValue"] * span
            metrics["cashObservedSeconds"] = metrics.get("cashObservedSeconds", 0) + span
            if row["_cashValue"] >= HIGH_CASH:
                metrics["highCashSeconds"] = metrics.get("highCashSeconds", 0) + span
            cursor = end
    row["_cashAt"] = stamp


def cash_flow(room, player_id, category, amount):
    """Called after a real balance change; never changes gameplay money itself."""
    state = _state(room)
    if not state or state["finished"] or amount <= 0 or category not in CASH_DIRECTIONS:
        return
    row = state["players"].get(player_id)
    if row is None or row["eliminatedAt"] is not None:
        return
    _observe_cash(room, row)
    row["_cashValue"] = float(room["players"][player_id].get("cash", 0))
    row["cashFlow"][category] += amount
    phase_add(room, player_id, category, amount)


def production_delay(room, player_id, category, seconds):
    state = _state(room)
    if not state or state["finished"] or seconds <= 0:
        return
    row = state["players"].get(player_id)
    if row is None or row["eliminatedAt"] is not None:
        return
    row["productionDelay"][category] = row["productionDelay"].get(category, 0) + seconds


def _keep_engagement(state, episode):
    state["engagements"].append(episode)
    if len(state["engagements"]) > MAX_ENGAGEMENTS:
        smallest = min(range(len(state["engagements"])), key=lambda i: state["engagements"][i]["value"])
        state["engagements"].pop(smallest)
        state["omittedEngagements"] += 1


def _engagement_loss(room, target, source_owner, value):
    state = _state(room)
    pair = tuple(sorted((target["owner"], source_owner)))
    stamp = _time(room)
    episode = state["_activeEngagements"].get(pair)
    if episode is None or stamp - episode["end"] > ENGAGEMENT_GAP:
        if episode is not None:
            _keep_engagement(state, episode)
        episode = {"start": stamp, "end": stamp, "value": 0, "players": {
            pid: {"lostValue": 0, "byKind": {}} for pid in pair}}
        state["_activeEngagements"][pair] = episode
    episode["end"] = stamp
    episode["value"] += value
    side = episode["players"][target["owner"]]
    side["lostValue"] += value
    kind = target["kind"]
    side["byKind"][kind] = side["byKind"].get(kind, 0) + 1


def opponent_row(row, opponent_id):
    if opponent_id not in row["opponents"]:
        row["opponents"][opponent_id] = {
            "damageDealt": 0.0, "damageTaken": 0.0,
            "unitsDestroyed": 0, "structuresDestroyed": 0,
            "destroyedValue": 0, "lostValue": 0, "harvestersDestroyed": 0,
        }
    return row["opponents"][opponent_id]


def structure_completed(room, structure, initial=False, transformed=False):
    state = _state(room)
    if not state or state["finished"]:
        return
    row = state["players"].get(structure["owner"])
    kind = structure["kind"]
    if row is None or row["eliminatedAt"] is not None:
        return
    if not structure.get("_reportCompleted"):
        structure["_reportCompleted"] = True
        if not transformed:
            kind_row(row, kind)["initial" if initial else "produced"] += 1
            if not initial:
                _production(room, row, kind)
    if kind in row["techTimes"] or structure_role(kind) not in KEY_STRUCTURE_ROLES:
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
    cash_flow(room, player_id, "harvest", amount)


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


def damage(room, target, amount, source_owner, hostile, source_kind=None):
    state = _state(room)
    if not state or state["finished"] or amount <= 0 or not hostile:
        return
    owner = target.get("owner")
    rows = state["players"]
    if owner not in rows or source_owner not in rows:
        return  # Neutral guards, friendly fire and system strikes are not PvP.
    if rows[owner]["eliminatedAt"] is not None or rows[source_owner]["eliminatedAt"] is not None:
        return
    if owner == source_owner:
        return
    amount = max(0.0, min(float(amount), float(target.get("hp", 0))))
    if not amount:
        return
    attacker, defender = rows[source_owner], rows[owner]
    attacker["damageDealt"] += amount
    defender["damageTaken"] += amount
    source_stats = kind_row(attacker, source_kind)
    source_stats["damageDealt"] += amount
    source_stats["structureDamage" if target["id"].startswith("s") else "unitDamage"] += amount
    kind_row(defender, target.get("kind"))["damageTaken"] += amount
    opponent_row(attacker, owner)["damageDealt"] += amount
    opponent_row(defender, source_owner)["damageTaken"] += amount
    if attacker["firstCombatAt"] is not None and defender["firstCombatAt"] is not None:
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
    phase_add(room, owner, "lostValue", value)
    phase_add(room, owner, "structuresLost" if is_structure else "unitsLost", 1)
    if self_consumed:
        row["selfConsumedValue"] += value
    attacker = state["players"].get(source_owner) if hostile else None
    if attacker is not None and (source_owner == owner or attacker["eliminatedAt"] is not None):
        attacker = None
    cause = "self" if self_consumed else "enemy" if attacker else "other"
    cause_stats = row["lossCauses"].setdefault(cause, {"units": 0, "structures": 0, "value": 0})
    cause_stats["structures" if is_structure else "units"] += 1
    cause_stats["value"] += value
    if attacker is not None and source_owner != owner:
        attacker["destroyedValue"] += value
        attacker["structuresDestroyed" if is_structure else "unitsDestroyed"] += 1
        source_stats = kind_row(attacker, source_kind)
        source_stats["destroyed"] += 1
        source_stats["destroyedValue"] += value
        pair = opponent_row(attacker, owner)
        pair["structuresDestroyed" if is_structure else "unitsDestroyed"] += 1
        pair["destroyedValue"] += value
        opponent_row(row, source_owner)["lostValue"] += value
        phase_add(room, source_owner, "destroyedValue", value)
        _engagement_loss(room, target, source_owner, value)
    if not is_structure and unit_role(target["kind"]) == "harvester":
        row["harvestersLost"] += 1
        phase_add(room, owner, "harvestersLost", 1)
        row["cargoLost"] += max(0.0, float(target.get("cargo", 0)))
        if attacker is not None:
            opponent_row(attacker, owner)["harvestersDestroyed"] += 1
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
    _observe_cash(room, row)
    row["_lastIncomeAt"] = None
    row["eliminatedAt"] = _time(room)
    row["_cashValue"] = float(room["players"].get(player_id, {}).get("cash", row["_cashValue"]))
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
    phase_add(room, None, None, 0)  # Include silent closing intervals too.
    # One terminal scan, never another per-frame entity walk. Survivors are not
    # inferred from production minus losses (selling/transforming/retreat exist).
    for entity in (*room["game"]["units"], *room["game"]["structures"]):
        row = state["players"].get(entity.get("owner"))
        if row is None or row["eliminatedAt"] is not None or entity.get("hp", 0) <= 0:
            continue
        if entity["id"].startswith("s") and not entity.get("active"):
            continue
        stats = kind_row(row, entity["kind"])
        stats["remaining"] += 1
        definition = UNIT_TYPES.get(entity["kind"], STRUCTURE_TYPES.get(entity["kind"], {}))
        stats["remainingValue"] += int(definition.get("cost", 0))
    winners = set(room["game"].get("winnerIds", []))
    for player_id, row in state["players"].items():
        row["won"] = player_id in winners
        if row["eliminatedAt"] is None:
            _observe_cash(room, row)
            row["_cashValue"] = float(room["players"].get(player_id, {}).get("cash", row["_cashValue"]))
            _close_income_gap(room, player_id)
            row["_lastIncomeAt"] = None
        row["averageCash"] = row["cashSeconds"] / max(0.01, row["cashObservedSeconds"])
        row["closingCash"] = row["_cashValue"]
        row["cashReconciliation"] = (row["openingCash"] + sum(
            CASH_DIRECTIONS[key] * value for key, value in row["cashFlow"].items()) - row["closingCash"])
    for episode in state["_activeEngagements"].values():
        _keep_engagement(state, episode)
    state["_activeEngagements"].clear()
    state["engagements"].sort(key=lambda episode: (-episode["value"], episode["start"]))
    state["duration"] = _time(room)
    state["finished"] = True
    state["public"] = {
        key: deepcopy(state[key]) for key in
        ("version", "matchId", "mapName", "mapId", "duration", "firstCombatAt",
         "samples", "events", "droppedEvents", "sampleInterval",
         "phases", "phaseSeconds", "engagements", "omittedEngagements")
    }
    state["public"]["players"] = [deepcopy({k: v for k, v in row.items() if not k.startswith("_")})
                                   for row in state["players"].values()]
    diagnostics.queue_archive(room, force=True)


def published(room, match_id):
    state = _state(room)
    if room.get("status") != "finished":
        raise ValueError("整局结束后才能查看战报")
    if not state or not state["finished"]:
        raise ValueError("本局未记录战报，请更新服务后开启新对局")
    if not match_id or match_id != state["matchId"]:
        raise ValueError("战报不属于当前对局，请刷新页面")
    return state["public"]
