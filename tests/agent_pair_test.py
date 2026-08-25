#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""AI co-pilot pairing codes are browser-approved, expiring and one-use."""

from __future__ import print_function

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import server


def make_room():
    player = server.create_human("配对玩家", server.COLORS[0])
    room = {
        "id": "PAIR01", "name": "配对测试", "status": "lobby",
        "hostId": player["id"], "players": {player["id"]: player},
        "chat": [], "game": None, "createdAt": server.now(),
        "selectedMap": server.DEFAULT_MAP,
        "lock": server.threading.RLock(),
    }
    return room, player


def check_finished_stops_server_agents():
    """headless 副官打完不会自己退出，分出胜负就得由服务器收掉。

    它每 0.7 秒的心跳会一直刷新 lastSeen，房间因此永远达不到过期阈值；
    不在这里收，进程和房间都回收不了。
    """
    room, player = make_room()
    bot = server.create_bot(room)
    room["players"][bot["id"]] = bot
    server.start_game(room)
    key = server._server_agent_key(room["id"], player["id"])
    server.SERVER_AGENT_PENDING.add(key)
    bot["eliminated"] = True
    server.check_elimination_and_victory(room, force=True)
    assert room["status"] == "finished"
    assert key not in server.SERVER_AGENT_PENDING, "对局结束必须收掉服务器副官"


def main():
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    with open(os.path.join(root, "public", "app.js"), "r", encoding="utf-8") as handle:
        app = handle.read()

    # Escape still opens the tactical menu, but AI connection now lives directly
    # in the deputy panel and must not depend on that keyboard route.
    assert "function toggleGameMenu()" in app
    assert "if (event.code === 'Escape' && currentScreen === 'game')" in app
    assert "toggleGameMenu();" in app
    assert "$('#gameMenuBtn').addEventListener('click', openGameMenu);" in app
    assert "agentUserMessage" in app
    assert "startServerAgent" in app
    assert "stopServerAgent" in app
    # 面板占着聊天框的位置，Enter 必须先收面板，否则 focus() 打在
    # display:none 的输入框上，按键会继续触发单位热键。
    assert "if (!agentPanel.classList.contains('hidden')) {" in app
    # 静默帧不带对话正文，客户端要能靠本地副本重绘。
    assert "agentMessageCache" in app

    with open(os.path.join(root, "public", "index.html"), "r", encoding="utf-8") as handle:
        index = handle.read()
    assert 'id="agentPanel"' in index
    assert 'id="agentMessages"' in index
    assert 'id="agentInput"' in index
    panel = index[index.index('id="agentPanel"'):index.index('</section>', index.index('id="agentPanel"'))]
    assert 'id="startServerAgentBtn"' in panel
    assert 'id="pairAgentBtn"' in panel
    assert 'id="stopAgentBtn"' in panel

    room, player = make_room()
    code = server.issue_agent_pair(player)
    assert len(code) == 8 and code.isalnum()
    assert server.ensure_agent_channel(player)["status"] == "pairing"
    assert server.redeem_agent_pair(room, code.lower()) is player
    channel = server.public_agent_channel(player)
    assert channel["connected"] is True
    assert channel["status"] == "connecting"
    assert channel["messages"][-1]["role"] == "system"
    assert server.redeem_agent_pair(room, code) is None, "配对码必须只能用一次"

    server.append_agent_message(player, "user", "只应由本人看到")
    assert server.public_agent_channel(player)["messages"][-1]["message"] == "只应由本人看到"
    server.append_agent_message(player, "assistant", "第一行\n第二行")
    assert server.public_agent_channel(player)["messages"][-1]["message"] == "第一行\n第二行"
    assert "agent" in server.public_room(room, viewer_id=player["id"])
    assert "agent" not in server.public_room(room), "副官对话不得进入公开房间快照"

    # 对话正文可以轻松涨到一帧游戏数据的好几倍，且只在有新消息时才变化。
    # 静默帧必须能省掉正文，只留 revision 让客户端判断要不要重绘。
    quiet = server.public_room(room, viewer_id=player["id"],
                               agent_messages=False)["agent"]
    assert "messages" not in quiet
    assert quiet["revision"] == server.ensure_agent_channel(player)["revision"]

    # 停止副官：清空邮箱并撤掉服务器托管标记，之后才能重新启动。
    server.ensure_agent_channel(player)["serverManaged"] = True
    assert server.public_agent_channel(player)["serverManaged"] is True
    assert server.mark_agent_offline(player) is True, "停止前应处于连接状态"
    stopped = server.public_agent_channel(player)
    assert stopped["connected"] is False and stopped["status"] == "offline"
    assert stopped["serverManaged"] is False
    assert server.ensure_agent_channel(player)["inputs"] == [], "残留指令不得转交下一个副官"
    assert server.mark_agent_offline(player) is False

    # 本地配对不算服务器托管，否则「停止副官」会去杀一个不存在的进程。
    server.ensure_agent_channel(player)["serverManaged"] = True
    server.issue_agent_pair(player)
    assert server.ensure_agent_channel(player)["serverManaged"] is False
    player.pop("agentPair", None)

    # 进程创建在 room_lock 之外进行，这段窗口里的停止请求必须能取消掉它。
    key = server._server_agent_key(room["id"], player["id"])
    server.SERVER_AGENT_PENDING.add(key)
    server.stop_server_agents_for_room(room["id"])
    assert key not in server.SERVER_AGENT_PENDING, "在途的服务器副官必须可取消"

    check_finished_stops_server_agents()

    expired = server.issue_agent_pair(player)
    player["agentPair"]["expires"] = server.now() - 1
    assert server.redeem_agent_pair(room, expired) is None
    assert "agentPair" not in player

    other = server.issue_agent_pair(player)
    assert server.redeem_agent_pair(room, other + "X") is None
    assert server.redeem_agent_pair(room, other) is player

    # 配对码只有 8 位十六进制。没有限流的话，局域网里的人可以在这 2 分钟窗口
    # 里慢慢刷，所以连续猜错要进冷却。
    assert server.agent_pair_cooldown(room) == 0
    for _ in range(server.AGENT_PAIR_MAX_FAILS):
        assert server.redeem_agent_pair(room, "DEADBEEF") is None
        server.note_agent_pair_failure(room)
    assert server.agent_pair_cooldown(room) > 0, "连续猜错必须进冷却"

    # 冷却是给猜错的人设的：正确的码兑换成功后要立刻解除，
    # 不然玩家自己误输一次也会被关在门外一分钟。
    room["agentPairGate"]["until"] = server.now() - 1
    assert server.agent_pair_cooldown(room) == 0
    fresh = server.issue_agent_pair(player)
    server.note_agent_pair_failure(room)
    assert server.redeem_agent_pair(room, fresh) is player
    assert "agentPairGate" not in room
    print("agent pair tests passed")


if __name__ == "__main__":
    main()
