#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Cosmetic easter eggs for 赤潮：钢铁前线.

Rules live here so tests can hit them without spinning a full match.
Nothing in this module changes unit stats, damage, cash, or victory.
"""

from __future__ import print_function

import math
import re

# 1) 密语：大厅或战场聊天输入「东风快递」——只有说话的人看见回句。
CHAT_PHRASE = "东风快递"
CHAT_REPLY = "密电：运单已核销。弹头在路上，指挥部勿再催件。"

# 2) 连点己方指挥中心 / 魔法主堡 7 下（间隔不超过窗口）——私聊 + 冒烟敬礼。
HQ_TAP_COUNT = 7
HQ_TAP_WINDOW = 2.4
HQ_REPLY_TECH = "指挥中心：雷达又给人拍转了。东风不会因为你手痒就提前到。"
HQ_REPLY_MAGIC = "魔法主堡：顶晶多转了两圈。圣泉说，指挥官的手很闲。"

# 3) 军犬咬死法师 / 冰霜女巫：约两成概率冒一句，并带一口独特扑咬特效。
DOG_MAGE_KINDS = frozenset(("mage", "frost"))
DOG_LINE_RATE = 0.18
DOG_LINES = (
    "军犬：袍子不好吃。",
    "军犬：秘法会，今晚加餐。",
    "军犬：法师的帽子卡牙了。",
)

# 4) 单兵第 16 杀：沿用晋升礼花，再按阵营补一句授衔。
PROMOTE_16_TECH = "%s 的王牌挂上了钢铁勋标。十六杀，东风可以稍等。"
PROMOTE_16_MAGIC = "%s 的秘法会士踏过十六具残骸。圣泉为他亮了一下。"

# 5) 赤金陨坑陨石核上的木牌。立在山体里，不挡路、不挡矿。
CRATER_LANDMARK = {
    "id": "first_pick",
    "x": 5000.0,
    "y": 3200.0,
    "radius": 88.0,
    "label": "先挖先富",
    "line": "坑边木牌：先挖先富。后挖的，去跟陨石核讲理。",
}

_PUNCT_RE = re.compile(r"[\s！!。.?？,，、~～…·—\-]+")


def normalize_chat_phrase(text):
    if not isinstance(text, str):
        return ""
    return _PUNCT_RE.sub("", text.strip())


def chat_reply(message):
    """Return the private reply if `message` is the secret phrase, else None."""
    if normalize_chat_phrase(message) == CHAT_PHRASE:
        return CHAT_REPLY
    return None


def note_hq_tap(player, now_ts):
    """Count a click on own HQ. Return True when the 7-tap salute should fire."""
    last = player.get("hqTapAt") or 0.0
    count = player.get("hqTaps") or 0
    if now_ts - last > HQ_TAP_WINDOW:
        count = 0
    count += 1
    player["hqTapAt"] = now_ts
    player["hqTaps"] = count
    if count < HQ_TAP_COUNT:
        return False
    player["hqTaps"] = 0
    return True


def hq_salute_line(player):
    if player.get("faction") == "magic":
        return HQ_REPLY_MAGIC
    return HQ_REPLY_TECH


def should_dog_quip(source_kind, target_kind, rng):
    if source_kind != "dog" or target_kind not in DOG_MAGE_KINDS:
        return False
    return rng.random() < DOG_LINE_RATE


def dog_quip(rng):
    return rng.choice(DOG_LINES)


def promote_16_line(player):
    name = player.get("name") or "指挥官"
    if player.get("faction") == "magic":
        return PROMOTE_16_MAGIC % name
    return PROMOTE_16_TECH % name


def inspect_landmark(map_def, x, y):
    """Return the landmark dict if (x, y) is on it, else None."""
    if not map_def:
        return None
    for mark in map_def.get("landmarks") or []:
        radius = float(mark.get("radius") or 80.0)
        if math.hypot(float(x) - float(mark["x"]), float(y) - float(mark["y"])) <= radius:
            return mark
    return None


def crater_landmark_on_core(map_def):
    """True when the flavor sign sits on the meteor mountain, clear of ore."""
    marks = list(map_def.get("landmarks") or [])
    if len(marks) != 1:
        return False
    mark = marks[0]
    core = None
    cx, cy = map_def["width"] / 2.0, map_def["height"] / 2.0
    for mountain in map_def.get("mountains") or []:
        if math.hypot(mountain["x"] - cx, mountain["y"] - cy) < 40:
            core = mountain
            break
    if core is None:
        return False
    dist = math.hypot(mark["x"] - core["x"], mark["y"] - core["y"])
    if dist >= core["r"] * 0.55:
        return False
    for ore in map_def.get("bonusResources") or []:
        if math.hypot(mark["x"] - ore["x"], mark["y"] - ore["y"]) < 160:
            return False
    return True
