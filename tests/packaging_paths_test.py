#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Frozen resource root, writable battle_reports, and browser-open policy."""

from __future__ import print_function

import os
import sys
import tempfile
import threading
from urllib.request import ProxyHandler, build_opener

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import paths
import server


class FrozenBundle(object):
    def __init__(self, meipass, executable):
        self.meipass = meipass
        self.executable = executable
        self._old_frozen = getattr(sys, "frozen", None)
        self._old_meipass = getattr(sys, "_MEIPASS", None)
        self._old_executable = sys.executable

    def __enter__(self):
        sys.frozen = True
        sys._MEIPASS = self.meipass
        sys.executable = self.executable
        return self

    def __exit__(self, exc_type, exc, tb):
        if self._old_frozen is None:
            delattr(sys, "frozen")
        else:
            sys.frozen = self._old_frozen
        if self._old_meipass is None:
            delattr(sys, "_MEIPASS")
        else:
            sys._MEIPASS = self._old_meipass
        sys.executable = self._old_executable


def main():
    repo = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    index = os.path.join(server.PUBLIC_ROOT, "index.html")
    assert server.ROOT == paths.resource_root()
    assert server.PUBLIC_ROOT == paths.public_root()
    assert os.path.isfile(index), "source PUBLIC_ROOT must serve public/index.html"
    assert paths.battle_reports_dir() == os.path.join(repo, "battle_reports")

    empty = {"STEEL_FRONT_RESOURCE_DIR": "", "STEEL_FRONT_DATA_DIR": ""}
    with tempfile.TemporaryDirectory() as folder:
        meipass = os.path.join(folder, "meipass")
        exe_dir = os.path.join(folder, "payload")
        os.makedirs(os.path.join(meipass, "public"))
        os.makedirs(exe_dir)
        exe = os.path.join(exe_dir, "ChichaoSteelFront.exe")
        with open(exe, "wb") as handle:
            handle.write(b"stub")
        with open(os.path.join(meipass, "public", "index.html"), "w") as handle:
            handle.write("<html></html>")

        with FrozenBundle(meipass, exe):
            assert paths.is_frozen()
            assert paths.resource_root(empty) == os.path.abspath(meipass)
            assert paths.public_root(empty) == os.path.join(
                os.path.abspath(meipass), "public")
            assert paths.executable_dir() == os.path.abspath(exe_dir)
            assert paths.writable_root(empty) == os.path.abspath(exe_dir)
            assert paths.battle_reports_dir(empty) == os.path.join(
                os.path.abspath(exe_dir), "battle_reports")
            assert os.path.isfile(os.path.join(paths.public_root(empty), "index.html"))

            appdata = os.path.join(folder, "appdata")
            os.makedirs(appdata)
            blocked = dict(empty)
            blocked["APPDATA"] = appdata
            blocked["XDG_DATA_HOME"] = appdata
            original = paths.directory_is_writable
            paths.directory_is_writable = lambda directory: False
            try:
                fallback = paths.writable_root(blocked)
                reports = paths.battle_reports_dir(blocked)
            finally:
                paths.directory_is_writable = original
            if os.name == "nt":
                expected = os.path.join(appdata, "ChichaoSteelFront")
            else:
                expected = os.path.join(appdata, "chichao-steel-front")
            assert fallback == expected, fallback
            assert reports == os.path.join(expected, "battle_reports")

        override = {"STEEL_FRONT_DATA_DIR": os.path.join(folder, "custom-data")}
        assert paths.writable_root(override) == os.path.abspath(override["STEEL_FRONT_DATA_DIR"])

    argv = ["server.py"]
    quiet = {"STEEL_FRONT_OPEN_BROWSER": "", "STEEL_FRONT_NO_BROWSER": "",
             "STEEL_FRONT_LAUNCHER": "", "DISPLAY": ":0", "WAYLAND_DISPLAY": ""}
    assert paths.should_open_browser(argv, quiet) is False
    forced = dict(quiet)
    forced["STEEL_FRONT_OPEN_BROWSER"] = "1"
    assert paths.should_open_browser(argv, forced) is True
    launcher = dict(forced)
    launcher["STEEL_FRONT_LAUNCHER"] = "1"
    # C# launcher already opens a tab; its suppress flags win over inherited env.
    assert paths.should_open_browser(argv, launcher) is False
    no_flag = dict(quiet)
    no_flag["STEEL_FRONT_LAUNCHER"] = "1"
    assert paths.should_open_browser(argv, no_flag) is False
    assert paths.should_open_browser(["server.py", "--no-browser"], forced) is False
    assert paths.should_open_browser(["server.py", "--open-browser"], quiet) is True
    headless = dict(forced)
    headless["DISPLAY"] = ""
    headless["WAYLAND_DISPLAY"] = ""
    if os.name != "nt" and sys.platform != "darwin":
        assert paths.should_open_browser(argv, headless) is False

    with tempfile.TemporaryDirectory() as folder:
        exe = os.path.join(folder, "game")
        with FrozenBundle(folder, exe):
            frozen_env = dict(quiet)
            if os.name != "nt" and sys.platform != "darwin":
                frozen_env["DISPLAY"] = ":0"
            assert paths.should_open_browser(["ChichaoSteelFront"], frozen_env) is True
            frozen_env["STEEL_FRONT_LAUNCHER"] = "1"
            assert paths.should_open_browser(["ChichaoSteelFront"], frozen_env) is False

    assert paths.game_local_url("127.0.0.1", 18081) == "http://127.0.0.1:18081/"

    httpd = server.ThreadedHTTPServer(("127.0.0.1", 0), server.GameHandler)
    worker = threading.Thread(target=httpd.serve_forever, daemon=True)
    worker.start()
    try:
        port = httpd.server_address[1]
        opener = build_opener(ProxyHandler({}))
        with opener.open("http://127.0.0.1:%d/api/health" % port, timeout=3) as response:
            assert response.status == 200
        with opener.open("http://127.0.0.1:%d/" % port, timeout=3) as response:
            body = response.read()
            assert response.status == 200
            assert b"html" in body.lower()
    finally:
        httpd.shutdown()
        httpd.server_close()
        worker.join(3)

    print("packaging paths: frozen ROOT, writable reports, browser policy passed.")


if __name__ == "__main__":
    main()
