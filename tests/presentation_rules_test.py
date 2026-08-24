#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""建筑目录与探索黑幕的静态回归检查。"""

from __future__ import print_function

import os
import random
import re
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
    styles = read("public/styles.css")

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

    # 侧栏的隐式网格列和三列生产网格都必须允许缩到 0；否则在浏览器
    # 缩放或高 DPI 下，canvas 的固有宽度会把第三列撑出侧栏并被裁掉。
    assert "grid-template-columns: minmax(0, 1fr);" in styles
    assert styles.count("grid-template-columns: repeat(3, minmax(0, 1fr));") >= 2
    assert ".command-sidebar > *" in styles
    assert "max-width: 100%;" in styles

    # Other live maps stay mountain-only; the two crater maps are rim-bridge maps.
    crater_ids = ("gold_crater", "gold_crater_small")
    for map_id in crater_ids:
        crater = server.MAPS[map_id]
        assert crater.get("rivers") and crater.get("bridges")
    for map_id, map_def in server.MAPS.items():
        if map_id in crater_ids:
            continue
        assert not map_def.get("rivers"), "%s still has river data" % map_id
        assert not map_def.get("bridges"), "%s still has bridge data" % map_id
        assert map_def.get("mountains"), "%s needs mountain blockers" % map_id
    expected_sizes = {
        "north_conflict": (9600, 6000),
        "island_hop": (7200, 6000),
        "urban_siege": (6400, 6400),
        "narrow_standoff": (4800, 3200),
        "triple_pass": (5400, 4200),
        "valley_clash": (6400, 4800),
        "gold_crater": (10000, 6400),
        "gold_crater_small": (6400, 6400),
    }
    assert {map_id: (map_def["width"], map_def["height"])
            for map_id, map_def in server.MAPS.items()} == expected_sizes

    # 建造卡造价/名称/角色只信服务端目录，避免客户端再抄一份数字表。
    catalog = server.public_catalog()
    assert catalog["buildings"] and catalog["units"]
    for kind, entry in catalog["buildings"].items():
        assert kind in server.STRUCTURE_TYPES, kind
        assert entry["cost"] == server.STRUCTURE_TYPES[kind]["cost"], (
            kind, entry["cost"], server.STRUCTURE_TYPES[kind]["cost"])
        assert entry["name"] == server.STRUCTURE_TYPES[kind]["name"]
        assert entry["role"] == server.STRUCTURE_TYPES[kind]["role"]
        assert entry["faction"] == server.STRUCTURE_TYPES[kind]["faction"]
    for kind, entry in catalog["units"].items():
        assert kind in server.UNIT_TYPES, kind
        assert entry["cost"] == server.UNIT_TYPES[kind]["cost"], (
            kind, entry["cost"], server.UNIT_TYPES[kind]["cost"])
        assert entry["name"] == server.UNIT_TYPES[kind]["name"]
        assert entry["role"] == server.UNIT_TYPES[kind]["role"]
        assert entry["faction"] == server.UNIT_TYPES[kind]["faction"]
    assert catalog["buildings"]["mhq"]["name"] == "魔法主堡"
    view = server.public_game(room["game"], alpha["id"], full=True)
    assert view["catalog"]["buildings"]["power"]["cost"] == server.STRUCTURE_TYPES["power"]["cost"]
    assert view["catalog"]["units"]["mage"]["name"] == "奥术法师"

    assert "function applyCatalog" in app
    assert "/api/catalog" in app
    for var_name in ("BUILDING_VFX", "UNIT_VFX"):
        block = re.search(r"var %s = \{([\s\S]*?)\n  \};" % var_name, app)
        assert block, "missing %s" % var_name
        assert "cost:" not in block.group(1), "%s must not hardcode costs" % var_name
    assert "var FACTION_COPY" in app
    assert "infantryTab: '圣殿'" in app
    assert "vehicleTab: '法阵'" in app
    assert "function applyFactionHud" in app

    # 客户端建造锚点、空格回基地、展开/折叠必须走 role，不能写死 hq/mcv。
    assert "function structureRole(kind)" in app
    assert "function unitRole(kind)" in app
    assert "BUILD_ANCHOR_RANGES[structureRole(s.kind)]" in app
    server_src = read("server.py")
    assert 'BUILD_ANCHOR_RANGES.get(structure_role(structure["kind"]))' in server_src
    assert "def player_has_command(" in server_src

    # 大厅/文档不能再写已删除的火焰兵，也不能只提 Windows bat。
    index = read("public/index.html")
    readme = read("README.md")
    assert "火焰兵" not in index and "火焰克步兵" not in index
    assert "火焰兵" not in readme
    assert "钢铁军团" in readme and "秘法会" in readme
    assert "start-game.sh" in readme
    assert os.path.isfile(os.path.join(ROOT, "start-game.sh"))
    starter = read("start-game.sh")
    assert "python3" in starter and "server.py" in starter
    bat = read("start-game.bat")
    assert bat.find("py.exe") < bat.find("Python36")

    # 秘法会有圣泉（role=repair）：维修按钮按阵营换文案，不再整阵营隐藏。
    assert "function isOwnMagicFaction" in app
    assert "repairBtn.classList.toggle('hidden', isMagic)" not in app
    assert "structureRole(structure.kind) === 'repair'" in app
    assert "structureRole(target.kind) === 'repair'" in app
    assert catalog["buildings"]["mspring"]["role"] == "repair"
    assert catalog["buildings"]["mspring"]["faction"] == "magic"
    assert catalog["buildings"]["mspring"]["cost"] == server.STRUCTURE_TYPES["repair"]["cost"]
    assert catalog["units"]["golem"]["repairable"] is True
    assert catalog["units"]["dragon"]["repairable"] is True
    assert catalog["units"]["warden"]["repairable"] is True
    assert catalog["units"]["colossus"]["repairable"] is True
    assert catalog["units"]["mharvester"]["repairable"] is True
    assert catalog["units"]["mage"]["repairable"] is False
    assert catalog["units"]["dragon"]["requires"] == ["mspring"]
    assert catalog["units"]["warden"]["requires"] == ["mspring"]
    assert catalog["units"]["colossus"]["requires"] == ["mspring"]
    assert catalog["units"]["comet"]["requires"] == ["mspring"]
    assert catalog["units"]["comet"]["name"] == "坠星台"
    assert catalog["units"]["comet"]["repairable"] is True
    assert catalog["units"]["comet"]["producer"] == "mcircle"
    assert catalog["units"]["comet"]["faction"] == "magic"
    assert catalog["units"]["comet"]["cost"] == 2000

    assert server.select_lan_ips(
        ["127.0.0.1", "192.168.1.5", "10.18.0.2", "10.0.0.1"]
    ) == ["10.18.0.2", "10.0.0.1", "192.168.1.5"]
    saved_rooms = dict(server.ROOMS)
    try:
        server.ROOMS.clear()
        for index in range(server.MAX_ROOMS):
            server.ROOMS["X%02d" % index] = {"id": "X%02d" % index}
        try:
            server.ensure_room_capacity()
            raise AssertionError("room cap should fire")
        except ValueError as error:
            assert "满" in str(error)
    finally:
        server.ROOMS.clear()
        server.ROOMS.update(saved_rooms)

    # SSE/GET 查询串里的 session token 不能进 access log。
    leaked = '"GET /api/events?roomId=R1&playerId=P1&token=SECRETTOKEN HTTP/1.1" 200 -'
    cleaned = server.sanitize_access_log(leaked)
    assert "SECRETTOKEN" not in cleaned
    assert "?" not in cleaned
    assert "/api/events" in cleaned

    # 战场地表必须按主题上色，并且片元细节着色器要真正接到地面材质上。
    # 旧版 applyTerrainDetail 写了却没调用，开局就是一块荧光绿平板。
    assert "export const MAP_DISPLAY_THEMES" in render
    assert "applyTerrainDetail(applyFogMask" in render
    assert "function makeProceduralGroundTexture" in render
    assert "function spawnWearAt" in render
    assert "function tuftParts" not in render
    assert "function pineParts" not in render
    assert "function buildScatter" not in render
    assert "function makeCraterSign" not in render
    assert "function buildLandmarks" not in render
    assert "mixGroundPhoto" not in render
    assert "terrain-ground.png" not in render
    for theme_id in ("grassland", "arid", "urban", "crater"):
        assert ("  %s:" % theme_id) in render
    assert server.MAPS["north_conflict"]["theme"] == "grassland"
    assert server.MAPS["narrow_standoff"]["theme"] == "arid"
    assert server.MAPS["urban_siege"]["theme"] == "urban"
    assert server.MAPS["gold_crater"]["theme"] == "crater"
    assert server.MAPS["gold_crater_small"]["theme"] == "crater"
    assert "mapBriefingDisplay" in app
    assert server.MAPS["gold_crater"].get("briefing")
    assert server.MAPS["gold_crater_small"].get("briefing")
    assert "function paintGrassBase(c, w, h, themeId)" in app
    assert "paintTerrainFeatures(miniCtx, roomState.game.terrain, sx, sy)" in app
    # 道路只留玩法数据：不再铺 3D 条带、路肩脏土或小地图/大厅描线。
    assert "function buildRoads" not in render
    assert "function roadWearAt" not in render
    assert "swatch.road" not in app
    assert "roadWearAt(" not in render
    assert "shadowQuality: 'structures'" in app
    assert "sceneryQuality" not in app
    assert "terrain-ground.png" not in app

    # 建筑/单位视觉第二轮：阵营地基、尘土围裙、共享金属/石面着色，不能退回灰方块。
    assert "function addStructureFoundation(c, kind, s)" in render
    assert "const MAGIC_STRUCTURE_KINDS = {" in render
    assert "function makeBuildingPadTexture()" in render
    assert "尘土围裙略大于新地基" in render
    assert "指挥中心：矮宽地堡 + 两侧翼楼 + 收束主塔" in render
    assert "法力塔：两根收束晶柱托一颗中心法力球" in render
    assert "teamOrOwn4" in render
    assert "armyTimeUniform" in render
    assert "躯干走橄榄布甲" in render
    assert "长袍法师：暗紫袍是固有色" in render
    assert "冰霜女巫：苍蓝袍 + 冰晶头冠" in render
    assert "秘法巨龙：拉长的翼展剪影" in render
    assert "晶铠卫士：晶体铠甲前排" in render
    assert "裂地晶兽：四足晶兽驮晶陨鞍塔" in render
    assert "裂地晶兽：四足晶兽 + 背上晶陨鞍塔" in app
    assert "坠星台：重型石座底盘上的黑曜发射架" in render
    assert "坠星台：重型石座 + 黑曜发射架 + 待发彗核" in app
    assert "自爆卡车：轮式药箱车" in render
    assert "爆裂魔仆：矮小符核活体" in render
    assert "type === 'blast'" in render
    assert catalog["units"]["bomb_truck"]["name"] == "自爆卡车"
    assert catalog["units"]["hexling"]["name"] == "爆裂魔仆"
    assert catalog["units"]["bomb_truck"]["faction"] == "tech"
    assert catalog["units"]["hexling"]["faction"] == "magic"
    assert catalog["units"]["bomb_truck"]["repairable"] is True
    assert catalog["units"]["hexling"]["repairable"] is False
    assert catalog["units"]["bomb_truck"]["producer"] == "factory"
    assert catalog["units"]["hexling"]["producer"] == "mcircle"
    assert catalog["units"]["bomb_truck"]["cost"] == catalog["units"]["hexling"]["cost"]
    assert catalog["units"]["bomb_truck"]["build"] == catalog["units"]["hexling"]["build"]
    hud = read("public/index.html")
    assert "魔导甲怕磁暴/狙击×1.6" in hud
    assert "魔导甲怕磁暴/狙击×2.0" not in hud
    assert "frostRobe:" in render
    assert "look: 'shard'" in render
    assert "look: 'fireball'" in render
    assert "look: 'meteor'" in render
    assert "look: 'comet'" in render
    assert "look: 'crystal'" in render
    assert "iris:" in render
    assert "function guessMuzzleKind" in render
    assert "kind === 'meteor'" in render
    assert "kind === 'comet'" in render
    assert "function emitIdleAura" in render
    assert "步兵有持枪手臂，远看是人不是积木" in render
    assert "主堡顶是石穹加晶刺，不是叠方块" in render

    # 彩蛋挂钩：视觉件只锁字符串，触发逻辑在 easter_egg_test。
    # 陨坑木牌 / 撒点草木已从地图上拆掉，不能再被字符串锁住。
    assert "kind === 'dog_arcane'" in render
    assert "type === 'hq_salute'" in render
    assert "command: 'tapHq'" in app
    assert "function landmarkAt" not in app
    assert "type === 'hq_salute'" in app

    # Selection is only the current control set. A left-click / box / additive
    # gesture must not post move/stop, and a context click on an own unit is
    # select — otherwise the previous group is re-ordered onto the new pick.
    assert "function isAdditiveSelect(event)" in app
    assert "function selectedUnitIdList()" in app
    assert "event.shiftKey || event.ctrlKey || event.metaKey" in app
    assert "selectAt(worldX, worldY, isAdditiveSelect(event));" in app
    assert "Own-unit context click is a selection change, never a move/stop." in app
    pointer_up = re.search(
        r"canvas\.addEventListener\('pointerup', function \(event\) \{([\s\S]*?)\n  \}\);",
        app)
    assert pointer_up, "missing pointerup handler"
    up_body = pointer_up.group(1)
    assert "selectAt(pointer.worldX, pointer.worldY, dragging.additive)" in up_body
    assert "selectBoxUnits(" in up_body
    assert "issueGroundCommand" not in up_body
    assert "issueContextCommand" not in up_body
    assert "command: 'stop'" not in up_body
    assert "command: 'move'" not in up_body
    select_at = re.search(
        r"function selectAt\(worldX, worldY, additive\) \{([\s\S]*?)\n  \}",
        app)
    assert select_at, "missing selectAt"
    select_body = select_at.group(1)
    assert "command: 'move'" not in select_body
    assert "command: 'stop'" not in select_body
    assert "command: 'attackMove'" not in select_body
    box_fn = re.search(
        r"function selectBoxUnits\([\s\S]*?\) \{([\s\S]*?)\n  \}",
        app)
    assert box_fn, "missing selectBoxUnits"
    assert "sendAction" not in box_fn.group(1)
    assert "heldMs < 220 && currentScreen === 'game'" in app
    assert "stopKeyDownAt = performance.now();" in app

    # Playability QoL: double-click same-kind (visible/rendered only) and
    # control groups 1-3 remain, while production hotkeys are fully removed.
    assert "function selectAllOfType(worldX, worldY, additive)" in app
    assert "function unitIsCurrentlySeen(unit)" in app
    assert "view3d.isVisible && !view3d.isVisible(visual.x, visual.y)" in app
    assert "return visibleAt(visual.x, visual.y);" in app
    assert "selectAllOfType(pointer.worldX, pointer.worldY, isAdditiveSelect(event));" in app
    assert "CONTROL_GROUP_JUMP_MS = 350" in app
    assert "event.code >= 'Digit1' && event.code <= 'Digit3'" in app
    assert "function pruneControlGroups()" in app
    assert "TRAIN_HOTKEYS" not in app
    assert catalog["units"]["imp"]["name"] == "晶刺"
    assert catalog["units"]["oracle"]["name"] == "虹视使"
    assert catalog["units"]["imp"]["producer"] == "mtemple"
    assert catalog["units"]["oracle"]["producer"] == "mtemple"
    assert catalog["units"]["imp"]["faction"] == "magic"
    assert catalog["units"]["oracle"]["faction"] == "magic"
    assert catalog["units"]["imp"]["repairable"] is False
    assert catalog["units"]["oracle"]["repairable"] is False
    assert "晶刺：晶体碎片人形" in render
    assert "虹视使：细长远视者" in render
    assert "晶刺：碎晶人形 + 肩刺" in app
    assert "虹视使：细长袍 + 棱镜杖" in app
    assert "tryTrainHotkey" not in app
    assert "trainHotkeyLetter" not in app
    assert "cameraTrainKeyDownAt" not in app
    assert "command-hotkey" not in app
    assert "command-hotkey" not in styles
    assert "id=\"productionHint\"" not in hud
    assert "production-hint" not in styles
    assert "双击己方单位" in readme
    assert "Ctrl+1 / Ctrl+2 / Ctrl+3" in readme
    assert "不设置生产快捷键" in readme

    # 可选模式「轨道天降」：大厅开关文案在，预警圈跟这发 radius 走。
    assert "轨道天降" in index
    assert "随机轨道打击，范围×5，默认关" in index
    assert 'data-mode="orbital_rain"' in index
    assert "orbitalRainToggle" in index
    assert "轨道天降" in readme
    assert "setOrbitalRain" in app
    assert "function syncOrbitalRainToggle" in app
    assert "strike.radius" in app
    assert "vecScale.set(STRIKE_RADIUS," not in render
    assert "const ringR = (s.radius > 0) ? s.radius : STRIKE_RADIUS_FALLBACK;" in render

    print("presentation rules ok: radar removed, shroud persists, vehicles distinct, maps use valleys, catalog from server")


if __name__ == "__main__":
    main()
