#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Release staging must drop tests, git metadata, and debug helpers."""

from __future__ import print_function

import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))
import stage_release


def main():
    repo = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    assert stage_release.cmd_check(repo) == 0

    rels = list(stage_release.iter_source_files(repo))
    assert "server.py" in rels
    assert "paths.py" in rels
    assert "public/index.html" in rels
    assert "public/assets/audio/KENNEY-LICENSE.txt" in rels
    assert "start-game.sh" in rels
    assert "give_cash.py" not in rels
    assert "CLAUDE.md" not in rels
    assert "ai_commander/llm.example.json" not in rels
    for rel in rels:
        top = rel.split("/")[0]
        assert top not in ("tests", ".git", ".kiro", "scripts", "dist", "build")
        assert not rel.endswith(".pyc")
        assert os.path.basename(rel) != "give_cash.py"

    with tempfile.TemporaryDirectory() as folder:
        staged = os.path.join(folder, "source")
        copied = stage_release.stage_source(staged, repo)
        assert "server.py" in copied
        assert os.path.isfile(os.path.join(staged, "public", "index.html"))
        assert not os.path.exists(os.path.join(staged, "give_cash.py"))
        assert not os.path.exists(os.path.join(staged, "tests"))
        assert not os.path.exists(os.path.join(staged, ".git"))
        assert not os.path.exists(os.path.join(staged, ".kiro"))
        assert not os.path.exists(os.path.join(staged, "scripts"))

        windows = os.path.join(folder, "win64")
        stage_release.stage_windows_layout(
            windows, dist_dir=os.path.join(folder, "missing-dist"),
            root=repo, allow_missing_exe=True)
        assert os.path.isfile(os.path.join(windows, "开始游戏.txt"))
        assert os.path.isfile(os.path.join(windows, "start-game.bat"))
        assert os.path.isfile(os.path.join(windows, "PACKAGING.md"))
        text = open(os.path.join(windows, "开始游戏.txt"), encoding="utf-8").read()
        assert "SmartScreen" in text
        assert "ChichaoSteelFront.exe" in text

    print("packaging manifest: exclude checklist and staging passed.")


if __name__ == "__main__":
    main()
