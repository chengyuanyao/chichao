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
    hud = read("public/index.html")
    server_source = read("server.py")

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

    # 矿脉现在是可选中的情报目标：详情给出准确余量/总量/百分比；四档
    # 图例由渲染层统一提供给 3D 矿簇、小地图和侧栏，且点选不能穿透迷雾。
    assert "export const ORE_RESERVE_TIERS" in render
    assert "export function oreReserveTier(amount)" in render
    for tier_id, minimum, pips in (
            ("poor", 0, 2), ("standard", 8000, 4),
            ("rich", 30000, 6), ("giant", 80000, 8)):
        tier_pattern = (r"id: '%s'[\s\S]*?minAmount: %d[\s\S]*?"
                        r"minimapPips: %d" % (tier_id, minimum, pips))
        assert re.search(tier_pattern, render), tier_id
    assert "oreReserveTier" in app.split("from './render3d.js';", 1)[0]
    assert "var selectedResourceId = null;" in app
    assert "function resourceAt(worldX, worldY)" in app
    resource_at = re.search(
        r"function resourceAt\(worldX, worldY\) \{([\s\S]*?)\n  \}", app)
    assert resource_at
    assert "resource.amount <= 0" in resource_at.group(1)
    assert "view3d.isVisible(resource.x, resource.y)" in resource_at.group(1)
    assert "var resource = entity ? null : resourceAt(worldX, worldY);" in app
    assert "selectedResourceId = resource.id;" in app
    assert "selectedResourceId: selectedResourceId" in app
    assert "剩余 " in app
    assert "resource.maxAmount" in app
    assert "reservePercent" in app
    assert 'class="health-track ore-track"' in app
    assert "resource.id === selectedResourceId" in app
    assert "payload.selectedResourceId" in render
    assert "oreReserveTier(res.amount)" in render
    assert "new THREE.InstancedMesh(crystalGeo, crystalMat, count)" in render
    assert "new THREE.Mesh(crystalGeo, crystalMat)" not in render
    assert "crystals.count = live ?" in render
    assert "tier.crystalCount" in render
    assert 'class="ore-reserve-legend"' in hud
    for tier_id in ("poor", "standard", "rich", "giant"):
        assert "ore-tier-%s" % tier_id in hud
        assert ".ore-tier-%s" % tier_id in styles
    assert ".ore-reserve-legend" in styles
    assert ".ore-glyph" in styles
    assert ".ore-track i" in styles

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

    # Other live maps stay mountain-only; the retained crater map uses rim bridges.
    crater_ids = ("gold_crater_small",)
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
        "narrow_standoff": (4800, 3200),
        "gold_crater_small": (6400, 6400),
        "central_scramble": (4000, 4000),
    }
    assert {map_id: (map_def["width"], map_def["height"])
            for map_id, map_def in server.MAPS.items()} == expected_sizes

    # 建造卡造价/名称/角色只信服务端目录，避免客户端再抄一份数字表。
    catalog = server.public_catalog()
    assert catalog["buildings"] and catalog["units"]
    assert catalog["veterancy"]["regenDelay"] == 6.0
    assert [rank["minKills"] for rank in catalog["veterancy"]["ranks"]] == [0, 3, 8, 16]
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
        assert entry["canVeteran"] == (server.UNIT_TYPES[kind].get("damage", 0) > 0)
    assert catalog["buildings"]["mhq"]["name"] == "魔法主堡"
    view = server.public_game(room["game"], alpha["id"], full=True)
    assert view["catalog"]["buildings"]["power"]["cost"] == server.STRUCTURE_TYPES["power"]["cost"]
    assert view["catalog"]["units"]["mage"]["name"] == "奥术法师"

    assert "function applyCatalog" in app
    assert "/api/catalog" in app
    assert "function veterancySummary(kills)" in app
    assert "军衔增益：" in app
    assert "距' + nextRank.name + '还差 " in app
    assert "veterancy-detail" in app
    assert ".selected-summary .veterancy-detail" in styles
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
    assert "ENEMY_BUILD_EXCLUSION" not in app
    assert "ENEMY_BUILD_EXCLUSION" not in server_src
    assert "outside_enemy_build_zone" not in server_src
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
    assert "const TERRAIN_DETAIL_DEFAULTS = {" in render
    assert "function resolveTerrainDetail(map, terrain)" in render
    assert "function terrainFlatnessAt(x, y)" in render
    assert "function buildGroundDetail()" in render
    assert "mesh.name = 'ground-detail'" in render
    assert "const grassTarget = Math.min(640" in render
    assert "三片交叉三角叶组成一簇草" in render
    assert "const rockTarget = Math.min(180" in render
    assert "mesh.castShadow = false" in render
    assert "groundDetailParts: state.groundDetailParts" in render
    assert "terrainDetail\": visual_terrain_detail(m)" in server_source
    # 团队胜利必须按完整获胜成员列表显示；winnerId 只是兼容字段，不能再让
    # 同队其余客户端误弹“失败”。空名单还要按 winnerTeam / isFriendly 回退，
    # 不能把网络切帧期间的 [] 当成“所有人都输了”。
    assert "function didPlayerWin(game, playerId)" in app
    assert "Array.isArray(game.winnerIds) && game.winnerIds.length" in app
    assert "game.winnerTeam > 0" in app
    assert "isFriendly(game.winnerId)" in app
    assert "roomState.game.winnerId === session.playerId" not in app
    assert '"winnerIds": list(game.get("winnerIds", []))' in server_source
    # 分队会连带多次 setSpawn；必须串行确认完才能把 start 发给服务端。
    assert "function queueLobbyMutation(work)" in app
    assert "var lobbyMutationTail = Promise.resolve();" in app
    assert "lobbyMutationsPending > 0" in app
    assert "async function autoAssignSpawns()" in app
    assert "await autoAssignSpawns();" in app
    assert "return sendAction('start');" in app
    assert "function tuftParts" not in render
    assert "function pineParts" not in render
    assert "function buildScatter" not in render
    assert "function makeCraterSign" not in render
    assert "function buildLandmarks" not in render
    assert "mixGroundPhoto" not in render
    assert "terrain-ground.png" not in render
    for theme_id in ("grassland", "arid", "urban", "crater"):
        assert ("  %s:" % theme_id) in render
    assert server.MAPS["central_scramble"]["theme"] == "grassland"
    assert server.MAPS["narrow_standoff"]["theme"] == "arid"
    assert server.MAPS["gold_crater_small"]["theme"] == "crater"
    assert "mapBriefingDisplay" in app
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
    assert "法力塔：细针晶柱 + 绕轨碎晶" in render
    assert "水晶精炼所：横置晶液大釜" in render
    assert "奥术圣殿：露天新月门" in render
    assert "召唤法阵：多层平面符环 + 悬浮核" in render
    assert "圣泉：石碗泉盆 + 上升泉光" in render
    assert "奥术塔：扭转尖塔 + 武器晶碟" in render
    assert "teamOrOwn8-occ-" in render
    assert "armyTimeUniform" in render
    # 顶点烘焙遮蔽 + 逐零件表面通道：两条通道必须一直写进合并几何体，
    # 着色器声明了属性却拿不到数据的话，整支部队会被当成全黑。
    assert "function bakeOcclusion(" in render
    assert "merged.setAttribute('aOcc'" in render
    assert "merged.setAttribute('aSurf'" in render
    assert "attribute float aOcc;" in render
    assert "attribute float aSurf;" in render
    assert "diffuseColor.rgb *= mix(1.0, vOcc, 1.0 - gEmissive);" in render
    assert "float gMode = vSurf < -0.5 ? uArmySurfaceMode : vSurf;" in render
    # 晶体是新增的第五种表面：粗糙度最低、边缘光最强
    assert "const SURF = Object.freeze({" in render
    assert "gRoughness = 0.24; gBumpScale = 0.10" in render
    assert "float gRimGain = gMode > 3.5 ? 0.42 : 0.13;" in render
    # 烘焙目前只在试点兵种上打开；铺开时改这张表即可，管线不用动
    occlusion_kinds = re.search(
        r"const OCCLUSION_BAKED_KINDS = \{([\s\S]*?)\};", render)
    assert occlusion_kinds
    for kind in ("dragon", "overlord", "overlord_v1", "overlord_v2"):
        assert re.search(r"\b%s\s*:\s*1\b" % kind,
                         occlusion_kinds.group(1)), kind
    assert "OCCLUSION_BAKED_KINDS[kind] ? { occlusion: true } : null" in render
    # 写实升级必须保持合批边界：军械共享压缩贴图；自然草簇和碎石允许整张
    # 地图共用一个额外 Mesh，但不能退回“一棵草/一块石头一个 draw call”。
    assert "function makeArmySurfaceTexture()" in render
    assert "uniform sampler2D uArmySurface" in render
    assert "const CLOTH_UNIT_KINDS = {" in render
    for kind in ("rifle", "rocket", "sniper", "tesla", "mage", "frost", "oracle"):
        assert re.search(r"\b%s: 1\b" % kind, render[render.index(
            "const CLOTH_UNIT_KINDS = {"):render.index(
                "const HIDE_UNIT_KINDS = {")]), kind
    assert "surfaceKind === 'cloth' ? 2" in render
    assert "gRoughness = 0.92; gBumpScale = 0.20" in render
    assert "function makeUnitShadowTexture()" in render
    assert "map: makeUnitShadowTexture()" in render
    assert "armyHash(" not in render
    assert "function makeOreVeinTexture()" in render
    assert "map: makeOreVeinTexture()" in render
    for texture in (
        "army-real-atlas.webp",
        "ground-real.webp",
        "foliage-real.webp",
        "ore-real.webp",
    ):
        assert os.path.isfile(os.path.join(ROOT, "public", "assets", "textures", texture))
        assert texture in render
    # 近景用低面数倒角和圆肢体去掉积木轮廓；远景必须退回 12 面方盒控制面数。
    assert "function chamferedBoxGeometry(w, h, d)" in render
    assert "geo: chamferedBoxGeometry(w, h, d)" in render
    assert "function isEmissivePaint(paint)" in render
    assert "? new THREE.BoxGeometry(w, h, d)" in render
    assert ": chamferedBoxGeometry(w, h, d)" in render
    assert "material !== GLOW && geo && geo.type === 'BoxGeometry'" in render
    assert "function plainBox(w, h, d" in render
    assert "const box = plainBox;" in render
    assert "function plainTaperedBox(" in render
    assert "const taperedBox = plainTaperedBox;" in render
    assert "两点之间的圆肢体" in render
    assert "function profiledVolume(profile, radiusX, radiusZ" in render
    assert "new THREE.LatheGeometry(points" in render
    assert "运行时仍是一个 InstancedMesh，不增加 draw call" in render
    # 车体与发光件仍旧合并成同一份几何体；烘焙开关只是多传一个参数，
    # 不能演化成「发光件单独一个 Mesh」那种额外 draw call。
    assert "body: mergeParts(parts.body.concat(parts.glow || []), bake)" in render
    assert "大头积木人" in render
    assert "groundTexture.repeat.set(mw / 420, mh / 420);" in render
    assert "同一棵树的三层树冠分别压暗、保持、提亮" in render
    assert "真人比例重做" in render
    # 秘法会比例校正只变换已有零件，不能靠新增独立 Mesh/实例硬堆体量；
    # 近景、远景和点选半径必须一起更新，玩法 size 则保持与钢铁对位一致。
    assert "function scalePartList(parts, sx, sy, sz)" in render
    assert "function scaleUnitModel(model, sx, sy, sz)" in render
    assert "}, 1.65, 1.25, 1.65);" in render
    assert "}, 1.65, 1.42, 1.65);" in render
    assert "scalePartList(wingBody, 1.0, 1.0, 0.82)" in render
    assert "scalePartList(wings, 1.0, 1.0, 0.82)" in render
    assert "export const UNIT_VISUAL_PICK_SCALE" in render
    assert "UNIT_VISUAL_PICK_SCALE" in app
    assert "Math.max(unit.size + 8 / camera.zoom, visualTolerance)" in app
    assert server.UNIT_TYPES["mharvester"]["size"] == server.UNIT_TYPES["harvester"]["size"]
    assert server.UNIT_TYPES["mmcv"]["size"] == server.UNIT_TYPES["mcv"]["size"]
    assert server.UNIT_TYPES["golem"]["size"] == server.UNIT_TYPES["tank"]["size"]
    assert "奥术法师：高挑长袍施法者，暗紫袍 + 金饰法杖" in render
    assert "冰霜女巫：宽檐帽 + 苍白斗篷 + 霜环" in render
    assert "秘法巨龙：「玉剑传说」路线的东方玉龙" in render
    assert "天启级巨型持盾构装" in render
    assert "}, 1.18, 1.14, 1.18);" in render
    assert "warden: 1.55" in render
    assert "warden: 1.75" in render
    assert "裂地晶兽：四足晶兽驮晶陨鞍塔" in render
    assert "裂地晶兽：四足晶兽 + 背上晶陨鞍塔" in app
    assert "坠星台：厚重发射底盘 + 竖直晶炮" in render
    assert "坠星台：厚重底盘 + 竖直晶炮" in app
    assert "自爆卡车：轮式药箱车" in render
    assert "爆裂魔仆：脉冲不稳的符核魔球" in render
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
    assert catalog["units"]["bomb_truck"]["cost"] == 1000
    assert catalog["units"]["hexling"]["cost"] == 1000
    assert catalog["units"]["bomb_truck"]["build"] == 8.5
    assert catalog["units"]["hexling"]["build"] == 8.5
    assert server.UNIT_TYPES["bomb_truck"]["speed"] == server.UNIT_TYPES["hexling"]["speed"]
    assert server.UNIT_TYPES["bomb_truck"]["speed"] == 97.9
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
    assert "手臂在肘部转折后共同托枪" in render
    assert "魔法主堡：双尖塔托浮空金冠，不是矮方堡" in render

    # 两个阵营目录里的每一种单位都必须有专属近景 builder；不能悄悄回退到
    # rifle 占位模型。曲面推广只增加缓存几何，仍保持每种单位一个实例批次。
    builder_block = render[render.index("const UNIT_BUILDERS = {"):
                           render.index("/* ------------------------------------------------------------------ *\n * 建筑模型")]
    for kind in catalog["units"]:
        assert re.search(r"\n  %s: function \(" % re.escape(kind), builder_block), kind
    for profile_name in (
            "mantleProfile", "seerProfile", "cuirassProfile", "beastProfile",
            "launchBaseProfile", "migrateBaseProfile"):
        assert profile_name in builder_block
    # 巨龙走「玉剑传说」玉龙路线：躯干仍是椭球不能退回方盒；明度必须保持
    # 墨玉背 / 翡翠身 / 白玉腹三段，翼膜也要分出翼尖那一段透光的白玉，
    # 否则又变回通体一个调的深色剪影。金角、龙须、玉鳍是东方龙的辨识件。
    assert "ellipsoid(14.2, 4.2, 5.7" in builder_block
    for jade in ("MAT.jadeScaleDark", "MAT.jadeScale", "MAT.jadeBelly",
                 "MAT.jadeFin", "MAT.jadeMembrane", "MAT.jadeMembraneLit"):
        assert jade in builder_block, jade
    assert "分叉鹿角" in builder_block
    assert "后掠长龙须" in builder_block
    # 玉件必须走晶体表面通道，金件走金属：一次绘制调用里三种高光
    assert "surfaced(SURF.crystal, [" in builder_block
    assert "surfaced(SURF.metal, [" in builder_block
    # 攻击特效跟模型一起换玉色：火球是巨龙独有弹道，不能残留橙火配色。
    # projectile 键仍是 fireball（服务端目录约定），只换表现。
    assert server.UNIT_TYPES["dragon"]["projectile"] == "fireball"
    assert "fireball: { len: 15, thick: 3.1, color: 0x4fd8a0" in render
    for orange in ("0xff7a28", "0xff7a2a", "0xffb060", "0xffc878"):
        assert orange not in render, orange
    assert "flashAt(x, y, 0x7dffc8);" in render        # 命中闪光
    assert "flashAt(x, y, 0x9fffdc);" in render        # 龙口喷吐闪光
    assert "} else if (kind === 'fireball') {" in render

    # 建筑同样逐项覆盖目录，所有非发光直角盒会在首次缓存时换成倒角截面。
    structure_block = render[render.index("function structureParts(kind, size)"):
                             render.index("return c.parts;", render.index(
                                 "function structureParts(kind, size)"))]
    for kind in catalog["buildings"]:
        assert "kind === '%s'" % kind in structure_block, kind

    # 秘法会既要保留固定紫/蓝的阵营材质，也必须在近景、远景和建筑上
    # 留出足够大的玩家色识别面，不能再出现整只构装或整座建筑不随玩家变色。
    assert "背部披挂用玩家色标明归属" in render
    assert "玩家色鞍甲" in render
    assert "玩家色平台上盖" in render
    assert "玩家色浮台上盖" in render
    magic_near = render[render.index("/* ==================== 秘法会（魔法阵营）模型 ==================== */"):
                        render.index("tank: function ()", render.index("/* ==================== 秘法会（魔法阵营）模型 ==================== */"))]
    for signature in (
            "ellipsoid(3.6, 0.48, 3.55", "chamferedBox(5.8, 0.55, 6.1",
            "box(6.4, 0.70, 4.8", "chamferedBox(5.0, 0.52, 5.5",
            "ellipsoid(4.55, 0.62, 3.4", "taperedBox(10.0, 6.8",
            "box(14.0, 0.75, 6.2", "box(10.4, 0.95, 6.8",
            "taperedBox(15.2, 9.8", "taperedBox(27, 16",
            "profiledVolume(deckProfile, 7.8, 6.5", "taperedBox(19, 13",
            "torus(4.2, 0.45"):
        assert signature in magic_near, "magic unit lost owner-color marker: %s" % signature
    # 样板近景的主体轮廓必须是连续曲面；这四个块状旧签名不能重新混回来。
    for blocky_signature in (
            "taperedBox(8.8, 8.8, 3.4, 3.4",
            "box(5.4, 10.2, 5.4",
            "taperedBox(16, 14, 18, 16",
            "new THREE.BoxGeometry(s * 0.20, s * 0.36, s * 0.03)"):
        assert blocky_signature not in magic_near
    magic_lod = render[render.index("/* ---- 秘法会 LOD ---- */"):
                       render.index("return infantry;", render.index("/* ---- 秘法会 LOD ---- */"))]
    for signature in (
            "box(6.0, 1.6, 7", "box(5.8, 0.65, 6.0",
            "box(6.4, 0.70, 4.8", "box(5.2, 0.65, 5.8",
            "box(9.0, 0.90, 6.6", "taperedBox(10.0, 6.8",
            "box(14.0, 0.75, 6.2", "box(10.4, 0.95, 6.8",
            "taperedBox(15.2, 9.8", "taperedBox(27, 16",
            "taperedBox(15, 12", "taperedBox(19, 13",
            "torus(4.2, 0.45"):
        assert signature in magic_lod, "magic LOD lost owner-color marker: %s" % signature
    magic_buildings = render[render.index("} else if (kind === 'mhq')"):
                             render.index("return c.parts;", render.index("} else if (kind === 'mhq')"))]
    for kind in ("mhq", "mpower", "mrefinery", "mtemple", "mcircle", "mspring", "mtower"):
        start = magic_buildings.index("kind === '%s'" % kind)
        next_start = magic_buildings.find("kind === '", start + 10)
        branch = magic_buildings[start:next_start if next_start >= 0 else len(magic_buildings)]
        assert "TEAM" in branch, "magic structure has no owner-color surface: %s" % kind

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
    # 3D 模型不能继续用 y=0 地面交点的小圆来点选。渲染层按模型几何包围盒
    # 投影出屏幕命中区，app 优先采用它，点头部/炮塔/龙翼也不会漏选或选到
    # 背后的建筑；计算仅发生在鼠标操作时，不进入 render 热循环。
    assert "function unitModelPickBox(kind)" in render
    assert "entry.body.computeBoundingBox();" in render
    assert "function unitPickScore(unit, sx, sy)" in render
    assert "const padding = 8;" in render
    assert "unitPickScore: unitPickScore" in render
    assert "view3d.unitPickScore(unit, clickScreen.x, clickScreen.y)" in app
    assert "if (bestIsScreenUnit) { return; }" in app
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
    assert "晶刺：贴地锯齿晶螨" in render
    assert "虹视使：细长棱晶杖 + 发光面罩" in render
    assert "晶刺：贴地晶螨 + 锯齿背刺" in app
    assert "虹视使：细长杖 + 发光面罩" in app
    assert "爆裂魔仆：脉冲符核魔球" in app
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
    # 上面的房间上限循环把 index 重绑成了 int，这里读 hud（同一份 index.html）。
    assert "轨道天降" in hud
    assert "随机轨道打击，范围×5，默认关" in hud
    assert 'data-mode="orbital_rain"' in hud
    assert "orbitalRainToggle" in hud
    assert "轨道天降" in readme
    assert "setOrbitalRain" in app
    assert "function syncOrbitalRainToggle" in app
    assert "strike.radius" in app
    assert "vecScale.set(STRIKE_RADIUS," not in render
    assert "const ringR = (s.radius > 0) ? s.radius : STRIKE_RADIUS_FALLBACK;" in render

    # 可选开关「中立守卫」：默认开，大厅文案与房主同步函数在。
    assert "中立守卫" in hud
    assert "矿区中立单位，可关闭" in hud
    assert 'data-mode="neutral_camps"' in hud
    assert "neutralCampsToggle" in hud
    assert "中立守卫" in readme
    assert "setNeutrals" in app
    assert "function syncNeutralCampsToggle" in app
    assert "function roomHasNeutrals" in app

    # 可选模式「指挥官模式」：大厅开关、方针条、小地图焦点。
    assert "指挥官模式" in hud
    assert "手机下方针，执行层做微操，默认关" in hud
    assert 'data-mode="commander_mode"' in hud
    assert "commanderModeToggle" in hud
    assert 'id="commanderHud"' in hud
    assert 'data-intent="rush"' in hud
    assert 'data-intent="eco"' in hud
    assert 'data-intent="defend"' in hud
    assert 'data-intent="snipe"' in hud
    assert "指挥官模式" in readme
    assert "setCommanderMode" in app
    assert "function roomHasCommanderMode" in app
    assert "function sendCommanderIntent" in app
    assert "function commanderHudActive" in app
    assert ".game-screen.commander-play" in styles
    assert "方针条独占底栏" in styles
    assert "min-width: 0" in styles

    print("presentation rules ok: radar removed, shroud persists, vehicles distinct, maps use valleys, catalog from server")


if __name__ == "__main__":
    main()
