#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""彩蛋触发测试（非视觉）：
   1) 聊天密语「东风快递」只给说话者一条系统回句
   2) 连点己方指挥中心 / 魔法主堡 7 次才敬礼，途中断开会重置
   3) 军犬咬死法师/女巫按 18% 出一句；咬步兵或未过检定不出
   4) 单兵第 16 杀按阵营补授衔句，3/8 杀不说话
   5) 地图不再带装饰地标 / 木牌；陨石核仍是阻挡山体

视觉项（hq_salute 雷达加速、dog_arcane 紫金牙印）只在
render3d.js / app.js 里冒烟，见 presentation_rules_test 的字符串锁。
"""

from __future__ import print_function

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import easter_eggs
import server


class ScriptedRng(object):
    """tiny stand-in so crate/dog rolls stay deterministic in tests."""

    def __init__(self, randoms, choices=None):
        self.randoms = list(randoms)
        self.choices = list(choices or [])

    def random(self):
        return self.randoms.pop(0)

    def choice(self, seq):
        if self.choices:
            return self.choices.pop(0)
        return seq[0]


def make_room(tag, map_id=None, factions=None):
    a = server.create_human("甲", server.COLORS[0])
    b = server.create_human("乙", server.COLORS[1])
    if factions:
        a["faction"] = factions[0]
        b["faction"] = factions[1]
    room = {
        "id": tag, "name": "egg test", "status": "lobby",
        "hostId": a["id"],
        "players": {a["id"]: a, b["id"]: b},
        "chat": [], "game": None, "createdAt": time.time(),
    }
    if map_id:
        room["selectedMap"] = map_id
    server.start_game(room)
    return room, a, b


def chat_texts(view):
    return [item["message"] for item in view["chat"]]


def main():
    print("=== Test 1: 东风快递密语只给说话者 ===")
    assert easter_eggs.chat_reply("东风快递") == easter_eggs.CHAT_REPLY
    assert easter_eggs.chat_reply("东风快递！") == easter_eggs.CHAT_REPLY
    assert easter_eggs.chat_reply("  东风快递  ") == easter_eggs.CHAT_REPLY
    assert easter_eggs.chat_reply("东风快递到了") is None
    assert easter_eggs.chat_reply("how do you turn this on") is None

    room, a, b = make_room("EGG-CHAT")
    server.post_player_chat(room, a, "东风快递")
    server.post_player_chat(room, b, "收到")
    view_a = server.public_room(room, viewer_id=a["id"])
    view_b = server.public_room(room, viewer_id=b["id"])
    assert "东风快递" in chat_texts(view_a)
    assert easter_eggs.CHAT_REPLY in chat_texts(view_a)
    assert "东风快递" in chat_texts(view_b)
    assert easter_eggs.CHAT_REPLY not in chat_texts(view_b)
    assert "收到" in chat_texts(view_a) and "收到" in chat_texts(view_b)
    print("  短语匹配 / 密语过滤: PASS")

    print("\n=== Test 2: 指挥中心七连点 ===")
    clock = [1000.0]

    def now_at(ts):
        def _now():
            return ts
        return _now

    room, a, b = make_room("EGG-HQ")
    game = room["game"]
    hq = next(s for s in game["structures"]
              if s["owner"] == a["id"] and server.structure_role(s["kind"]) == "hq")
    enemy_hq = next(s for s in game["structures"]
                    if s["owner"] == b["id"] and server.structure_role(s["kind"]) == "hq")

    saved_now = server.now
    try:
        for i in range(6):
            server.now = now_at(clock[0] + i * 0.4)
            fired = server.tap_own_hq(room, a, hq["id"])
            assert fired is False, "tap %d should not salute" % (i + 1)
        assert a["hqTaps"] == 6
        server.now = now_at(clock[0] + 6 * 0.4)
        assert server.tap_own_hq(room, a, hq["id"]) is True
        assert a["hqTaps"] == 0
        view_a = server.public_room(room, viewer_id=a["id"])
        view_b = server.public_room(room, viewer_id=b["id"])
        assert easter_eggs.HQ_REPLY_TECH in chat_texts(view_a)
        assert easter_eggs.HQ_REPLY_TECH not in chat_texts(view_b)
        salute = [e for e in game["effects"] if e.get("type") == "hq_salute"]
        smoke = [e for e in game["effects"] if e.get("type") == "smoke"]
        assert len(salute) == 1 and salute[0]["x"] == hq["x"]
        assert smoke, "salute should puff extra smoke"
        # 点错别人的主堡不计
        before = a["hqTaps"]
        server.now = now_at(2000.0)
        assert server.tap_own_hq(room, a, enemy_hq["id"]) is False
        assert a["hqTaps"] == before
        # 窗口断开后要从头数
        server.now = now_at(3000.0)
        assert server.tap_own_hq(room, a, hq["id"]) is False
        server.now = now_at(3000.0 + easter_eggs.HQ_TAP_WINDOW + 0.5)
        assert server.tap_own_hq(room, a, hq["id"]) is False
        assert a["hqTaps"] == 1
    finally:
        server.now = saved_now

    room_m, ma, _mb = make_room("EGG-MHQ", factions=("magic", "tech"))
    mhq = next(s for s in room_m["game"]["structures"]
               if s["owner"] == ma["id"] and s["kind"] == "mhq")
    saved_now = server.now
    try:
        for i in range(7):
            server.now = now_at(4000.0 + i * 0.3)
            fired = server.tap_own_hq(room_m, ma, mhq["id"])
        assert fired is True
        assert easter_eggs.HQ_REPLY_MAGIC in chat_texts(
            server.public_room(room_m, viewer_id=ma["id"]))
    finally:
        server.now = saved_now
    print("  七连点 / 窗口重置 / 阵营台词 / 点错不计: PASS")

    print("\n=== Test 3: 军犬咬法师出句率 ===")
    assert easter_eggs.should_dog_quip("dog", "mage", ScriptedRng([0.0]))
    assert easter_eggs.should_dog_quip("dog", "frost", ScriptedRng([0.17]))
    assert not easter_eggs.should_dog_quip("dog", "frost", ScriptedRng([0.18]))
    assert not easter_eggs.should_dog_quip("dog", "rifle", ScriptedRng([0.0]))
    assert not easter_eggs.should_dog_quip("rifle", "mage", ScriptedRng([0.0]))
    assert easter_eggs.dog_quip(ScriptedRng([], [easter_eggs.DOG_LINES[1]])) == (
        easter_eggs.DOG_LINES[1])

    room, a, b = make_room("EGG-DOG")
    game = room["game"]
    dog = server.make_unit("dog", a["id"], 800, 800)
    game["units"].append(dog)
    game["_egg_rng"] = ScriptedRng([0.01], [easter_eggs.DOG_LINES[0]])
    victim = server.make_unit("mage", b["id"], 9000, 9000)
    victim["hp"] = 1.0
    game["units"].append(victim)
    game["effects"][:] = []
    room["chat"][:] = []
    server.apply_damage(room, victim, 9999.0, a["id"], "bite", game, dog["id"])
    assert victim["hp"] == 0
    assert easter_eggs.DOG_LINES[0] in chat_texts(
        server.public_room(room, viewer_id=a["id"]))
    bites = [e for e in game["effects"]
             if e.get("type") == "impact" and e.get("kind") == "dog_arcane"]
    assert len(bites) == 1, bites

    # 检定没过：死了也不说话
    room, a, b = make_room("EGG-DOG-MISS")
    game = room["game"]
    dog = server.make_unit("dog", a["id"], 800, 800)
    game["units"].append(dog)
    game["_egg_rng"] = ScriptedRng([0.99])
    victim = server.make_unit("frost", b["id"], 9000, 9000)
    victim["hp"] = 1.0
    game["units"].append(victim)
    room["chat"][:] = []
    server.apply_damage(room, victim, 9999.0, a["id"], "bite", game, dog["id"])
    for line in easter_eggs.DOG_LINES:
        assert line not in chat_texts(server.public_room(room, viewer_id=a["id"]))

    # 咬死步兵：永不触发
    room, a, b = make_room("EGG-DOG-RIFLE")
    game = room["game"]
    dog = server.make_unit("dog", a["id"], 800, 800)
    game["units"].append(dog)
    game["_egg_rng"] = ScriptedRng([0.0], [easter_eggs.DOG_LINES[0]])
    victim = server.make_unit("rifle", b["id"], 9000, 9000)
    victim["hp"] = 1.0
    game["units"].append(victim)
    room["chat"][:] = []
    server.apply_damage(room, victim, 9999.0, a["id"], "bite", game, dog["id"])
    assert easter_eggs.DOG_LINES[0] not in chat_texts(
        server.public_room(room, viewer_id=a["id"]))
    print("  法师/女巫概率句 / 步兵不触发: PASS")

    print("\n=== Test 4: 十六杀授衔按阵营 ===")
    room, a, b = make_room("EGG-PROMO", factions=("tech", "magic"))
    game = room["game"]
    shooter = server.make_unit("rifle", a["id"], 500, 500)
    game["units"].append(shooter)
    for kill_no in range(1, 17):
        target = server.make_unit("rifle", b["id"], 9000, 9000)
        target["hp"] = 1.0
        game["units"].append(target)
        room["chat"][:] = []
        server.apply_damage(room, target, 9999.0, a["id"], "bullet",
                            game, shooter["id"])
        texts = chat_texts(server.public_room(room, viewer_id=a["id"]))
        line = easter_eggs.promote_16_line(a)
        if kill_no == 16:
            assert line in texts, texts
        else:
            assert line not in texts
        game["units"].remove(target)

    room, a, b = make_room("EGG-PROMO-M", factions=("magic", "tech"))
    game = room["game"]
    shooter = server.make_unit("mage", a["id"], 500, 500)
    game["units"].append(shooter)
    shooter["kills"] = 15
    target = server.make_unit("rifle", b["id"], 9000, 9000)
    target["hp"] = 1.0
    game["units"].append(target)
    room["chat"][:] = []
    server.apply_damage(room, target, 9999.0, a["id"], "magic", game, shooter["id"])
    assert easter_eggs.PROMOTE_16_MAGIC % a["name"] in chat_texts(
        server.public_room(room, viewer_id=b["id"]))
    print("  只在 16 杀说话，钢铁/秘法会各一句: PASS")

    print("\n=== Test 5: 地图无装饰地标 ===")
    assert not hasattr(easter_eggs, "CRATER_LANDMARK")
    assert not hasattr(easter_eggs, "inspect_landmark")
    assert not hasattr(easter_eggs, "crater_landmark_on_core")
    for map_id, map_def in server.MAPS.items():
        assert not map_def.get("landmarks"), map_id
        assert "先挖先富" not in str(map_def)
    for map_id, core in (("gold_crater", (5000, 3200)),
                         ("gold_crater_small", (3200, 3200))):
        room, a, b = make_room("EGG-CRATER-%s" % map_id, map_id=map_id)
        assert not (room["game"]["terrain"].get("landmarks") or [])
        pub = server.PUBLIC_MAPS[map_id]
        assert not pub.get("landmarks")
        # 陨石核仍是山体：采矿车走不进去
        terrain = server.game_terrain(room["game"])
        assert terrain.blocked(core[0], core[1]), map_id
    print("  全图无地标 / 陨石核仍阻挡: PASS")

    print("\n=== 彩蛋测试全部通过 ===")


if __name__ == "__main__":
    main()
