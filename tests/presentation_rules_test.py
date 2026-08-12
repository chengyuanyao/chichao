#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""建筑目录与探索黑幕的静态回归检查。"""

from __future__ import print_function

import os
import random
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import server


def read(relative):
    with open(os.path.join(ROOT, relative), "r", encoding="utf-8") as handle:
        return handle.read()


def make_room():
    random.seed(6201)
    alpha = server.create_human("规则甲", server.COLORS[0])
    beta = server.create_human("规则乙", server.COLORS[1])
    room = {
        "id": "RULE01", "name": "规则测试", "status": "lobby",
        "hostId": alpha["id"],
        "players": {alpha["id"]: alpha, beta["id"]: beta},
        "chat": [], "game": None, "createdAt": time.time(),
    }
    server.start_game(room)
    return room, alpha


def main():
    app = read("public/app.js")
    render = read("public/render3d.js")

    assert "radar" not in server.STRUCTURE_TYPES
    assert "全景雷达" not in app
    assert "kind === 'radar'" not in render

    room, alpha = make_room()
    try:
        server.queue_structure(room, alpha["id"], "radar")
    except ValueError as error:
        assert "未知建筑" in str(error)
    else:
        raise AssertionError("服务端不应再接受全景雷达建造请求")

    # 探索层必须累积软边视野，而最终黑幕只能从累计层清除；旧版的 0.62
    # 灰雾会让单位离开后重新压暗地形，因此明确锁住它不再出现。
    assert "exploredCtx.drawImage(fogGradientCanvas" in render
    assert "fogCtx.drawImage(exploredCanvas" in render
    assert "fogCtx.globalAlpha = 0.62" not in render

    # 小地图不能从全量静态资源表泄露矿点；只登记进入过友军视野的矿，
    # 并在换局时清空登记表。
    assert "var discoveredResourceIds = new Set();" in app
    assert "if (!view3d.isVisible(resource.x, resource.y)) { return; }" in app
    assert "discoveredResourceIds.add(resource.id);" in app
    assert "discoveredResourceIds.clear();" in app

    # 两辆经济载具在高低模里都有独立识别特征。
    assert "大型切削滚筒是采矿车的主剪影" in render
    assert "四个外伸液压支腿" in render
    assert "sph(6, 6, -7, 29, 0, MAT.oreGlow)" in render
    assert "box(32, 10, 3.2, -4, 25, 17.5" in render

    # Four-player rendering must keep model identity while shedding only work
    # that cannot affect the current frame: snapshot bookkeeping is 8Hz,
    # culling follows the viewport, static overlays are 20Hz while moving bars
    # follow interpolated units every frame, and adaptive quality changes pixel
    # density rather than swapping every unit for one box mesh.
    assert "if (game !== lastEntityGame)" in render
    assert "updateViewportBounds(190);" in render
    assert "let movingVisibleBar = false;" in render
    assert "if (movingVisibleBar || payload.time - lastBarsAt >= 50)" in render
    assert "selected.forEach(function (id)" in render
    assert "var renderScaleSteps = [1, 0.90, 0.80, 0.70, 0.60];" in app
    assert "timestamp - lastHudOverlayAt >= 50" in app
    assert "game.units.length >" not in render

    # Live battlefields use mountains and valleys only: no bridge bottlenecks.
    for map_id, map_def in server.MAPS.items():
        assert not map_def.get("rivers"), "%s still has river data" % map_id
        assert not map_def.get("bridges"), "%s still has bridge data" % map_id
        assert map_def.get("mountains"), "%s needs mountain blockers" % map_id
    expected_sizes = {
        "north_conflict": (9600, 6000),
        "cliff_assault": (9600, 6000),
        "island_hop": (7200, 6000),
        "urban_siege": (6400, 6400),
        "narrow_standoff": (4800, 3200),
        "valley_clash": (6400, 4800),
    }
    assert {map_id: (map_def["width"], map_def["height"])
            for map_id, map_def in server.MAPS.items()} == expected_sizes

    print("presentation rules ok: radar removed, shroud persists, vehicles distinct, maps use valleys")


if __name__ == "__main__":
    main()
