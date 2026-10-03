#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""跨阵营控制规则 H 回归（tribe-faction-redesign 任务 2.2）。

   性质（design.md「Correctness Properties」1-3）
     Property 1  减速/定身与参考模型一致：apply_slow + tick_status_timers 驱动，
                 逐步对照 (slowMult, slowTimer, rootResist)
     Property 2  定身节律上界：单段定身 <= 触发施加时长 + dt、相邻两段间隔
                 >= 1.0 s - dt；单只巨蛛按目录冷却持续命中 60 s，定身占比 <= 55%
     Property 3  持续伤害强者优先：apply_dot + tick_dot 驱动，逐步对照 6 个来源
                 字段与掉血，并核对毒死时的击杀归属
   示例
     1 冰霜命中已定身目标仍定身        2 雷暴不把冰霜降级
     3 冰霜覆盖雷暴                    4 同强度取较长 / 抗性期定身降为 x0.5
     5 毒雾坑不被蛛毒降级              6 建筑、已阵亡单位与零时长施加免疫
     7 DoT 致死记给当时的 dotOwner

   参考模型按 design.md §2.1 / §2.2 独立书写，只读目录数据：catalog 的来源数值
   与 ROOT_RESIST_*，以及伤种倍率表 DAMAGE_MULTIPLIER（server.py 中的纯数据表）；
   不调用 apply_slow / tick_status_timers / apply_dot / tick_dot /
   damage_armor_multiplier。来源数值一律读目录：毒矢高台的 dot 会在任务 5.1
   改值，这里不写死。
   浮点：以 0.05 步长推进时计时可能残留约 1e-17 的正余量，要多走一个 tick
   才归零；本文件不假设整除，比较时都留容差。
"""

from __future__ import print_function

import math
import os
import random
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import catalog
import server


FEATURE = "tribe-faction-redesign"

DT = 0.05                     # 服务器 20 Hz 固定步长
MATCH_TOL = 1e-6              # 参考模型对照误差（Property 1、3）
STRENGTH_EPS = 1e-9           # 强度相等的容差（design.md §2.2）
BOUND_EPS = 1e-9              # Property 2 上下界比较的浮点余量
BIG_HP = 1.0e6                # Property 3 先不让目标毒死，单独观察强度与计时
SPIDER_ROOT_SHARE_CAP = 0.55  # 需求 11.12

ROOT_RESIST_SECONDS = float(catalog.ROOT_RESIST_SECONDS)
ROOT_RESIST_SLOW_MULT = float(catalog.ROOT_RESIST_SLOW_MULT)

# ---- 减速 / 定身来源（数值全部读目录） ----
FROST_SLOW = catalog.UNIT_TYPES["frost"]["slow"]          # 冰霜女巫
STORM_SLOW = catalog.STRUCTURE_TYPES["mstorm"]["slow"]    # 雷暴塔
WEB_SLOW = catalog.UNIT_TYPES["spider"]["slow"]           # 蛛网巨蛛（定身）
TRAP_SLOW = catalog.STRUCTURE_TYPES["ttrap"]["slow"]      # 兽夹陷阱（定身）
SPIDER_COOLDOWN = float(catalog.UNIT_TYPES["spider"]["cooldown"])
SLOW_SOURCES = (("frost", FROST_SLOW), ("mstorm", STORM_SLOW),
                ("spider", WEB_SLOW), ("ttrap", TRAP_SLOW))
ROOT_SOURCES = tuple(item for item in SLOW_SOURCES
                     if float(item[1]["mult"]) <= 0.0)

# ---- 持续伤害来源（数值全部读目录） ----
WEB_DOT = catalog.UNIT_TYPES["spider"]["dot"]             # 蛛毒
DART_DOT = catalog.STRUCTURE_TYPES["ttoxtower"]["dot"]    # 毒矢高台
PIT_DOT = catalog.STRUCTURE_TYPES["tpit"]["dot"]          # 毒雾坑
DOT_SOURCES = (("spider", WEB_DOT), ("ttoxtower", DART_DOT), ("tpit", PIT_DOT))
DOT_FIELDS = ("dotDps", "dotTimer", "dotDamageType",
              "dotOwner", "dotSourceId", "dotSourceKind")

UNIT_KINDS = tuple(sorted(catalog.UNIT_TYPES))


# ================================================================ 辅助函数

def property_banner(number, title):
    print("Feature: %s, Property %d: %s" % (FEATURE, number, title))


def make_room(tag, factions=("tribe", "tech")):
    """最小房间：中立关闭、地形压平。2 人用铁峡争渡，3 人用赤金陨坑。"""
    players = []
    for index, faction in enumerate(factions):
        player = server.create_human("P%d" % index, server.COLORS[index])
        player["faction"] = faction
        players.append(player)
    room = {
        "id": tag, "name": "control rules test", "status": "lobby",
        "hostId": players[0]["id"],
        "players": dict((player["id"], player) for player in players),
        "chat": [], "game": None, "createdAt": time.time(),
        "selectedMap": ("iron_river_duel" if len(players) <= 2
                        else "gold_crater_small"),
        "neutrals": False,
    }
    server.start_game(room)
    game = room["game"]
    game["terrainCtx"] = server.FLAT_TERRAIN
    game["victoryClock"] = 999.0
    return room, players


def isolate(game, *keep):
    """只留 keep 里的单位；清空建筑、弹丸与中立营，毒死或自爆不波及旁物。"""
    game["units"] = list(keep)
    game["structures"] = []
    game["projectiles"] = []
    game["neutralCamps"] = []


def fresh_unit(kind="tank", owner="pB"):
    return server.make_unit(kind, owner, 1600.0, 1600.0)


def dot_payload(dot, owner, source_id, source_kind):
    """与弹丸 / 毒雾坑脉冲相同的 DoT 载荷形状。"""
    return {"dot": dot, "owner": owner,
            "sourceId": source_id, "sourceKind": source_kind}


def advance(unit, seconds, dt=DT):
    for _ in range(int(round(seconds / dt))):
        server.tick_status_timers(unit, dt)


def advance_until(unit, predicate, limit=10.0, dt=DT):
    """推进到 predicate 成立；不假设计时恰好整除。"""
    elapsed = 0.0
    while not predicate(unit):
        assert elapsed < limit, ("超时未达到目标状态", unit["slowMult"],
                                 unit["slowTimer"], unit["rootResist"])
        server.tick_status_timers(unit, dt)
        elapsed += dt
    return elapsed


def split_advance(seconds, step=DT):
    """把一段推进拆成 step 细分；不足一步的余量单独成一步。"""
    whole = int(seconds / step + 1e-9)
    parts = [step] * whole
    rest = seconds - whole * step
    if rest > 1e-9:
        parts.append(rest)
    return parts


def is_rooted(unit):
    """术语表「定身」：slowMult 为 0 且 slowTimer 大于 0。"""
    return unit["slowTimer"] > 0.0 and unit["slowMult"] <= 0.0


def ref_armor_multiplier(damage_type, armor):
    """伤种对护甲倍率：缺项按 1.0，混甲取各片平均（只读 DAMAGE_MULTIPLIER 表）。"""
    table = server.DAMAGE_MULTIPLIER.get(damage_type) or {}
    if isinstance(armor, (list, tuple)):
        pieces = tuple(armor)
    else:
        pieces = (armor,) if armor else ()
    if not pieces:
        return 1.0
    return sum(table.get(piece, 1.0) for piece in pieces) / float(len(pieces))


def unit_armor(kind):
    """与 apply_dot / apply_damage 一致的护甲来源：缺省按 structure。"""
    return catalog.UNIT_TYPES[kind].get("armor", "structure")


def dot_strength(dps, damage_type, armor):
    return float(dps or 0.0) * ref_armor_multiplier(damage_type, armor)


# ================================================================ 参考模型

class SlowModel(object):
    """减速/定身参考模型：design.md §2.1 计时 + §2.2 施加决策表。"""

    def __init__(self):
        self.mult = 1.0
        self.timer = 0.0
        self.resist = 0.0

    def state(self):
        if self.timer > 0.0 and self.mult <= 0.0:
            return "rooted"
        if self.timer > 0.0 and self.mult < 1.0:
            return "slowed"
        return "free"

    def apply(self, mult, duration):
        """按决策表施加；返回走到的分支名，供覆盖率自检。"""
        if duration <= 0.0:
            return "ignored-duration"                     # 11.10
        state = self.state()
        if state == "rooted":
            return "ignored-rooted"                       # 定身中：一律忽略（11.6）
        prefix = ""
        if mult <= 0.0:
            if self.resist <= 0.0:
                # 无抗性：定身，覆盖任何减速
                self.mult, self.timer = 0.0, duration
                return "root-over-slow" if state == "slowed" else "root"
            mult = ROOT_RESIST_SLOW_MULT                  # 抗性期：降为 x0.5 减速（11.8）
            prefix = "resist-"
        if state == "slowed":
            if self.mult < mult - STRENGTH_EPS:
                return prefix + "weaker-ignored"          # 已有更强（11.5）
            if abs(self.mult - mult) <= STRENGTH_EPS:
                self.timer = max(self.timer, duration)    # 同强度取较长（11.4）
                return prefix + "same-strength"
        self.mult, self.timer = mult, duration            # 更强或原本无减速（11.3）
        return prefix + ("stronger" if state == "slowed" else "fresh")

    def tick(self, dt):
        if self.resist > 0.0:
            self.resist = max(0.0, self.resist - dt)      # 先衰减抗性（11.9）
        if self.timer > 0.0:
            self.timer = max(0.0, self.timer - dt)
            if self.timer <= 0.0:
                if self.mult <= 0.0:
                    self.resist = ROOT_RESIST_SECONDS     # 定身到期进入抗性（11.7）
                self.mult = 1.0                           # 普通减速到期不给抗性


class DotModel(object):
    """持续伤害参考模型（需求 12.2-12.6）。

    强度 = dps x 伤种对目标护甲倍率；「已有 DoT」= 计时 > 0 且 dps > 0；
    强度相等容差 1e-9；同强度且剩余 >= 新时长（精确比较）忽略；
    其余情况整组覆盖 6 个来源字段，到期全部清空。
    """

    def __init__(self, armor):
        self.armor = armor
        self.clear()

    def clear(self):
        self.dps = 0.0
        self.timer = 0.0
        self.damage_type = None
        self.owner = None
        self.source_id = None
        self.source_kind = None

    def active(self):
        return self.timer > 0.0 and self.dps > 0.0

    def apply(self, payload):
        dot = payload["dot"]
        dps = float(dot.get("dps") or 0.0)
        duration = float(dot.get("duration") or 0.0)
        if dps <= 0.0 or duration <= 0.0:
            return "ignored-empty"                        # 12.8
        damage_type = dot.get("damageType")
        label = "fresh"
        if self.active():
            current = dot_strength(self.dps, self.damage_type, self.armor)
            incoming = dot_strength(dps, damage_type, self.armor)
            if current > incoming + STRENGTH_EPS:
                return "weaker-ignored"                   # 12.3
            if abs(current - incoming) <= STRENGTH_EPS:
                if self.timer >= duration:
                    return "same-ignored"                 # 12.4
                label = "same-longer"
            else:
                label = "stronger"
        # 12.5：整组覆盖——谁写入计时，谁拥有击杀归属
        self.dps = dps
        self.timer = duration
        self.damage_type = damage_type
        self.owner = payload.get("owner")
        self.source_id = payload.get("sourceId")
        self.source_kind = payload.get("sourceKind")
        return label

    def tick(self, dt, hp):
        """推进一步，返回期望 hp（毒死时夹到 0）；到期清空来源字段（12.6）。"""
        if self.timer <= 0.0:
            return hp
        if self.dps > 0.0 and hp > 0.0:
            hp -= self.dps * dt * ref_armor_multiplier(self.damage_type, self.armor)
            if hp <= 0.0:
                hp = 0.0
        self.timer = max(0.0, self.timer - dt)
        if self.timer <= 0.0:
            self.clear()
        return hp


# ================================================================ 对照工具

def slow_fields(unit):
    return (float(unit["slowMult"]), float(unit["slowTimer"]),
            float(unit["rootResist"]))


def check_slow(unit, model, history):
    got = slow_fields(unit)
    want = (model.mult, model.timer, model.resist)
    if any(abs(g - w) > MATCH_TOL for g, w in zip(got, want)):
        raise AssertionError(
            "Property 1 反例\n  序列: %s\n"
            "  实现 (slowMult, slowTimer, rootResist) = %r\n  参考模型 = %r"
            % (" ".join(history), got, want))
    # 对照通过后把连续量同步为实现值：浮点残差不能让两边的离散判定分叉。
    model.mult, model.timer, model.resist = got


def dot_fields(unit):
    return dict((field, unit.get(field)) for field in DOT_FIELDS)


def check_dot(unit, model, expected_hp, history):
    got = dot_fields(unit)
    want = {"dotDps": model.dps, "dotTimer": model.timer,
            "dotDamageType": model.damage_type, "dotOwner": model.owner,
            "dotSourceId": model.source_id, "dotSourceKind": model.source_kind}
    bad = [field for field in ("dotDps", "dotTimer")
           if abs(float(got[field] or 0.0) - want[field]) > MATCH_TOL]
    bad += [field for field in DOT_FIELDS[2:] if got[field] != want[field]]
    if abs(unit["hp"] - expected_hp) > MATCH_TOL:
        bad.append("hp")
    if float(got["dotTimer"] or 0.0) <= 0.0 and (
            float(got["dotDps"] or 0.0) != 0.0
            or any(got[field] is not None for field in DOT_FIELDS[2:])):
        bad.append("到期未清空来源字段")
    if bad:
        raise AssertionError(
            "Property 3 反例（%s）\n  序列: %s\n  实现 = %r, hp=%r\n"
            "  参考模型 = %r, hp=%r"
            % (", ".join(bad), " ".join(history), got, unit["hp"],
               want, expected_hp))
    model.timer = float(got["dotTimer"] or 0.0)   # 同 Property 1：同步浮点残差
    return unit["hp"]


def tick_dot_checked(room, players, target, model, hp, dt, history):
    """推进一步 tick_dot 并对照；目标被毒死时核对击杀归属（12.7）。

    返回 (hp, 本步是否被毒死)。
    """
    killer = model.owner if model.active() else None
    kills_before = [player["kills"] for player in players]
    alive = target["hp"] > 0
    server.tick_dot(room, target, dt)
    hp = check_dot(target, model, model.tick(dt, hp), history)
    if not (alive and target["hp"] <= 0):
        return hp, False
    assert killer is not None, ("Property 3 反例：无活动 DoT 却被毒死",
                                " ".join(history))
    for player, before in zip(players, kills_before):
        expected = before + (1 if player["id"] == killer else 0)
        assert player["kills"] == expected, (
            "Property 3 反例：击杀未记给当时的 dotOwner", " ".join(history),
            player["name"], player["kills"], expected)
    return hp, True


def run_root_timeline(dt, ticks, hits_at):
    """固定步长推进：每步先 tick_status_timers，再结算本步命中（与 tick_game
    中 tick_units -> tick_projectiles 的顺序一致），步末采样是否定身。

    返回 (定身段列表, 步末处于定身的步数)。段 = {start, end, trigger}：
    第 start..end-1 步步末处于定身；trigger 为把单位带入这段定身的那次施加时长。
    """
    unit = server.make_unit("rifle", "pB", 1600.0, 1600.0)
    segments = []
    current = None
    rooted_ticks = 0
    for k in range(ticks):
        server.tick_status_timers(unit, dt)
        if current is not None and not is_rooted(unit):
            current["end"] = k
            segments.append(current)
            current = None
        for name, slow in hits_at(k):
            was = is_rooted(unit)
            server.apply_slow({"slow": slow}, unit)
            now = is_rooted(unit)
            if now and not was:
                current = {"start": k, "end": None, "source": name,
                           "trigger": float(slow["duration"])}
            elif was and not now:
                current["end"] = k
                segments.append(current)
                current = None
        if is_rooted(unit):
            rooted_ticks += 1
    if current is not None:
        current["end"] = ticks
        segments.append(current)
    return segments, rooted_ticks


def check_root_rhythm(segments, dt, context):
    for seg in segments:
        length = (seg["end"] - seg["start"]) * dt
        assert length <= seg["trigger"] + dt + BOUND_EPS, (
            "Property 2 反例：单段定身超过触发时长 + dt", context, seg, length)
    for prev, nxt in zip(segments, segments[1:]):
        gap = (nxt["start"] - prev["end"]) * dt
        assert gap >= ROOT_RESIST_SECONDS - dt - BOUND_EPS, (
            "Property 2 反例：相邻两段定身间隔不足 1.0 s - dt", context,
            prev, nxt, gap)


def random_root_schedule(rng, dt):
    """1-5 个定身来源：周期型（周期 0-3 s，接近 0 即每步都命中）或逐步随机型。"""
    sources = []
    for _ in range(rng.randint(1, 5)):
        name, slow = rng.choice(ROOT_SOURCES)
        if rng.random() < 0.5:
            sources.append({"name": name, "slow": slow, "mode": "periodic",
                            "period": rng.uniform(0.0, 3.0),
                            "next": rng.uniform(0.0, 3.0)})
        else:
            sources.append({"name": name, "slow": slow, "mode": "random",
                            "prob": rng.uniform(0.02, 1.0)})
    description = [
        ("%s/每 %.3fs 起于 %.3fs" % (src["name"], src["period"], src["next"])
         if src["mode"] == "periodic"
         else "%s/每步 p=%.3f" % (src["name"], src["prob"]))
        for src in sources]

    def hits_at(k):
        now = k * dt
        hits = []
        for src in sources:
            if src["mode"] == "periodic":
                if now + 1e-9 >= src["next"]:
                    hits.append((src["name"], src["slow"]))
                    src["next"] += src["period"]
            elif rng.random() < src["prob"]:
                hits.append((src["name"], src["slow"]))
        rng.shuffle(hits)
        return hits

    return description, hits_at


def spider_schedule(dt, phase):
    """单只巨蛛：从 phase 起每隔目录冷却命中一次（落在命中时刻之后的第一步）。"""
    state = {"next": phase}

    def hits_at(k):
        if k * dt + 1e-9 >= state["next"]:
            state["next"] += SPIDER_COOLDOWN
            return [("spider", WEB_SLOW)]
        return []

    return hits_at


# ================================================================ 性质测试

def property_slow_matches_model():
    """Property 1：减速/定身与参考模型一致。

    任意单位、长度 <= 30 的施加序列（每步随机取冰霜 / 雷暴 / 蛛网 / 兽夹或空步，
    步间以 0.05 s 细分推进 0-1.5 s），每次施加与每个 tick 后实现的
    (slowMult, slowTimer, rootResist) 与参考模型一致（误差 1e-6）。

    **Validates: Requirements 11.1, 11.2, 11.3, 11.4, 11.5, 11.6, 11.7, 11.8, 11.9, 11.10**
    """
    property_banner(1, "减速/定身与参考模型一致")
    rng = random.Random(1101)
    iterations = 300
    labels = {}
    for iteration in range(iterations):
        kind = rng.choice(UNIT_KINDS)
        unit = server.make_unit(kind, "pB", 1600.0, 1600.0)
        model = SlowModel()
        history = ["#%d" % iteration, kind]
        check_slow(unit, model, history)
        for _ in range(rng.randint(1, 30)):
            pick = rng.randrange(len(SLOW_SOURCES) + 1)
            if pick < len(SLOW_SOURCES):
                name, slow = SLOW_SOURCES[pick]
                history.append(name)
                server.apply_slow({"slow": slow}, unit)
                label = model.apply(float(slow["mult"]), float(slow["duration"]))
                labels[label] = labels.get(label, 0) + 1
                check_slow(unit, model, history)
            else:
                history.append("空步")
            seconds = 0.0 if rng.random() < 0.15 else rng.uniform(0.0, 1.5)
            history.append("+%.3fs" % seconds)
            for dt in split_advance(seconds):
                server.tick_status_timers(unit, dt)
                model.tick(dt)
                check_slow(unit, model, history)
    # 生成器自检：决策表的每个可达分支都被走到（雷暴与抗性降级同为 0.5，
    # 没有比 0.5 更弱的来源，所以「抗性降级后更强」不可达）。
    required = ("root", "root-over-slow", "ignored-rooted", "fresh", "stronger",
                "same-strength", "weaker-ignored", "resist-fresh",
                "resist-same-strength", "resist-weaker-ignored")
    missing = [label for label in required if not labels.get(label)]
    assert not missing, ("生成器未覆盖分支", missing, labels)
    print("  %d 条序列逐步对照通过；分支 %s: PASS" % (
        iterations, ", ".join("%s=%d" % item for item in sorted(labels.items()))))


def property_root_rhythm():
    """Property 2：定身节律上界。

    任意定身施加时间序列（任意频率、任意来源数，固定步长 dt <= 0.05）：任一连续
    定身段 <= 触发它的施加时长 + dt，相邻两段间隔 >= 1.0 s - dt；单只巨蛛按目录
    冷却持续命中 60 s，定身时间占比 <= 55%。

    **Validates: Requirements 11.11, 11.12**
    """
    property_banner(2, "定身节律上界")
    assert [name for name, _ in ROOT_SOURCES] == ["spider", "ttrap"], ROOT_SOURCES
    rng = random.Random(2202)
    iterations = 200
    segments_seen = 0
    worst_share = 0.0
    worst_case = None
    for iteration in range(iterations):
        if iteration % 2 == 0:
            dt = rng.choice((0.05, 0.04, 0.025, 0.02))
        else:
            dt = rng.uniform(0.01, 0.05)
        # (a) 任意频率、任意来源数的定身序列
        description, hits_at = random_root_schedule(rng, dt)
        ticks = int(rng.uniform(6.0, 20.0) / dt)
        segments, _ = run_root_timeline(dt, ticks, hits_at)
        check_root_rhythm(segments, dt, ("#%d" % iteration, dt, description))
        segments_seen += len(segments)
        # (b) 单只巨蛛持续命中 60 s；每 4 轮取一次相位 0（最坏情形）
        phase = 0.0 if iteration % 4 == 0 else rng.uniform(0.0, SPIDER_COOLDOWN)
        ticks = int(round(60.0 / dt))
        segments, rooted_ticks = run_root_timeline(
            dt, ticks, spider_schedule(dt, phase))
        check_root_rhythm(segments, dt, ("#%d spider" % iteration, dt, phase))
        share = rooted_ticks / float(ticks)
        assert share <= SPIDER_ROOT_SHARE_CAP, (
            "Property 2 反例：单蛛 60 s 定身占比超过 55%", dt, phase, share)
        if share > worst_share:
            worst_share, worst_case = share, (dt, phase)
    assert segments_seen > iterations, segments_seen
    # 连续时间理论值：定身 + 抗性走完后，下一次能定身的命中落在
    # ceil((定身 + 抗性) / 冷却) 个冷却之后（现值 2.2 + 1.0 -> 3 x 1.45 = 4.35 s）。
    cycle = math.ceil((WEB_SLOW["duration"] + ROOT_RESIST_SECONDS)
                      / SPIDER_COOLDOWN) * SPIDER_COOLDOWN
    print("  %d 轮通过；随机序列定身段 %d 个；单蛛 60 s 最高占比 %.1f%%"
          "（dt=%.4f, 相位 %.3f s；理论 %.1f%%，上限 55%%）: PASS" % (
              iterations, segments_seen, worst_share * 100.0, worst_case[0],
              worst_case[1], WEB_SLOW["duration"] / cycle * 100.0))


def property_dot_strongest_wins():
    """Property 3：持续伤害强者优先。

    任意 DoT 施加序列（蛛毒 / 毒矢 / 毒雾，任意间隔与目标护甲）：活动 DoT 的强度
    不因更弱的施加而下降；同强度时剩余时长取较大者；dotSourceId 属于最后一次写入
    计时的施加；到期后来源字段全部清空；毒死时击杀记给当时的 dotOwner。

    **Validates: Requirements 12.1, 12.2, 12.3, 12.4, 12.5, 12.6, 12.7**
    """
    property_banner(3, "持续伤害强者优先")
    rng = random.Random(3303)
    room, players = make_room("CTRLP3", ("tribe", "tech", "magic"))
    a, b, c = players
    owner_names = {a["id"]: "A", c["id"]: "C"}
    owners = (a["id"], c["id"])
    iterations = 300
    labels = {}
    kills_checked = 0
    serial = 0
    for iteration in range(iterations):
        kind = rng.choice(UNIT_KINDS)
        target = server.make_unit(kind, b["id"], 1600.0, 1600.0)
        target["hp"] = BIG_HP
        isolate(room["game"], target)
        model = DotModel(unit_armor(kind))
        hp = target["hp"]
        history = ["#%d" % iteration, kind]
        steps = rng.randint(1, 30)
        # 一半序列在随机一步把血量压低，让毒在后续某步致死，核对击杀归属。
        kill_step = rng.randrange(steps) if rng.random() < 0.5 else None
        dead = False
        for step in range(steps):
            if step == kill_step:
                hp = target["hp"] = rng.uniform(0.2, 25.0)
                history.append("hp=%.3f" % hp)
            if rng.random() < 0.8:
                name, dot = rng.choice(DOT_SOURCES)
                serial += 1
                owner = rng.choice(owners)
                payload = dot_payload(dot, owner, "%s#%d" % (name, serial), name)
                history.append("%s#%d/%s" % (name, serial, owner_names[owner]))
                before = dot_fields(target)
                was_active = model.active()
                current = dot_strength(model.dps, model.damage_type, model.armor)
                server.apply_dot(payload, target)
                label = model.apply(payload)
                labels[label] = labels.get(label, 0) + 1
                hp = check_dot(target, model, hp, history)
                if was_active:
                    incoming = dot_strength(dot["dps"], dot.get("damageType"),
                                            model.armor)
                    after = dot_strength(target["dotDps"], target["dotDamageType"],
                                         model.armor)
                    assert after >= current - STRENGTH_EPS, (
                        "强度因施加而下降", " ".join(history))
                    if incoming < current - STRENGTH_EPS:
                        assert dot_fields(target) == before, (
                            "更弱的施加改动了 DoT", " ".join(history))
                    elif abs(incoming - current) <= STRENGTH_EPS:
                        longest = max(float(before["dotTimer"]),
                                      float(dot["duration"]))
                        assert abs(target["dotTimer"] - longest) <= 1e-12, (
                            "同强度未取较长剩余", " ".join(history))
            seconds = 0.0 if rng.random() < 0.2 else rng.uniform(0.0, 1.5)
            history.append("+%.3fs" % seconds)
            for dt in split_advance(seconds):
                hp, dead = tick_dot_checked(room, players, target, model, hp,
                                            dt, history)
                if dead:
                    break
            if dead:
                break
        if kill_step is not None and not dead and model.active():
            history.append("收尾:按 %.2fs 推进到毒死或到期" % DT)
        while kill_step is not None and not dead and model.active():
            hp, dead = tick_dot_checked(room, players, target, model, hp,
                                        DT, history)
        if dead:
            kills_checked += 1
            # 已阵亡单位不再挂毒（12.8）
            frozen = dot_fields(target)
            name, dot = rng.choice(DOT_SOURCES)
            server.apply_dot(dot_payload(dot, a["id"], "late#%d" % iteration,
                                         name), target)
            assert dot_fields(target) == frozen, (
                "已阵亡单位被挂毒", " ".join(history))
    required = ("fresh", "stronger", "weaker-ignored", "same-longer",
                "same-ignored")
    missing = [label for label in required if not labels.get(label)]
    assert not missing, ("生成器未覆盖分支", missing, labels)
    assert kills_checked >= 20, kills_checked
    print("  %d 条序列逐步对照通过；分支 %s；毒死归属核对 %d 次: PASS" % (
        iterations, ", ".join("%s=%d" % item for item in sorted(labels.items())),
        kills_checked))


# ================================================================ 示例

def example_frost_keeps_root():
    print("\n=== 示例 1: 冰霜命中已定身目标仍定身（11.6、11.7、11.13） ===")
    unit = fresh_unit()
    server.apply_slow({"slow": WEB_SLOW}, unit)
    advance(unit, 0.5)
    remain = unit["slowTimer"]
    assert abs(remain - (WEB_SLOW["duration"] - 0.5)) < 1e-6, remain
    server.apply_slow({"slow": FROST_SLOW}, unit)
    assert unit["slowMult"] == 0.0, unit["slowMult"]
    assert unit["slowTimer"] == remain, (unit["slowTimer"], remain)
    assert server.public_unit(unit).get("rooted") is True
    # 定身中再定身也不续时
    server.apply_slow({"slow": TRAP_SLOW}, unit)
    server.apply_slow({"slow": WEB_SLOW}, unit)
    assert unit["slowTimer"] == remain, (unit["slowTimer"], remain)
    # 定身到期：恢复满速并写入 1.0 s 抗性；冰霜是普通减速，照常生效
    advance_until(unit, lambda u: u["slowTimer"] <= 0.0)
    assert unit["slowMult"] == 1.0, unit["slowMult"]
    assert abs(unit["rootResist"] - ROOT_RESIST_SECONDS) < 1e-9, unit["rootResist"]
    server.apply_slow({"slow": FROST_SLOW}, unit)
    assert abs(unit["slowMult"] - FROST_SLOW["mult"]) < 1e-9, unit["slowMult"]
    assert abs(unit["slowTimer"] - FROST_SLOW["duration"]) < 1e-9, unit["slowTimer"]
    print("  冰霜不解定身 / 定身不续时 / 到期抗性后冰霜生效: PASS")


def example_storm_keeps_frost():
    print("\n=== 示例 2: 雷暴不把冰霜降级（11.5、11.14） ===")
    assert FROST_SLOW["mult"] < STORM_SLOW["mult"] - STRENGTH_EPS, "前提：冰霜强于雷暴"
    unit = fresh_unit()
    server.apply_slow({"slow": FROST_SLOW}, unit)
    advance(unit, 1.0)
    remain = unit["slowTimer"]
    # 剩余短于雷暴时长：「忽略」与「同强度续时」在这里可区分
    assert 0.0 < remain < STORM_SLOW["duration"], remain
    server.apply_slow({"slow": STORM_SLOW}, unit)
    assert abs(unit["slowMult"] - FROST_SLOW["mult"]) < 1e-9, unit["slowMult"]
    assert unit["slowTimer"] == remain, (unit["slowTimer"], remain)
    print("  冰霜 %.2f 中被雷暴命中仍为 %.2f，剩余 %.2f s 不变: PASS" % (
        FROST_SLOW["mult"], unit["slowMult"], remain))


def example_frost_overrides_storm():
    print("\n=== 示例 3: 冰霜覆盖雷暴（11.3、11.15） ===")
    unit = fresh_unit()
    server.apply_slow({"slow": STORM_SLOW}, unit)
    advance(unit, 0.5)
    server.apply_slow({"slow": FROST_SLOW}, unit)
    assert abs(unit["slowMult"] - FROST_SLOW["mult"]) < 1e-9, unit["slowMult"]
    assert abs(unit["slowTimer"] - FROST_SLOW["duration"]) < 1e-9, unit["slowTimer"]
    public = server.public_unit(unit)
    assert public.get("slow") is True and public.get("rooted") is None, public
    print("  雷暴 %.2f 中被冰霜命中 -> %.2f / %.2f s: PASS" % (
        STORM_SLOW["mult"], FROST_SLOW["mult"], FROST_SLOW["duration"]))


def example_same_strength_and_resist():
    print("\n=== 示例 4: 同强度取较长；抗性期定身降为 x0.5（11.4、11.7、11.8、11.9） ===")
    unit = fresh_unit()
    server.apply_slow({"slow": STORM_SLOW}, unit)
    advance(unit, 1.0)
    assert abs(unit["slowTimer"] - (STORM_SLOW["duration"] - 1.0)) < 1e-6
    server.apply_slow({"slow": STORM_SLOW}, unit)
    assert abs(unit["slowTimer"] - STORM_SLOW["duration"]) < 1e-9, unit["slowTimer"]

    unit = fresh_unit()
    server.apply_slow({"slow": TRAP_SLOW}, unit)
    advance_until(unit, lambda u: u["slowTimer"] <= 0.0)
    assert unit["slowMult"] == 1.0, unit["slowMult"]
    assert abs(unit["rootResist"] - ROOT_RESIST_SECONDS) < 1e-9, unit["rootResist"]
    # 抗性期：定身改为 x0.5 减速，时长不变
    server.apply_slow({"slow": TRAP_SLOW}, unit)
    assert abs(unit["slowMult"] - ROOT_RESIST_SLOW_MULT) < 1e-9, unit["slowMult"]
    assert abs(unit["slowTimer"] - TRAP_SLOW["duration"]) < 1e-9, unit["slowTimer"]
    advance(unit, 0.3)
    assert abs(unit["rootResist"] - (ROOT_RESIST_SECONDS - 0.3)) < 1e-6
    # 再中一次（同为降级后的 0.5）：剩余取较长
    server.apply_slow({"slow": WEB_SLOW}, unit)
    longest = max(TRAP_SLOW["duration"] - 0.3, WEB_SLOW["duration"])
    assert abs(unit["slowMult"] - ROOT_RESIST_SLOW_MULT) < 1e-9, unit["slowMult"]
    assert abs(unit["slowTimer"] - longest) < 1e-6, (unit["slowTimer"], longest)
    held = unit["slowTimer"]
    server.apply_slow({"slow": TRAP_SLOW}, unit)
    assert unit["slowTimer"] == held, (unit["slowTimer"], held)
    # 抗性走完：定身恢复，覆盖仍在生效的 0.5 减速
    advance_until(unit, lambda u: u["rootResist"] <= 0.0)
    assert unit["slowTimer"] > 0.0 and unit["slowMult"] > 0.0
    server.apply_slow({"slow": WEB_SLOW}, unit)
    assert unit["slowMult"] == 0.0, unit["slowMult"]
    assert abs(unit["slowTimer"] - WEB_SLOW["duration"]) < 1e-9, unit["slowTimer"]
    print("  同强度续到较长 / 抗性期降级 / 抗性结束后定身覆盖减速: PASS")


def example_pit_not_downgraded():
    print("\n=== 示例 5: 毒雾坑中再中蛛毒仍保持毒雾坑（12.3、12.5、12.9） ===")
    armor = unit_armor("rifle")
    pit = dot_strength(PIT_DOT["dps"], PIT_DOT.get("damageType"), armor)
    web = dot_strength(WEB_DOT["dps"], WEB_DOT.get("damageType"), armor)
    assert pit > web + STRENGTH_EPS, ("前提：毒雾坑强于蛛毒", pit, web)
    rifle = fresh_unit("rifle")
    server.apply_dot(dot_payload(PIT_DOT, "pA", "s-pit", "tpit"), rifle)
    server.apply_dot(dot_payload(WEB_DOT, "pC", "u-spider", "spider"), rifle)
    assert rifle["dotDps"] == PIT_DOT["dps"], rifle["dotDps"]
    assert rifle["dotTimer"] == PIT_DOT["duration"], rifle["dotTimer"]
    assert (rifle["dotOwner"], rifle["dotSourceId"], rifle["dotSourceKind"]) == (
        "pA", "s-pit", "tpit"), dot_fields(rifle)
    # 反过来：更强的毒雾坑覆盖蛛毒，即使时长更短
    rifle = fresh_unit("rifle")
    server.apply_dot(dot_payload(WEB_DOT, "pC", "u-spider", "spider"), rifle)
    server.apply_dot(dot_payload(PIT_DOT, "pA", "s-pit", "tpit"), rifle)
    assert rifle["dotDps"] == PIT_DOT["dps"], rifle["dotDps"]
    assert rifle["dotTimer"] == PIT_DOT["duration"], rifle["dotTimer"]
    assert rifle["dotOwner"] == "pA" and rifle["dotSourceKind"] == "tpit"
    print("  毒雾坑 %.0f 不被蛛毒 %.0f 降级 / 蛛毒被毒雾坑覆盖: PASS" % (
        PIT_DOT["dps"], WEB_DOT["dps"]))


def example_immunity():
    print("\n=== 示例 6: 建筑、已阵亡单位与零时长施加免疫（11.10、12.8） ===")

    def hit_everything(entity, duration=None):
        for _, slow in SLOW_SOURCES:
            if duration is not None:
                slow = dict(slow, duration=duration)
            server.apply_slow({"slow": slow}, entity)
        for name, dot in DOT_SOURCES:
            if duration is not None:
                dot = dict(dot, duration=duration)
            server.apply_dot(dot_payload(dot, "pA", "x-" + name, name), entity)

    structure = server.make_structure("ttoxtower", "pB", 1600.0, 1600.0, True)
    before = dict(structure)
    hit_everything(structure)
    assert structure == before, "建筑不应挂减速/定身/持续伤害"

    dead = fresh_unit("rifle")
    dead["hp"] = 0.0
    before = dict(dead)
    hit_everything(dead)
    assert dead == before, "已阵亡单位不应挂减速/定身/持续伤害"

    alive = fresh_unit("rifle")
    before = dict(alive)
    for duration in (0.0, -1.0):
        hit_everything(alive, duration)
    assert alive == before, "时长 <= 0 的施加应被忽略"
    # 已有减速与持续伤害时，零时长施加同样不改状态
    server.apply_slow({"slow": STORM_SLOW}, alive)
    server.apply_dot(dot_payload(WEB_DOT, "pA", "u-spider", "spider"), alive)
    before = dict(alive)
    for duration in (0.0, -1.0):
        hit_everything(alive, duration)
    assert alive == before, "时长 <= 0 的施加不应改写现有状态"
    print("  建筑 / 已阵亡 / 时长 <= 0 一律忽略: PASS")


def example_dot_kill_attribution():
    print("\n=== 示例 7: DoT 致死记给当时的 dotOwner（12.5、12.7） ===")
    room, players = make_room("CTRLKILL", ("tribe", "tech", "magic"))
    a, b, c = players
    game = room["game"]

    def kills():
        return [player["kills"] for player in players]

    def poison_to_death(target, index):
        elapsed = 0.0
        while target["hp"] > 0:
            assert elapsed < 5.0, ("毒没能致死", target["hp"], dot_fields(target))
            server.tick_dot(room, target, DT, index)
            elapsed += DT

    # 1) 来源巨蛛在场：玩家击杀 +1，巨蛛自身击杀数 +1
    spider_a = server.make_unit("spider", a["id"], 3000.0, 3000.0)
    rifle = server.make_unit("rifle", b["id"], 3080.0, 3000.0)
    isolate(game, spider_a, rifle)
    rifle["hp"] = 8.0
    start = kills()
    server.apply_dot(dot_payload(WEB_DOT, a["id"], spider_a["id"], "spider"), rifle)
    poison_to_death(rifle, {spider_a["id"]: spider_a, rifle["id"]: rifle})
    assert kills() == [start[0] + 1, start[1], start[2]], (start, kills())
    assert spider_a["kills"] == 1, spider_a["kills"]

    # 2) 来源巨蛛已离场：仍记给 dotOwner
    spider_c = server.make_unit("spider", c["id"], 3000.0, 3000.0)
    rifle = server.make_unit("rifle", b["id"], 3080.0, 3000.0)
    isolate(game, spider_c, rifle)
    rifle["hp"] = 8.0
    server.apply_dot(dot_payload(WEB_DOT, c["id"], spider_c["id"], "spider"), rifle)
    isolate(game, rifle)
    start = kills()
    poison_to_death(rifle, {rifle["id"]: rifle})
    assert kills() == [start[0], start[1], start[2] + 1], (start, kills())
    assert spider_c["kills"] == 0, spider_c["kills"]

    # 3) 更强的毒覆盖后归属随之转移：A 的蛛毒 -> C 的毒雾坑 -> 记给 C
    rifle = server.make_unit("rifle", b["id"], 3080.0, 3000.0)
    isolate(game, rifle)
    rifle["hp"] = 8.0
    server.apply_dot(dot_payload(WEB_DOT, a["id"], "u-gone", "spider"), rifle)
    server.apply_dot(dot_payload(PIT_DOT, c["id"], "s-pit", "tpit"), rifle)
    assert rifle["dotOwner"] == c["id"] and rifle["dotSourceKind"] == "tpit"
    start = kills()
    poison_to_death(rifle, {rifle["id"]: rifle})
    assert kills() == [start[0], start[1], start[2] + 1], (start, kills())
    print("  来源在场 / 来源离场 / 覆盖后归属转移: PASS")


def main():
    started = time.time()
    property_slow_matches_model()
    property_root_rhythm()
    property_dot_strongest_wins()
    example_frost_keeps_root()
    example_storm_keeps_frost()
    example_frost_overrides_storm()
    example_same_strength_and_resist()
    example_pit_not_downgraded()
    example_immunity()
    example_dot_kill_attribution()
    print("\n=== 控制规则测试全部通过（%.1f s） ===" % (time.time() - started))


if __name__ == "__main__":
    main()
