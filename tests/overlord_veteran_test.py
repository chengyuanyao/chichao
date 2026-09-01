#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""天启坦克「战功换形态」的回归检查：

   1) veteran_projectile 的阈值与 tick_units 的 3/8/16 军衔线一致
   2) launch_projectile 只换 kind，不在既有军衔倍率外追加数值变化
   3) 建筑（炮塔）没有 kills，永远走目录里的原弹种
   4) 客户端有三副形态、三个实例池，以及两种新弹道的表现定义
"""

from __future__ import print_function

import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import server


def read(relative):
    with open(os.path.join(ROOT, relative), "r", encoding="utf-8") as handle:
        return handle.read()


def make_room():
    a = server.create_human("甲", server.COLORS[0])
    b = server.create_human("乙", server.COLORS[1])
    room = {
        "id": "APOC01", "name": "天启测试", "status": "lobby",
        "hostId": a["id"],
        "players": {a["id"]: a, b["id"]: b},
        "chat": [], "game": None, "createdAt": time.time(),
    }
    server.start_game(room)
    return room, a, b


def fire(game, attacker, target, definition):
    game["projectiles"][:] = []
    game["effects"][:] = []
    server.launch_projectile(game, attacker, target, definition)
    assert len(game["projectiles"]) == 1
    return game["projectiles"][-1]


def muzzle(game):
    shots = [e for e in game["effects"] if e.get("type") == "muzzle"]
    assert len(shots) == 1, shots
    return shots[0]


def main():
    print("=== Test 1: 弹种阈值贴着 3/8/16 军衔线 ===")
    expected = [
        (0, "shell"), (2, "shell"),
        (3, "plasma"), (7, "plasma"),
        (8, "plasmalance"), (15, "plasmalance"),
        (16, "plasmalance"), (40, "plasmalance"),
    ]
    for kills, want in expected:
        got = server.veteran_projectile("overlord", kills, "shell")
        assert got == want, "kills=%d -> %s, expected %s" % (kills, got, want)
    # 没有登记的兵种不受影响，杀再多也用目录里的弹种
    for kind in ("tank", "artillery", "prism", "dragon"):
        base = server.UNIT_TYPES[kind]["projectile"]
        assert server.veteran_projectile(kind, 99, base) == base, kind
    print("  0/2→shell，3/7→plasma，8/15/16/40→plasmalance；其他兵种不变: PASS")

    print("\n=== Test 2: 换弹只改表现，不额外叠加弹体数值 ===")
    room, a, b = make_room()
    game = room["game"]
    definition = server.UNIT_TYPES["overlord"]
    target = server.make_unit("rifle", b["id"], 900, 900)
    game["units"].append(target)

    shots = {}
    for kills in (0, 3, 8, 16):
        attacker = server.make_unit("overlord", a["id"], 800, 900)
        attacker["kills"] = kills
        game["units"].append(attacker)
        shots[kills] = fire(game, attacker, target, definition)

    assert shots[0]["kind"] == "shell"
    assert shots[3]["kind"] == "plasma"
    assert shots[8]["kind"] == "plasmalance"
    assert shots[16]["kind"] == "plasmalance"
    for kills, projectile in shots.items():
        assert projectile["damage"] == definition["damage"], kills
        assert projectile["speed"] == definition["projectileSpeed"], kills
        assert projectile["splash"] == definition.get("splash"), kills
        assert projectile["damageType"] == definition["damageType"], kills
    # 公开负载把 kind 带给客户端，客户端才能换弹道表现
    assert server.public_projectile(shots[8])["kind"] == "plasmalance"

    # 炮口闪光：换过装的才标注弹种，人形态靠它驱动抬臂动画（弹道特效关掉也有效）；
    # 没换装的仍旧不带 kind，客户端照原路按最近弹丸去猜，其他兵种表现不变。
    for kills, want in ((0, None), (3, "plasma"), (8, "plasmalance"), (16, "plasmalance")):
        attacker = server.make_unit("overlord", a["id"], 800, 900)
        attacker["kills"] = kills
        fire(game, attacker, target, definition)
        got = muzzle(game).get("kind")
        assert got == want, "kills=%d muzzle kind %s, expected %s" % (kills, got, want)
    rifle = server.make_unit("rifle", a["id"], 850, 900)
    rifle["kills"] = 30
    fire(game, rifle, target, server.UNIT_TYPES["rifle"])
    assert "kind" not in muzzle(game), muzzle(game)
    print("  0/3/8/16 → shell/plasma/plasmalance/plasmalance，"
          "同一军衔倍率入参下伤害 %.0f、速度 %.0f、溅射 %.0f、类型 %s 不额外变化: PASS" % (
              definition["damage"], definition["projectileSpeed"],
              definition["splash"], definition["damageType"]))

    print("\n=== Test 3: 换装只认 kind，炮塔永远是目录弹种 ===")
    turret_def = server.STRUCTURE_TYPES["turret"]
    turret = server.make_structure("turret", a["id"], 820, 940)
    game["structures"].append(turret)
    shot = fire(game, turret, target, turret_def)
    assert shot["kind"] == turret_def["projectile"], shot["kind"]
    # 就算硬塞一个战功字段，kind 不在换装表里也不能换弹
    turret["kills"] = 40
    shot = fire(game, turret, target, turret_def)
    assert shot["kind"] == turret_def["projectile"], shot["kind"]
    print("  炮塔弹种仍是 %s（塞了 40 杀也不换）: PASS" % shot["kind"])

    print("\n=== Test 4: 客户端三副形态 + 两种新弹道 ===")
    render = read("public/render3d.js")
    # 三副形态各自一份合并几何体 + 一个实例池，不能退化成逐单位 draw call
    assert "function apocalypseTankParts(skin)" in render
    assert "function apocalypseTitanParts()" in render
    assert "function apocalypseArmParts()" in render
    assert "overlord: function () { return apocalypseTankParts(APOC_SKIN_LINE); }" in render
    assert "overlord_v1: function () { return apocalypseTankParts(APOC_SKIN_VET); }" in render
    assert "overlord_v2: function () { return apocalypseTitanParts(); }" in render
    # 军衔线必须和服务端同步
    assert "const APOC_VETERAN_KILLS = 3;" in render
    assert "const APOC_TITAN_KILLS = 8;" in render
    assert "function unitVisualKind(unit)" in render
    assert "byKind.get(vkind)" in render
    # 一星换涂装：两套皮共用同一副载具模型
    assert "const APOC_SKIN_LINE = {" in render
    assert "const APOC_SKIN_VET = {" in render
    assert "apocVetTrim:" in render and "apocIon:" in render
    # 二星抬臂开炮：手臂是单独一层实例，靠炮口特效回指开火者
    assert "function ensureApocArmMesh(needed)" in render
    assert "function triggerApocFire(x, y)" in render
    assert "fxKind === 'plasmalance'" in render
    assert "apocArmLocal.makeRotationZ(-angle)" in render
    # 两种新弹道的表现定义
    assert "plasma: { len:" in render
    assert "plasmalance: { len:" in render
    assert "look === 'plasma'" in render
    assert "kind === 'plasma' || kind === 'plasmalance'" in render
    # 远景 LOD 也要跟着分形态，否则拉远一格模型就变回原样
    assert "kind === 'overlord' || kind === 'overlord_v1'" in render
    assert "kind === 'overlord_v2'" in render
    assert "overlord: 1.30, overlord_v1: 1.30, overlord_v2: 1.06," in render
    app = read("public/app.js")
    assert "二星展开人形态双臂炮" in app
    print("  三副形态/两种弹道/抬臂动画的客户端定义齐全: PASS")

    print("\n天启坦克战功换形态：全部通过")


if __name__ == "__main__":
    main()
