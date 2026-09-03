#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""秘法巨龙「奥德赛」硬表面换皮的回归测试。

这次换皮是纯表现层的：服务端目录一个字段没动，客户端换掉模型、调色板、
弹道特效和小地图图标。所以这里锁三件事——

  1. 战斗数值确实没跟着模型一起改；
  2. 玩家色配额没有掉回上一版玉龙那种「整只龙只有一块背甲随玩家变色」；
  3. 环绕核球层仍然是一个实例一台龙，且整圈都待在主模型的轮廓以内。
"""

from __future__ import print_function

import io
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import server


def read(relative):
    with io.open(os.path.join(ROOT, relative), encoding="utf-8") as handle:
        return handle.read()


def slice_between(text, start, end):
    head = text.index(start)
    return text[head:text.index(end, head)]


def test_catalog_untouched():
    """换皮不许碰玩法：伤害、射程、溅射、护甲判定和弹种键全部照旧。"""
    dragon = server.UNIT_TYPES["dragon"]
    assert dragon["projectile"] == "fireball"
    assert dragon["damage"] == 95.0
    assert dragon["range"] == 260.0
    assert dragon["splash"] == 60.0
    assert dragon["projectileSpeed"] == 520.0
    assert dragon["armor"] == "arcane"
    assert dragon["damageType"] == "magic"
    assert dragon["requires"] == ["mspring"]
    assert dragon["size"] == 24.0


def test_owner_color_quota():
    """玩家色配额。

    上一版玉龙整只只有一块 `box(14.0, 0.75, 6.2, ..., 0.90)` 背甲随玩家变色，
    按包围盒表面积算只占 5.2%，四家的龙在小地图和远景基本分不出主人。奥德赛
    那套黑铬 + 固定霓虹如果照搬只会更糟，所以这一版把俯视看得见的大面——背甲、
    颈甲、尾甲、顶冠、侧裙、翼板——全部放到玩家色实色上，脊梁、节缝和胸核放到
    玩家色自发光上，实测占到 42.9%。

    Python 侧没法执行 three.js 去重算面积，这里退一步锁数量与位置：只要玩家色
    零件的条数掉下来，或者关键部位不再挂玩家色，就说明配额被改回去了。
    """
    render = read("public/render3d.js")
    builder = slice_between(render, u"  dragon: function () {", u"  warden: function () {")
    assert "const TEAM = 0.94;" in builder
    assert "const TEAM_LIT = 1.55;" in builder
    # 含两条 const 声明本身；实色 >= 10 件、自发光 >= 6 件
    assert len(re.findall(r"\bTEAM\b", builder)) >= 11
    assert len(re.findall(r"\bTEAM_LIT\b", builder)) >= 7
    # 关键部位逐个点名，避免「条数够了但全挂在小零件上」
    for anchor, paint in (
            (u"taperedBox(13.6, 11.0", "TEAM"),      # 躯干第一片背甲
            (u"box(41, 2.3, 3.4", "TEAM_LIT"),       # 贯穿首尾的能量脊梁
            (u"box(4.4, 0.7, 4.8", "TEAM"),          # 头顶识别冠
            (u"cyl(3.0, 3.4, 2.4", "TEAM_LIT")):     # 胸核
        line = [row for row in builder.split("\n") if anchor in row]
        assert line, anchor
        assert paint in line[0], (anchor, line[0])
    # 远景低模同样要读得出主人：脊线加粗 + 背甲 + 两片翼板
    lod = slice_between(render, u"    if (kind === 'dragon') {", u"    if (kind === 'warden') {")
    assert u"box(30, 1.8, 3.6, -3.0, 10.4, 0, 1.55)" in lod
    assert lod.count("0.94") >= 4


def test_orbit_layer():
    """环绕核球：一台龙一个实例，且整圈都在主模型轮廓以内。"""
    render = read("public/render3d.js")
    assert "function dragonOrbitParts()" in render
    assert "function ensureDragonOrbitMesh(needed)" in render
    assert "const dragons = byKind.get('dragon');" in render
    # 和天启双臂同一套：合进一份几何体、原点即环绕中心、远景 LOD 不跑这层
    orbit = slice_between(render, u"    /* --- 秘法巨龙：环绕核球 --- */",
                          u"    /* --- 建筑 --- */")
    assert "if (!useSimple) {" in orbit
    assert "dragonOrbitLocal.makeTranslation(DRAGON_ORBIT_PIVOT_X, 0, 0);" in orbit
    assert "dragonOrbitLocal.makeRotationY(" in orbit
    assert "orbs.setMatrixAt(i, matrix);" in orbit
    # 场上没有龙时整层隐藏，而不是只把 count 归零
    assert "dragonOrbitMesh.visible = false;" in orbit

    def number(name):
        match = re.search(r"const %s = ([0-9.]+);" % name, render)
        assert match, name
        return float(match.group(1))

    pivot_x = number("DRAGON_ORBIT_PIVOT_X")
    pivot_y = number("DRAGON_ORBIT_PIVOT_Y")
    radius = number("DRAGON_ORBIT_RADIUS")
    # 主模型（模型坐标）的包围盒：x[-30.3, 33.5] y[0.4, 22.3] z[±26.3]，
    # 核球半径 1.15。加了这层单位在战场上不能变大，所以整圈必须包得进去。
    orb = 1.15
    assert pivot_x + radius + orb <= 33.5, pivot_x + radius + orb
    assert pivot_x - radius - orb >= -30.3, pivot_x - radius - orb
    assert pivot_y + orb <= 22.3, pivot_y + orb
    assert radius + orb <= 26.3, radius + orb
    # 环要落在颈甲顶面（y 15.6）之上，否则会插进脖子里
    assert pivot_y - orb >= 15.6, pivot_y - orb


def test_surface_and_faction():
    """硬表面材质 + 阵营归属：巨龙改走金属，但仍是秘法会的单位。"""
    render = read("public/render3d.js")
    assert "const HIDE_UNIT_KINDS = { dog: 1, panther: 1 };" in render
    assert re.search(r"MAGIC_UNIT_KINDS = \{[^}]*dragon: 1", render, re.S)
    assert re.search(r"OCCLUSION_BAKED_KINDS = \{[^}]*dragon: 1", render, re.S)
    # 秘法会的金饰必须留住，否则黑铬会读成钢铁军团的涂装
    assert "MAT.odyGold" in render
    for jade in ("jadeScale", "jadeBelly", "jadeMembrane", "jadeGlow"):
        assert jade not in render, jade


def test_client_ui_follows():
    """小地图图标和兵种说明跟着一起换，别留一只绿玉龙在小地图上。"""
    app = read("public/app.js")
    for token in ("P_ODY_D", "P_ODY", "P_ODY_L", "P_ODY_SEAM", "P_ODY_CORE"):
        assert token in app, token
    assert "P_JADE" not in app
    assert u"奥术龙息" in app


def main():
    test_catalog_untouched()
    test_owner_color_quota()
    test_orbit_layer()
    test_surface_and_faction()
    test_client_ui_follows()
    print("dragon odyssey ok: catalog untouched, owner color quota kept, "
          "orbit layer inside silhouette")


if __name__ == "__main__":
    main()
