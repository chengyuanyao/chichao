#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""AI 指挥官：给内置 AI 换一套会看克制关系的大脑。

设计约束（和本仓库其他代码一致）：
  * 只用 Python 3.6 标准库，不引入任何依赖；
  * **不修改任何既有文件**——靠 hook.install() 在运行时替换 server.tick_bots；
  * 服务端仍然是权威的，本包只调用 server 已有的下令接口。

入口：`python ai_commander/start.py`（Windows 双击 start-ai.bat）。
"""

import os as _os
import sys as _sys

# 允许 `python ai_commander/start.py` 这种跑法：把仓库根目录放进 sys.path，
# 这样 `import server` / `import catalog` 才找得到。
_ROOT = _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))
if _ROOT not in _sys.path:
    _sys.path.insert(0, _ROOT)

__all__ = ["codex", "templates", "planner", "commander", "llm", "hook", "config"]
