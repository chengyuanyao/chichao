#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""带 AI 指挥官启动游戏服务器。

    python ai_commander/start.py                # 启动时问一次 API Key
    python ai_commander/start.py --no-llm       # 直接走固定模板，不问
    python ai_commander/start.py --key sk-xxx --model gpt-4o-mini
    python ai_commander/start.py --mode first   # 一个房间里新旧 AI 各来一个

服务器本体、端口、静态文件全部沿用 server.py，这里只是在启动前把内置 AI
换掉。想跑回原版就直接 `python server.py`，什么都不用改。
"""

from __future__ import print_function

import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

import server                                    # noqa: E402
from ai_commander import config as ai_config     # noqa: E402
from ai_commander import hook                    # noqa: E402


def parse_args(argv):
    options = {"llm": None, "mode": None, "key": None, "base": None,
               "model": None, "provider": None, "interval": None, "save": False}
    index = 0
    while index < len(argv):
        item = argv[index]
        if item == "--no-llm":
            options["llm"] = False
        elif item == "--save":
            options["save"] = True
        elif item in ("-h", "--help"):
            print(__doc__)
            return None
        elif item.startswith("--") and index + 1 < len(argv):
            name = item[2:].replace("-", "_")
            if name in options:
                options[name] = argv[index + 1]
                index += 1
            else:
                print("未知参数 %s（--help 看用法）" % item)
                return None
        else:
            print("未知参数 %s（--help 看用法）" % item)
            return None
        index += 1
    return options


def build_settings(options):
    settings = ai_config.Settings()
    settings.load_file()
    settings.load_env()
    for name in ("provider", "base", "model", "key"):
        value = options.get(name)
        if value:
            setattr(settings, {"base": "base_url", "key": "api_key"}.get(name, name),
                    value)
    if options.get("interval"):
        try:
            settings.interval = max(10.0, float(options["interval"]))
        except ValueError:
            pass
    if options.get("mode"):
        mode = str(options["mode"]).strip().lower()
        if mode in ai_config.MODES:
            settings.mode = mode
        else:
            print("未知模式 %s，可选 %s" % (mode, "/".join(ai_config.MODES)))
    if options.get("llm") is False:
        settings.api_key = ""
        settings.model = ""
    elif not settings.llm_enabled():
        ai_config.prompt_for_llm(settings)
    if options.get("save") and settings.llm_enabled():
        settings.save_file()
    return settings


def main(argv=None):
    options = parse_args(list(argv if argv is not None else sys.argv[1:]))
    if options is None:
        return 0
    settings = build_settings(options)

    if settings.llm_enabled():
        print("  正在探活 LLM 端点……")
        why = settings.make_client().probe()
        if why:
            print("  ! LLM 不可用（%s）" % why)
            print("  ! 已自动切回固定模板模式，游戏照常开。")
            settings.api_key = ""
            settings.model = ""

    hook.install(settings)
    print("")
    print("  %s" % settings.describe())
    print("  接管范围：%s" % {"all": "全部 AI", "first": "每房第一个 AI（其余用原版）",
                               "off": "不接管"}[settings.mode])
    print("  （原版玩法不受影响，想跑回去直接 python server.py）")
    return server.main()


if __name__ == "__main__":
    sys.exit(main())
