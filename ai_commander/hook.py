#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把内置 AI 换成 ai_commander，且**不动任何既有文件**。

`server.tick_game` 里是 `tick_bots(room)` 这样按模块全局名调用的，所以在
运行时重新绑定 `server.tick_bots` 就能整体接管，不需要改 server.py 一个字。

三种模式（环境变量 AI_COMMANDER 或 start.py --mode）：
    all   —— 所有 AI 都换新大脑（默认）
    first —— 每个房间只换第一个 AI，其余留给原版，方便同场对比新旧
    off   —— 完全不接管，等于没装
"""

from __future__ import print_function

import traceback

import server

from ai_commander import config as ai_config
from ai_commander.commander import STATE_KEY, Commander

_ORIGINAL = None
_STATE = {"settings": None, "commander": None, "log": print,
          "seen_errors": set()}


def _log(*parts):
    _STATE["log"]("".join(str(part) for part in parts))


def _ensure_advisor(bot, mem):
    settings = _STATE["settings"]
    if not settings or not settings.llm_enabled():
        return
    advisor = mem.get("advisor")
    if advisor is not None and advisor.alive():
        return
    # 顾问线程闲置过久会自己退出（见 llm.IDLE_EXIT_SECONDS）。这局又打起来了
    # 就重新拉一个，别让这个 bot 从此永远只剩固定模板。
    from ai_commander.llm import Advisor
    client = settings.make_client()
    if client is None:
        return
    mem["advisor"] = Advisor(client, settings.interval, log=_log)


def _stop_advisor(player):
    mem = player.get(STATE_KEY) or {}
    advisor = mem.get("advisor")
    if advisor is not None:
        advisor.stop()
        mem["advisor"] = None


def _stop_advisors(room):
    """显式收掉顾问线程。

    注意这条路径靠不住：`tick_game` 在 status != "playing" 时第一行就 return，
    所以房间一结束 `tick_bots` 就再也不会被调用，写在这里的清理跑不到。真正
    兜底的是 `llm.Advisor` 自己的闲置超时退出，这里只是能收就早点收。
    """
    for player in room["players"].values():
        _stop_advisor(player)


def _selected(bots, mode):
    if mode == "off":
        return []
    if mode == "first":
        return bots[:1]
    return list(bots)


def tick_bots(room):
    """替换掉的 tick_bots。任何异常都退回原版，绝不让一个 bug 卡住整局。"""
    brain = _STATE["commander"]
    settings = _STATE["settings"]
    if brain is None or settings is None:
        return _ORIGINAL(room)

    if room.get("status") == "finished":
        _stop_advisors(room)
        return _ORIGINAL(room)

    bots = []
    for player in room["players"].values():
        if not player["isBot"]:
            continue
        if player["eliminated"]:
            # 淘汰了就不会再有人喂它快照，顾问留着也是空转。
            _stop_advisor(player)
            continue
        bots.append(player)
    if not bots:
        return None

    taken = []
    for bot in _selected(bots, settings.mode):
        if bot.get("_aic_failed"):
            continue
        mem = brain.state(bot)
        _ensure_advisor(bot, mem)
        try:
            brain.tick(room, bot)
            taken.append(bot)
        except Exception:                     # noqa: BLE001 - 出错就降级回原版
            bot["_aic_failed"] = True
            trace = traceback.format_exc()
            # 按异常签名去重：同一个 bug 被六个 bot 同时撞上只报一行，但换一
            # 个 bug 仍然报得出来。全进程只报一次的话，第二个 bot 因为别的原因
            # 静默退回内置逻辑，现象就是「新 AI 好像没生效」，非常难查。
            signature = trace.strip().rsplit("\n", 1)[-1]
            if signature not in _STATE["seen_errors"]:
                _STATE["seen_errors"].add(signature)
                _log("[AI] %s 的指挥官出错，该 AI 已退回内置逻辑：\n%s"
                     % (bot.get("name", bot["id"]), trace))

    leftovers = [bot for bot in bots if bot not in taken]
    if not leftovers:
        return None

    # 让原版只处理没被接管的那些：它的筛选条件是 isBot and not eliminated，
    # 所以在这一次同步调用里临时把已接管的 bot 标成非 AI 即可。整段都在
    # room_lock 里跑，finally 保证一定还原。
    for bot in taken:
        bot["isBot"] = False
    try:
        return _ORIGINAL(room)
    finally:
        for bot in taken:
            bot["isBot"] = True


def install(settings=None, log=print):
    """装上新 AI。重复调用是安全的。"""
    global _ORIGINAL
    _STATE["settings"] = settings or ai_config.load(interactive=False)
    _STATE["log"] = log
    _STATE["commander"] = Commander(_STATE["settings"], log=log)
    _STATE["seen_errors"] = set()
    if _ORIGINAL is None:
        _ORIGINAL = server.tick_bots
        server.tick_bots = tick_bots
    return _STATE["settings"]


def uninstall():
    global _ORIGINAL
    if _ORIGINAL is not None:
        server.tick_bots = _ORIGINAL
        _ORIGINAL = None
    _STATE["commander"] = None


def installed():
    return _ORIGINAL is not None
