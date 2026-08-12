#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Small end-to-end smoke test for a running Steel Front server."""

from __future__ import print_function

import json
import os
import sys
import time
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import server


BASE = (sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:18081").rstrip("/")


def call(path, payload=None, expected_status=200):
    body = None
    headers = {}
    method = "GET"
    if payload is not None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json"
        method = "POST"
    request = Request(BASE + path, data=body, headers=headers, method=method)
    try:
        with urlopen(request, timeout=5) as response:
            status = response.getcode()
            data = json.loads(response.read().decode("utf-8"))
    except HTTPError as error:
        status = error.code
        data = json.loads(error.read().decode("utf-8"))
    assert status == expected_status, (path, status, data)
    return data


def fetch_static(path):
    request = Request(BASE + path, method="GET")
    with urlopen(request, timeout=5) as response:
        return response.getcode(), response.headers.get_content_type(), response.read()


def action(session, name, payload=None, expected_status=200):
    return call("/api/action", {
        "roomId": session["roomId"],
        "playerId": session["playerId"],
        "token": session["token"],
        "action": name,
        "payload": payload or {},
    }, expected_status)


def state(session):
    query = urlencode(session)
    return call("/api/state?" + query)["room"]


def main():
    health = call("/api/health")
    assert health["ok"] is True

    terrain_status, terrain_type, terrain = fetch_static("/terrain-ground.png")
    assert terrain_status == 200
    assert terrain_type == "image/png"
    assert terrain.startswith(b"\x89PNG\r\n\x1a\n") and len(terrain) > 500000
    style_status, style_type, stylesheet = fetch_static("/styles.css")
    assert style_status == 200 and style_type == "text/css"
    assert b"Soviet Steel v3" in stylesheet
    assert b"#hudCanvas" in stylesheet, "3D 叠加层样式缺失"
    script_status, script_type, script = fetch_static("/app.js")
    assert script_status == 200 and "javascript" in script_type
    assert b"issueRepairCommand" in script and b"terrain-ground.png" in script
    assert b"render3d.js" in script, "app.js 应当引入 3D 渲染层"

    # 3D 渲染层与内置的 three.js 必须能直出（局域网客户端不联网）
    r3d_status, r3d_type, r3d = fetch_static("/render3d.js")
    assert r3d_status == 200 and "javascript" in r3d_type
    assert b"InstancedMesh" in r3d
    # 后处理链（辉光/暗角）也必须能直出
    fx_status, fx_type, fx = fetch_static("/postfx.js")
    assert fx_status == 200 and "javascript" in fx_type
    assert b"colorspace_fragment" in fx, "合成 pass 必须自己做色彩空间转换"
    assert b"__" not in stylesheet[:200]
    for vendor in ("/vendor/three.module.min.js", "/vendor/three.core.min.js"):
        v_status, v_type, payload = fetch_static(vendor)
        assert v_status == 200, vendor
        assert "javascript" in v_type, (vendor, v_type)
        assert len(payload) > 100000, vendor

    alpha_data = call("/api/create", {
        "playerName": "联调甲",
        "roomName": "自动化联调战场",
    }, 201)
    alpha = alpha_data["session"]
    room_id = alpha["roomId"]

    beta_data = call("/api/join", {
        "playerName": "联调乙",
        "roomId": room_id,
    })
    beta = beta_data["session"]

    action(alpha, "addBot")
    action(beta, "ready", {"ready": True})
    started = action(alpha, "start")["room"]
    assert started["status"] == "playing"
    assert len(started["players"]) == 3
    assert len(started["game"]["structures"]) == 3
    assert len(started["game"]["units"]) == 5
    assert started["game"]["map"]["width"] == server.MAPS[server.DEFAULT_MAP]["width"]
    assert started["game"]["map"]["height"] == server.MAPS[server.DEFAULT_MAP]["height"]
    assert "seed" in started["game"]["map"]
    # REST 拉取始终是完整帧：静态数据（地形/矿脉布局/视距表）都在
    assert started["game"]["full"] is True
    assert not started["game"]["terrain"]["rivers"]
    assert not started["game"]["terrain"]["bridges"]
    assert started["game"]["terrain"]["mountains"]
    assert started["game"]["resources"]
    assert started["game"]["sight"]["units"]["rifle"] > 0
    assert started["game"]["sight"]["structures"]["hq"] > 0
    # 迷雾由客户端从视距表推导，服务端不再逐帧重发一份视野列表
    assert "vision" not in started["game"]
    assert started["game"]["ore"], "每帧应携带矿脉余量"

    # Training is correctly gated by production buildings.
    failure = action(alpha, "command", {
        "command": "train",
        "unitType": "rifle",
    }, 400)
    assert failure["ok"] is False
    assert "生产建筑" in failure["error"]

    queued = action(alpha, "command", {
        "command": "prepareBuild",
        "structureType": "barracks",
    })["room"]
    alpha_player = next(item for item in queued["players"] if item["id"] == alpha["playerId"])
    assert alpha_player["buildQueue"][0]["kind"] == "barracks"
    assert alpha_player["buildQueue"][0]["remaining"] > 0

    unit = next(item for item in queued["game"]["units"]
                if item["owner"] == alpha["playerId"] and item["kind"] == "rifle")
    old_x, old_y = unit["x"], unit["y"]
    action(alpha, "command", {
        "command": "move",
        "unitIds": [unit["id"]],
        "x": old_x + 250,
        "y": old_y + 160,
    })
    time.sleep(0.45)
    moved = state(alpha)
    moved_unit = next(item for item in moved["game"]["units"] if item["id"] == unit["id"])
    assert abs(moved_unit["x"] - old_x) + abs(moved_unit["y"] - old_y) > 8

    action(beta, "chat", {"message": "联调消息"})
    chatted = state(alpha)
    assert any(item["message"] == "联调消息" for item in chatted["chat"])

    def read_frame(response):
        event_line = response.readline().decode("utf-8").strip()
        data_line = response.readline().decode("utf-8").strip()
        response.readline()          # 事件之间的空行
        assert event_line == "event: state", event_line
        assert data_line.startswith("data: ")
        return json.loads(data_line[6:])

    event_query = urlencode(alpha)
    with urlopen(BASE + "/api/events?" + event_query, timeout=8) as response:
        first = read_frame(response)
        assert first["id"] == room_id
        assert first["status"] == "playing"
        # 首帧带全部静态数据
        assert first["game"]["full"] is True
        assert not first["game"]["terrain"]["rivers"]
        assert not first["game"]["terrain"]["bridges"]
        assert first["game"]["terrain"]["mountains"]
        assert first["game"]["sight"]
        assert first["maps"]

        # 之后每帧省掉静态部分，客户端用缓存补齐
        second = read_frame(response)
        assert not second["game"].get("full")
        assert "terrain" not in second["game"]
        assert "resources" not in second["game"]
        assert "sight" not in second["game"]
        assert "maps" not in second, "对局中不应再重发地图目录"
        assert second["game"]["units"], "增量帧仍要带单位"
        assert second["game"]["ore"], "增量帧仍要带矿脉余量"
        trimmed = len(json.dumps(second, separators=(",", ":")).encode("utf-8"))
        full_size = len(json.dumps(first, separators=(",", ":")).encode("utf-8"))
        assert trimmed < full_size, (trimmed, full_size)

    rooms = call("/api/rooms")["rooms"]
    assert any(item["id"] == room_id and item["status"] == "playing" for item in rooms)
    print(json.dumps({
        "ok": True,
        "roomId": room_id,
        "players": len(started["players"]),
        "visibleInitialUnits": len(started["game"]["units"]),
        "fogVerified": True,
        "buildQueueVerified": True,
        "movementVerified": True,
        "sseVerified": True,
        "chatVerified": True,
        "visualAssetsVerified": True,
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
