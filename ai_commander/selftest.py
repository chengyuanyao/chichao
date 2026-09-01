#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ai_commander 的离线自检：不需要 LLM，也不需要跑起服务器。

    python ai_commander/selftest.py

每一条都钉住一个具体的判断：护甲/克制读的是不是服务端那张表、固定模板
会不会在换了对手阵营之后变、被克制到零伤害的兵会不会被换掉、接管之后
AI 是不是真的在造楼出兵、以及出错时会不会安全退回内置逻辑。
"""

from __future__ import print_function

import os
import sys
import time

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

import server                                              # noqa: E402
from ai_commander import codex, config, hook, llm, planner, templates  # noqa: E402
from ai_commander.commander import (STATE_KEY, WOUNDED_FLOOR,   # noqa: E402
                                    Commander)

PASSED = []


def check(label, condition, detail=""):
    if not condition:
        raise AssertionError("%s  %s" % (label, detail))
    PASSED.append(label)
    print("  PASS  %s" % label)


def make_room(tag, bots=1, bot_faction="magic", human_faction="tech"):
    human = server.create_human("HUMAN", server.COLORS[0])
    human["faction"] = human_faction
    players = {human["id"]: human}
    room = {
        "id": tag, "name": "ai_commander selftest", "status": "lobby",
        "hostId": human["id"], "players": players,
        "chat": [], "game": None, "createdAt": time.time(),
    }
    made = []
    for _ in range(bots):
        bot = server.create_bot(room)
        bot["faction"] = bot_faction
        bot["team"] = 0
        made.append(bot)
    server.start_game(room)
    room["game"]["terrainCtx"] = server.FLAT_TERRAIN
    room["game"]["botClock"] = 999.0
    room["game"]["victoryClock"] = 999.0
    return room, human, made


def give(game, owner_id, kind, x=900.0, y=900.0):
    structure = server.make_structure(kind, owner_id, x, y, True)
    game["structures"].append(structure)
    return structure


def owned_kinds(game, owner_id):
    return sorted(s["kind"] for s in game["structures"] if s["owner"] == owner_id)


def queued_units(game, owner_id):
    out = []
    for structure in game["structures"]:
        if structure["owner"] != owner_id:
            continue
        for item in structure.get("queue") or []:
            out.append(item["kind"])
    return out


# ---------------------------------------------------------------- 1. 克制表
def test_counter_table():
    print("\n=== 1. 克制系数直接读 server.DAMAGE_MULTIPLIER ===")
    check("穿甲对重甲 ×2.10", abs(codex.counter("ap", "tank") - 2.10) < 1e-6)
    check("穿甲对魔导甲只有 ×1.00（别拿歼击车反秘法会）",
          abs(codex.counter("ap", "dragon") - 1.00) < 1e-6)
    check("子弹对魔导甲 ×1.50", abs(codex.counter("bullet", "mage") - 1.50) < 1e-6)
    check("磁暴对魔导甲 ×1.60", abs(codex.counter("tesla", "mage") - 1.60) < 1e-6)
    check("攻城对建筑 ×1.80、对重甲只有 ×0.25",
          abs(codex.counter("siege", "power") - 1.80) < 1e-6
          and abs(codex.counter("siege", "tank") - 0.25) < 1e-6)
    check("混甲取平均：穿甲对晶铠卫士 (2.10+0.65)/2",
          abs(codex.counter("ap", "warden") - 1.375) < 1e-6)
    check("扑咬对构装体是硬 0（巨龙护甲是 arcane 但算载具）",
          codex.counter("bite", "dragon") == 0.0
          and codex.counter("bite", "golem") == 0.0)
    check("扑咬对肉身魔导还是 ×1.50",
          abs(codex.counter("bite", "mage") - 1.50) < 1e-6)
    check("自爆单位按死亡爆炸算输出，不是 0",
          codex.sustained_damage("bomb_truck") > 0)
    check("卡车/魔仆只对建筑与矿车 ×1.50，其他单位（含天启/巨龙）×0.80",
          all(codex.attacker_counter(kind, "power") == 1.50
              and codex.attacker_counter(kind, "harvester") == 1.50
              and codex.attacker_counter(kind, "mharvester") == 1.50
              and codex.attacker_counter(kind, "rifle") == 0.80
              and codex.attacker_counter(kind, "tank") == 0.80
              and codex.attacker_counter(kind, "mage") == 0.80
              and codex.attacker_counter(kind, "overlord") == 0.80
              and codex.attacker_counter(kind, "dragon") == 0.80
              for kind in ("bomb_truck", "hexling")))
    check("护甲表覆盖 catalog 里全部兵种",
          all(codex.armor_of(kind) for kind in server.UNIT_TYPES))


# ---------------------------------------------------------------- 2. 模板
def test_templates():
    print("\n=== 2. 固定模板按局势选，换对手就换配比 ===")
    arcane = codex.enemy_profile({"dragon": 6, "mage": 4})
    heavy = codex.enemy_profile({"tank": 6, "tank_destroyer": 3})
    infantry = codex.enemy_profile({"rifle": 10, "rocket": 4})

    check("巨龙+法师被识别成魔导甲阵容",
          codex.dominant_armor(arcane) == "arcane", codex.dominant_armor(arcane))
    check("坦克阵容被识别成重甲", codex.dominant_armor(heavy) == "heavy")
    check("步兵阵容被识别成步兵甲", codex.dominant_armor(infantry) == "infantry")

    have = set(["hq", "power", "refinery", "barracks", "factory"])
    vs_arcane = planner.make_plan("tech", set(["factory", "barracks"]), 200.0,
                                  arcane, have)
    vs_heavy = planner.make_plan("tech", set(["factory", "barracks"]), 200.0,
                                 heavy, have)
    check("换了对手阵营配比确实不一样",
          vs_arcane["mix"] != vs_heavy["mix"],
          "%s vs %s" % (vs_arcane["mix"], vs_heavy["mix"]))
    check("打秘法会不会把坦克歼击车当主力",
          "tank_destroyer" not in vs_arcane["mix"], str(vs_arcane["mix"]))
    check("打钢铁重甲会用上穿甲",
          "tank_destroyer" in vs_heavy["mix"], str(vs_heavy["mix"]))
    for kind in vs_arcane["mix"]:
        check("打秘法会选的 %s 对魔导甲有效" % kind,
              codex.effective_dps(kind, "dragon") > 0
              or codex.effective_dps(kind, "mage") > 0)

    every = []
    for faction in ("tech", "magic"):
        for bucket in templates.ARMOR_BUCKETS:
            for phase in templates.PHASES:
                entry = templates.lookup(faction, bucket, phase)
                for kind in entry["mix"]:
                    spec = server.UNIT_TYPES.get(kind)
                    every.append(bool(spec)
                                 and spec.get("faction", "tech") == faction)
    check("36 个模板格子里的兵种全部存在且阵营正确", all(every) and len(every) > 60)


# ---------------------------------------------------------------- 3. 安全过滤
def test_sanitize():
    print("\n=== 3. 打不动的兵会被换掉 ===")
    constructs = codex.enemy_profile({"dragon": 8, "colossus": 4})
    have = set(["hq", "power", "refinery", "barracks", "factory"])
    mix, replaced = planner.sanitize_mix({"dog": 5, "rifle": 2}, "tech",
                                         constructs, have)
    check("军犬对全构装体阵容会被换掉", "dog" not in mix,
          "%s replaced=%s" % (mix, replaced))
    check("换出来的兵确实打得动",
          all(codex.unit_value(kind, constructs, have)["dps"] > 0 for kind in mix))

    mages = codex.enemy_profile({"mage": 6, "imp": 6})
    mix2, _ = planner.sanitize_mix({"dog": 5, "rifle": 2}, "tech", mages, have)
    check("对肉身法师阵容军犬会被保留", "dog" in mix2, str(mix2))

    plan = planner.make_plan("tech", set(["barracks"]), 30.0,
                             codex.enemy_profile({}, ["magic"]),
                             set(["hq", "power", "barracks"]))
    buildable = [k for k in plan["mix"]
                 if not (server.UNIT_TYPES[k].get("requires") or [])]
    check("开局配比里至少有一个当前就能造的兵", bool(buildable), str(plan["mix"]))

    late = planner.make_plan("tech", set(["factory", "barracks", "repair"]), 400.0,
                             constructs,
                             set(["hq", "power", "refinery", "barracks", "factory"]))
    for kind in late["mix"]:
        for need in server.UNIT_TYPES[kind].get("requires") or []:
            check("%s 的前置 %s 进了建造序列" % (kind, need), need in late["build"],
                  str(late["build"]))


# ---------------------------------------------------------------- 4. 指令校验
def test_directive():
    print("\n=== 4. LLM 指令解析与校验 ===")
    allowed_units = set(codex.faction_combat_units("tech").keys())
    allowed_structures = set(["power", "factory", "barracks"])
    good = llm.parse_directive(
        '随便说点什么 {"army_mix": {"tesla": 4, "dragon": 9, "nonsense": 2},'
        ' "attack_at": 15, "max_turrets": 99, "note": "换磁暴"} 后面还有话',
        allowed_units, allowed_structures)
    check("能从啰嗦的回答里抠出 JSON", good is not None)
    check("敌方阵营的兵被过滤掉", "dragon" not in good["army_mix"])
    check("不存在的兵被过滤掉", "nonsense" not in good["army_mix"])
    check("本阵营的兵保留", good["army_mix"].get("tesla") == 4)
    check("越界数值被夹住", good["max_turrets"] == 6, str(good))
    check("垃圾输入返回 None", llm.parse_directive("我不知道", allowed_units,
                                                   allowed_structures) is None)
    check("空 JSON 返回 None", llm.parse_directive("{}", allowed_units,
                                                   allowed_structures) is None)


# ---------------------------------------------------------------- 5. 实跑
def test_live_ticks():
    print("\n=== 5. 接管后真的在造楼、出兵、打人 ===")
    settings = config.Settings()
    settings.mode = "all"
    settings.verbose = False
    hook.install(settings, log=lambda *a: None)
    try:
        room, human, bots = make_room("AIC-LIVE", bots=1, bot_faction="tech")
        game = room["game"]
        bot = bots[0]
        bot["cash"] = 20000

        for _ in range(40):
            server.tick_bots(room)
            # 建筑读条在真实循环里要花时间，自检里直接放行
            queue = bot.get("buildQueue") or []
            if queue:
                queue[0]["ready"] = True
                queue[0]["remaining"] = 0.0
            bot["cash"] = 20000
        kinds = owned_kinds(game, bot["id"])
        check("造出了发电站/精炼厂等基础建筑", len(kinds) >= 4, str(kinds))
        check("建起了兵营或工厂",
              any(server.structure_role(k) in ("barracks", "factory") for k in kinds),
              str(kinds))
        check("生产队列里有战斗单位或已经出了兵",
              bool(queued_units(game, bot["id"]))
              or any(u["owner"] == bot["id"] for u in game["units"]),
              str(queued_units(game, bot["id"])))
        check("AI 没有崩过（没被标记为退回内置逻辑）",
              not bot.get("_aic_failed"))
        mem = bot.get(STATE_KEY) or {}
        check("状态挂在自己的私有键上", STATE_KEY in bot)
        check("普查表结构存在", isinstance(mem.get("census"), dict))
    finally:
        hook.uninstall()


def test_mode_first():
    print("\n=== 6. first 模式：同房间里新旧 AI 各一个 ===")
    settings = config.Settings()
    settings.mode = "first"
    hook.install(settings, log=lambda *a: None)
    try:
        room, human, bots = make_room("AIC-MIX", bots=2, bot_faction="tech")
        for bot in bots:
            bot["cash"] = 9000
        server.tick_bots(room)
        first_taken = STATE_KEY in bots[0]
        second_taken = STATE_KEY in bots[1]
        check("第一个 AI 被接管", first_taken)
        check("第二个 AI 留给原版", not second_taken)
        check("两个 AI 都还是 AI（临时改的 isBot 已还原）",
              bots[0]["isBot"] and bots[1]["isBot"])
        check("原版 AI 照常运转（内置逻辑建了它自己的 _ai 状态）",
              bots[1].get("_ai") is not None)
    finally:
        hook.uninstall()


def test_failure_fallback():
    print("\n=== 7. 指挥官抛异常时安全退回内置逻辑 ===")
    settings = config.Settings()
    hook.install(settings, log=lambda *a: None)
    try:
        room, human, bots = make_room("AIC-BOOM", bots=1, bot_faction="tech")
        bot = bots[0]
        bot["cash"] = 9000

        original_tick = hook._STATE["commander"].tick

        def boom(_room, _bot):
            raise RuntimeError("故意炸一个")

        hook._STATE["commander"].tick = boom
        server.tick_bots(room)
        check("出错的 AI 被标记", bool(bot.get("_aic_failed")))
        check("这一跳仍然交给了内置 AI（建筑队列有东西）",
              bool(bot.get("buildQueue")) or bool(bot.get("_ai")))
        hook._STATE["commander"].tick = original_tick
        server.tick_bots(room)
        check("标记之后不再尝试新 AI", bool(bot.get("_aic_failed")))
    finally:
        hook.uninstall()


# ------------------------------------------------- 8. 已修问题的回归
def _plain_commander():
    settings = config.Settings()
    settings.verbose = False
    return Commander(settings, log=lambda *a: None)


def _neutral_guard(game, x, y, kind="rifle"):
    guard = server.make_unit(kind, server.NEUTRAL_OWNER, x, y)
    game["units"].append(guard)
    return guard


def test_regressions():
    print("\n=== 8. 已修问题的回归 ===")
    brain = _plain_commander()

    # -- 中立矿营守军不是敌人 --------------------------------------
    room, human, bots = make_room("AIC-NEUTRAL", bots=1, bot_faction="tech",
                                  human_faction="magic")
    game = room["game"]
    bot = bots[0]
    hq = server.bot_own_hq(game, bot["id"])
    _neutral_guard(game, hq["x"] + 60, hq["y"])          # 步兵甲，就在家门口
    _neutral_guard(game, hq["x"] - 60, hq["y"], "rocket")
    mem = brain.state(bot)
    brain._update_census(game, bot["id"], mem)
    check("中立矿营守军不进敌情普查（否则整张出兵模板被带偏）",
          not mem["census"], str(mem["census"]))
    check("中立守军不算入侵者（公共矿常在老家 700 半径内，"
          "否则 AI 一整局卡在防守）",
          brain._nearest_invader(game, bot["id"]) is None)
    enemy = server.make_unit("mage", human["id"], hq["x"] + 80, hq["y"])
    game["units"].append(enemy)
    check("真的敌人还是算入侵者",
          brain._nearest_invader(game, bot["id"]) is enemy)
    brain._update_census(game, bot["id"], mem)
    check("真的敌人会进普查", mem["census"].get("mage") == 1, str(mem["census"]))

    # -- LLM 改不掉经济建筑 ----------------------------------------
    blank = codex.enemy_profile({}, ["magic"])
    hijacked = planner.make_plan(
        "tech", set(["power"]), 30.0, blank, set(["hq", "power"]),
        directive={"build_order": ["turret", "turret", "turret"]})
    check("LLM 删光建造序列时精炼厂被补回（否则这局没有收入）",
          "refinery" in hijacked["build"], str(hijacked["build"]))
    check("LLM 删光建造序列时矿车产地被补回（tech 矿车产自 factory）",
          "factory" in hijacked["build"], str(hijacked["build"]))
    magic_hijacked = planner.make_plan(
        "magic", set(["mpower"]), 30.0, blank, set(["mhq", "mpower"]),
        directive={"build_order": ["mtower"]})
    check("秘法会同理补回 mrefinery / mcircle",
          "mrefinery" in magic_hijacked["build"]
          and "mcircle" in magic_hijacked["build"], str(magic_hijacked["build"]))

    # -- 兜底兵要看产地，不只看 requires ---------------------------
    only_barracks = set(["hq", "power", "barracks"])
    mix, _ = planner.sanitize_mix(
        {"tesla": 3, "prism": 3, "overlord": 3, "tank_destroyer": 3},
        "tech", codex.enemy_profile({"golem": 4}, ["magic"]), only_barracks)
    check("配比全是造不出的兵时会补一个当前就能排的"
          "（歼击车没有 requires，但产地是工厂）",
          any(planner._producible_now(kind, only_barracks) for kind in mix),
          str(mix))
    check("补完仍然不超过 %d 个兵种槽位" % planner.MIX_SLOTS,
          len(mix) <= planner.MIX_SLOTS, str(mix))

    # -- 炮塔数按阶段生效 ------------------------------------------
    late = planner.make_plan("tech", set(["factory", "barracks", "repair"]),
                             400.0, blank,
                             set(["hq", "power", "refinery", "barracks",
                                  "factory", "repair"]))
    room2, _human2, bots2 = make_room("AIC-TURRET", bots=1, bot_faction="tech")
    game2 = room2["game"]
    bot2 = bots2[0]
    # 把 OPENING_BUILD 序列里 defense 之前的条目全部满足，否则会先去补它们。
    for index, kind in enumerate(("power", "refinery", "barracks", "factory",
                                  "factory", "repair")):
        give(game2, bot2["id"], kind, 900.0 + 40 * index, 900.0)
    for index in range(late["max_turrets"] - 1):
        give(game2, bot2["id"], "turret", 1200.0 + 40 * index, 1200.0)
    bot2["cash"] = 30000
    nxt = brain._next_building(room2, bot2, late,
                              [s for s in game2["structures"]
                               if s["owner"] == bot2["id"]], 300, 10)
    check("后期 max_turrets=%d 时还会继续补炮塔（过去恒定只造 1 座）"
          % late["max_turrets"],
          late["max_turrets"] >= 2 and nxt == "turret", str(nxt))

    # -- 矿车预算不再被无谓冻结 ------------------------------------
    room3, _human3, bots3 = make_room("AIC-CASH", bots=1, bot_faction="tech")
    game3 = room3["game"]
    bot3 = bots3[0]
    give(game3, bot3["id"], "barracks", 950.0, 950.0)
    plan3 = planner.make_plan("tech", set(["barracks"]), 30.0, blank,
                              set(["hq", "power", "refinery", "barracks"]))
    bot3["cash"] = 400          # 买得起步兵，买不起 920 的矿车
    brain._produce(room3, bot3, plan3, "tech")
    check("还没有工厂时不冻结矿车预算（那笔钱当下根本花不出去）",
          bool(queued_units(game3, bot3["id"])),
          "cash=%d queued=%s" % (bot3["cash"], queued_units(game3, bot3["id"])))

    room4, _human4, bots4 = make_room("AIC-DEADLOCK", bots=1, bot_faction="tech")
    game4 = room4["game"]
    bot4 = bots4[0]
    give(game4, bot4["id"], "barracks", 950.0, 950.0)
    give(game4, bot4["id"], "factory", 1050.0, 950.0)
    game4["units"] = [u for u in game4["units"]
                      if not (u["owner"] == bot4["id"]
                              and server.unit_role(u["kind"]) == "harvester")]
    bot4["cash"] = 400          # 矿车全没了 + 买不起新的 = 没有收入
    brain._produce(room4, bot4, plan3, "tech")
    check("矿车全灭又买不起时不死守预算（攒钱等于坐着等死）",
          bool(queued_units(game4, bot4["id"])),
          "cash=%d queued=%s" % (bot4["cash"], queued_units(game4, bot4["id"])))

    # -- 老家被打立刻回防，不被防抖窗口挡住 ------------------------
    room5, human5, bots5 = make_room("AIC-DEFEND", bots=1, bot_faction="tech")
    game5 = room5["game"]
    bot5 = bots5[0]
    hq5 = server.bot_own_hq(game5, bot5["id"])
    defender = server.make_unit("rifle", bot5["id"], hq5["x"] + 40, hq5["y"] + 40)
    game5["units"].append(defender)
    far = server.make_unit("mage", human5["id"], hq5["x"] + 3000, hq5["y"])
    invader = server.make_unit("mage", human5["id"], hq5["x"] + 90, hq5["y"])
    game5["units"].extend([far, invader])
    mem5 = brain.state(bot5)
    mem5["assign"]["rifle"] = (far["id"], time.time())   # 刚刚才分配过目标
    brain._assign(game5, bot5["id"], [defender], [invader], mem5, force=True)
    check("老家被打时立刻改打入侵者，不等 3 秒防抖窗口",
          defender.get("targetId") == invader["id"],
          str(defender.get("targetId")))

    # -- 自爆车按波次砸建筑，不跟主力冲 ----------------------------
    room6, human6, bots6 = make_room("AIC-BOOM2", bots=1, bot_faction="tech")
    game6 = room6["game"]
    bot6 = bots6[0]
    hq6 = server.bot_own_hq(game6, bot6["id"])
    trucks = []
    for index in range(server.BOT_SUICIDE_WAVE):
        truck = server.make_unit("bomb_truck", bot6["id"],
                                 hq6["x"] + 30 * index, hq6["y"] + 30)
        game6["units"].append(truck)
        trucks.append(truck)
    bait = server.make_unit("imp", human6["id"], hq6["x"] + 200, hq6["y"])
    game6["units"].append(bait)
    plan6 = planner.make_plan("tech", set(["barracks"]), 30.0, blank,
                              set(["hq", "power", "barracks"]))
    plan6["attack_at"] = 0
    brain._fight(room6, bot6, plan6, set(["barracks"]),
                 [s for s in game6["structures"] if s["owner"] == bot6["id"]])
    targets = set(truck.get("targetId") for truck in trucks)
    check("自爆车凑够一波就出发", None not in targets, str(targets))
    check("自爆车只砸建筑，不去撞步兵（1000 块换一个步兵不划算）",
          all(server.find_entity(game6, tid) is not None
              and str(tid).startswith("s") for tid in targets),
          str(targets))

    # -- 残血单位不跟推进 ------------------------------------------
    room7, _human7, bots7 = make_room("AIC-WOUNDED", bots=1, bot_faction="tech")
    game7 = room7["game"]
    bot7 = bots7[0]
    game7["units"] = [u for u in game7["units"] if u["owner"] != bot7["id"]]
    hq7 = server.bot_own_hq(game7, bot7["id"])
    hurt = []
    for index in range(3):
        unit = server.make_unit("rifle", bot7["id"], hq7["x"] + 20 * index, hq7["y"])
        unit["hp"] = unit["maxHp"] * 0.2
        game7["units"].append(unit)
        hurt.append(unit)
    plan7 = planner.make_plan("tech", set(["barracks"]), 30.0, blank,
                              set(["hq", "power", "barracks"]))
    plan7["attack_at"] = 1
    brain._fight(room7, bot7, plan7, set(["barracks"]),
                 [s for s in game7["structures"] if s["owner"] == bot7["id"]])
    check("血量低于 %.0f%% 的兵不跟着主力推进" % (WOUNDED_FLOOR * 100),
          all(unit.get("destX") is None for unit in hurt))

    # -- 顾问线程闲置自退，不再每局漏一个 --------------------------
    class _Stub(object):
        def ask(self, _text):
            return "{}"

    original_idle = llm.IDLE_EXIT_SECONDS
    llm.IDLE_EXIT_SECONDS = 0.2
    try:
        advisor = llm.Advisor(_Stub(), interval=999.0)
        check("顾问初始状态就愿意收快照", advisor.wants())
        deadline = time.time() + 5.0
        while advisor.alive() and time.time() < deadline:
            time.sleep(0.05)
        check("闲置超时后顾问线程自己退出"
              "（房间打完 tick_bots 不再被调用，等不到显式 stop）",
              not advisor.alive())
        check("退出后不再接收快照", not advisor.wants())
    finally:
        llm.IDLE_EXIT_SECONDS = original_idle



def test_no_source_modified():
    print("\n=== 9. 不改既有代码 ===")
    check("卸载后 server.tick_bots 恢复原样",
          not hook.installed() and server.tick_bots.__module__ == "server")
    here = os.path.dirname(os.path.abspath(__file__))
    check("本包所有文件都在 ai_commander/ 下",
          all(os.path.abspath(getattr(module, "__file__", here)).startswith(here)
              for module in (codex, templates, planner, hook, llm, config)))


def main():
    tests = [test_counter_table, test_templates, test_sanitize, test_directive,
             test_live_ticks, test_mode_first, test_failure_fallback,
             test_regressions, test_no_source_modified]
    for test in tests:
        test()
    print("\nai_commander 自检通过：%d 项。" % len(PASSED))
    return 0


if __name__ == "__main__":
    sys.exit(main())
