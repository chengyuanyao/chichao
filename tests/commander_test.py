#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""指挥官模式：方针覆盖微操，内置大师 AI / 外部副官执行。"""

from __future__ import print_function

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import server


def make_room(tag, commander_mode=False, extra=None):
    a = server.create_human("指挥甲", server.COLORS[0])
    b = server.create_human("指挥乙", server.COLORS[1])
    players = {a["id"]: a, b["id"]: b}
    if extra:
        for player in extra:
            players[player["id"]] = player
    room = {
        "id": tag, "name": "commander test", "status": "lobby",
        "hostId": a["id"],
        "players": players,
        "chat": [], "game": None, "createdAt": time.time(),
        "commanderMode": bool(commander_mode),
        "lock": server.threading.RLock(),
    }
    server.start_game(room)
    game = room["game"]
    game["terrainCtx"] = server.FLAT_TERRAIN
    game["botClock"] = 999.0
    game["victoryClock"] = 999.0
    return room, a, b


def give(game, pid, kind, x=900, y=900):
    structure = server.make_structure(kind, pid, x, y, True)
    game["structures"].append(structure)
    return structure


def player_hq(game, pid):
    for structure in game["structures"]:
        if (structure["owner"] == pid and structure["hp"] > 0
                and server.structure_role(structure["kind"]) == "hq"):
            return structure
    return None


def queued_kinds(game, pid):
    kinds = []
    for structure in game["structures"]:
        if structure["owner"] != pid:
            continue
        for item in structure["queue"]:
            kinds.append(item["kind"])
    return kinds


def combat_units(game, pid):
    return [
        unit for unit in game["units"]
        if unit["owner"] == pid and unit["hp"] > 0
        and server.unit_role(unit["kind"]) not in ("harvester", "mcv")
        and unit["kind"] not in server.SUICIDE_KINDS
    ]


def check_mode_off_unchanged():
    print("=== 模式关：快照无方针要求，电脑 bot 仍走原版速推 ===")
    host = server.create_human("房主", server.COLORS[0])
    guest = server.create_human("访客", server.COLORS[1])
    lobby = {
        "id": "CM00", "name": "off", "status": "lobby",
        "hostId": host["id"],
        "players": {host["id"]: host, guest["id"]: guest},
        "chat": [], "game": None, "createdAt": time.time(),
        "commanderMode": False,
    }
    pub = server.public_room(lobby, viewer_id=host["id"])
    assert pub["commanderMode"] is False
    me = [p for p in pub["players"] if p["id"] == host["id"]][0]
    assert me.get("intent") is None
    assert not me.get("bindToken")

    try:
        server.set_commander_mode(lobby, guest, True)
        raise AssertionError("访客不该能开模式")
    except ValueError as exc:
        assert "房主" in str(exc)
    server.set_commander_mode(lobby, host, True)
    assert lobby["commanderMode"] is True
    guest_view = server.public_room(lobby, viewer_id=guest["id"])
    assert guest_view["commanderMode"] is True
    host_view = server.public_room(lobby, viewer_id=host["id"])
    host_pub = [p for p in host_view["players"] if p["id"] == host["id"]][0]
    assert host_pub.get("bindToken")
    guest_pub = [p for p in guest_view["players"] if p["id"] == host["id"]][0]
    assert not guest_pub.get("bindToken"), "绑定令牌不能泄露给别人"

    room, a, b = make_room("CM01", commander_mode=False)
    assert room["game"].get("commanderMode") is False
    view = server.public_game(room["game"], a["id"], full=True)
    assert view["commanderMode"] is False
    a["isBot"] = True
    a["faction"] = "tech"
    a["buildQueue"] = []
    server.tick_bots(room)
    queued = a.get("buildQueue") or []
    assert queued and queued[0]["kind"] == "barracks", queued

    room2, human, foe = make_room("CM01b", commander_mode=False)
    human["isBot"] = False
    human["buildQueue"] = []
    before = list(human.get("buildQueue") or [])
    server.tick_bots(room2)
    assert (human.get("buildQueue") or []) == before, "模式关时不该替人类微操"
    print("  关模式 / 房主开关 / bot 原版: PASS")


def check_intent_generation_and_override():
    print("=== 方针写入 kind+focus，换方针清作战指令，不动矿车 ===")
    room, a, b = make_room("CM02", commander_mode=True)
    game = room["game"]
    assert game.get("commanderMode") is True
    try:
        server.set_commander_intent(room, a, {"kind": "rush"}, role="agent")
        raise AssertionError("副官不该能改方针")
    except ValueError as exc:
        assert "副官" in str(exc)

    first = server.set_commander_intent(room, a, {"kind": "rush"})
    assert first["kind"] == "rush"
    assert first["generation"] == 1
    assert first["setAt"] > 0
    same = server.set_commander_intent(room, a, {"kind": "rush"})
    assert same["generation"] == 1, "相同方针不应加代"

    hq = player_hq(game, b["id"])
    tank = server.make_unit("tank", a["id"], 400, 400)
    truck = server.make_unit("bomb_truck", a["id"], 420, 410)
    harvester = next(
        unit for unit in game["units"]
        if unit["owner"] == a["id"] and server.unit_role(unit["kind"]) == "harvester")
    game["units"].extend([tank, truck])
    server.issue_move(game, a["id"], {tank["id"], truck["id"]}, hq["x"], hq["y"], True)
    server.issue_move(game, a["id"], {harvester["id"]}, harvester["x"] + 80, harvester["y"])
    harvester_dest = (harvester["destX"], harvester["destY"], harvester.get("order"))
    assert tank.get("order") in ("move", "attackMove")
    assert tank.get("destX") is not None

    second = server.set_commander_intent(
        room, a, {"kind": "defend", "x": hq["x"], "y": hq["y"]})
    assert second["kind"] == "defend"
    assert second["generation"] == 2
    assert second["focus"]["x"] == hq["x"] or abs(second["focus"]["x"] - hq["x"]) < 1
    assert tank.get("order") == "guard"
    assert tank.get("destX") is None
    assert tank.get("targetId") is None
    assert tank.get("_path") is None
    assert truck.get("order") == "guard"
    assert (harvester["destX"], harvester["destY"], harvester.get("order")) == harvester_dest

    third = server.set_commander_intent(room, a, {"x": 1200, "y": 800})
    assert third["kind"] == "defend"
    assert third["generation"] == 3
    pub = server.public_player(room, a, a["id"])
    assert pub["intent"]["generation"] == 3
    assert pub["intent"]["kind"] == "defend"
    print("  代次 / 覆盖微操 / 矿车保留: PASS")


def check_bot_intents_distinct():
    print("=== 内置执行层：速推 / 发育 / 防守 / 偷家 去向与建造不同 ===")
    room, a, b = make_room("CM03", commander_mode=True)
    game = room["game"]
    a["isBot"] = False
    a["faction"] = "tech"
    a["cash"] = 99999
    a["buildQueue"] = [{"id": "busy", "kind": "power",
                        "remaining": 4.0, "total": 8.0, "ready": False}]
    give(game, a["id"], "factory", 1400, 900)
    enemy_hq = player_hq(game, b["id"])
    own_hq = player_hq(game, a["id"])

    server.set_commander_intent(room, a, {"kind": "rush"})
    server.tick_bots(room)
    produced = queued_kinds(game, a["id"])
    assert "bomb_truck" in produced, produced
    print("  速推排自爆: PASS")

    room, a, b = make_room("CM04", commander_mode=True)
    game = room["game"]
    a["faction"] = "tech"
    a["cash"] = 99999
    a["buildQueue"] = []
    give(game, a["id"], "barracks")
    give(game, a["id"], "factory", 1400, 900)
    tank = server.make_unit("tank", a["id"], own_origin_x(game, a), own_origin_y(game, a))
    game["units"].append(tank)
    server.set_commander_intent(room, a, {"kind": "eco"})
    server.tick_bots(room)
    produced = queued_kinds(game, a["id"])
    queued = a.get("buildQueue") or []
    assert "bomb_truck" not in produced, produced
    assert queued and queued[0]["kind"] in ("refinery", "power", "repair"), queued
    own_hq = player_hq(game, a["id"])
    assert tank.get("order") in ("move", "guard"), tank.get("order")
    if tank.get("destX") is not None:
        dist = hypot(tank["destX"] - own_hq["x"], tank["destY"] - own_hq["y"])
        assert dist < 400, (tank["destX"], tank["destY"], own_hq)
    print("  发育不自杀推、补经济、军队回家: PASS")

    room, a, b = make_room("CM05", commander_mode=True)
    game = room["game"]
    a["faction"] = "tech"
    a["cash"] = server.STRUCTURE_TYPES["turret"]["cost"]
    a["buildQueue"] = []
    give(game, a["id"], "barracks")
    give(game, a["id"], "factory")
    own_hq = player_hq(game, a["id"])
    focus_x, focus_y = own_hq["x"] + 160, own_hq["y"] + 40
    tank = server.make_unit("tank", a["id"], own_hq["x"] + 40, own_hq["y"])
    game["units"].append(tank)
    server.set_commander_intent(room, a, {"kind": "defend", "x": focus_x, "y": focus_y})
    server.tick_bots(room)
    queued = a.get("buildQueue") or []
    assert queued and queued[0]["kind"] == "turret", queued
    assert tank.get("destX") is not None
    dist = hypot(tank["destX"] - focus_x, tank["destY"] - focus_y)
    assert dist < 80, (tank["destX"], tank["destY"], focus_x, focus_y)
    print("  防守补塔、军队去焦点: PASS")

    room, a, b = make_room("CM06", commander_mode=True)
    game = room["game"]
    a["faction"] = "tech"
    a["cash"] = 100
    a["buildQueue"] = [{"id": "busy", "kind": "power",
                        "remaining": 4.0, "total": 8.0, "ready": False}]
    enemy_hq = player_hq(game, b["id"])
    decoy = server.make_unit("rifle", b["id"], 200, 200)
    decoy["hp"] = 200
    game["units"].append(decoy)
    trucks = [
        server.make_unit("bomb_truck", a["id"], 220, 200),
        server.make_unit("bomb_truck", a["id"], 240, 210),
    ]
    tank = server.make_unit("tank", a["id"], 260, 220)
    game["units"].extend(trucks + [tank])
    server.set_commander_intent(room, a, {"kind": "snipe"})
    picked = server.commander_snipe_target(game, a)
    assert picked is not None
    assert picked["kind"] not in server.UNIT_TYPES
    server.tick_bots(room)
    for truck in trucks:
        assert truck["order"] == "attack", truck["order"]
        assert truck["targetId"] != decoy["id"]
        target = server.find_entity(game, truck["targetId"])
        assert target is not None
        assert target["kind"] in server.STRUCTURE_TYPES
    assert tank.get("targetId") != decoy["id"]
    if tank.get("targetId"):
        target = server.find_entity(game, tank["targetId"])
        assert server.structure_role(target["kind"]) == "hq" or target["id"] == enemy_hq["id"]
    print("  偷家打总部/建筑，不追野战步枪: PASS")


def check_agent_bind_and_override():
    print("=== 副官：不能改方针，能微操；新方针清副官指令；断开交回内置 AI ===")
    room, a, b = make_room("CM07", commander_mode=True)
    game = room["game"]
    token = server.ensure_bind_token(a)
    player, agent_token = server.bind_executor(room, token)
    assert player is a
    assert server.executor_is_bound(a)
    assert server.session_role(a, agent_token) == "agent"
    assert not server.should_tick_master_bot(room, a)

    try:
        server.set_commander_intent(room, a, {"kind": "rush"}, role="agent")
        raise AssertionError("副官不能改方针")
    except ValueError as exc:
        assert "副官" in str(exc)

    tank = server.make_unit("tank", a["id"], 500, 500)
    game["units"].append(tank)
    server.handle_game_command(room, a, {
        "command": "move",
        "unitIds": [tank["id"]],
        "x": 1800,
        "y": 1600,
    }, role="agent")
    assert tank.get("order") == "move"
    assert tank.get("destX") is not None

    try:
        server.handle_game_command(room, a, {"command": "setIntent", "kind": "eco"},
                                   role="agent")
        raise AssertionError("副官不能用 setIntent")
    except ValueError as exc:
        assert "副官" in str(exc)

    a["eliminated"] = True
    try:
        server.handle_game_command(room, a, {
            "command": "move", "unitIds": [tank["id"]], "x": 100, "y": 100,
        }, role="agent")
        raise AssertionError("淘汰后副官不该还能动")
    except ValueError as exc:
        assert "击败" in str(exc)
    a["eliminated"] = False

    server.set_commander_intent(room, a, {"kind": "defend"})
    assert tank.get("order") == "guard"
    assert tank.get("destX") is None

    a["faction"] = "tech"
    a["cash"] = 99999
    a["buildQueue"] = [{"id": "busy", "kind": "power",
                        "remaining": 4.0, "total": 8.0, "ready": False}]
    give(game, a["id"], "factory", 1400, 900)
    server.set_commander_intent(room, a, {"kind": "rush"})
    before = queued_kinds(game, a["id"])
    server.tick_bots(room)
    after = queued_kinds(game, a["id"])
    assert after == before, "绑定副官时内置 AI 不该抢微操"

    server.unbind_executor(a)
    assert not server.executor_is_bound(a)
    assert server.should_tick_master_bot(room, a)
    server.tick_bots(room)
    produced = queued_kinds(game, a["id"])
    assert "bomb_truck" in produced, produced
    print("  副官权限 / 覆盖 / 断开交回: PASS")


def check_join_agent_requires_mode():
    print("=== 绑定令牌：模式关拒绝，淘汰席拒绝 ===")
    room, a, b = make_room("CM08", commander_mode=False)
    try:
        server.bind_executor(room, server.ensure_bind_token(a))
        raise AssertionError("模式关不该绑定")
    except ValueError as exc:
        assert "指挥官" in str(exc)
    room["commanderMode"] = True
    room["game"]["commanderMode"] = True
    a["eliminated"] = True
    try:
        server.bind_executor(room, server.ensure_bind_token(a))
        raise AssertionError("淘汰席不该绑定")
    except ValueError as exc:
        assert "击败" in str(exc)
    print("  绑定门禁: PASS")


def own_origin_x(game, player):
    return server.bot_own_origin(game, player["id"])[0]


def own_origin_y(game, player):
    return server.bot_own_origin(game, player["id"])[1]


def hypot(dx, dy):
    return (dx * dx + dy * dy) ** 0.5


def main():
    assert server.COMMANDER_MODE == "commander_mode"
    assert server.COMMANDER_INTENT_KINDS == ("rush", "eco", "defend", "snipe")
    check_mode_off_unchanged()
    check_intent_generation_and_override()
    check_bot_intents_distinct()
    check_agent_bind_and_override()
    check_join_agent_requires_mode()
    print("\n指挥官模式测试全部通过")


if __name__ == "__main__":
    main()
