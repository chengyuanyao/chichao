#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把 ai_commander 的离线自检纳入 run_tests.py。

自检本体在 `ai_commander/selftest.py`，那里也可以单独跑
（`python ai_commander/selftest.py`）。这个壳的作用只是让仓库统一的
`python run_tests.py` 能一起覆盖到——否则新 AI 的 60 多项检查永远在
回归之外，改 catalog 平衡时不会有人发现它被改坏了。

不需要 LLM，也不需要跑起服务器。
"""

from __future__ import print_function

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ai_commander import selftest  # noqa: E402


if __name__ == "__main__":
    sys.exit(selftest.main())
