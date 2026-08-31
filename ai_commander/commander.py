#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""每个 AI 玩家的大脑：一 tick 内跑完建造、生产、战斗三件事。

节奏和职责划分照搬外置 agent 那套（规则层高频执行、LLM 低频给意图），
只是这里的"规则层"就是 `tick_bots` 本身（2.25s 一次），而 LLM 挪到了
后台线程，主循环永远不等它。

所有对局面的改动都走 server 已有的接口（queue_structure / queue_unit /
issue_move / issue_attack / issue_repair），服务端仍然是权威的一方。
"""

from __future__ import print_function

import math
import time

import server
from server import (BOT_HOME_RADIUS, BOT_SUICIDE_BLAST, BOT_SUICIDE_WAVE,
                    NEUTRAL_OWNER, STRUCTURE_TYPES, SUICIDE_KINDS, UNIT_TYPES,
                    VEHICLE_KINDS, clear_repair_order, faction_buildings,
                    has_active_structure, is_friendly, issue_attack, issue_move,
                    issue_repair, player_power, queue_structure, queue_unit,
                    structure_role, unit_role, vision_field)

from ai_commander import codex, planner

STATE_KEY = "_aic"          # 挂在 bot 上的私有状态，和内置 AI 的 "_ai" 不冲突

POWER_BUFFER = 35           # 电力余量低于这个数就先补电站
QUEUE_DEPTH = 3             # 每个生产建筑最多压几个（服务端上限是 5）
SURPLUS_CASH = 5000         # 现金堆到这个数说明产能不够，加产地
CONTACT = 520.0             # 进入这个距离算接火，开始按克制分配目标
COHESION = 380.0            # 距队伍重心超过这个距离算脱队
ARTY_STANDOFF = 300.0       # 攻城类相对目标保持的后撤距离
RETARGET_SECONDS = 3.0      # 同一兵种的目标至少保持这么久，避免抖动
MIN_USEFUL_DPS = 0.05
WOUNDED_FLOOR = 0.45        # 低于这个血线不跟随主力推进（和内置 AI 同口径）
SUICIDE_LEASH = BOT_HOME_RADIUS + 220.0   # 进到这个半径内的敌方自爆单位算“已入家”


def _dist(a, b):
    return math.hypot(a["x"] - b["x"], a["y"] - b["y"])


def _hold(game, owner_id, unit_ids):
    """就地待命，等同于玩家按 S。

    server 的 stop 是写在命令分发里的内联逻辑，没有独立函数可调；维修相关
    的字段则复用 `clear_repair_order`，免得 server 那边加字段时这里静默走偏。
    """
    for unit in game["units"]:
        if unit["owner"] == owner_id and unit["id"] in unit_ids:
            unit["destX"] = None
            unit["destY"] = None
            unit["targetId"] = None
            clear_repair_order(unit)
            unit["order"] = "guard"


def _hostile(game, entity, bot_id):
    """是不是「真正的敌方玩家」实体。

    中立矿营的守军（rifle×2 + rocket×1）和炮塔 owner 是 NEUTRAL_OWNER，
    `is_friendly` 对它返回 False，于是会被当成敌军。它们全是 infantry 甲，
    一旦进了敌情普查就会把整张出兵模板带偏——对面明明是全 arcane 的秘法会，
    却因为家门口那座矿营而去出反步兵的军犬。中立守军有 leash 不会离开矿营，
    也不构成威胁，一律不算敌人。
    """
    owner = entity.get("owner")
    if owner == NEUTRAL_OWNER:
        return False
    return not is_friendly(game, owner, bot_id)


def _role_kind(faction, role):
    for kind, spec in UNIT_TYPES.items():
        if spec.get("role") == role and spec.get("faction", "tech") == faction:
            return kind
    return None


class Commander(object):
    """一个 bot 一个实例，状态存在 bot[STATE_KEY] 里，随房间一起消失。"""

    def __init__(self, settings, log=print):
        self.settings = settings
        self.log = log

    # ------------------------------------------------------------------
    def state(self, bot):
        mem = bot.get(STATE_KEY)
        if mem is None:
            mem = {
                "census": {},        # kind -> 同时见过的最大数量
                "assign": {},        # kind -> (targetId, 时间戳)
                "advisor": None,
                "last_note": "",
                "born": time.time(),
            }
            bot[STATE_KEY] = mem
        return mem

    # ------------------------------------------------------------------
    def tick(self, room, bot):
        game = room["game"]
        mem = self.state(bot)
        faction = bot.get("faction", "tech")
        bot_id = bot["id"]

        own_structures = [s for s in game["structures"]
                          if s["owner"] == bot_id and s["hp"] > 0]
        roles = set(structure_role(s["kind"]) for s in own_structures if s["active"])
        have_kinds = set(s["kind"] for s in own_structures if s["active"])
        supply, usage = player_power(room, bot_id)

        self._update_census(game, bot_id, mem)
        profile = codex.enemy_profile(mem["census"],
                                      self._enemy_factions(room, bot_id))
        directive = None
        advisor = mem.get("advisor")
        if advisor is not None:
            directive = advisor.take()

        plan = planner.make_plan(faction, roles, game.get("elapsed", 0.0),
                                 profile, have_kinds, directive)
        self._announce(bot, mem, plan, profile, faction)
        # 先问一句收不收。拼那段快照要跑两趟 rank_units 再拼一大串字符串，
        # 而这里是在 room_lock 里；顾问多数 tick 都还在间隔冷却中。
        if advisor is not None and advisor.wants():
            self._feed_advisor(advisor, room, bot, plan, profile, faction,
                               own_structures, supply, usage)

        self._build(room, bot, plan, own_structures, supply, usage)
        self._produce(room, bot, plan, faction)
        self._fight(room, bot, plan, roles, own_structures)

    # ---------------------------------------------------------------- 情报
    def _update_census(self, game, bot_id, mem):
        """敌军普查：记录每个兵种"同时见到过最多几个"。

        即时视野会随对方进出迷雾剧烈抖动，直接拿它选模板会让生产在两套兵之间
        来回横跳；取历史最大值既稳定又不会因为对方躲起来就失忆。
        """
        field = vision_field(game, bot_id)
        current = {}
        for unit in game["units"]:
            if unit["hp"] <= 0 or not _hostile(game, unit, bot_id):
                continue
            if field is not None and not field.visible(
                    unit["x"], unit["y"], unit.get("size", 0)):
                continue
            kind = unit["kind"]
            if codex.is_combat_unit(kind):
                current[kind] = current.get(kind, 0) + 1
        census = mem["census"]
        for kind, count in current.items():
            if count > census.get(kind, 0):
                census[kind] = count

    @staticmethod
    def _enemy_factions(room, bot_id):
        out = []
        me = room["players"].get(bot_id) or {}
        game = room["game"]
        for player in room["players"].values():
            if player["id"] == bot_id or player.get("eliminated"):
                continue
            if is_friendly(game, player["id"], bot_id):
                continue
            faction = player.get("faction", "tech")
            if faction not in out:
                out.append(faction)
        if not out:
            out = ["tech" if me.get("faction") == "magic" else "magic"]
        return out

    def _announce(self, bot, mem, plan, profile, faction):
        """计划变了才打一行日志，别刷屏。"""
        signature = "%s|%s|%s" % (
            plan["template"], plan["source"],
            ",".join("%s:%d" % item for item in sorted(plan["mix"].items())))
        if signature == mem.get("last_note"):
            return
        mem["last_note"] = signature
        seen = profile.get("seen") or 0
        detail = codex.counter_note(faction, profile)
        swapped = ""
        if plan["replaced"]:
            swapped = "；换兵=" + ",".join("%s→%s" % pair for pair in plan["replaced"])
        self.log("[AI] %s 阶段=%s 敌甲=%s 来源=%s 配比=%s（已侦察%d兵）%s\n     %s | %s"
                 % (bot.get("name", bot["id"]), plan["phase"], plan["armor_bucket"],
                    plan["source"],
                    ",".join("%s:%d" % item for item in sorted(plan["mix"].items())),
                    seen, swapped, plan["note"], detail))

    # ---------------------------------------------------------------- 建造
    def _prereq_ok(self, game, bot_id, kind):
        """前置建筑是否都已建成并在运转（和 queue_structure 的校验同口径）。"""
        definition = STRUCTURE_TYPES.get(kind)
        if not definition:
            return False
        for need in definition.get("requires", []):
            if not has_active_structure(game, bot_id, need):
                return False
        return True

    def _next_building(self, room, bot, plan, own_structures, supply, usage):
        game = room["game"]
        bot_id = bot["id"]
        power_kind = faction_buildings(bot.get("faction", "tech")).get("power")

        # 电力是所有产能的总开关，排在固定序列之前。
        if power_kind and supply - usage < POWER_BUFFER:
            if self._prereq_ok(game, bot_id, power_kind):
                return power_kind

        counts = {}
        for structure in own_structures:
            counts[structure["kind"]] = counts.get(structure["kind"], 0) + 1

        want = {}
        for kind in plan["build"]:
            want[kind] = want.get(kind, 0) + 1
            if structure_role(kind) == "defense":
                # 建造序列里 defense 只写一次，真正要几座由阶段（或 LLM）的
                # max_turrets 决定。照抄序列里的出现次数的话，PHASE_ECONOMY 里
                # mid=2 / late=3 就永远是死数字，一局到头只有一座炮塔。
                want[kind] = plan["max_turrets"]
                if want[kind] <= 0:
                    continue
            if counts.get(kind, 0) >= want[kind]:
                continue
            if not self._prereq_ok(game, bot_id, kind):
                continue
            return kind

        # 序列走完还堆着钱，说明产能不够：按配比给权重最高的产地加一座。
        if bot.get("cash", 0) >= SURPLUS_CASH:
            best = None
            best_key = None
            for unit_kind, weight in plan["mix"].items():
                producer = (UNIT_TYPES.get(unit_kind) or {}).get("producer")
                if not producer or not self._prereq_ok(game, bot_id, producer):
                    continue
                have = counts.get(producer, 0)
                if have >= 4:
                    continue
                key = (have / float(max(1, weight)), producer)
                if best_key is None or key < best_key:
                    best, best_key = producer, key
            if best:
                return best
        return None

    def _build(self, room, bot, plan, own_structures, supply, usage):
        build_queue = bot.get("buildQueue", [])
        if build_queue and build_queue[0].get("ready"):
            server.bot_place_prepared(room, bot, build_queue[0]["kind"])
            return
        if build_queue:
            return
        kind = self._next_building(room, bot, plan, own_structures, supply, usage)
        if not kind:
            return
        try:
            queue_structure(room, bot["id"], kind)
        except ValueError:
            pass

    # ---------------------------------------------------------------- 生产
    def _produce(self, room, bot, plan, faction):
        game = room["game"]
        bot_id = bot["id"]

        harvester_kind = _role_kind(faction, "harvester")
        reserve = 0
        if harvester_kind:
            spec = UNIT_TYPES[harvester_kind]
            live = sum(1 for unit in game["units"]
                       if unit["owner"] == bot_id and unit["hp"] > 0
                       and unit["kind"] == harvester_kind)
            queued = self._queued(game, bot_id, harvester_kind)
            # 产地还没建起来时（开局工厂/法阵未完工）根本排不出矿车，这时
            # queue_unit 抛的是「缺少对应生产建筑」而不是「资金不足」。照抓
            # 不误地扣住一整辆矿车的钱，等于凭空冻结一笔当下花不出去的预算。
            ready = has_active_structure(game, bot_id, spec["producer"])
            if ready and live + queued < plan["harvesters"]:
                try:
                    queue_unit(room, bot_id, harvester_kind)
                except ValueError:
                    # 买不起就把这笔钱留住，别被便宜兵一路抢光。上一局就是这样
                    # 死循环的：现金一到 870 就被歼击车吃掉，矿车永远补不上。
                    reserve = int(spec["cost"])
            if live + queued == 0 and bot.get("cash", 0) < spec["cost"]:
                # 矿车全没了又买不起新的：攒钱是死路，没有矿车就没有收入，
                # 现金永远涨不到那个数。放开预算先出兵保命。
                reserve = 0

        # 只在真正能出兵的产地上排产。电站/精炼厂也有 queue 字段，扫它们
        # 纯属白跑一遍 _pick_unit。
        wanted_producers = set()
        for kind in plan["mix"]:
            producer = (UNIT_TYPES.get(kind) or {}).get("producer")
            if producer:
                wanted_producers.add(producer)
        producers = {}
        for structure in game["structures"]:
            if (structure["owner"] != bot_id or structure["hp"] <= 0
                    or not structure["active"]
                    or structure["kind"] not in wanted_producers):
                continue
            producers.setdefault(structure["kind"], []).append(structure)

        for producer_kind in sorted(producers):
            plants = producers[producer_kind]
            depth = sum(len(p["queue"]) for p in plants)
            slots = len(plants) * QUEUE_DEPTH - depth
            planned = {}
            while slots > 0:
                pick = self._pick_unit(room, bot, plan, producer_kind, reserve, planned)
                if not pick:
                    break
                try:
                    queue_unit(room, bot_id, pick)
                except ValueError:
                    break
                planned[pick] = planned.get(pick, 0) + 1
                slots -= 1

    @staticmethod
    def _queued(game, bot_id, kind):
        total = 0
        for structure in game["structures"]:
            if structure["owner"] != bot_id:
                continue
            for item in structure.get("queue") or []:
                if item.get("kind") == kind:
                    total += 1
        return total

    def _pick_unit(self, room, bot, plan, producer_kind, reserve, planned):
        """在该产地能出的兵里，挑当前占比距目标配比差最多、又买得起的那个。"""
        game = room["game"]
        bot_id = bot["id"]
        cash = bot.get("cash", 0) - reserve
        options = {}
        for kind, weight in plan["mix"].items():
            spec = UNIT_TYPES.get(kind)
            if not spec or spec.get("producer") != producer_kind or weight <= 0:
                continue
            if cash < spec["cost"]:
                continue
            # 前置科技没建好的兵要跳过：server 会直接拒绝，而拒绝一次就会
            # 打断整个产地这一跳的排产。
            if any(not has_active_structure(game, bot_id, need)
                   for need in spec.get("requires", [])):
                continue
            options[kind] = weight
        if not options:
            return None
        total_weight = float(sum(options.values()))
        have = {}
        for unit in game["units"]:
            if unit["owner"] == bot_id and unit["hp"] > 0 and unit["kind"] in options:
                have[unit["kind"]] = have.get(unit["kind"], 0) + 1
        for structure in game["structures"]:
            if structure["owner"] != bot_id:
                continue
            for item in structure.get("queue") or []:
                if item.get("kind") in options:
                    have[item["kind"]] = have.get(item["kind"], 0) + 1
        for kind, count in planned.items():
            if kind in options:
                have[kind] = have.get(kind, 0) + count
        fielded = float(max(1, sum(have.values())))
        return max(options,
                   key=lambda k: options[k] / total_weight - have.get(k, 0) / fielded)

    # ---------------------------------------------------------------- 战斗
    def _fight(self, room, bot, plan, roles, own_structures):
        game = room["game"]
        bot_id = bot["id"]
        mem = self.state(bot)

        self._repair(room, bot, own_structures)

        field = [unit for unit in game["units"]
                 if unit["owner"] == bot_id and unit["hp"] > 0
                 and unit_role(unit["kind"]) not in ("harvester", "mcv")
                 and unit.get("order") != "repair"
                 and codex.is_combat_unit(unit["kind"])]
        # 自爆单位不进野战编制：它们撞上去就没了，跟着主力冲等于拿 1000 块
        # 换一个步兵。单独按波次去砸建筑。
        suicides = [unit for unit in field if unit["kind"] in SUICIDE_KINDS]
        army = [unit for unit in field if unit["kind"] not in SUICIDE_KINDS]

        inbound = self._inbound_suicide(game, bot_id)
        evaded = server.bot_evade_suicide(game, bot, inbound)
        server.bot_maybe_pack(game, bot, roles, game.get("elapsed", 0.0))
        self._launch_suicides(game, bot_id, suicides, mem)

        if not army:
            return

        # 家里进了敌人：最高优先级，压过一切进攻意图。
        invader = self._nearest_invader(game, bot_id)
        if invader is not None:
            self._assign(game, bot_id, army, [invader], mem, force=True)
            return
        if inbound is not None:
            # 敌方自爆车已经进家：别再往总部方向凑，这一跳交给炮塔。
            # bot_evade_suicide 只拉爆炸圈里的廉价单位；它没事可做时（重甲部队
            # 挨得住那一下、或者根本不在圈里）仍要把军团从总部直线上让开，
            # 免得卡车顺着队伍一路滚到总部门口。
            if not evaded:
                self._sidestep(game, bot_id, army, inbound)
            return

        # 残血单位不跟着推进（和内置 AI 同口径）：送进去只是白给对方补刀，
        # 有维修厂时 _repair 会把载具收回去修。
        healthy = [unit for unit in army
                   if unit["hp"] / float(unit["maxHp"]) >= WOUNDED_FLOOR]
        if len(healthy) < plan["attack_at"]:
            return

        focus = server.bot_focus_hq(game, bot_id)
        enemies = self._visible_enemies(game, bot_id)
        if enemies:
            self._assign(game, bot_id, healthy, enemies, mem)
        if focus is not None:
            self._advance(game, bot_id, healthy, focus, enemies, mem)

    def _nearest_invader(self, game, bot_id):
        """家门口最近的敌方作战单位；没有就返回 None。

        不用 `server.bot_nearest_invader` / `bot_needs_defense`：它们只看
        `is_friendly`，中立矿营的守军会被算成入侵者。公共矿常常就在老家
        700 半径内，那样判定会让 AI 一整局都卡在「防守」状态不出门。
        """
        hq = server.bot_own_hq(game, bot_id)
        origin_x, origin_y = server.bot_own_origin(game, bot_id)
        origin = {"x": origin_x, "y": origin_y}
        threatened = hq is not None and hq["hp"] < hq["maxHp"] - 0.5
        best = None
        best_dist = None
        for unit in game["units"]:
            if (unit["hp"] <= 0 or not _hostile(game, unit, bot_id)
                    or unit_role(unit["kind"]) == "harvester"):
                continue
            dist = _dist(unit, origin)
            if dist <= BOT_HOME_RADIUS and (best is None or dist < best_dist):
                best = unit
                best_dist = dist
        if best is not None:
            return best
        if threatened:
            # 总部在掉血但家门口没人：多半是射程外的攻城单位在点。退而求其次，
            # 打最近的可见敌方单位。
            visible = [e for e in self._visible_enemies(game, bot_id)
                       if e["id"].startswith("u")]
            if visible:
                return min(visible, key=lambda e: _dist(e, origin))
        return None

    @staticmethod
    def _sidestep(game, bot_id, army, inbound):
        """把部队从「自爆车 → 总部」这条直线上横向让开（照内置 AI 的算法）。"""
        hq = server.bot_own_hq(game, bot_id)
        if hq is None or not army:
            return
        dx = hq["x"] - inbound["x"]
        dy = hq["y"] - inbound["y"]
        length = math.hypot(dx, dy) or 1.0
        try:
            issue_move(game, bot_id, set(u["id"] for u in army),
                       hq["x"] + (-dy / length) * 180.0,
                       hq["y"] + (dx / length) * 180.0)
        except ValueError:
            pass

    @staticmethod
    def _inbound_suicide(game, bot_id):
        """已经摸进家门的敌方自爆单位，取最近的一个。"""
        hq = server.bot_own_hq(game, bot_id)
        if hq is None:
            return None
        best = None
        best_dist = None
        for unit in game["units"]:
            if (unit["hp"] <= 0 or unit["kind"] not in SUICIDE_KINDS
                    or not _hostile(game, unit, bot_id)):
                continue
            dist = _dist(unit, hq)
            if dist <= SUICIDE_LEASH and (best is None or dist < best_dist):
                best = unit
                best_dist = dist
        return best

    def _launch_suicides(self, game, bot_id, suicides, mem):
        """自爆车专用波次：凑够人就走，且只许砸建筑。

        `_score_target` 会挑「倍率×残血×距离」最优的野战目标，自爆车撞上去
        就没了。卡车/魔仆只对建筑与采矿单位 ×1.5，所以目标限定为总部或贴着
        总部的建筑团，才对得起 1000 块的造价。
        """
        if len(suicides) < BOT_SUICIDE_WAVE:
            return
        # bot_pick_suicide_target 只看 is_friendly，中立矿营的炮塔也会被它选中。
        target = server.bot_pick_suicide_target(game, bot_id)
        if target is None or not _hostile(game, target, bot_id):
            return
        idle = []
        for unit in suicides:
            if unit.get("order") != "attack":
                idle.append(unit)
                continue
            prey = server.find_entity(game, unit.get("targetId"))
            # 已经在追一个单位（而不是建筑）也要拉回来重新指派。
            if prey is None or prey.get("kind") in UNIT_TYPES:
                idle.append(unit)
        if not idle:
            return
        try:
            issue_attack(game, bot_id, set(u["id"] for u in idle), target["id"])
            mem["suicide_waves"] = mem.get("suicide_waves", 0) + 1
        except ValueError:
            pass

    @staticmethod
    def _visible_enemies(game, bot_id):
        field = vision_field(game, bot_id)
        out = []
        for collection in (game["units"], game["structures"]):
            for entity in collection:
                if entity["hp"] <= 0 or not _hostile(game, entity, bot_id):
                    continue
                if field is not None and not field.visible(
                        entity["x"], entity["y"], entity.get("size", 0)):
                    continue
                out.append(entity)
        return out

    def _score_target(self, attacker_kind, target, origin):
        """克制系数为主，残血优先，距离惩罚。"""
        multiplier = codex.counter(codex.damage_type_of(attacker_kind),
                                   target.get("kind"))
        if multiplier <= 0:
            return 0.0
        hp = float(target.get("hp") or 1.0)
        max_hp = float(target.get("maxHp") or hp or 1.0)
        wounded = 1.0 + 0.35 * (1.0 - min(1.0, hp / max_hp))
        near = 1.0 / (1.0 + _dist(target, origin) / 900.0)
        return multiplier * wounded * near

    def _assign(self, game, bot_id, army, enemies, mem, force=False):
        """按兵种分组，各打各自克制的目标。"""
        by_kind = {}
        for unit in army:
            by_kind.setdefault(unit["kind"], []).append(unit)
        now = time.time()
        assign = mem["assign"]

        for kind, units in by_kind.items():
            centroid = self._centroid(units)
            spec = UNIT_TYPES.get(kind) or {}
            reach = CONTACT + max(0.0, float(spec.get("range") or 0.0))
            nearby = [e for e in enemies if _dist(e, centroid) <= reach] if not force else enemies
            if not nearby:
                continue

            # 保持上一个目标是为了防抖，但老家被打时不能等：tick 周期 2.25s、
            # 保持窗口 3.0s，照抖动规则走的话，刚分配过目标的兵种要等下一跳
            # （再 2.25s）才肯回防。force 直接跳过这段。
            previous = assign.get(kind)
            if not force and previous and now - previous[1] < RETARGET_SECONDS:
                still = server.find_entity(game, previous[0])
                if still is not None and still.get("hp", 0) > 0:
                    continue

            best = max(nearby, key=lambda e: self._score_target(kind, e, centroid))
            if self._score_target(kind, best, centroid) <= 0.0:
                # 这个兵种对眼前所有目标都是零伤害（军犬撞上一队构装体就是
                # 这样）。硬派它去打等于送掉，交回给推进逻辑跟队。
                continue
            assign[kind] = (best["id"], now)
            try:
                issue_attack(game, bot_id, set(u["id"] for u in units), best["id"])
            except ValueError:
                assign.pop(kind, None)

    def _advance(self, game, bot_id, army, focus, enemies, mem):
        """还没接火的兵种分梯队推进：快的等慢的，攻城类保持后撤位。"""
        engaged = set(kind for kind, (_tid, stamp) in mem["assign"].items()
                      if time.time() - stamp < RETARGET_SECONDS)
        pending = [unit for unit in army if unit["kind"] not in engaged]
        if not pending:
            return
        centroid = self._centroid(pending)
        dx, dy = focus["x"] - centroid["x"], focus["y"] - centroid["y"]
        length = math.hypot(dx, dy) or 1.0
        ux, uy = dx / length, dy / length

        by_kind = {}
        for unit in pending:
            by_kind.setdefault(unit["kind"], []).append(unit)

        for kind, units in by_kind.items():
            spec = UNIT_TYPES.get(kind) or {}
            long_range = float(spec.get("range") or 0.0) >= 280.0
            standoff = ARTY_STANDOFF if long_range else 0.0
            aim_x = focus["x"] - ux * standoff
            aim_y = focus["y"] - uy * standoff
            screen = spec.get("armor") == "heavy" and not long_range

            ahead, rest = [], []
            for unit in units:
                lead = ((unit["x"] - centroid["x"]) * ux
                        + (unit["y"] - centroid["y"]) * uy)
                if lead > COHESION and not screen:
                    ahead.append(unit["id"])
                else:
                    rest.append(unit["id"])
            if ahead:
                _hold(game, bot_id, set(ahead))
            if rest:
                try:
                    issue_move(game, bot_id, set(rest), aim_x, aim_y, attack_move=True)
                except ValueError:
                    pass

    @staticmethod
    def _centroid(units):
        count = float(len(units) or 1)
        return {"x": sum(u["x"] for u in units) / count,
                "y": sum(u["y"] for u in units) / count}

    def _repair(self, room, bot, own_structures):
        game = room["game"]
        bot_id = bot["id"]
        bays = [s for s in own_structures
                if structure_role(s["kind"]) == "repair" and s["active"]]
        if not bays:
            return
        damaged = [unit for unit in game["units"]
                   if unit["owner"] == bot_id and unit["kind"] in VEHICLE_KINDS
                   and unit["hp"] > 0 and unit["hp"] / unit["maxHp"] < 0.62
                   and unit.get("order") != "repair"
                   and unit_role(unit["kind"]) != "harvester"]
        if not damaged:
            return
        try:
            issue_repair(game, bot_id, set(u["id"] for u in damaged[:12]), bays[0]["id"])
        except ValueError:
            pass

    # ---------------------------------------------------------------- LLM
    def _feed_advisor(self, advisor, room, bot, plan, profile, faction,
                      own_structures, supply, usage):
        game = room["game"]
        bot_id = bot["id"]
        army = {}
        for unit in game["units"]:
            if unit["owner"] == bot_id and unit["hp"] > 0:
                army[unit["kind"]] = army.get(unit["kind"], 0) + 1
        structures = {}
        for structure in own_structures:
            structures[structure["kind"]] = structures.get(structure["kind"], 0) + 1

        rows = codex.rank_units(faction, profile, set(structures))
        menu = "\n".join(
            "  %s(%s) 造价%d 伤害类型=%s 护甲=%s 对当前敌军有效dps=%.0f%s"
            % (UNIT_TYPES[row["kind"]]["name"], row["kind"], row["cost"],
               row["damageType"], codex.armor_label(codex.armor_of(row["kind"])),
               row["dps"], ("（缺前置 %s）" % ",".join(row["missing"])) if row["missing"] else "")
            for row in rows)
        enemy = "、".join(
            "%s x%d(%s)" % (UNIT_TYPES[kind]["name"], count,
                            codex.armor_label(codex.armor_of(kind)))
            for kind, count in sorted(self.state(bot)["census"].items(),
                                      key=lambda item: -item[1])) or "还没侦察到"

        prompt = (
            "我方阵营=%s 阶段=%s 现金=%d 电力=%d/%d 已用时=%.0fs\n"
            "我方建筑：%s\n我方部队：%s\n"
            "已侦察到的敌军：%s\n"
            "当前配比（固定模板给的）=%s，建造序列=%s，出击门槛=%d，矿车目标=%d\n"
            "克制速记：%s\n"
            "可用兵种：\n%s\n"
            "可用建筑：%s\n"
            "只在确有把握时改动；没有更好的选择就回 {}。"
            % (faction, plan["phase"], int(bot.get("cash", 0)), usage, supply,
               game.get("elapsed", 0.0),
               ", ".join("%s x%d" % (k, v) for k, v in sorted(structures.items())) or "无",
               ", ".join("%s x%d" % (k, v) for k, v in sorted(army.items())) or "无",
               enemy,
               ",".join("%s:%d" % item for item in sorted(plan["mix"].items())),
               ">".join(plan["build"]), plan["attack_at"], plan["harvesters"],
               codex.counter_note(faction, profile) or "无",
               menu,
               ", ".join(sorted(kind for kind, spec in STRUCTURE_TYPES.items()
                                if spec.get("faction", "tech") == faction
                                and structure_role(kind) != "hq"))))

        advisor.submit({
            "who": bot.get("name", bot_id),
            "prompt": prompt,
            "units": set(codex.faction_combat_units(faction).keys()),
            "structures": set(kind for kind, spec in STRUCTURE_TYPES.items()
                              if spec.get("faction", "tech") == faction),
        })
