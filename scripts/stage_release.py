#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Stage itch.io release trees. Build-time helper; not imported by the game.

用法：
  python scripts/stage_release.py check
  python scripts/stage_release.py source --output release/ChichaoSteelFront-source
  python scripts/stage_release.py windows-layout --output release/ChichaoSteelFront-win64
"""

from __future__ import print_function

import argparse
import os
import shutil
import sys
import zipfile


ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

# 发行 zip 必须排除的目录名（任意层级）。
EXCLUDE_DIR_NAMES = frozenset((
    ".git",
    ".github",
    ".kiro",
    ".cursor",
    "__pycache__",
    "tests",
    "dist",
    "build",
    "release",
    "scripts",
    "artifacts",
    "battle_reports",
))

# 仅按文件名排除。
EXCLUDE_FILE_NAMES = frozenset((
    "give_cash.py",
    "CLAUDE.md",
    ".gitignore",
    ".gitattributes",
    "launcher.log",
))

# 相对仓库根的路径（正斜杠）。
EXCLUDE_RELATIVE = frozenset((
    "ai_commander/llm.example.json",
    "ai_commander/llm.json",
    "ai_commander/.gitignore",
))

EXCLUDE_SUFFIXES = (".pyc", ".pyo", ".pid", ".log")

# 源码发行包至少要带上这些文件，缺了就不要打 zip。
REQUIRED_SOURCE_FILES = (
    "server.py",
    "paths.py",
    "catalog.py",
    "easter_eggs.py",
    "battle_report.py",
    "diagnostics.py",
    "rift_map.py",
    "tactical_orders.py",
    "formation.py",
    "event_stream.py",
    "start-game.bat",
    "start-game.sh",
    "README.md",
    "PACKAGING.md",
    "public/index.html",
    "public/app.js",
    "public/render3d.js",
    "public/assets/audio/KENNEY-LICENSE.txt",
)

REQUIRED_WINDOWS_FILES = (
    "ChichaoSteelFront.exe",
    "开始游戏.txt",
    "start-game.bat",
)


def normalize_rel(path):
    return path.replace("\\", "/").lstrip("./")


def excluded_dir_name(name):
    return name in EXCLUDE_DIR_NAMES


def excluded_file(rel, name):
    rel = normalize_rel(rel)
    if name in EXCLUDE_FILE_NAMES:
        return True
    if rel in EXCLUDE_RELATIVE:
        return True
    if name.endswith(EXCLUDE_SUFFIXES):
        return True
    return False


def iter_source_files(root=None):
    """Yield repo-relative paths that belong in the source / macOS / Linux zip."""
    root = ROOT if root is None else root
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(
            name for name in dirnames if not excluded_dir_name(name))
        rel_dir = os.path.relpath(dirpath, root)
        for name in sorted(filenames):
            if rel_dir == ".":
                rel = name
            else:
                rel = os.path.join(rel_dir, name)
            if excluded_file(rel, name):
                continue
            yield normalize_rel(rel)


def checklist():
    """Human-readable exclude / include summary for PACKAGING.md and CI."""
    lines = [
        "排除目录: " + ", ".join(sorted(EXCLUDE_DIR_NAMES)),
        "排除文件名: " + ", ".join(sorted(EXCLUDE_FILE_NAMES)),
        "排除相对路径: " + ", ".join(sorted(EXCLUDE_RELATIVE)),
        "排除后缀: " + ", ".join(EXCLUDE_SUFFIXES),
        "源码包必含: " + ", ".join(REQUIRED_SOURCE_FILES),
        "Windows 冻结包必含: " + ", ".join(REQUIRED_WINDOWS_FILES),
    ]
    return lines


def missing_required(root, required):
    missing = []
    for rel in required:
        if not os.path.isfile(os.path.join(root, rel.replace("/", os.sep))):
            missing.append(rel)
    return missing


def stage_source(output, root=None):
    root = ROOT if root is None else root
    if os.path.exists(output):
        shutil.rmtree(output)
    os.makedirs(output)
    copied = []
    for rel in iter_source_files(root):
        src = os.path.join(root, rel.replace("/", os.sep))
        dest = os.path.join(output, rel.replace("/", os.sep))
        parent = os.path.dirname(dest)
        if parent and not os.path.isdir(parent):
            os.makedirs(parent)
        shutil.copy2(src, dest)
        copied.append(rel)
    missing = missing_required(output, REQUIRED_SOURCE_FILES)
    if missing:
        raise SystemExit("源码发行目录缺少: %s" % ", ".join(missing))
    return copied


def stage_windows_layout(output, dist_dir=None, root=None, allow_missing_exe=False):
    """Copy PyInstaller onedir output plus player-facing extras."""
    root = ROOT if root is None else root
    if dist_dir is None:
        dist_dir = os.path.join(root, "dist", "ChichaoSteelFront")
    if os.path.exists(output):
        shutil.rmtree(output)
    os.makedirs(output)
    if os.path.isdir(dist_dir):
        for name in os.listdir(dist_dir):
            src = os.path.join(dist_dir, name)
            dest = os.path.join(output, name)
            if os.path.isdir(src):
                shutil.copytree(src, dest)
            else:
                shutil.copy2(src, dest)
    elif not allow_missing_exe:
        raise SystemExit("找不到 PyInstaller 输出目录: %s" % dist_dir)

    extras = (
        (os.path.join(root, "scripts", "player-readme.txt"), "开始游戏.txt"),
        (os.path.join(root, "start-game.bat"), "start-game.bat"),
        (os.path.join(root, "PACKAGING.md"), "PACKAGING.md"),
        (os.path.join(root, "README.md"), "README.md"),
    )
    for src, dest_name in extras:
        if os.path.isfile(src):
            shutil.copy2(src, os.path.join(output, dest_name))

    missing = missing_required(output, REQUIRED_WINDOWS_FILES)
    if missing and not allow_missing_exe:
        raise SystemExit("Windows 发行目录缺少: %s" % ", ".join(missing))
    return output


def write_zip(folder, zip_path):
    parent = os.path.dirname(zip_path)
    if parent and not os.path.isdir(parent):
        os.makedirs(parent)
    prefix = os.path.basename(folder.rstrip(os.sep))
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as archive:
        for dirpath, dirnames, filenames in os.walk(folder):
            dirnames.sort()
            for name in sorted(filenames):
                full = os.path.join(dirpath, name)
                rel = os.path.relpath(full, os.path.dirname(folder))
                archive.write(full, rel.replace("\\", "/"))
    return zip_path


def cmd_check(root=None):
    root = ROOT if root is None else root
    for line in checklist():
        print(line)
    missing = missing_required(root, REQUIRED_SOURCE_FILES)
    if missing:
        print("仓库缺少发行所需文件: %s" % ", ".join(missing))
        return 1
    leaked = []
    for rel in iter_source_files(root):
        name = os.path.basename(rel)
        if name in EXCLUDE_FILE_NAMES or rel in EXCLUDE_RELATIVE:
            leaked.append(rel)
        if rel.split("/")[0] in EXCLUDE_DIR_NAMES:
            leaked.append(rel)
    if leaked:
        print("过滤失败，仍会打进源码包: %s" % ", ".join(leaked))
        return 1
    print("源码发行清单检查通过，共 %d 个文件。" % len(list(iter_source_files(root))))
    return 0


def build_parser():
    parser = argparse.ArgumentParser(description="Stage itch.io release trees")
    sub = parser.add_subparsers(dest="command")
    sub.add_parser("check")
    source = sub.add_parser("source")
    source.add_argument("--output", required=True)
    source.add_argument("--zip")
    windows = sub.add_parser("windows-layout")
    windows.add_argument("--output", required=True)
    windows.add_argument("--dist")
    windows.add_argument("--zip")
    windows.add_argument("--allow-missing-exe", action="store_true")
    return parser


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command == "check" or args.command is None:
        return cmd_check()
    if args.command == "source":
        copied = stage_source(os.path.abspath(args.output))
        print("已暂存源码发行目录 %s（%d 个文件）" % (args.output, len(copied)))
        if args.zip:
            write_zip(os.path.abspath(args.output), os.path.abspath(args.zip))
            print("已写入 %s" % args.zip)
        return 0
    if args.command == "windows-layout":
        stage_windows_layout(
            os.path.abspath(args.output),
            dist_dir=os.path.abspath(args.dist) if args.dist else None,
            allow_missing_exe=args.allow_missing_exe,
        )
        print("已暂存 Windows 发行目录 %s" % args.output)
        if args.zip:
            write_zip(os.path.abspath(args.output), os.path.abspath(args.zip))
            print("已写入 %s" % args.zip)
        return 0
    parser.print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main())
