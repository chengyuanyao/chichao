#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""固定出兵模板：没有 LLM 时，AI 就按"局势 → 模板"这张表打。

局势由三个离散量决定，都能在一 tick 内从战场状态直接读出来：

    我方阵营(tech/magic) × 敌方主护甲(unknown/infantry/light/heavy/arcane/mixed) × 阶段(open/mid/late)

表是手写的，因为它要能被人读懂和改。`planner.py` 会在应用模板前做一次
安全过滤：对当前实际看到的敌军零伤害的兵会被替换掉（军犬撞上一队构装体
就是这种情况），造不出来的兵（阵营不对/前置没有且短期补不上）也会被剔掉。

注释里的倍率来自 server.DAMAGE_MULTIPLIER，改平衡时请一并复核。
"""

from __future__ import print_function

# 建造顺序用 role 写，faction_buildings() 会翻译成两个阵营各自的建筑 kind。
# 这样一张表同时服务钢铁军团和秘法会。
OPENING_BUILD = [
    "power", "refinery", "barracks", "factory",
    "power", "refinery", "factory", "repair", "defense",
]

# 阶段 -> (矿车目标, 出击门槛, 炮塔上限)
PHASE_ECONOMY = {
    "open": (4, 999, 1),      # 开局不出击，先把经济和产能立起来
    "mid": (5, 14, 2),
    "late": (6, 20, 3),
}

ARMOR_BUCKETS = ("unknown", "infantry", "light", "heavy", "arcane", "mixed")
PHASES = ("open", "mid", "late")


def _t(mix, note):
    return {"mix": mix, "note": note}


TEMPLATES = {
    "tech": {
        # 还没侦察到：便宜、通用、不押注
        "unknown": {
            "open": _t({"rifle": 4, "dog": 2}, "没情报，先出便宜的兵营兵占场"),
            "mid": _t({"rifle": 3, "tank": 3, "rocket": 2}, "没情报，坦克抗线 + 火箭补反装甲"),
            "late": _t({"tank": 3, "overlord": 2, "rocket": 2, "tesla": 2},
                       "没情报，走通用重型混编"),
        },
        # 对面堆步兵：扑咬 ×4.00、狙击 ×2.20、爆炸 ×1.80
        "infantry": {
            "open": _t({"dog": 5, "rifle": 2}, "军犬扑咬对步兵 ×4.00，一口一个"),
            "mid": _t({"dog": 4, "sniper": 3, "tank": 2, "rifle": 2},
                      "军犬 ×4.00 + 狙击 ×2.20，坦克溅射清堆"),
            "late": _t({"dog": 3, "sniper": 3, "overlord": 2, "bomb_truck": 2},
                       "自爆爆炸对步兵 ×1.80，专炸成团步兵"),
        },
        # 对面轻甲载具：激光 ×1.50、磁暴 ×1.40、火箭 ×1.30
        "light": {
            "open": _t({"rifle": 3, "rocket": 2}, "火箭对轻甲 ×1.30，早期够用"),
            "mid": _t({"rocket": 3, "tesla": 3, "tank": 2},
                      "磁暴 ×1.40 / 火箭 ×1.30 打轻甲"),
            "late": _t({"prism": 4, "tesla": 3, "rocket": 2},
                       "光棱激光对轻甲 ×1.50，射程 305 还能拆建筑"),
        },
        # 对面重甲：穿甲 ×2.10、火箭 ×1.50、磁暴 ×1.30
        "heavy": {
            "open": _t({"rifle": 3, "rocket": 3}, "火箭对重甲 ×1.50，早期唯一的反装甲"),
            "mid": _t({"tank_destroyer": 4, "rocket": 3, "tank": 2},
                      "歼击车穿甲对重甲 ×2.10，是硬克星"),
            "late": _t({"tank_destroyer": 4, "overlord": 3, "rocket": 2, "tesla": 2},
                       "歼击车 ×2.10 打输出，天启 2000 血抗线"),
        },
        # 对面魔导甲（秘法会主力）：子弹 ×1.50、狙击/磁暴 ×1.60、激光 ×1.50
        # **穿甲对魔导甲只有 ×1.00**，这条是上一局输掉的直接原因
        "arcane": {
            "open": _t({"rifle": 4, "dog": 3},
                       "子弹对魔导甲 ×1.50；军犬能咬法师/晶刺这些肉身魔导"),
            "mid": _t({"tesla": 4, "rifle": 3, "tank": 2},
                      "磁暴对魔导甲 ×1.60，是钢铁反法师的答案；别造歼击车（×1.00）"),
            "late": _t({"tesla": 3, "prism": 3, "overlord": 3, "rifle": 2},
                       "光棱激光 ×1.50 远程点，天启抗魔法（魔法对重甲 ×1.60，靠 2000 血硬吃）"),
        },
        # 混编/混甲（晶铠卫士、裂地晶兽这种重轻混甲也落这里）
        "mixed": {
            "open": _t({"rifle": 3, "dog": 2, "rocket": 2}, "对面混编，先铺便宜的通用兵"),
            "mid": _t({"tank": 3, "rocket": 3, "tesla": 2, "rifle": 2},
                      "火箭/磁暴覆盖轻重甲，坦克抗线"),
            "late": _t({"overlord": 3, "tesla": 3, "prism": 2, "rocket": 2},
                       "重型混编，任何一种护甲都有人对付"),
        },
    },
    "magic": {
        # 魔法伤害对步兵 ×1.20、轻甲 ×1.30、重甲 ×1.60、魔导 ×1.00、建筑 ×0.60
        "unknown": {
            "open": _t({"imp": 4, "mage": 2}, "没情报，晶刺 200 一个先铺场"),
            "mid": _t({"mage": 3, "golem": 3, "imp": 2}, "傀儡抗线 + 法师输出"),
            "late": _t({"dragon": 3, "golem": 2, "mage": 2, "warden": 2}, "巨龙 + 卫士通用重型"),
        },
        "infantry": {
            "open": _t({"imp": 4, "mage": 2}, "魔法对步兵 ×1.20，晶刺便宜好铺"),
            "mid": _t({"golem": 3, "imp": 3, "mage": 2}, "傀儡溅射 34 清步兵堆"),
            "late": _t({"dragon": 3, "golem": 3, "oracle": 2},
                       "巨龙溅射 60 清人海，虹视使 300 射程点后排"),
        },
        "light": {
            "open": _t({"mage": 3, "imp": 3}, "魔法对轻甲 ×1.30"),
            "mid": _t({"mage": 3, "golem": 2, "oracle": 2}, "法师主输出，虹视使远程补枪"),
            "late": _t({"dragon": 3, "mage": 2, "oracle": 2, "warden": 2}, "巨龙领衔，卫士挡前"),
        },
        "heavy": {
            "open": _t({"mage": 3, "imp": 3}, "魔法对重甲 ×1.60，法师天生反坦克"),
            "mid": _t({"mage": 4, "golem": 2, "imp": 2}, "堆法师熔钢铁载具"),
            "late": _t({"dragon": 3, "mage": 3, "warden": 2, "golem": 2},
                       "巨龙 1100 血 + 法师 ×1.60，钢铁重甲吃不消"),
        },
        # 镜像内战：魔法对魔导甲是中性 ×1.00，纯拼性价比和血量
        "arcane": {
            "open": _t({"imp": 4, "mage": 2}, "同族对轰是中性伤害，拼每块钱输出"),
            "mid": _t({"imp": 3, "golem": 3, "mage": 2}, "傀儡 760 血换血，晶刺补输出"),
            "late": _t({"dragon": 3, "golem": 2, "warden": 2, "imp": 2}, "拼血量和溅射"),
        },
        "mixed": {
            "open": _t({"imp": 3, "mage": 3}, "对面混编，法师伤害对各甲都不吃亏"),
            "mid": _t({"mage": 3, "golem": 3, "imp": 2}, "法师 + 傀儡的通用组合"),
            "late": _t({"dragon": 3, "warden": 2, "golem": 2, "mage": 2}, "重型混编"),
        },
    },
}


def lookup(faction, armor_bucket, phase):
    """按局势取模板。任何一维没命中都逐级退到通用格子，永远返回一份可用配比。"""
    by_faction = TEMPLATES.get(faction) or TEMPLATES["tech"]
    by_armor = by_faction.get(armor_bucket) or by_faction["unknown"]
    entry = by_armor.get(phase) or by_armor.get("mid") or list(by_armor.values())[0]
    return {"mix": dict(entry["mix"]), "note": entry["note"],
            "id": "%s/%s/%s" % (faction, armor_bucket, phase)}


def economy(phase):
    return PHASE_ECONOMY.get(phase, PHASE_ECONOMY["mid"])
