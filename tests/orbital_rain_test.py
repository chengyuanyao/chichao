#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""可选模式「轨道天降」：系统 5 倍轨道打击，玩家超武仍是 1 倍。"""

from __future__ import print_function

import os
import random
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import server


def make_room(tag, orbital_rain=False):
    random.seed(hash(tag) & 0xFFFFFFFF)
    alpha = server.create_human("天降甲", server.COLORS[0])
    beta = server.create_human("天降乙", server.COLORS[1])
    room = {
        "id": tag, "name": "orbital rain test", "status": "lobby",
        "hostId": alpha["id"],
        "players": {alpha["id"]: alpha, beta["id"]: beta},
        "chat": [], "game": None, "createdAt": time.time(),
        "orbitalRain": bool(orbital_rain),
    }
    server.start_game(room)
    return room, alpha, beta


def tick_for(room, seconds, step=0.05):
    for _ in range(int(round(seconds / step))):
        server.tick_game(room, step)


def system_strikes(game):
    return [s for s in game.get("pendingStrikes") or [] if s.get("system")]


def player_strikes(game):
    return [s for s in game.get("pendingStrikes") or [] if not s.get("system")]


def fire_one_impact(room, x, y, splash, owner=None, system=False):
    game = room["game"]
    game["elapsed"] = max(game.get("elapsed", 0.0), 10.0)
    game["pendingStrikes"] = [{
        "owner": owner, "x": x, "y": y,
        "radius": 180.0, "splash": splash,
        "warnUntil": game["elapsed"], "fireUntil": game["elapsed"],
        "impacts": [{"x": x, "y": y, "fireAt": game["elapsed"]}],
        "fired": 0, "system": system,
    }]
    server.tick_pending_strikes(room, 0.05)


def main():
    print("=== Test 1: 模式关，模拟一分钟不出现系统打击；玩家超武仍是 180/60 ===")
    assert server.STRIKE_RADIUS == 180.0
    assert server.STRIKE_SPLASH == 60.0
    assert server.ORBITAL_RAIN_RADIUS == 900.0
    assert server.ORBITAL_RAIN_SPLASH == 300.0
    room, alpha, beta = make_room("RAIN00", orbital_rain=False)
    game = room["game"]
    assert game.get("orbitalRain") is False
    assert game.get("nextOrbitalRainAt") is None
    lobby = server.public_room(room, viewer_id=alpha["id"])
    assert lobby["orbitalRain"] is False
    seen_system = 0
    for _ in range(int(60.0 / 0.05)):
        server.tick_game(room, 0.05)
        seen_system += len(system_strikes(game))
    assert seen_system == 0, seen_system
    alpha["strikeCharges"] = 1
    server.issue_strike(room, alpha["id"], 2400, 1800)
    assert alpha["strikeCharges"] == 0
    player = player_strikes(game)
    assert len(player) == 1, player
    assert player[0]["radius"] == server.STRIKE_RADIUS
    assert player[0]["splash"] == server.STRIKE_SPLASH
    assert player[0].get("system") is False
    view = server.public_game(game, alpha["id"], full=True)
    assert view["orbitalRain"] is False
    pub = view["strikes"][0]
    assert pub["radius"] == 180.0
    assert pub["splash"] == 60.0
    print("  关模式一分钟无系统弹 / 玩家 180/60: PASS")

    print("\n=== Test 2: 大厅开关写入房间，开战带进 game，旁观者能看见 ===")
    host = server.create_human("房主", server.COLORS[0])
    guest = server.create_human("访客", server.COLORS[1])
    lobby_room = {
        "id": "RAIN01", "name": "lobby rain", "status": "lobby",
        "hostId": host["id"],
        "players": {host["id"]: host, guest["id"]: guest},
        "chat": [], "game": None, "createdAt": time.time(),
        "orbitalRain": False,
    }
    try:
        server.set_orbital_rain(lobby_room, guest, True)
        raise AssertionError("访客不该能开模式")
    except ValueError as exc:
        assert "房主" in str(exc)
    server.set_orbital_rain(lobby_room, host, True)
    assert lobby_room["orbitalRain"] is True
    guest_view = server.public_room(lobby_room, viewer_id=guest["id"])
    assert guest_view["orbitalRain"] is True
    server.start_game(lobby_room)
    assert lobby_room["game"]["orbitalRain"] is True
    first_at = lobby_room["game"]["nextOrbitalRainAt"]
    assert 45.0 <= first_at <= 60.0, first_at
    playing = server.public_room(lobby_room, viewer_id=guest["id"], full=True)
    assert playing["orbitalRain"] is True
    assert playing["game"]["orbitalRain"] is True
    try:
        server.set_orbital_rain(lobby_room, host, False)
        raise AssertionError("开战后不该还能改")
    except ValueError as exc:
        assert "开始" in str(exc)
    print("  大厅开关 / 旁观可见 / 开战锁定: PASS")

    print("\n=== Test 3: 模式开，系统弹 900/300，随机点在界内，不耗玩家充能 ===")
    room, alpha, beta = make_room("RAIN02", orbital_rain=True)
    game = room["game"]
    alpha["strikeCharges"] = 1
    beta["strikeCharges"] = 0
    game["nextOrbitalRainAt"] = game["elapsed"]
    server.tick_orbital_rain(room)
    rains = system_strikes(game)
    assert len(rains) == 1, rains
    strike = rains[0]
    assert strike["radius"] == 900.0
    assert strike["splash"] == 300.0
    assert strike["owner"] is None
    assert strike.get("system") is True
    mw, mh = game["map"]["width"], game["map"]["height"]
    assert 0 <= strike["x"] <= mw
    assert 0 <= strike["y"] <= mh
    assert not server.game_terrain(game).blocked(strike["x"], strike["y"])
    assert alpha["strikeCharges"] == 1
    assert beta["strikeCharges"] == 0
    pub = [s for s in server.public_game(game, alpha["id"])["strikes"] if s.get("system")]
    assert pub and pub[0]["radius"] == 900.0 and pub[0]["splash"] == 300.0
    # 同时最多一发系统弹
    assert server.issue_orbital_rain(room) is None
    assert len(system_strikes(game)) == 1
    # 手动超武仍是 1 倍
    server.issue_strike(room, alpha["id"], 2100, 1600)
    manual = player_strikes(game)
    assert len(manual) == 1
    assert manual[0]["radius"] == 180.0
    assert manual[0]["splash"] == 60.0
    assert server.STRIKE_RADIUS == 180.0
    assert server.STRIKE_SPLASH == 60.0
    print("  系统 900/300 / 不耗充能 / 玩家仍 1 倍: PASS")

    print("\n=== Test 4: 单发仍走 super + 友伤；溅射跟这发走 ===")
    room, alpha, beta = make_room("RAIN03", orbital_rain=True)
    game = room["game"]
    ally = server.make_unit("rifle", alpha["id"], 4000, 3000)
    foe = server.make_unit("rifle", beta["id"], 4000, 3000)
    ally["hp"] = foe["hp"] = 500
    game["units"].extend([ally, foe])
    fire_one_impact(room, 4000, 3000, 300.0, owner=None, system=True)
    expect = server.STRIKE_DAMAGE * server.DAMAGE_MULTIPLIER["super"]["infantry"]
    assert abs((500 - ally["hp"]) - expect) < 0.1, (ally["hp"], expect)
    assert abs((500 - foe["hp"]) - expect) < 0.1, (foe["hp"], expect)

    far = server.make_unit("rifle", beta["id"], 4080, 3000)
    far["hp"] = 500
    game["units"].append(far)
    fire_one_impact(room, 4000, 3000, server.STRIKE_SPLASH, owner=alpha["id"], system=False)
    assert abs(far["hp"] - 500) < 0.1, far["hp"]
    fire_one_impact(room, 4000, 3000, server.ORBITAL_RAIN_SPLASH, owner=None, system=True)
    assert far["hp"] < 500
    assert abs((500 - far["hp"]) - expect) < 0.1, far["hp"]
    print("  super×友伤 / 玩家溅射 60 打不到 80 外: PASS")

    print("\n=== Test 5: 节拍与大厅文案 ===")
    room, alpha, beta = make_room("RAIN04", orbital_rain=True)
    game = room["game"]
    assert 45.0 <= game["nextOrbitalRainAt"] <= 60.0
    game["elapsed"] = 12.0
    game["nextOrbitalRainAt"] = 12.0
    server.tick_orbital_rain(room)
    assert system_strikes(game)
    nxt = game["nextOrbitalRainAt"]
    assert 12.0 + 40.0 <= nxt <= 12.0 + 55.0, nxt
    index = open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                              "public", "index.html"), "r", encoding="utf-8").read()
    assert "轨道天降" in index
    assert "随机轨道打击，范围×5，默认关" in index
    print("  首发 45–60 / 间隔 40–55 / 大厅标签: PASS")

    print("\n=== 轨道天降测试全部通过 ===")


if __name__ == "__main__":
    main()
