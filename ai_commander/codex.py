#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""克制计算层：数值全部从 server / catalog 现读，不另抄一份。

外置的那版 agent 必须自己维护一张护甲表，因为 `/api/catalog` 不下发 `armor`；
它猜错了秘法会的护甲（法师当步兵甲、巨龙当重甲），于是全程拿穿甲
（对重甲 ×2.10、**对魔导甲只有 ×1.00**）当反甲主力，两波送光了部队。

跑在服务端进程里就没有这个问题：`UNIT_TYPES` 带 armor/damage/cooldown/range，
`DAMAGE_MULTIPLIER` 就是 `apply_damage` 真正查的那张表。catalog.py 改平衡，
这里自动跟上，不需要同步任何副本。
"""

from __future__ import print_function

import math

import server
from server import (DAMAGE_MULTIPLIER, STRUCTURE_TYPES, UNIT_TYPES,
                    VEHICLE_KINDS, damage_armor_multiplier)

ECONOMY_ROLES = ("harvester", "mcv")

# 自爆单位没有攻击间隔：它把 deathExplosion 一次性交出去然后自己没了。
# 用一个名义接敌时间把这一下摊开，dps 才和常规兵可比——否则 700 伤害
# 会让它看起来是全场最高输出。
SUICIDE_APPROACH_SECONDS = 12.0

# 造价的几次方：1.0 只看"每块钱战力"会一路偏向贵兵；2.0（兰彻斯特平方律，
# 同预算买便宜兵能买更多）会一路偏向最便宜的兵。溅射和射程压制会吃掉密集
# 廉价部队的人数优势，所以取几何中值。想要更"暴兵"就调低。
COST_EXPONENT = 1.5

TECH_UP_DISCOUNT = 0.85     # 还得先补前置建筑的兵，打个折但不排除


# ---------------------------------------------------------------- 基础查询
def is_combat_unit(kind):
    spec = UNIT_TYPES.get(kind)
    if not spec:
        return False
    if spec.get("role") in ECONOMY_ROLES:
        return False
    damage_type = spec.get("damageType")
    return bool(damage_type) and damage_type != "none"


def armor_of(kind):
    spec = UNIT_TYPES.get(kind)
    if spec is not None:
        return spec.get("armor", "heavy")
    spec = STRUCTURE_TYPES.get(kind)
    if spec is not None:
        return spec.get("armor", "structure")
    return "structure"


def armor_label(armor):
    """混甲 ('heavy','light') 打印成 heavy/light，方便日志对照。"""
    if isinstance(armor, (tuple, list)):
        return "/".join(str(piece) for piece in armor)
    return str(armor)


def counter(damage_type, target_kind):
    """伤害类型对某个 kind 的实际倍率。

    和 `apply_damage` 走同一张表、同一条特判：扑咬对载具（含秘法巨龙、
    岩石傀儡这些 armor 是 arcane 的构装体）是硬 0，只看护甲类看不出来。
    """
    if not damage_type or damage_type == "none":
        return 0.0
    if damage_type == "bite" and target_kind in VEHICLE_KINDS:
        return 0.0
    return damage_armor_multiplier(damage_type, armor_of(target_kind))


def attacker_counter(attacker_kind, target_kind):
    """具体兵种对目标的倍率；自爆单位优先读取按 kind 配置的目标倍率。"""
    spec = UNIT_TYPES.get(attacker_kind) or {}
    blast = spec.get("deathExplosion") or {}
    multipliers = blast.get("targetMultipliers")
    if multipliers is not None:
        if target_kind in multipliers:
            return float(multipliers[target_kind])
        if target_kind in STRUCTURE_TYPES:
            return float(multipliers.get(
                "structure", multipliers.get("default", 1.0)))
        return float(multipliers.get("default", 1.0))
    return counter(damage_type_of(attacker_kind), target_kind)


def sustained_damage(kind):
    """单位的"每秒基础伤害"，自爆单位按名义接敌时间摊开。"""
    spec = UNIT_TYPES.get(kind) or {}
    damage = float(spec.get("damage") or 0.0)
    cooldown = float(spec.get("cooldown") or 0.0)
    if damage > 0 and cooldown > 0:
        return damage / cooldown
    blast = spec.get("deathExplosion")
    if blast:
        return float(blast.get("damage") or 0.0) / SUICIDE_APPROACH_SECONDS
    return 0.0


def damage_type_of(kind):
    spec = UNIT_TYPES.get(kind) or {}
    blast = spec.get("deathExplosion")
    if blast and not spec.get("damage"):
        return blast.get("damageType") or spec.get("damageType")
    return spec.get("damageType")


def effective_dps(attacker_kind, target_kind):
    """打某个具体 kind 的每秒有效伤害（已乘护甲/目标倍率）。"""
    base = sustained_damage(attacker_kind)
    if base <= 0:
        return 0.0
    return base * attacker_counter(attacker_kind, target_kind)


def reach_of(kind):
    spec = UNIT_TYPES.get(kind) or {}
    return float(spec.get("range") or 0.0)


def faction_units(faction):
    return dict((kind, spec) for kind, spec in UNIT_TYPES.items()
                if spec.get("faction", "tech") == faction)


def faction_combat_units(faction):
    return dict((kind, spec) for kind, spec in faction_units(faction).items()
                if is_combat_unit(kind))


# ---------------------------------------------------------------- 敌情画像
def enemy_profile(census, prior_factions=()):
    """把"看见过什么"变成护甲/伤害/射程画像。

    census 是 {kind: 数量}，保留到 kind 这一层而不是只留护甲占比——军犬对
    构装体是硬 0、对法师却有 ×1.5，只看"魔导甲 72%"这个数字算不出这个差别。
    什么都没侦察到时，用对方阵营的全部战斗兵种做均匀先验，免得计划空转。
    """
    weights = {}
    total_seen = 0
    for kind, count in (census or {}).items():
        if count > 0 and kind in UNIT_TYPES and is_combat_unit(kind):
            weights[kind] = weights.get(kind, 0.0) + float(count)
            total_seen += count
    if not weights:
        prior = []
        for faction in prior_factions or ():
            prior.extend(faction_combat_units(faction).keys())
        for kind in prior:
            weights[kind] = weights.get(kind, 0.0) + 1.0
    total = sum(weights.values())
    if total <= 0:
        return {"targets": [], "armor": {}, "damage": {}, "range": 0.0, "seen": 0}

    targets = sorted(((kind, value / total) for kind, value in weights.items()),
                     key=lambda item: -item[1])
    armor = {}
    damage = {}
    range_sum = 0.0
    range_weight = 0.0
    for kind, share in targets:
        key = armor_label(armor_of(kind))
        armor[key] = armor.get(key, 0.0) + share
        dtype = damage_type_of(kind) or "none"
        damage[dtype] = damage.get(dtype, 0.0) + share
        rng = reach_of(kind)
        if rng > 0:
            range_sum += rng * share
            range_weight += share
    return {
        "targets": targets,
        "armor": armor,
        "damage": damage,
        "range": (range_sum / range_weight) if range_weight > 0 else 0.0,
        "seen": total_seen,
    }


def dominant_armor(profile):
    """占比最高的护甲类；混甲和并列都算 mixed，用来选固定模板。"""
    armor = profile.get("armor") or {}
    if not armor:
        return "unknown"
    ordered = sorted(armor.items(), key=lambda item: -item[1])
    top_key, top_share = ordered[0]
    if "/" in top_key:
        return "mixed"
    if top_share < 0.45:
        return "mixed"
    return top_key


# ---------------------------------------------------------------- 单兵评分
def unit_value(kind, profile, have_structures=()):
    """这个兵对这套敌情值不值得造。返回明细，便于日志解释。

        分数 = 对敌有效DPS × 有效HP ÷ 造价^1.5 × 射程系数 × 科技折扣

    倍率只是其中一项因子。只看倍率会选出"倍率最高"的贵兵；对秘法会来说，
    突击兵（子弹 ×1.50 打魔导甲、180 一个）的每块钱输出是坦克歼击车
    （穿甲对魔导甲 ×1.00、1050 一辆）的四倍多。
    """
    spec = UNIT_TYPES.get(kind)
    if not spec or not is_combat_unit(kind):
        return None
    cost = float(spec.get("cost") or 0.0)
    hp = float(spec.get("hp") or 0.0)
    if cost <= 0 or hp <= 0:
        return None

    targets = profile.get("targets") or []
    dps = 0.0
    for target_kind, share in targets:
        dps += effective_dps(kind, target_kind) * share
    if dps <= 0:
        return None

    # 有效 HP：挨的每一下都带对方伤害类型对我方护甲的倍率
    my_armor = spec.get("armor", "heavy")
    incoming = 0.0
    for dtype, share in (profile.get("damage") or {}).items():
        incoming += damage_armor_multiplier(dtype, my_armor) * share
    if incoming <= 0:
        incoming = 1.0
    ehp = hp / max(incoming, 0.2)

    # 射程：被风筝的兵活不到输出。62 个射程 125/205 的步兵冲 10 条射程 260
    # 且带溅射的巨龙，就是两波全送。
    reach = 1.0
    enemy_range = profile.get("range") or 0.0
    mine = reach_of(kind)
    if enemy_range > 0 and mine > 0:
        ratio = mine / enemy_range
        if ratio >= 1.0:
            reach = 1.25
        elif ratio < 0.6:
            reach = 0.7
        else:
            reach = 0.95

    have = set(have_structures or ())
    missing = [need for need in (spec.get("requires") or []) if need not in have]
    techup = TECH_UP_DISCOUNT if missing else 1.0

    score = dps * ehp / math.pow(cost, COST_EXPONENT) * reach * techup * 1000.0
    return {
        "kind": kind, "score": score, "dps": dps, "ehp": ehp,
        "cost": int(cost), "reach": reach, "missing": missing,
        "damageType": damage_type_of(kind),
    }


def rank_units(faction, profile, have_structures=()):
    """本阵营所有战斗兵种按性价比排序，返回明细列表。"""
    rows = []
    for kind in faction_combat_units(faction):
        value = unit_value(kind, profile, have_structures)
        if value is not None:
            rows.append(value)
    rows.sort(key=lambda row: (-row["score"], row["cost"], row["kind"]))
    return rows


def counter_note(faction, profile, limit=3):
    """一句人能读的克制速记，写进日志和 LLM 提示词。"""
    rows = rank_units(faction, profile)
    if not rows:
        return ""
    armor = "、".join(
        "%s%d%%" % (key, int(round(share * 100)))
        for key, share in sorted((profile.get("armor") or {}).items(),
                                 key=lambda item: -item[1])[:3])
    good = "、".join(
        "%s(%.0fdps/%d钱)" % (UNIT_TYPES[row["kind"]]["name"], row["dps"], row["cost"])
        for row in rows[:limit])
    worst = [row for row in reversed(rows) if row["score"] < rows[0]["score"] * 0.4]
    text = "敌方护甲以 %s 为主；性价比最高=%s" % (armor or "未知", good)
    if worst:
        text += "；别堆=" + "、".join(
            "%s(%.0fdps/%d钱)" % (UNIT_TYPES[row["kind"]]["name"], row["dps"], row["cost"])
            for row in worst[:2])
    return text
