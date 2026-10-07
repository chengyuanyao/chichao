#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Resource and writable locations for source runs and frozen (PyInstaller) builds.

静态资源在冻结后从 ``sys._MEIPASS`` 读取；战报等写入目录必须离开只读包，
写到 exe 旁边，写不进去时再落到用户目录。
"""

from __future__ import print_function

import os
import sys
import tempfile


def is_frozen():
    """True when running inside a PyInstaller (or similar) bundle."""
    return bool(getattr(sys, "frozen", False)) or hasattr(sys, "_MEIPASS")


def _environ(environ):
    return os.environ if environ is None else environ


def resource_root(environ=None):
    """Read-only tree that contains ``public/`` and bundled data files."""
    environ = _environ(environ)
    override = environ.get("STEEL_FRONT_RESOURCE_DIR", "").strip()
    if override:
        return os.path.abspath(override)
    if is_frozen():
        return os.path.abspath(getattr(sys, "_MEIPASS"))
    return os.path.dirname(os.path.abspath(__file__))


def public_root(environ=None):
    return os.path.join(resource_root(environ), "public")


def executable_dir():
    """Directory of the running exe (frozen) or the source checkout."""
    if is_frozen():
        return os.path.dirname(os.path.abspath(sys.executable))
    return resource_root()


def user_data_dir(environ=None):
    """Per-user writable fallback when the exe directory is read-only."""
    environ = _environ(environ)
    if os.name == "nt":
        base = environ.get("APPDATA") or os.path.expanduser("~")
        return os.path.join(base, "ChichaoSteelFront")
    xdg = environ.get("XDG_DATA_HOME", "").strip()
    if xdg:
        return os.path.join(xdg, "chichao-steel-front")
    return os.path.join(os.path.expanduser("~"), ".local", "share",
                        "chichao-steel-front")


def directory_is_writable(directory):
    """Return True if a temp file can be created and removed in *directory*."""
    probe = None
    try:
        if not os.path.isdir(directory):
            os.makedirs(directory)
        fd, probe = tempfile.mkstemp(prefix=".sf_write_", dir=directory)
        os.close(fd)
        os.remove(probe)
        return True
    except OSError:
        if probe:
            try:
                os.remove(probe)
            except OSError:
                pass
        return False


def writable_root(environ=None):
    """Directory that may receive ``battle_reports/`` and similar outputs."""
    environ = _environ(environ)
    override = environ.get("STEEL_FRONT_DATA_DIR", "").strip()
    if override:
        return os.path.abspath(override)
    if is_frozen():
        beside = executable_dir()
        if directory_is_writable(beside):
            return beside
        return user_data_dir(environ)
    return resource_root(environ)


def battle_reports_dir(environ=None):
    return os.path.join(writable_root(environ), "battle_reports")


def display_available(environ=None):
    """Whether opening a desktop browser is likely to work."""
    environ = _environ(environ)
    if os.name == "nt" or sys.platform == "darwin":
        return True
    return bool(environ.get("DISPLAY") or environ.get("WAYLAND_DISPLAY"))


def _truthy(value):
    return str(value or "").strip().lower() in ("1", "true", "yes", "on")


def _falsey(value):
    return str(value or "").strip().lower() in ("0", "false", "no", "off")


def should_open_browser(argv=None, environ=None):
    """Open the local game URL after a successful bind, when reasonable.

    Frozen itch builds open by default. Source runs stay quiet unless the
    launcher scripts set ``STEEL_FRONT_OPEN_BROWSER=1``. ``--no-browser``,
    ``STEEL_FRONT_NO_BROWSER`` and ``STEEL_FRONT_LAUNCHER`` win, because the
    C# launcher already opens a tab.
    """
    argv = sys.argv if argv is None else list(argv)
    environ = _environ(environ)
    flags = set(item.lower() for item in argv[1:])
    if "--no-browser" in flags:
        return False
    if _truthy(environ.get("STEEL_FRONT_NO_BROWSER", "")):
        return False
    if _truthy(environ.get("STEEL_FRONT_LAUNCHER", "")):
        return False
    if "--open-browser" in flags:
        return True
    explicit = environ.get("STEEL_FRONT_OPEN_BROWSER", "")
    if _falsey(explicit):
        return False
    if _truthy(explicit):
        return display_available(environ)
    if is_frozen():
        return display_available(environ)
    return False


def game_local_url(host, port):
    return "http://%s:%d/" % (host, port)
