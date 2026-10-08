#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""The Windows CI workflow must build, smoke-test, and upload the zip."""

from __future__ import print_function

import os


def main():
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    path = os.path.join(root, ".github", "workflows", "windows-release.yml")
    assert os.path.isfile(path), path
    text = open(path, encoding="utf-8").read()

    assert "workflow_dispatch" in text
    assert "v*" in text
    assert "windows-latest" in text
    assert "actions/setup-python" in text
    assert "run_tests.py" in text
    assert "build_windows_release.ps1" in text
    assert "smoke_windows_exe.ps1" in text
    assert "actions/upload-artifact" in text
    assert "release/ChichaoSteelFront-win64.zip" in text
    assert "release/ChichaoSteelFront-source.zip" in text
    assert "draft" in text
    assert "butler" not in text
    assert "Not published to itch.io" in text
    assert "${{ secrets." not in text
    assert "ITCH_API_KEY" not in text
    assert "BUTLER_API_KEY" not in text

    smoke = os.path.join(root, "scripts", "smoke_windows_exe.ps1")
    assert os.path.isfile(smoke), smoke
    smoke_text = open(smoke, encoding="utf-8").read()
    assert "/api/health" in smoke_text
    assert "--no-browser" in smoke_text
    assert "127.0.0.1" in smoke_text

    print("windows release workflow: dispatch/tag triggers, artifact, smoke, no itch publish.")


if __name__ == "__main__":
    main()
