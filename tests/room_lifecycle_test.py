#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Empty rooms disappear and the Windows launcher owns its process tree."""

from __future__ import print_function

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import server


def human(player_id, last_seen, connections=0):
    return {
        "id": player_id, "name": player_id, "isBot": False,
        "connections": connections, "lastSeen": last_seen,
    }


def room(room_id, players, created_at=100.0, status="lobby"):
    return {
        "id": room_id, "name": room_id, "status": status,
        "hostId": next(iter(players), ""), "players": players,
        "chat": [], "game": None, "createdAt": created_at,
    }


def main():
    original = server.ROOMS.copy()
    server.ROOMS.clear()
    try:
        current = 1000.0
        connected = human("connected", 1.0, connections=1)
        recent = human(
            "recent", current - server.EMPTY_ROOM_GRACE_SECONDS + 0.1)
        stale_lobby = human(
            "stale-lobby", current - server.EMPTY_ROOM_GRACE_SECONDS)
        stale_game = human(
            "stale-game", current - server.EMPTY_ROOM_GRACE_SECONDS - 30)
        bot = {"id": "bot", "name": "bot", "isBot": True,
               "connections": 1, "lastSeen": current}

        server.ROOMS.update({
            "LIVE01": room("LIVE01", {connected["id"]: connected}),
            "GRACE1": room("GRACE1", {recent["id"]: recent}),
            "EMPTY1": room("EMPTY1", {stale_lobby["id"]: stale_lobby}),
            "EMPTY2": room(
                "EMPTY2", {stale_game["id"]: stale_game}, status="playing"),
            "BOT001": room("BOT001", {bot["id"]: bot}),
        })

        removed = set(server.reap_abandoned_rooms(current))
        assert removed == {"EMPTY1", "EMPTY2", "BOT001"}, removed
        assert set(server.ROOMS) == {"LIVE01", "GRACE1"}
        assert server.room_has_connected_human(server.ROOMS["LIVE01"])
        assert not server.room_has_connected_human(server.ROOMS["GRACE1"])

        removed = server.reap_abandoned_rooms(current + 0.2)
        assert removed == ["GRACE1"], removed
        assert [item["id"] for item in server.room_list()] == ["LIVE01"]

        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        with open(os.path.join(root, "launcher", "SteelFrontLauncher.cs"),
                  "r", encoding="utf-8") as handle:
            launcher = handle.read()
        assert "JobObjectLimitKillOnJobClose" in launcher
        assert "AssignProcessToJobObject" in launcher
        assert "ReleaseServerJob()" in launcher
        assert "KillProcessTree(process.Id)" in launcher
        assert "WaitForPortRelease(port, 5000)" in launcher
        with open(os.path.join(root, "server.py"), "r", encoding="utf-8") as handle:
            server_source = handle.read()
        assert "SO_EXCLUSIVEADDRUSE" in server_source

        first_server = server.ThreadedHTTPServer(
            ("127.0.0.1", 0), server.GameHandler)
        try:
            port = first_server.server_address[1]
            try:
                duplicate = server.ThreadedHTTPServer(
                    ("127.0.0.1", port), server.GameHandler)
            except OSError:
                duplicate = None
            if duplicate is not None:
                duplicate.server_close()
                raise AssertionError("a second server bound the same port")
        finally:
            first_server.server_close()
    finally:
        server.ROOMS.clear()
        server.ROOMS.update(original)

    print("room lifecycle ok: 10s reconnect grace, empty reap, launcher tree kill")


if __name__ == "__main__":
    main()
