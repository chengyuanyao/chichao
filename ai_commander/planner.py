#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把"局势"变成一份可执行的计划：造什么楼、出什么兵、什么时候压。

两条输入，优先级从低到高：
  1. `templates.py` 的固定模板 —— 没有 LLM 时唯一的来源，也是永远的兜底；
  2. LLM 顾问给的指令 —— 只允许覆盖配比/建造/门槛这几个字段，而且要过校验。

不管来源是哪个，最后都会跑一遍**克制安全过滤**：对当前真正看到的敌军
零伤害的兵一律换掉。这条是硬约束，LLM 也改不动——它正是上一局的死因
（拿对魔导甲 ×1.00 的穿甲当反甲主力，还把军犬派去咬构装体）。
"""

from __future__ import print_function

from server import STRUCTURE_TYPES, UNIT_TYPES, faction_buildings

from ai_commander import codex, templates

MIX_SLOTS = 4          # 一份配比最多同时铺几个兵种
MIN_USEFUL_DPS = 0.05  # 低于这个有效 dps 视为"打不动"，直接换兵

# LLM 的 build_order 会整段替掉建造序列，但这两样不许被替没：
#   refinery —— 唯一的收入来源；
#   factory  —— 矿车的产地（钢铁军团 harvester.producer 就是 factory，
#               秘法会是 mcircle）。
# 少任何一个，这一局的经济当场判死刑：没有矿车就没有收入，没有收入就永远
# 补不上矿车。电力另有 commander.POWER_BUFFER 兜底，不必列在这里。
ESSENTIAL_ROLES = ("refinery", "factory")


# ---------------------------------------------------------------- 局势判定
def phase_of(roles, elapsed):
    """开局 / 中期 / 后期。用建筑进度判定，比掐秒表稳。"""
    if "repair" in roles:
        return "late"
    if "factory" in roles:
        return "mid"
    if elapsed > 240.0:
        # 四分钟还没立起工厂/法阵，多半是被压着打，别一直按开局模板过日子
        return "mid"
    return "open"


def build_kind(faction, role):
    """把 role 翻成本阵营的建筑 kind。"""
    return faction_buildings(faction).get(role)


def role_of_kind(kind):
    return (STRUCTURE_TYPES.get(kind) or {}).get("role")


# ---------------------------------------------------------------- 配比过滤
def _producer_of(kind):
    return (UNIT_TYPES.get(kind) or {}).get("producer")


def _buildable_ever(kind, faction):
    spec = UNIT_TYPES.get(kind)
    if not spec or spec.get("faction", "tech") != faction:
        return False
    return codex.is_combat_unit(kind)


def _producible_now(kind, have_structures):
    """这个兵**现在**就能排进队列吗：产地建好了，前置科技也建好了。

    只看 `requires` 是不够的。歼击车没有 requires，产地却是工厂；工厂没立起来
    之前它一样一个都排不出。判错的后果是「兜底兵」这条不触发——兵营明明立在
    那里，配比里却一个兵营兵都没有，于是整段科技期一个兵都产不出来。
    """
    spec = UNIT_TYPES.get(kind) or {}
    producer = spec.get("producer")
    if producer and producer not in have_structures:
        return False
    for need in spec.get("requires") or []:
        if need not in have_structures:
            return False
    return True


def sanitize_mix(mix, faction, profile, have_structures):
    """把配比修成"这局真能造、而且真打得动"的样子。

    - 阵营不对 / 不是战斗兵 -> 丢掉；
    - 对已侦察到的敌军有效 dps ≈ 0 -> 换成同产地里评分最高的兵；
    - 全是二级兵 -> 补一个当前就能造的，否则科技起来前一个兵都排不出来。
    """
    ranked = codex.rank_units(faction, profile, have_structures)
    by_kind = dict((row["kind"], row) for row in ranked)
    seen_enemy = (profile.get("seen") or 0) > 0

    result = {}
    replaced = []
    for kind, weight in sorted(mix.items(), key=lambda item: -item[1]):
        weight = int(weight)
        if weight <= 0 or not _buildable_ever(kind, faction):
            continue
        row = by_kind.get(kind)
        useless = seen_enemy and (row is None or row["dps"] < MIN_USEFUL_DPS)
        if not useless:
            result[kind] = weight
            continue
        # 换一个同产地、评分最高、还没进配比的兵
        producer = _producer_of(kind)
        swap = None
        for candidate in ranked:
            if candidate["kind"] in result or candidate["dps"] < MIN_USEFUL_DPS:
                continue
            if _producer_of(candidate["kind"]) == producer:
                swap = candidate["kind"]
                break
        if swap is None:
            for candidate in ranked:
                if candidate["kind"] not in result and candidate["dps"] >= MIN_USEFUL_DPS:
                    swap = candidate["kind"]
                    break
        if swap is not None:
            result[swap] = max(result.get(swap, 0), weight)
            replaced.append((kind, swap))

    if not result:
        for row in ranked[:MIX_SLOTS]:
            result[row["kind"]] = 3

    def _rank_key(item):
        return -(item[1] * by_kind.get(item[0], {}).get("score", 1.0))

    if len(result) > MIX_SLOTS:
        result = dict(sorted(result.items(), key=_rank_key)[:MIX_SLOTS])

    # 兜底兵：配比全是现在造不出来的兵时，补一个立刻就能排的。
    # 必须放在裁剪之后——先补再裁的话，兜底兵权重最低，往往正好被裁掉。
    if result and not any(_producible_now(kind, have_structures) for kind in result):
        for row in ranked:
            if not _producible_now(row["kind"], have_structures):
                continue
            if len(result) >= MIX_SLOTS:
                result.pop(sorted(result.items(), key=_rank_key)[-1][0])
            result[row["kind"]] = 2
            break
    return result, replaced


def sanitize_build(build, faction):
    """建造序列的硬约束：精炼厂和矿车产地必须在，缺了就补到最前面。

    和 `sanitize_mix` 一个道理——配比归 LLM 管，但「还能不能活下去」不归它管。
    """
    out = list(build)
    for role in reversed(ESSENTIAL_ROLES):
        kind = build_kind(faction, role)
        if kind and kind not in out:
            out.insert(0, kind)
    return out


def required_structures(mix, faction):
    """这套配比要真出得来，最少得有哪几栋建筑（产地 + 前置科技）。"""
    out = []
    for kind in mix:
        spec = UNIT_TYPES.get(kind) or {}
        for need in [spec.get("producer")] + list(spec.get("requires") or []):
            if not need or need in out:
                continue
            definition = STRUCTURE_TYPES.get(need)
            if definition and definition.get("faction", "tech") == faction:
                out.append(need)
    return out


# ---------------------------------------------------------------- 计划装配
def make_plan(faction, roles, elapsed, profile, have_structures, directive=None):
    """返回这一 tick 该执行的计划。directive 是 LLM 指令，可以为 None。"""
    phase = phase_of(roles, elapsed)
    bucket = codex.dominant_armor(profile)
    template = templates.lookup(faction, bucket, phase)
    harvesters, attack_at, max_turrets = templates.economy(phase)

    mix = dict(template["mix"])
    note = template["note"]
    source = "template"

    if directive:
        source = "llm"
        if directive.get("army_mix"):
            mix = dict(directive["army_mix"])
        if directive.get("harvesters"):
            harvesters = int(directive["harvesters"])
        if directive.get("attack_at") is not None:
            attack_at = int(directive["attack_at"])
        if directive.get("max_turrets") is not None:
            max_turrets = int(directive["max_turrets"])
        if directive.get("note"):
            note = str(directive["note"])[:160]

    mix, replaced = sanitize_mix(mix, faction, profile, have_structures)

    build = []
    for role in templates.OPENING_BUILD:
        kind = build_kind(faction, role)
        if kind:
            build.append(kind)
    if directive and directive.get("build_order"):
        override = []
        for item in directive["build_order"]:
            kind = build_kind(faction, item) or (
                item if role_of_kind(item) and
                STRUCTURE_TYPES[item].get("faction", "tech") == faction else None)
            if kind:
                override.append(kind)
        if override:
            build = override
    build = sanitize_build(build, faction)
    for kind in required_structures(mix, faction):
        if kind not in build:
            build.append(kind)

    return {
        "phase": phase,
        "armor_bucket": bucket,
        "template": template["id"],
        "source": source,
        "mix": mix,
        "build": build,
        "harvesters": max(2, min(9, harvesters)),
        "attack_at": max(0, attack_at),
        "max_turrets": max(0, min(6, max_turrets)),
        "note": note,
        "replaced": replaced,
    }
