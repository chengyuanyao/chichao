#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Orders named in a command must not clear dest/path on other units.

Selection is a client-side control set. A later move/stop/attackMove that
only lists group B has to leave group A's march intact.
"""

from __future__ import print_function

import os
import random
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import server


def make_room():
    random.seed(20260821)
    alpha = server.create_human("隔离甲", server.COLORS[0])
    beta = server.create_human("隔离乙", server.COLORS[1])
    room = {
        "id": "ISO001", "name": "指令隔离", "status": "lobby",
        "hostId": alpha["id"],
        "players": {alpha["id"]: alpha, beta["id"]: beta},
        "chat": [], "game": None, "createdAt": time.time(),
    }
    server.start_game(room)
    game = room["game"]
    game["units"] = []
    game["projectiles"] = []
    game["effects"] = []
    game["victoryClock"] = 999.0
    return room, alpha, beta


def dest_of(unit):
    return (unit.get("order"), unit.get("destX"), unit.get("destY"),
            unit.get("_path"), unit.get("_pathDest"))


def main():
    room, alpha, _beta = make_room()
    game = room["game"]

    group_a = []
    group_b = []
    for index in range(3):
        walker = server.make_unit("tank", alpha["id"], 800 + index * 40, 900)
        group_a.append(walker)
        other = server.make_unit("scout", alpha["id"], 800 + index * 40, 1100)
        group_b.append(other)
    game["units"].extend(group_a + group_b)

    server.handle_game_command(room, alpha, {
        "command": "move",
        "unitIds": [unit["id"] for unit in group_a],
        "x": 2200, "y": 900,
    })
    before_a = [dest_of(unit) for unit in group_a]
    assert all(unit["order"] == "move" and unit["destX"] is not None
               for unit in group_a)
    assert all(unit.get("_pathDest") is None or unit["_path"] is not None
               or unit.get("_pathUnavailable")
               for unit in group_a)

    # A later command that only names B must not rewrite A's dest/path/order.
    server.handle_game_command(room, alpha, {
        "command": "move",
        "unitIds": [unit["id"] for unit in group_b],
        "x": 400, "y": 1100,
    })
    assert [dest_of(unit) for unit in group_a] == before_a
    assert all(unit["order"] == "move" and unit["destX"] is not None
               for unit in group_b)

    server.handle_game_command(room, alpha, {
        "command": "stop",
        "unitIds": [unit["id"] for unit in group_b],
    })
    assert [dest_of(unit) for unit in group_a] == before_a
    assert all(unit["order"] == "guard" and unit["destX"] is None
               for unit in group_b)

    server.handle_game_command(room, alpha, {
        "command": "attackMove",
        "unitIds": [unit["id"] for unit in group_b],
        "x": 500, "y": 1300,
    })
    assert [dest_of(unit) for unit in group_a] == before_a
    assert all(unit["order"] == "attackMove" for unit in group_b)

    # Missing or empty unitIds is a no-op, never "every unit I own".
    server.handle_game_command(room, alpha, {"command": "stop"})
    server.handle_game_command(room, alpha, {"command": "stop", "unitIds": []})
    server.handle_game_command(room, alpha, {
        "command": "move", "x": 100, "y": 100,
    })
    assert [dest_of(unit) for unit in group_a] == before_a
    assert all(unit["order"] == "attackMove" and unit["destX"] is not None
               for unit in group_b)

    print("order isolation ok: later commands that name B leave A's dest/path")


if __name__ == "__main__":
    main()
