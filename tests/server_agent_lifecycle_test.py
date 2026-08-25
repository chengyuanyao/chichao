#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""服务器托管的 AI 副官必须能被收掉。

headless 的 rts-agent 打完一局不会自己退出，它每 0.7 秒的心跳还会不停刷新
玩家的 lastSeen，房间因此永远达不到过期阈值。所以「启动」之外必须有一条同样
可靠的「停止」路径，且进程创建不能压在 room_lock 里。
"""

from __future__ import print_function

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import server


class FakeProcess(object):
    """够用的 Popen 替身：只需要 poll / terminate。"""

    def __init__(self):
        self.terminated = False
        self._alive = True

    def poll(self):
        return None if self._alive else 0

    def terminate(self):
        self.terminated = True
        self._alive = False


SPAWNED = []


def fake_popen(command, **kwargs):
    process = FakeProcess()
    SPAWNED.append(process)
    return process


def boom_popen(command, **kwargs):
    raise OSError("No such file")


def make_room():
    player = server.create_human("副官玩家", server.COLORS[0])
    room = {
        "id": "LIFE01", "name": "副官生命周期", "status": "playing",
        "hostId": player["id"], "players": {player["id"]: player},
        "chat": [], "game": None, "createdAt": server.now(),
        "selectedMap": server.DEFAULT_MAP,
        "lock": server.threading.RLock(),
    }
    return room, player


def main():
    # 让用例与这台机器上是否真的装了 rts-agent 无关。
    server.RTS_AGENT_DIR = os.path.join(os.sep, "tmp", "fake-agent")
    server.RTS_AGENT_EXECUTABLE = os.path.join(server.RTS_AGENT_DIR, "python")
    server.subprocess.Popen = fake_popen

    room, player = make_room()
    request = server.prepare_server_agent(room, player)
    key = request["key"]
    # 占位先落，进程留到锁外拉起：fork/exec 在 Windows 上动辄上百毫秒，
    # 压在 room_lock 里会直接卡住这个房间 20Hz 的模拟。
    assert key in server.SERVER_AGENT_PENDING
    assert key not in server.SERVER_AGENT_PROCESSES
    assert "--headless" in request["command"] and "--full-control" in request["command"]
    assert server.ensure_agent_channel(player)["serverManaged"] is True
    assert server.launch_server_agent(request) == ""
    assert key in server.SERVER_AGENT_PROCESSES and key not in server.SERVER_AGENT_PENDING

    message = ""
    try:
        server.prepare_server_agent(room, player)
    except ValueError as exc:
        message = str(exc)
    assert "已经在运行" in message, message

    # 停掉之后必须能重新启动，否则副官卡死就再也收不回来了。
    server.stop_server_agent(room["id"], player["id"])
    assert SPAWNED[0].terminated is True
    assert key not in server.SERVER_AGENT_PROCESSES
    server.mark_agent_offline(player)
    assert server.launch_server_agent(server.prepare_server_agent(room, player)) == ""

    # 拉起进程的那段窗口里玩家点了停止：进程一落地就得收掉，不能变成孤儿。
    server.stop_server_agent(room["id"], player["id"])
    server.mark_agent_offline(player)
    pending = server.prepare_server_agent(room, player)
    server.stop_server_agent(room["id"], player["id"])
    error = server.launch_server_agent(pending)
    assert "取消" in error, error
    assert SPAWNED[-1].terminated is True, "被取消的进程必须立刻收掉"
    assert key not in server.SERVER_AGENT_PROCESSES, "取消的进程不得登记"

    # 起不来（venv 坏了、路径写错）要报错，且不能留下挡住重试的占位。
    server.subprocess.Popen = boom_popen
    server.mark_agent_offline(player)
    error = server.launch_server_agent(server.prepare_server_agent(room, player))
    assert "启动失败" in error, error
    assert key not in server.SERVER_AGENT_PENDING
    assert key not in server.SERVER_AGENT_PROCESSES

    # 并发上限要把在途的占位一起算进去，否则同时点几下就能超发。
    server.subprocess.Popen = fake_popen
    server.MAX_SERVER_AGENTS = 1
    server.mark_agent_offline(player)
    server.prepare_server_agent(room, player)
    other = server.create_human("另一位", server.COLORS[1])
    room["players"][other["id"]] = other
    message = ""
    try:
        server.prepare_server_agent(room, other)
    except ValueError as exc:
        message = str(exc)
    assert "上限" in message, message

    # 房间没了就把这一屋子副官全收掉，含还没落地的。
    server.stop_server_agents_for_room(room["id"])
    assert key not in server.SERVER_AGENT_PENDING
    assert not [k for k in server.SERVER_AGENT_PROCESSES if k.startswith(room["id"] + ":")]
    print("server agent lifecycle tests passed")


if __name__ == "__main__":
    main()
