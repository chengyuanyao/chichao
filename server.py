#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Steel Front LAN - dependency-free authoritative RTS server.

Compatible with the Windows Python 3.6 installation on this machine.
"""

from __future__ import print_function

import heapq
import json
import math
import mimetypes
import os
import random
import re
import signal
import socket
import socketserver
import sys
import threading
import time
import uuid
from email.utils import formatdate
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlparse


VERSION = "2.0.0"
ROOT = os.path.dirname(os.path.abspath(__file__))
PUBLIC_ROOT = os.path.join(ROOT, "public")
# 高位端口：8080 在装了 WSL2 / Hyper-V / Docker 的 Windows 上常被系统预留，
# 绑定会失败并报 WinError 10013。详见 README 的「端口说明」。
PORT = int(os.environ.get("PORT", "18081"))
HOST = os.environ.get("HOST", "0.0.0.0")
STARTED_AT = time.time()

# 刷钱调试接口 /api/give 默认只对服务器本机开放（你在服务器上跑 give_cash.py 做
# 测试），局域网其他玩家访问会被拒。确需从别的机器用时设环境变量 IFL_CHEATS=1 放开。
CHEATS_OPEN = os.environ.get("IFL_CHEATS", "").strip().lower() in ("1", "true", "on")

LOCK = threading.RLock()
ROOMS = {}
RUNNING = True

# 静态资源内存缓存：路径 -> ((mtime, size), (content, content_type, last_modified))。
# 用独立的小锁，不为读个文件去抢全局 LOCK（那会卡住 20Hz 模拟线程）。
_STATIC_CACHE = {}
_STATIC_LOCK = threading.Lock()

COLORS = ["#42d9ff", "#ff4f55", "#f6c84a", "#a77bff", "#3ddc84", "#ff8c42"]
BOT_NAMES = ["北辰", "赤狐", "磐石", "夜枭", "雷霆", "灰熊"]
ROOM_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"

MAPS = {
    "north_conflict": {
        "id": "north_conflict",
        "name": "北境冲突区",
        "width": 9600,
        "height": 6000,
        "maxPlayers": 6,
        "theme": "grassland",
        "spawnPoints": [
            (900, 800),
            (4800, 700),
            (8700, 800),
            (900, 5200),
            (4800, 5300),
            (8700, 5200),
        ],
        "spawnLabels": ["左上", "中上", "右上", "左下", "中下", "右下"],
        "rivers": [],
        "bridges": [],
        # 横向山脊把南北战区隔开，只留下左、中、右三条宽山谷。
        "mountains": [
            {"x": 240, "y": 3000, "r": 573},
            {"x": 960, "y": 3000, "r": 560},
            {"x": 2960, "y": 3000, "r": 520},
            {"x": 3760, "y": 3000, "r": 520},
            {"x": 5840, "y": 3000, "r": 520},
            {"x": 6640, "y": 3000, "r": 520},
            {"x": 8640, "y": 3000, "r": 560},
            {"x": 9360, "y": 3000, "r": 573},
            {"x": 3267, "y": 2250, "r": 280},
            {"x": 6333, "y": 3750, "r": 280},
        ],
        # 三条纵向道路穿过山谷，山谷本身就是军事要道。
        "roads": [
            {"x1": 667, "y1": 1636, "x2": 8933, "y2": 1636, "width": 125},
            {"x1": 667, "y1": 4364, "x2": 8933, "y2": 4364, "width": 125},
            {"x1": 2000, "y1": 1500, "x2": 2000, "y2": 4500, "width": 115},
            {"x1": 4800, "y1": 1432, "x2": 4800, "y2": 4568, "width": 120},
            {"x1": 7600, "y1": 1500, "x2": 7600, "y2": 4500, "width": 115},
            {"x1": 1000, "y1": 886, "x2": 2000, "y2": 1636, "width": 100},
            {"x1": 4800, "y1": 818, "x2": 4800, "y2": 1636, "width": 100},
            {"x1": 8600, "y1": 886, "x2": 7600, "y2": 1636, "width": 100},
            {"x1": 1000, "y1": 5114, "x2": 2000, "y2": 4364, "width": 100},
            {"x1": 4800, "y1": 5182, "x2": 4800, "y2": 4364, "width": 100},
            {"x1": 8600, "y1": 5114, "x2": 7600, "y2": 4364, "width": 100},
        ],
    },
    "narrow_standoff": {
        "id": "narrow_standoff",
        "name": "狭路对峙",
        "width": 4800,
        "height": 3200,
        "maxPlayers": 2,
        "theme": "arid",
        "spawnPoints": [
            (700, 1600),
            (4100, 1600),
        ],
        "spawnLabels": ["左翼阵地", "右翼阵地"],
        "rivers": [],
        "bridges": [],
        # 中央纵向山脊留出上、中、下三条通道，主力走中谷、侧翼可绕行。
        "mountains": [
            {"x": 2400, "y": 171, "r": 331},
            {"x": 2400, "y": 1086, "r": 297},
            {"x": 2400, "y": 2091, "r": 297},
            {"x": 2400, "y": 3029, "r": 331},
            {"x": 1416, "y": 743, "r": 240},
            {"x": 3384, "y": 2457, "r": 240},
        ],
        "roads": [
            {"x1": 480, "y1": 1600, "x2": 4320, "y2": 1600, "width": 125},
            {"x1": 780, "y1": 1600, "x2": 2400, "y2": 686, "width": 100},
            {"x1": 780, "y1": 1600, "x2": 2400, "y2": 2571, "width": 100},
            {"x1": 4020, "y1": 1600, "x2": 2400, "y2": 686, "width": 100},
            {"x1": 4020, "y1": 1600, "x2": 2400, "y2": 2571, "width": 100},
        ],
    },
    "island_hop": {
        "id": "island_hop",
        "name": "三谷争夺",
        "width": 7200,
        "height": 6000,
        "maxPlayers": 4,
        "theme": "grassland",
        "spawnPoints": [
            (900, 900),
            (6300, 900),
            (900, 5100),
            (6300, 5100),
        ],
        "spawnLabels": ["西北高地", "东北高地", "西南高地", "东南高地"],
        "rivers": [],
        "bridges": [],
        # 横贯地图的山链留下三条争夺谷地，四个角落都有两条以上进攻选择。
        "mountains": [
            {"x": 333, "y": 3000, "r": 507},
            {"x": 1093, "y": 3000, "r": 400},
            {"x": 2453, "y": 3000, "r": 427},
            {"x": 2987, "y": 3000, "r": 427},
            {"x": 4213, "y": 3000, "r": 427},
            {"x": 4747, "y": 3000, "r": 427},
            {"x": 6107, "y": 3000, "r": 400},
            {"x": 6867, "y": 3000, "r": 507},
            {"x": 2733, "y": 2250, "r": 280},
            {"x": 4467, "y": 3750, "r": 280},
        ],
        "roads": [
            {"x1": 600, "y1": 1575, "x2": 6600, "y2": 1575, "width": 120},
            {"x1": 600, "y1": 4425, "x2": 6600, "y2": 4425, "width": 120},
            {"x1": 1800, "y1": 1425, "x2": 1800, "y2": 4575, "width": 110},
            {"x1": 3600, "y1": 1425, "x2": 3600, "y2": 4575, "width": 115},
            {"x1": 5400, "y1": 1425, "x2": 5400, "y2": 4575, "width": 110},
            {"x1": 933, "y1": 975, "x2": 1800, "y2": 1575, "width": 100},
            {"x1": 6267, "y1": 975, "x2": 5400, "y2": 1575, "width": 100},
            {"x1": 933, "y1": 5025, "x2": 1800, "y2": 4425, "width": 100},
            {"x1": 6267, "y1": 5025, "x2": 5400, "y2": 4425, "width": 100},
        ],
    },
    "urban_siege": {
        "id": "urban_siege",
        "name": "围城战",
        "width": 6400,
        "height": 6400,
        "maxPlayers": 4,
        "theme": "urban",
        "spawnPoints": [
            (900, 3200),
            (3200, 900),
            (5500, 3200),
            (3200, 5500),
        ],
        "spawnLabels": ["西区", "北区", "东区", "南区"],
        "rivers": [],
        "bridges": [],
        # 城区街块：山体在这里当作成片废墟，切出棋盘式的街道
        "mountains": [
            {"x": 2338, "y": 2438, "r": 406},
            {"x": 4062, "y": 2438, "r": 406},
            {"x": 2338, "y": 3962, "r": 406},
            {"x": 4062, "y": 3962, "r": 406},
            {"x": 985, "y": 1219, "r": 271},
            {"x": 5415, "y": 1219, "r": 271},
            {"x": 985, "y": 5181, "r": 271},
            {"x": 5415, "y": 5181, "r": 271},
        ],
        # 城市棋盘路网
        "roads": [
            {"x1": 554, "y1": 1676, "x2": 5846, "y2": 1676, "width": 120},
            {"x1": 492, "y1": 3200, "x2": 5908, "y2": 3200, "width": 130},
            {"x1": 554, "y1": 4724, "x2": 5846, "y2": 4724, "width": 120},
            {"x1": 1600, "y1": 686, "x2": 1600, "y2": 5714, "width": 120},
            {"x1": 3200, "y1": 610, "x2": 3200, "y2": 5790, "width": 130},
            {"x1": 4800, "y1": 686, "x2": 4800, "y2": 5714, "width": 120},
        ],
    },
    "valley_clash": {
        "id": "valley_clash",
        "name": "峡谷交锋",
        "width": 6400,
        "height": 4800,
        "maxPlayers": 4,
        "theme": "grassland",
        "spawnPoints": [
            (800, 1800),
            (800, 3000),
            (5600, 1800),
            (5600, 3000),
        ],
        "spawnLabels": ["左路前哨", "左路后哨", "右路前哨", "右路后哨"],
        "rivers": [],
        "bridges": [],
        # 2v2 尺寸保持不变；中央山墙用三处宽谷替代原来的三座桥。
        "mountains": [
            {"x": 3200, "y": 180, "r": 380},
            {"x": 3200, "y": 1550, "r": 390},
            {"x": 3200, "y": 3150, "r": 390},
            {"x": 3200, "y": 4620, "r": 380},
            {"x": 1750, "y": 1350, "r": 240},
            {"x": 1750, "y": 3450, "r": 240},
            {"x": 4650, "y": 1350, "r": 240},
            {"x": 4650, "y": 3450, "r": 240},
        ],
        "roads": [
            {"x1": 500, "y1": 900, "x2": 5900, "y2": 900, "width": 110},
            {"x1": 500, "y1": 2400, "x2": 5900, "y2": 2400, "width": 125},
            {"x1": 500, "y1": 3900, "x2": 5900, "y2": 3900, "width": 110},
            {"x1": 800, "y1": 1800, "x2": 800, "y2": 3000, "width": 100},
            {"x1": 5600, "y1": 1800, "x2": 5600, "y2": 3000, "width": 100},
            {"x1": 800, "y1": 1800, "x2": 1600, "y2": 900, "width": 100},
            {"x1": 800, "y1": 3000, "x2": 1600, "y2": 3900, "width": 100},
            {"x1": 5600, "y1": 1800, "x2": 4800, "y2": 900, "width": 100},
            {"x1": 5600, "y1": 3000, "x2": 4800, "y2": 3900, "width": 100},
        ],
    },
    "cliff_assault": {
        "id": "cliff_assault",
        "name": "断崖强袭",
        "width": 9600,
        "height": 6000,
        "maxPlayers": 6,
        "theme": "arid",
        "spawnPoints": [
            (3200, 800),
            (4200, 800),
            (5200, 800),
            (3200, 5200),
            (4200, 5200),
            (5200, 5200),
        ],
        "spawnLabels": ["上路左翼", "上路中军", "上路右翼", "下路左翼", "下路中军", "下路右翼"],
        "rivers": [],
        "bridges": [],
        # 两道连续断崖纵贯南北，形成左、中、右三条主战山谷。
        "mountains": [
            {"x": 3467, "y": 1841, "r": 467},
            {"x": 3467, "y": 2523, "r": 467},
            {"x": 3467, "y": 3341, "r": 467},
            {"x": 3467, "y": 4159, "r": 467},
            {"x": 6133, "y": 1841, "r": 467},
            {"x": 6133, "y": 2523, "r": 467},
            {"x": 6133, "y": 3341, "r": 467},
            {"x": 6133, "y": 4159, "r": 467},
            {"x": 1200, "y": 3000, "r": 320},
            {"x": 8400, "y": 3000, "r": 320},
        ],
        "roads": [
            {"x1": 867, "y1": 1159, "x2": 8733, "y2": 1159, "width": 120},
            {"x1": 867, "y1": 4841, "x2": 8733, "y2": 4841, "width": 120},
            {"x1": 2133, "y1": 1091, "x2": 2133, "y2": 4909, "width": 115},
            {"x1": 4800, "y1": 1091, "x2": 4800, "y2": 4909, "width": 125},
            {"x1": 7467, "y1": 1091, "x2": 7467, "y2": 4909, "width": 115},
            {"x1": 2933, "y1": 818, "x2": 2133, "y2": 1159, "width": 100},
            {"x1": 4800, "y1": 818, "x2": 4800, "y2": 1159, "width": 100},
            {"x1": 6667, "y1": 818, "x2": 7467, "y2": 1159, "width": 100},
            {"x1": 2933, "y1": 5182, "x2": 2133, "y2": 4841, "width": 100},
            {"x1": 4800, "y1": 5182, "x2": 4800, "y2": 4841, "width": 100},
            {"x1": 6667, "y1": 5182, "x2": 7467, "y2": 4841, "width": 100},
        ],
    },
}
COMBAT_CELL_SIZE = 256.0
SEPARATION_CELL_SIZE = 64.0
VEHICLE_KINDS = frozenset(("tank", "scout", "harvester", "artillery", "tank_destroyer", "mcv", "v3", "overlord", "prism"))
REPAIR_RATE = 105.0
REPAIR_COST_PER_HP = 0.35
REPAIR_DOCKS_PER_RING = 8

# 公共矿区由不属于任何玩家的中立守军占据。守军只在矿区周围警戒，
# 追击目标越过缰绳半径后会立即脱战并回到自己的哨位。
NEUTRAL_OWNER = "neutral"
NEUTRAL_GUARD_AGGRO = 330.0
NEUTRAL_GUARD_LEASH = 540.0
NEUTRAL_GUARD_POST_RADIUS = 34.0

# 超级武器（轨道打击）：拾取箱得 1 次充能，手动瞄准投放。
# 预警 → 散布弹幕 → 范围伤害，全程友伤，给对手撤离的反制窗口。
STRIKE_MAX_CHARGES = 1
STRIKE_WARNING = 3.0       # 落弹前预警秒数（地面显示标圈）
STRIKE_RADIUS = 180.0      # 弹着点散布半径
STRIKE_IMPACTS = 10        # 弹着点数量
STRIKE_IMPACT_STEP = 0.09  # 弹幕落弹节奏（秒/发）
STRIKE_DAMAGE = 130.0      # 单发伤害（命中 super 甲种系数后再放大）
STRIKE_SPLASH = 60.0       # 单发溅射半径

# Only completed core buildings extend construction territory. Defensive
# structures deliberately do not, preventing turret chains across the map.
BUILD_ANCHOR_RANGES = {
    "hq": 360.0,
    "power": 220.0,
    "refinery": 250.0,
    "barracks": 220.0,
    "factory": 270.0,
    "repair": 240.0,
}
ENEMY_BUILD_EXCLUSION = 440.0

# 补给箱：地图上随机掉落的奖励道具
CRATE_TYPES = {
    "cash":   {"name": "资金补给", "color": "#ffd700"},
    "heal":   {"name": "战地医疗", "color": "#7dff5f"},
    "strike": {"name": "超级武器", "color": "#ff3b3b"},
}

# Armor types and damage multiplier table for unit-counter system.
DAMAGE_MULTIPLIER = {
    "bullet":  {"infantry": 1.0, "light": 0.65, "heavy": 0.35, "structure": 0.30},
    "rocket":  {"infantry": 0.75, "light": 1.30, "heavy": 1.50, "structure": 0.85},
    "shell":   {"infantry": 0.55, "light": 1.00, "heavy": 1.00, "structure": 1.20},
    "sniper":  {"infantry": 2.20, "light": 0.40, "heavy": 0.15, "structure": 0.10},
    "siege":   {"infantry": 0.25, "light": 0.30, "heavy": 0.25, "structure": 1.80},
    "ap":      {"infantry": 0.25, "light": 0.65, "heavy": 2.10, "structure": 0.70},
    # 超级武器：对全甲种都致命，清场用。siege 对步兵只有 0.25，清不动人。
    "super":   {"infantry": 1.50, "light": 1.30, "heavy": 1.10, "structure": 1.40},
    # V3 远程火箭：曲射拆建筑，溅射清阵，弹速慢能被看见躲
    "missile": {"infantry": 0.50, "light": 0.70, "heavy": 0.65, "structure": 1.50},
    # 磁暴步兵的电弧：快脉冲专电载具，对建筑和步兵都一般
    "tesla":   {"infantry": 0.80, "light": 1.40, "heavy": 1.30, "structure": 0.50},
    # 光棱坦克的聚焦光束：精准点杀伤，克轻型与建筑，打不动重甲与人群
    "laser":   {"infantry": 0.45, "light": 1.50, "heavy": 0.85, "structure": 1.70},
    # 军犬扑咬：一口一个步兵，对装甲和建筑完全无从下口（×0）
    "bite":    {"infantry": 4.00, "light": 0.00, "heavy": 0.00, "structure": 0.00},
}

UNIT_TYPES = {
    "rifle": {
        "name": "突击兵", "cost": 180, "hp": 110, "speed": 110.4,
        "damage": 13.0, "range": 125.0, "cooldown": 0.62,
        "size": 10.0, "build": 3.0, "producer": "barracks",
        "projectile": "bullet", "projectileSpeed": 680.0, "splash": 0.0,
        "sight": 350.0, "armor": "infantry", "damageType": "bullet",
    },
    "rocket": {
        "name": "火箭兵", "cost": 340, "hp": 95, "speed": 92.4,
        "damage": 38.0, "range": 205.0, "cooldown": 1.2,
        "size": 11.0, "build": 5.0, "producer": "barracks",
        "projectile": "rocket", "projectileSpeed": 285.0, "splash": 42.0,
        "sight": 390.0, "armor": "infantry", "damageType": "rocket",
    },
    "sniper": {
        "name": "狙击手", "cost": 420, "hp": 75, "speed": 90.0,
        "damage": 55.0, "range": 310.0, "cooldown": 1.6,
        "size": 10.0, "build": 6.0, "producer": "barracks",
        "projectile": "sniper", "projectileSpeed": 1200.0, "splash": 0.0,
        "sight": 480.0, "armor": "infantry", "damageType": "sniper",
    },
    # 军犬：红色警戒式近战特种兵。全场最速，扑咬对步兵一击必杀（克制表 ×4），
    # 但对载具/建筑零伤害；便宜的肉盾与侦察兵，专咬成群步兵。
    "dog": {
        "name": "军犬", "cost": 120, "hp": 55, "speed": 146.4,
        "damage": 60.0, "range": 30.0, "cooldown": 0.8,
        "size": 8.0, "build": 2.5, "producer": "barracks",
        "projectile": "bite", "projectileSpeed": 1000.0, "splash": 0.0,
        "sight": 400.0, "armor": "infantry", "damageType": "bite",
    },
    "tank": {
        "name": "先锋坦克", "cost": 780, "hp": 620, "speed": 75.6,
        "damage": 68.0, "range": 180.0, "cooldown": 1.38,
        "size": 20.0, "build": 8.0, "producer": "factory",
        "projectile": "shell", "projectileSpeed": 390.0, "splash": 51.0,
        "sight": 440.0, "armor": "heavy", "damageType": "shell",
    },
    "scout": {
        "name": "猎犬战车", "cost": 460, "hp": 260, "speed": 129.6,
        "damage": 20.0, "range": 145.0, "cooldown": 0.72,
        "size": 16.0, "build": 6.0, "producer": "factory",
        "projectile": "bullet", "projectileSpeed": 720.0, "splash": 0.0,
        "sight": 620.0, "armor": "light", "damageType": "bullet",
    },
    "harvester": {
        "name": "采矿车", "cost": 920, "hp": 680, "speed": 63.6,
        "damage": 0.0, "range": 0.0, "cooldown": 0.0,
        "size": 22.0, "build": 9.0, "producer": "factory",
        "projectile": "none", "projectileSpeed": 0.0, "splash": 0.0,
        "capacity": 850.0, "harvestRate": 145.0, "sight": 330.0,
        "armor": "heavy", "damageType": "none",
    },
    "artillery": {
        "name": "攻城炮", "cost": 960, "hp": 300, "speed": 50.4,
        "damage": 85.0, "range": 340.0, "cooldown": 2.2,
        "size": 22.0, "build": 10.0, "producer": "factory",
        "projectile": "siege", "projectileSpeed": 260.0, "splash": 55.0,
        "sight": 290.0, "armor": "heavy", "damageType": "siege",
    },
    "tank_destroyer": {
        "name": "坦克歼击车", "cost": 1050, "hp": 320, "speed": 66.0,
        "damage": 78.0, "range": 230.0, "cooldown": 1.7,
        "size": 18.0, "build": 8.0, "producer": "factory",
        "projectile": "ap", "projectileSpeed": 800.0, "splash": 0.0,
        "sight": 410.0, "armor": "heavy", "damageType": "ap",
    },
    "mcv": {
        "name": "基地车", "cost": 2500, "hp": 900, "speed": 45.6,
        "damage": 0.0, "range": 0.0, "cooldown": 0.0,
        "size": 24.0, "build": 14.0, "producer": "factory",
        "projectile": "none", "projectileSpeed": 0.0, "splash": 0.0,
        "sight": 320.0, "armor": "heavy", "damageType": "none",
        "canDeploy": True,
    },
    "v3": {
        "name": "东风快递", "cost": 2000, "hp": 260, "speed": 38.4,
        "damage": 200.0, "range": 500.0, "cooldown": 5.0,
        "size": 22.0, "build": 18.0, "producer": "factory",
        "projectile": "missile", "projectileSpeed": 160.0, "splash": 100.0,
        "sight": 310.0, "armor": "light", "damageType": "missile",
    },
    # ---- 高级兵种：靠 requires 卡在二级科技后，贵在单兵质量而非数量 ----
    "overlord": {
        "name": "天启坦克", "cost": 1700, "hp": 1500, "speed": 57.6,
        "damage": 120.0, "range": 195.0, "cooldown": 1.6,
        "size": 24.0, "build": 16.0, "producer": "factory",
        "requires": ["repair"],
        "projectile": "shell", "projectileSpeed": 400.0, "splash": 30.0,
        "sight": 450.0, "armor": "heavy", "damageType": "shell",
    },
    "tesla": {
        "name": "磁暴步兵", "cost": 650, "hp": 190, "speed": 81.6,
        "damage": 26.0, "range": 150.0, "cooldown": 0.5,
        "size": 11.0, "build": 7.0, "producer": "barracks",
        "requires": ["factory"],
        "projectile": "tesla", "projectileSpeed": 900.0, "splash": 0.0,
        "sight": 380.0, "armor": "infantry", "damageType": "tesla",
    },
    "prism": {
        "name": "光棱坦克", "cost": 1450, "hp": 360, "speed": 67.2,
        "damage": 100.0, "range": 305.0, "cooldown": 1.8,
        "size": 19.0, "build": 13.0, "producer": "factory",
        "requires": ["repair"],
        "projectile": "laser", "projectileSpeed": 1400.0, "splash": 0.0,
        "sight": 480.0, "armor": "light", "damageType": "laser",
    },
}

DEFAULT_MAP = "north_conflict"

STRUCTURE_TYPES = {
    "hq": {
        "name": "指挥中心", "cost": 0, "hp": 2400, "size": 58.0,
        "build": 0.0, "deploy": 0.0, "power": 35, "requires": [], "sight": 650.0,
        "armor": "structure",
    },
    "power": {
        "name": "磁能电站", "cost": 600, "hp": 760, "size": 40.0,
        "build": 8.0, "deploy": 2.2, "power": 120, "requires": ["hq"], "sight": 350.0,
        "armor": "structure",
    },
    "refinery": {
        "name": "矿石精炼厂", "cost": 1400, "hp": 1350, "size": 52.0,
        "build": 14.0, "deploy": 3.2, "power": -30, "requires": ["hq"], "sight": 390.0,
        "armor": "structure",
    },
    "barracks": {
        "name": "步兵营", "cost": 700, "hp": 900, "size": 42.0,
        "build": 10.0, "deploy": 2.8, "power": -20, "requires": ["power"], "sight": 410.0,
        "armor": "structure",
    },
    "factory": {
        "name": "重装工厂", "cost": 1600, "hp": 1600, "size": 58.0,
        "build": 18.0, "deploy": 4.2, "power": -45, "requires": ["refinery", "power"], "sight": 460.0,
        "armor": "structure",
    },
    "repair": {
        "name": "战地维修厂", "cost": 1250, "hp": 1280, "size": 50.0,
        "build": 15.0, "deploy": 3.6, "power": -35,
        "requires": ["factory", "power"], "sight": 440.0,
        "armor": "structure",
    },
    "turret": {
        "name": "哨戒炮塔", "cost": 950, "hp": 1300, "size": 30.0,
        "build": 12.0, "deploy": 3.0, "power": -25, "requires": ["power"], "sight": 560.0,
        "damage": 62.0, "range": 280.0, "cooldown": 0.70,
        "projectile": "shell", "projectileSpeed": 460.0, "splash": 51.0,
        "armor": "structure", "damageType": "shell",
    },
    "missile": {
        "name": "导弹炮塔", "cost": 1200, "hp": 1050, "size": 34.0,
        "build": 16.0, "deploy": 3.5, "power": -30, "requires": ["barracks", "power"],
        "sight": 580.0, "damage": 90.0, "range": 360.0, "cooldown": 1.6,
        "projectile": "shell", "projectileSpeed": 420.0, "splash": 45.0,
        "armor": "structure", "damageType": "shell",
    },
}

def now():
    return time.time()


def clamp(value, low, high):
    return max(low, min(high, value))


def distance(a, b):
    return math.hypot(a["x"] - b["x"], a["y"] - b["y"])


def spatial_cell(x, y, cell_size):
    return (int(math.floor(x / cell_size)), int(math.floor(y / cell_size)))


def spatial_candidates(spatial_index, x, y, radius, padding=0.0):
    if not spatial_index:
        return
    cell_size, cells = spatial_index
    extent = radius + padding
    min_x = int(math.floor((x - extent) / cell_size))
    max_x = int(math.floor((x + extent) / cell_size))
    min_y = int(math.floor((y - extent) / cell_size))
    max_y = int(math.floor((y + extent) / cell_size))
    for cell_x in range(min_x, max_x + 1):
        for cell_y in range(min_y, max_y + 1):
            for entity in cells.get((cell_x, cell_y), ()):
                yield entity


def build_combat_indexes(game):
    entities_by_id = {}
    cells = {}
    for collection in (game["units"], game["structures"]):
        for entity in collection:
            if entity["hp"] <= 0:
                continue
            entities_by_id[entity["id"]] = entity
            key = spatial_cell(entity["x"], entity["y"], COMBAT_CELL_SIZE)
            cells.setdefault(key, []).append(entity)
    return entities_by_id, (COMBAT_CELL_SIZE, cells)


def clean_text(value, maximum, fallback):
    if not isinstance(value, str):
        return fallback
    value = re.sub(r"[\x00-\x1f\x7f]", "", value).strip()
    return value[:maximum] or fallback


def new_id(prefix):
    return prefix + uuid.uuid4().hex[:10]


def new_room_code():
    for _ in range(100):
        code = "".join(random.choice(ROOM_ALPHABET) for _ in range(6))
        if code not in ROOMS:
            return code
    return uuid.uuid4().hex[:6].upper()


def is_friendly(game, owner_a, owner_b):
    if owner_a == owner_b:
        return True
    teams = game.get("playerTeams", {})
    ta = teams.get(owner_a, 0)
    tb = teams.get(owner_b, 0)
    return ta > 0 and ta == tb


def player_power(room, player_id):
    game = room.get("game")
    if not game:
        return 0, 0
    # 每个模拟帧按玩家缓存一次电力。过去 tick_structures 里每个在建/在产建筑、
    # 每辆矿车、每个 bot、每条 SSE 连接的 public_player 都各扫一遍全部建筑，
    # 叠加成 O(结构数²) 并全部压在全局锁内。电力在单个 tick 内本就不变，
    # _snapshotVersion 每 tick 末与每条改状态指令后都会自增，正好当缓存键。
    version = game.get("_snapshotVersion", 0)
    cache = game.get("_powerCache")
    if cache is None or cache[0] != version:
        cache = (version, {})
        game["_powerCache"] = cache
    per_player = cache[1]
    cached = per_player.get(player_id)
    if cached is not None:
        return cached
    supply = 0
    usage = 0
    for structure in game["structures"]:
        if structure["owner"] != player_id or not structure["active"] or structure["hp"] <= 0:
            continue
        value = STRUCTURE_TYPES[structure["kind"]].get("power", 0)
        if value >= 0:
            supply += value
        else:
            usage += -value
    per_player[player_id] = (supply, usage)
    return supply, usage


def public_player(room, player, viewer_id=None):
    supply, usage = player_power(room, player["id"])
    return {
        "id": player["id"],
        "name": player["name"],
        "color": player["color"],
        "team": player.get("team", 0),
        "spawn": player.get("spawn", -1),
        "ready": player["ready"],
        "isBot": player["isBot"],
        "isHost": room["hostId"] == player["id"],
        "connected": bool(player.get("connections", 0)) or now() - player.get("lastSeen", 0) < 12,
        "cash": int(player.get("cash", 0)),
        "eliminated": player.get("eliminated", False),
        "kills": player.get("kills", 0),
        "unitsLost": player.get("unitsLost", 0),
        "harvested": int(player.get("harvested", 0)),
        "powerSupply": supply,
        "powerUse": usage,
        "buildQueue": [dict(item) for item in player.get("buildQueue", [])]
        if viewer_id == player["id"] else [],
        "strikeCharges": player.get("strikeCharges", 0),
    }


def public_unit(unit):
    result = {
        "id": unit["id"], "kind": unit["kind"], "owner": unit["owner"],
        "x": round(unit["x"], 1), "y": round(unit["y"], 1),
        "hp": round(unit["hp"], 1), "maxHp": unit["maxHp"],
        "size": unit["size"], "dir": round(unit["dir"], 3),
        "kills": unit.get("kills", 0),
    }
    if unit["kind"] == "harvester":
        result["cargo"] = round(unit["cargo"], 1)
        result["capacity"] = unit["capacity"]
    if unit.get("repairing"):
        result["repairing"] = True
    return result


def public_structure(structure):
    result = {
        "id": structure["id"], "kind": structure["kind"],
        "owner": structure["owner"],
        "x": round(structure["x"], 1), "y": round(structure["y"], 1),
        "hp": round(structure["hp"], 1), "maxHp": structure["maxHp"],
        "size": structure["size"], "active": structure["active"],
        "queue": [{
            "kind": item["kind"],
            "remaining": round(item["remaining"], 2),
            "total": item["total"],
        } for item in structure["queue"]],
    }
    if structure["kind"] == "turret":
        result["dir"] = round(structure["dir"], 3)
    if structure.get("packable"):
        result["packable"] = True
    if structure.get("rally"):
        result["rally"] = [round(structure["rally"][0], 1), round(structure["rally"][1], 1)]
    if not structure["active"]:
        result["buildRemaining"] = round(structure["buildRemaining"], 2)
        result["buildTotal"] = structure["buildTotal"]
    return result


def public_projectile(projectile):
    remaining = math.hypot(projectile["targetX"] - projectile["x"],
                           projectile["targetY"] - projectile["y"])
    return {
        "x": round(projectile["x"], 1), "y": round(projectile["y"], 1),
        "targetX": round(projectile["targetX"], 1),
        "targetY": round(projectile["targetY"], 1),
        "kind": projectile["kind"],
        "owner": projectile["owner"],
        # Flight progress 0..1, used to arc the round over the terrain.
        "t": round(clamp(1.0 - remaining / projectile.get("span", 1.0), 0.0, 1.0), 3),
    }


def public_effect(effect):
    return {
        "id": effect["id"], "type": effect["type"],
        "x": round(effect["x"], 1), "y": round(effect["y"], 1),
        "ttl": round(effect["ttl"], 2),
    }


def public_resource(resource):
    return {
        "id": resource["id"], "x": resource["x"], "y": resource["y"],
        "amount": round(resource["amount"], 1),
        "maxAmount": resource["maxAmount"], "radius": resource["radius"],
        "public": bool(resource.get("public")),
        "guarded": bool(resource.get("guarded")),
    }


def invalidate_game_snapshot(game):
    """使下一次网络快照重建；仅清内部缓存，不触碰玩法状态。"""
    if not game:
        return
    game["_snapshotVersion"] = game.get("_snapshotVersion", 0) + 1
    game["_publicEntityFrame"] = None
    game["_publicViewCache"] = {}


def public_entity_frame(game):
    """每个模拟帧只把实体转换成公开 JSON 形态一次。

    多个 SSE 连接看到的是同一批单位。过去每位玩家都重复 round 坐标、创建
    几百个字典；这些转换与视野无关，先共享后再按视野挑选即可。
    """
    version = game.get("_snapshotVersion", 0)
    # 长度/时间戳让直接调用 public_game 的测试与调试代码在 append 实体后也能
    # 自动失效；正常对局仍走上面的显式版本号，计算成本为常数。
    stamp = (version, game["elapsed"], len(game["units"]), len(game["structures"]),
             len(game["projectiles"]), len(game["effects"]), len(game["pings"]),
             len(game.get("crates", [])), len(game.get("pendingStrikes", [])),
             game.get("winnerId"))
    cached = game.get("_publicEntityFrame")
    if cached is not None and cached["stamp"] == stamp:
        return cached
    elapsed = game["elapsed"]
    frame = {
        "version": version,
        "stamp": stamp,
        "elapsed": round(elapsed, 2),
        "units": [(unit, public_unit(unit)) for unit in game["units"]],
        "structures": [(structure, public_structure(structure))
                       for structure in game["structures"]],
        "projectiles": [(projectile, public_projectile(projectile))
                        for projectile in game["projectiles"]],
        "effects": [(effect, public_effect(effect)) for effect in game["effects"]],
        "pings": [(ping, {
            "owner": ping["owner"], "x": round(ping["x"], 1),
            "y": round(ping["y"], 1), "ttl": round(ping["ttl"], 2),
        }) for ping in game["pings"]],
        "ore": [[r["id"], round(r["amount"], 1), 1 if r.get("guarded") else 0]
                for r in game["resources"]],
        "winnerId": game.get("winnerId"),
        "crates": [{"id": c["id"], "x": c["x"], "y": c["y"], "kind": c["kind"]}
                   for c in game.get("crates", [])],
        "strikes": [{
            "owner": strike["owner"],
            "x": round(strike["x"], 1), "y": round(strike["y"], 1),
            "warnUntil": round(strike["warnUntil"] - elapsed, 2),
            "fireUntil": round(strike["fireUntil"] - elapsed, 2),
        } for strike in game.get("pendingStrikes", [])],
    }
    game["_publicEntityFrame"] = frame
    return frame


VISION_CELL_SIZE = 512.0
# Widest padding any visibility test can ask for, so a source bucketed by its
# reach is guaranteed to be found from the queried point's own cell.
MAX_VISION_PADDING = max(
    [float(d["size"]) for d in UNIT_TYPES.values()]
    + [float(d["size"]) for d in STRUCTURE_TYPES.values()]
    + [30.0])


class VisionField(object):
    """Vision sources bucketed into a grid.

    Visibility used to be a linear scan over every friendly unit and structure
    for every entity in the snapshot -- O(entities x sources), roughly 200k
    distance checks per snapshot in a six-player battle. Each source is now
    filed into the cells its sight circle reaches, so a test only examines the
    handful of sources covering that one cell.
    """

    __slots__ = ("sources", "_cells")

    def __init__(self, sources):
        self.sources = sources
        cells = {}
        for source in sources:
            sx, sy, radius = source
            reach = radius + MAX_VISION_PADDING
            cx0 = int((sx - reach) // VISION_CELL_SIZE)
            cx1 = int((sx + reach) // VISION_CELL_SIZE)
            cy0 = int((sy - reach) // VISION_CELL_SIZE)
            cy1 = int((sy + reach) // VISION_CELL_SIZE)
            for cx in range(cx0, cx1 + 1):
                for cy in range(cy0, cy1 + 1):
                    bucket = cells.get((cx, cy))
                    if bucket is None:
                        cells[(cx, cy)] = [source]
                    else:
                        bucket.append(source)
        self._cells = cells

    def visible(self, x, y, padding=0.0):
        bucket = self._cells.get((int(x // VISION_CELL_SIZE), int(y // VISION_CELL_SIZE)))
        if not bucket:
            return False
        for sx, sy, radius in bucket:
            dx = sx - x
            dy = sy - y
            reach = radius + padding
            if dx * dx + dy * dy <= reach * reach:
                return True
        return False


def player_vision_sources(game, player_id):
    """Sight circles a player sees through, as (x, y, radius) tuples."""
    sources = []
    for unit in game["units"]:
        if unit["hp"] > 0 and is_friendly(game, unit["owner"], player_id):
            sources.append((unit["x"], unit["y"],
                            UNIT_TYPES[unit["kind"]].get("sight", 350.0)))
    for structure in game["structures"]:
        if structure["hp"] > 0 and is_friendly(game, structure["owner"], player_id):
            radius = STRUCTURE_TYPES[structure["kind"]].get("sight", 350.0)
            if not structure["active"]:
                radius *= 0.45
            sources.append((structure["x"], structure["y"], radius))
    return sources


def vision_field(game, viewer_id):
    """Bucketed sight for one viewer, or None for the full spectator view.

    Deliberately not memoized across calls. Measured at 450 units and six
    viewers, caching this per tick was *slower* than rebuilding it (0.288 vs
    0.261 ms/viewer) because it only pays off for teammates sharing a view,
    and it made every snapshot depend on some caller remembering to bump a
    version counter after mutating the game between ticks.
    """
    if not viewer_id:
        return None
    return VisionField(player_vision_sources(game, viewer_id))


def public_game(game, viewer_id=None, full=True):
    """Snapshot of the battlefield as one viewer sees it."""
    frame = public_entity_frame(game)
    team = game.get("playerTeams", {}).get(viewer_id, 0) if viewer_id else 0
    view_key = ("all", 0) if not viewer_id else (
        ("team", team) if team > 0 else ("player", viewer_id))
    view_cache = game.setdefault("_publicViewCache", {})
    cached_view = view_cache.get(view_key)
    if cached_view is not None and cached_view[0] == frame["stamp"]:
        dynamic = cached_view[1]
    else:
        field = vision_field(game, viewer_id)
        if field is None:
            visible_units = [public for _raw, public in frame["units"]]
            visible_structures = [public for _raw, public in frame["structures"]]
            visible_projectiles = [public for _raw, public in frame["projectiles"]]
            visible_effects = [public for _raw, public in frame["effects"]]
            pings = [public for _raw, public in frame["pings"]]
        else:
            seen = field.visible
            visible_units = [
                public for unit, public in frame["units"]
                if is_friendly(game, unit["owner"], viewer_id)
                or seen(unit["x"], unit["y"], unit["size"])
            ]
            visible_structures = [
                public for structure, public in frame["structures"]
                if is_friendly(game, structure["owner"], viewer_id)
                or seen(structure["x"], structure["y"], structure["size"])
            ]
            visible_projectiles = [
                public for projectile, public in frame["projectiles"]
                if seen(projectile["x"], projectile["y"], 20.0)
            ]
            visible_effects = [
                public for effect, public in frame["effects"]
                if seen(effect["x"], effect["y"], 30.0)
            ]
            pings = [
                public for ping, public in frame["pings"]
                if is_friendly(game, ping["owner"], viewer_id)
            ]
        dynamic = {
            "elapsed": frame["elapsed"],
            "units": visible_units,
            "structures": visible_structures,
            "ore": frame["ore"],
            "projectiles": visible_projectiles,
            "effects": visible_effects,
            "pings": pings,
            "winnerId": frame["winnerId"],
            "crates": frame["crates"],
            "strikes": frame["strikes"],
        }
        view_cache[view_key] = (frame["stamp"], dynamic)

    # full 帧只在动态缓存的浅副本上追加静态块，避免污染同队共享的对象。
    result = dict(dynamic) if full else dynamic
    if full:
        # Static for the whole match: sent on the first snapshot of a stream
        # and on every REST fetch, then cached by the client.
        result["full"] = True
        result["map"] = dict(game["map"])
        result["terrain"] = (dict(game["terrain"]) if game.get("terrain")
                             else {"rivers": [], "bridges": []})
        result["resources"] = [public_resource(r) for r in game["resources"]]
        # Sight radii let the client derive fog of war from the friendly units
        # and structures it already receives, instead of the server re-sending
        # every friendly position a second time as a vision list.
        result["sight"] = {
            "units": {k: v.get("sight", 350.0) for k, v in UNIT_TYPES.items()},
            "structures": {k: v.get("sight", 350.0) for k, v in STRUCTURE_TYPES.items()},
        }
    return result


PUBLIC_MAPS = {
    mid: {
        "id": m["id"], "name": m["name"], "width": m["width"], "height": m["height"],
        "maxPlayers": m["maxPlayers"], "spawnLabels": m["spawnLabels"],
        "spawnPoints": m["spawnPoints"],
        # 静态地形一并下发：大厅的地图预览按真实山脉与道路绘制；
        # 而不是一张假想图。地图目录只在大厅阶段发送，体积不敏感。
        "theme": m.get("theme", "grassland"),
        "rivers": m.get("rivers", []),
        "bridges": m.get("bridges", []),
        "mountains": m.get("mountains", []),
        "roads": m.get("roads", []),
    }
    for mid, m in MAPS.items()
}


def public_room(room, include_game=True, viewer_id=None, full=True):
    room_map = MAPS.get(room.get("selectedMap", DEFAULT_MAP), MAPS[DEFAULT_MAP])
    result = {
        "id": room["id"],
        "name": room["name"],
        "status": room["status"],
        "hostId": room["hostId"],
        "players": [public_player(room, p, viewer_id) for p in room["players"].values()],
        "chat": [dict(message) for message in room["chat"][-30:]],
        "createdAt": room["createdAt"],
        "serverTime": now(),
        "selectedMap": room.get("selectedMap", DEFAULT_MAP),
        "mapConfig": {
            "id": room_map["id"],
            "name": room_map["name"],
            "width": room_map["width"],
            "height": room_map["height"],
            "maxPlayers": room_map["maxPlayers"],
            "spawnLabels": room_map["spawnLabels"],
            "spawnPoints": room_map["spawnPoints"],
        },
    }
    # The map catalogue only drives the lobby's map picker; re-sending it eight
    # times a second during a battle is pure waste.
    if full or room["status"] == "lobby":
        result["maps"] = PUBLIC_MAPS
    if include_game and room.get("game"):
        eliminated = False
        if viewer_id and viewer_id in room.get("players", {}):
            eliminated = room["players"][viewer_id].get("eliminated", False)
        result["game"] = public_game(
            room["game"],
            None if eliminated or room["status"] == "finished" else viewer_id,
            full)
    proposals = room.get("allianceProposals", {})
    if proposals and viewer_id:
        prop = proposals.get(viewer_id)
        if prop:
            proposer = room["players"].get(prop["from"])
            if proposer:
                result["incomingProposal"] = {"fromId": proposer["id"], "fromName": proposer["name"]}
    return result


def room_list():
    rooms = []
    for room in ROOMS.values():
        humans = sum(1 for p in room["players"].values() if not p["isBot"])
        room_map = MAPS.get(room.get("selectedMap", DEFAULT_MAP), MAPS[DEFAULT_MAP])
        rooms.append({
            "id": room["id"],
            "name": room["name"],
            "status": room["status"],
            "players": len(room["players"]),
            "humans": humans,
            "maxPlayers": room_map["maxPlayers"],
            "hostName": room["players"].get(room["hostId"], {}).get("name", "—"),
            "createdAt": room["createdAt"],
        })
    rooms.sort(key=lambda item: item["createdAt"], reverse=True)
    return rooms


def add_chat(room, sender, message, system=False):
    room["chat"].append({
        "id": new_id("m"),
        "sender": sender,
        "message": clean_text(message, 100, ""),
        "system": system,
        "time": now(),
    })
    room["chat"] = room["chat"][-30:]


def create_human(name, color, team=0, spawn=-1):
    return {
        "id": new_id("p"),
        "token": uuid.uuid4().hex + uuid.uuid4().hex,
        "name": clean_text(name, 16, "指挥官"),
        "color": color,
        "team": team,
        "spawn": spawn,
        "ready": False,
        "isBot": False,
        "connections": 0,
        "lastSeen": now(),
        "cash": 0,
        "eliminated": False,
        "kills": 0,
        "unitsLost": 0,
        "harvested": 0,
        "buildQueue": [],
        "strikeCharges": 0,
    }


def create_bot(room):
    used_names = set(p["name"] for p in room["players"].values())
    name = next((item for item in BOT_NAMES if item not in used_names), "战术 AI")
    used_colors = set(p["color"] for p in room["players"].values())
    color = next((item for item in COLORS if item not in used_colors), COLORS[len(room["players"]) % len(COLORS)])
    bot = {
        "id": new_id("b"), "token": None, "name": name, "color": color,
        "team": 0, "spawn": -1, "ready": True, "isBot": True, "connections": 1, "lastSeen": now(),
        "cash": 0, "eliminated": False, "kills": 0, "unitsLost": 0,
        "harvested": 0, "buildQueue": [], "strikeCharges": 0,
    }
    room["players"][bot["id"]] = bot
    return bot


def authenticate(room_id, player_id, token):
    room = ROOMS.get(str(room_id or "").upper())
    if not room:
        return None, None
    player = room["players"].get(player_id)
    if not player or player["isBot"] or player.get("token") != token:
        return room, None
    player["lastSeen"] = now()
    return room, player


def make_structure(kind, owner, x, y, active=True):
    definition = STRUCTURE_TYPES[kind]
    deploy_total = float(definition.get("deploy", 0.0))
    initial_progress = 1.0 if active or deploy_total <= 0 else 0.22
    return {
        "id": new_id("s"), "kind": kind, "owner": owner,
        "x": round(x, 2), "y": round(y, 2),
        "hp": float(definition["hp"] if active else max(80, definition["hp"] * initial_progress)),
        "maxHp": float(definition["hp"]), "size": definition["size"],
        "active": active,
        "buildRemaining": 0.0 if active else deploy_total * (1.0 - initial_progress),
        "buildTotal": deploy_total,
        "constructionDamage": 0.0,
        "queue": [], "cooldown": random.random(), "dir": 0.0, "rally": None,
    }


def make_unit(kind, owner, x, y):
    definition = UNIT_TYPES[kind]
    return {
        "id": new_id("u"), "kind": kind, "owner": owner,
        "x": round(x, 2), "y": round(y, 2),
        "hp": float(definition["hp"]), "maxHp": float(definition["hp"]),
        "size": definition["size"], "dir": random.random() * math.pi * 2,
        "destX": None, "destY": None, "targetId": None,
        "cooldown": random.random() * 0.6, "scan": random.random() * 0.4,
        "cargo": 0.0, "capacity": definition.get("capacity", 0.0),
        "harvestTarget": None, "returnTarget": None,
        "repairTargetId": None, "repairAngle": 0.0, "repairRing": 0,
        "repairing": False, "manualUntil": 0.0, "order": "guard",
        "_path": None, "_pathDest": None, "kills": 0,
    }


def add_resource(game, x, y, amount=8500, public=False):
    """放置一处矿脉。

    矿点是按出生点与地图中心的比例算出来的，可能正好落在河里或山上 —— 那样
    采矿车永远到不了。这里沿远离阻挡物的方向做几次外推，保证矿区可采；地图
    数据改动时也就不必手工回避每一处地形。
    """
    terrain = game_terrain(game)
    radius = 48.0
    if terrain.blocked(x, y, radius) or not terrain.cell_open(x, y):
        map_w = game["map"]["width"]
        map_h = game["map"]["height"]
        cx, cy = map_w / 2.0, map_h / 2.0
        best = None
        for step in range(1, 13):
            for index in range(8):
                angle = index * math.pi / 4.0
                nx = clamp(x + math.cos(angle) * step * 70, 120, map_w - 120)
                ny = clamp(y + math.sin(angle) * step * 70, 120, map_h - 120)
                if not terrain.blocked(nx, ny, radius) and terrain.cell_open(nx, ny):
                    best = (nx, ny)
                    break
            if best:
                break
        if best:
            x, y = best
        else:
            x, y = cx, cy
    resource = {
        "id": new_id("r"), "x": round(x, 2), "y": round(y, 2),
        "amount": float(amount), "maxAmount": float(amount), "radius": radius,
        "public": bool(public), "guarded": False,
    }
    game["resources"].append(resource)
    return resource


def neutral_guard_position(game, resource, base_angle, preferred_radius, size):
    """在矿脉周围找一个不压矿、不进阻挡地形的守军哨位。"""
    terrain = game_terrain(game)
    map_w = game["map"]["width"]
    map_h = game["map"]["height"]
    angle_offsets = (0.0, 0.32, -0.32, 0.68, -0.68, 1.05, -1.05, math.pi)
    radius_offsets = (0.0, 38.0, -28.0, 76.0, -52.0)
    for radius_offset in radius_offsets:
        radius = max(resource["radius"] + size + 18.0,
                     preferred_radius + radius_offset)
        for angle_offset in angle_offsets:
            angle = base_angle + angle_offset
            x = resource["x"] + math.cos(angle) * radius
            y = resource["y"] + math.sin(angle) * radius
            if not (size + 18 <= x <= map_w - size - 18
                    and size + 18 <= y <= map_h - size - 18):
                continue
            if terrain.blocked(x, y, size) or not terrain.cell_open(x, y):
                continue
            if any(math.hypot(s["x"] - x, s["y"] - y)
                   < s["size"] + size + 16.0
                   for s in game["structures"] if s["hp"] > 0):
                continue
            if any(math.hypot(u["x"] - x, u["y"] - y)
                   < u["size"] + size + 10.0
                   for u in game["units"] if u["hp"] > 0):
                continue
            return round(x, 2), round(y, 2)
    return None


def spawn_neutral_ore_camp(game, resource, rng):
    """为一处公共矿生成固定炮塔与机动守军。"""
    camp_id = new_id("n")
    camp = {
        "id": camp_id, "resourceId": resource["id"],
        "x": resource["x"], "y": resource["y"],
        "guardIds": [], "cleared": False,
    }
    resource["neutralCampId"] = camp_id
    resource["guarded"] = True
    game.setdefault("neutralCamps", []).append(camp)

    facing = rng.random() * math.pi * 2.0
    turret_position = neutral_guard_position(
        game, resource, facing, 145.0, STRUCTURE_TYPES["turret"]["size"])
    if turret_position:
        turret = make_structure(
            "turret", NEUTRAL_OWNER, turret_position[0], turret_position[1], True)
        turret["neutralCampId"] = camp_id
        turret["guardCenterX"] = resource["x"]
        turret["guardCenterY"] = resource["y"]
        game["structures"].append(turret)
        camp["guardIds"].append(turret["id"])

    # 两名近卫负责挡采矿车，一名火箭兵在后排逼玩家带作战部队清场。
    formations = (
        ("rifle", facing + 0.9, 112.0),
        ("rifle", facing - 0.9, 112.0),
        ("rocket", facing + math.pi, 158.0),
    )
    for kind, angle, radius in formations:
        position = neutral_guard_position(
            game, resource, angle, radius, UNIT_TYPES[kind]["size"])
        if not position:
            continue
        guard = make_unit(kind, NEUTRAL_OWNER, position[0], position[1])
        guard["neutralCampId"] = camp_id
        guard["guardCenterX"] = resource["x"]
        guard["guardCenterY"] = resource["y"]
        guard["guardPostX"] = position[0]
        guard["guardPostY"] = position[1]
        game["units"].append(guard)
        camp["guardIds"].append(guard["id"])

    # 极端地形下至少保留一个守军；公共矿本身保证是可通行点，因此可在
    # 矿圈边缘放一名步兵作为最终兜底。
    if not camp["guardIds"]:
        fallback_x = resource["x"] + resource["radius"] + 18.0
        fallback_y = resource["y"]
        guard = make_unit("rifle", NEUTRAL_OWNER, fallback_x, fallback_y)
        guard["neutralCampId"] = camp_id
        guard["guardCenterX"] = resource["x"]
        guard["guardCenterY"] = resource["y"]
        guard["guardPostX"] = fallback_x
        guard["guardPostY"] = fallback_y
        game["units"].append(guard)
        camp["guardIds"].append(guard["id"])


def refresh_neutral_camps(game):
    """刷新公共矿锁；只有所属建筑和守军全部阵亡才解锁。"""
    camps = game.get("neutralCamps", [])
    if not camps:
        game["_guardedNeutralCampIds"] = set()
        return
    live_guard_ids = {
        entity["id"]
        for entity in game["units"] + game["structures"]
        if entity["hp"] > 0 and entity.get("neutralCampId")
    }
    guarded_ids = set()
    resource_by_id = {resource["id"]: resource for resource in game["resources"]}
    for camp in camps:
        guarded = any(guard_id in live_guard_ids for guard_id in camp["guardIds"])
        camp["cleared"] = not guarded
        if guarded:
            guarded_ids.add(camp["id"])
        resource = resource_by_id.get(camp["resourceId"])
        if resource:
            resource["guarded"] = guarded
    game["_guardedNeutralCampIds"] = guarded_ids


def resource_is_guarded(game, resource):
    camp_id = resource.get("neutralCampId")
    if not camp_id:
        return False
    guarded_ids = game.get("_guardedNeutralCampIds")
    if guarded_ids is None:
        refresh_neutral_camps(game)
        guarded_ids = game.get("_guardedNeutralCampIds", set())
    return camp_id in guarded_ids


def add_random_resources(game, count, spawn_points):
    """在出生区之外放置随机公共矿区。

    出生点附近的保底矿由 ``start_game`` 单独生成；这里的矿只负责争夺区，
    因此既要避开各家基地，也要彼此拉开距离。使用本局地图 seed 创建独立的
    随机源，避免单位朝向、AI 等无关随机调用改变矿区布局。
    """
    if count <= 0:
        return

    terrain = game_terrain(game)
    map_w = game["map"]["width"]
    map_h = game["map"]["height"]
    rng = random.Random(int(game["map"]["seed"]) ^ 0x51A7C0DE)
    margin = 180.0
    # 地图缩小后也不能把公共矿刷到家门口；它们有守军，至少留出一段真正
    # 需要出兵护送采矿车的行军距离。
    home_exclusion = min(1050.0, max(960.0, min(map_w, map_h) * 0.18))
    resource_separation = 520.0

    # 只接受和首个出生点处于同一导航连通块的格子，避免随机矿落进被河流
    # 或山体完全封死的小块空地。地图很大时也只有约一万格，这段每局只跑一次。
    grid = terrain._ensure_grid()
    start_x, start_y = spawn_points[0]
    start_cell = (
        int(clamp(start_x / PATH_CELL_SIZE, 0, terrain._grid_w - 1)),
        int(clamp(start_y / PATH_CELL_SIZE, 0, terrain._grid_h - 1)),
    )
    reachable = set([start_cell])
    frontier = [start_cell]
    while frontier:
        cx, cy = frontier.pop()
        for dx, dy in _PATH_NEIGHBORS:
            nx, ny = cx + dx, cy + dy
            if not (0 <= nx < terrain._grid_w and 0 <= ny < terrain._grid_h):
                continue
            if (nx, ny) in reachable or not grid[nx][ny]:
                continue
            if dx and dy and (not grid[cx + dx][cy] or not grid[cx][cy + dy]):
                continue
            reachable.add((nx, ny))
            frontier.append((nx, ny))

    placed = 0
    attempts = 0
    public_resources = []
    while placed < count and attempts < count * 500:
        attempts += 1
        x = rng.uniform(margin, map_w - margin)
        y = rng.uniform(margin, map_h - margin)
        cell = (
            int(clamp(x / PATH_CELL_SIZE, 0, terrain._grid_w - 1)),
            int(clamp(y / PATH_CELL_SIZE, 0, terrain._grid_h - 1)),
        )
        if cell not in reachable:
            continue
        if terrain.blocked(x, y, 48.0) or not terrain.cell_open(x, y):
            continue
        if any(math.hypot(x - sx, y - sy) < home_exclusion
               for sx, sy in spawn_points):
            continue
        if any(math.hypot(x - r["x"], y - r["y"]) < resource_separation
               for r in game["resources"]):
            continue

        # 公共矿量有波动，但限制在可读的整千数，地图每次重开会变化又不会
        # 因极端随机值破坏经济节奏。
        amount = rng.randint(18, 28) * 1000
        public_resources.append(add_resource(game, x, y, amount, public=True))
        placed += 1

    if placed < count:
        raise RuntimeError("无法为地图生成足够的随机矿区")

    # 守军使用独立随机源，避免模型编队的随机数影响下一局公共矿坐标。
    guard_rng = random.Random(int(game["map"]["seed"]) ^ 0x6E657574)
    for resource in public_resources:
        spawn_neutral_ore_camp(game, resource, guard_rng)
    refresh_neutral_camps(game)


def start_game(room):
    players = list(room["players"].values())
    count = len(players)
    room_map = MAPS.get(room.get("selectedMap", DEFAULT_MAP), MAPS[DEFAULT_MAP])
    if count < 2:
        raise ValueError("至少需要 2 名玩家（可以添加 AI）")
    if count > room_map["maxPlayers"]:
        raise ValueError("房间最多 %d 名玩家" % room_map["maxPlayers"])

    map_width = room_map["width"]
    map_height = room_map["height"]
    spawn_points = room_map["spawnPoints"]
    spawn_labels = room_map["spawnLabels"]
    rivers = room_map.get("rivers", [])
    bridges = room_map.get("bridges", [])
    mountains = room_map.get("mountains", [])
    roads = room_map.get("roads", [])

    game = {
        "map": {"width": map_width, "height": map_height, "seed": random.randint(1, 999999)},
        "elapsed": 0.0, "units": [], "structures": [], "resources": [],
        "neutralCamps": [],
        "projectiles": [], "effects": [], "pings": [], "winnerId": None,
        "playerTeams": {p["id"]: p.get("team", 0) for p in room["players"].values()},
        "botClock": 1.0, "victoryClock": 1.0,
        # 单位分离是视觉碰撞，不需要和攻击/移动一样跑满 20Hz。独立时钟让
        # 密集军团以 10Hz 解重叠，客户端仍按 60Hz 插值显示。
        "separationClock": 0.0, "uid": new_id("g"),
        "_snapshotVersion": 0, "_publicEntityFrame": None,
        "_publicViewCache": {},
        "terrain": {
            "rivers": [{"x1": r["x1"], "y1": r["y1"], "x2": r["x2"], "y2": r["y2"], "width": r["width"]} for r in rivers],
            "bridges": [{"x": b["x"], "y": b["y"], "w": b["w"], "h": b["h"]} for b in bridges],
            "mountains": [{"x": m["x"], "y": m["y"], "r": m["r"]} for m in mountains],
            "roads": [{"x1": r["x1"], "y1": r["y1"], "x2": r["x2"], "y2": r["y2"], "width": r["width"]} for r in roads],
            "theme": room_map.get("theme", "grassland"),
        },
        # Shared per-map navigation context. Never serialized: public_game()
        # copies only the plain "terrain" dict above.
        "terrainCtx": terrain_for_map(room_map),
    }

    # Assign spawns: honor explicit selections, auto-assign rest with team grouping.
    center_x, center_y = map_width / 2.0, map_height / 2.0

    teams_used = set(p.get("team", 0) for p in players)
    any_team = any(t > 0 for t in teams_used)
    has_explicit_spawn = any(p.get("spawn", -1) >= 0 for p in players)
    total_spawns = len(spawn_points)

    if not any_team and not has_explicit_spawn:
        if total_spawns == 6:
            spawns_by_count = {
                2: [0, 5],
                3: [0, 2, 4],
                4: [0, 2, 3, 5],
                5: [0, 1, 2, 3, 5],
                6: [0, 1, 2, 3, 4, 5],
            }
            player_spawns = {}
            assigned_indices = spawns_by_count.get(count, list(range(count)))
            for index, player in enumerate(players):
                player_spawns[player["id"]] = assigned_indices[index] if index < len(assigned_indices) else 0
        else:
            player_spawns = {}
            for index, player in enumerate(players):
                player_spawns[player["id"]] = index if index < total_spawns else 0
    else:
        # Group players by team (treat team-0 solo players as individual teams)
        teams = {}
        for p in players:
            t = p.get("team", 0)
            key = t if t > 0 else p["id"]
            teams.setdefault(key, []).append(p)

        # Sort team groups: larger teams first, same-size by team number, solo last
        team_groups = sorted(teams.values(), key=lambda g: (
            -len(g),
            0 if isinstance(g[0].get("team", 0), int) and g[0].get("team", 0) > 0 else 1,
            g[0].get("team", 0), g[0]["id"]
        ))

        spawns_per_side = total_spawns // 2 if total_spawns >= 2 else total_spawns

        used_spawns = set()
        player_spawns = {}
        for p in players:
            sp = p.get("spawn", -1)
            if 0 <= sp < total_spawns:
                used_spawns.add(sp)
                player_spawns[p["id"]] = sp

        # Assign remaining players from team groups
        for group in team_groups:
            unassigned = [p for p in group if p["id"] not in player_spawns]
            if not unassigned:
                continue
            side = None
            for p in group:
                if p["id"] in player_spawns:
                    side = 0 if player_spawns[p["id"]] < spawns_per_side else 1
                    break
            if side is None:
                assigned_team_count = sum(1 for g in team_groups if any(p["id"] in player_spawns for p in g))
                side = assigned_team_count % 2

            available = [i for i in range(spawns_per_side * side, spawns_per_side * side + spawns_per_side) if i not in used_spawns]
            if len(available) < len(unassigned):
                available = [i for i in range(total_spawns) if i not in used_spawns]

            for p in unassigned:
                if available:
                    best = min(available, key=lambda i: abs(i - (spawns_per_side * side + spawns_per_side // 2)))
                    available.remove(best)
                    used_spawns.add(best)
                    player_spawns[p["id"]] = best

        # Fallback: if any player still unassigned, give first remaining
        remaining = [i for i in range(total_spawns) if i not in used_spawns]
        for p in players:
            if p["id"] not in player_spawns:
                if remaining:
                    player_spawns[p["id"]] = remaining.pop(0)
                    used_spawns.add(player_spawns[p["id"]])
                else:
                    player_spawns[p["id"]] = p.get("spawn", 0) if p.get("spawn", -1) >= 0 else 0
                    if player_spawns[p["id"]] in used_spawns:
                        for si in range(total_spawns):
                            if si not in used_spawns:
                                player_spawns[p["id"]] = si
                                break
                used_spawns.add(player_spawns[p["id"]])

    for player in players:
        player["cash"] = 6800
        player["eliminated"] = False
        player["kills"] = 0
        player["unitsLost"] = 0
        player["harvested"] = 0
        player["buildQueue"] = []
        player["strikeCharges"] = 0
        sp = player_spawns[player["id"]]
        x, y = spawn_points[sp]
        toward_x = 1 if x < center_x else -1
        toward_y = 1 if y < center_y else -1
        start_hq = make_structure("hq", player["id"], x, y, True)
        start_hq["packable"] = True
        game["structures"].append(start_hq)
        game["structures"].append(make_structure("power", player["id"], x + toward_x * 125, y, True))
        refinery = make_structure("refinery", player["id"], x, y + toward_y * 155, True)
        game["structures"].append(refinery)
        harvester = make_unit("harvester", player["id"], refinery["x"] + toward_x * 70, refinery["y"])
        game["units"].append(harvester)
        for n in range(3):
            game["units"].append(make_unit("rifle", player["id"], x + toward_x * (75 + n * 16), y + toward_y * 70))
        game["units"].append(make_unit("tank", player["id"], x + toward_x * 92, y + toward_y * 112))
        # 家矿要跟随出生方向，但不能随着大战场尺寸一起越推越远；否则恢复
        # 9600×6000 后首轮回款会比小地图慢十几秒。短边地图仍用 20%，
        # 大地图把矿区中心限制在距基地约 650 世界单位内。
        center_dx = center_x - x
        center_dy = center_y - y
        center_dist = max(1.0, math.hypot(center_dx, center_dy))
        home_ore_factor = min(0.20, 650.0 / center_dist)
        ore_x = x + center_dx * home_ore_factor
        ore_y = y + center_dy * home_ore_factor
        add_resource(game, ore_x - toward_y * 62, ore_y + toward_x * 62, 22000)
        add_resource(game, ore_x + toward_y * 58, ore_y - toward_x * 48, 16000)
        add_resource(game, ore_x + toward_x * 110, ore_y + toward_y * 80, 14000)

    # 各家保留一片稳定的开局矿；其余争夺矿每局随机散布在出生区之外。
    add_random_resources(game, 4, spawn_points)

    room["game"] = game
    room["status"] = "playing"
    teams_used = set(p.get("team", 0) for p in players)
    if any(t > 0 for t in teams_used):
        team_lines = []
        team_map = {}
        for p in players:
            t = p.get("team", 0)
            if t > 0:
                team_map.setdefault(t, []).append(p["name"])
        for t in sorted(team_map):
            add_chat(room, "作战系统", "第%d队：%s" % (t, "、".join(team_map[t])), True)
    add_chat(room, "作战系统", "战斗开始：摧毁敌方指挥中心即可获胜。", True)


def find_entity(game, entity_id, entity_index=None):
    if not entity_id:
        return None
    if entity_index is not None:
        entity = entity_index.get(entity_id)
        return entity if entity and entity["hp"] > 0 else None
    for entity in game["units"]:
        if entity["id"] == entity_id and entity["hp"] > 0:
            return entity
    for entity in game["structures"]:
        if entity["id"] == entity_id and entity["hp"] > 0:
            return entity
    return None


def has_active_structure(game, player_id, kind):
    return any(s["owner"] == player_id and s["kind"] == kind and s["active"] and s["hp"] > 0
               for s in game["structures"])


def construction_anchor_near(game, player_id, x, y):
    for structure in game["structures"]:
        radius = BUILD_ANCHOR_RANGES.get(structure["kind"])
        if (is_friendly(game, structure["owner"], player_id) and structure["hp"] > 0
                and structure["active"] and radius is not None):
            if math.hypot(structure["x"] - x, structure["y"] - y) <= radius:
                return True
    return False


def outside_enemy_build_zone(game, player_id, x, y):
    for structure in game["structures"]:
        if is_friendly(game, structure["owner"], player_id) or structure["hp"] <= 0:
            continue
        limit = ENEMY_BUILD_EXCLUSION + structure["size"] * 0.35
        if math.hypot(structure["x"] - x, structure["y"] - y) < limit:
            return False
    return True


def position_clear(game, x, y, size):
    # 山体和水面都不能建造；山体额外留出建筑半径的余量，免得半个建筑嵌进山里
    if game_terrain(game).blocked(x, y, size * 0.6):
        return False
    for structure in game["structures"]:
        if structure["hp"] <= 0:
            continue
        if math.hypot(structure["x"] - x, structure["y"] - y) < structure["size"] + size + 18:
            return False
    for resource in game["resources"]:
        if resource["amount"] > 0 and math.hypot(resource["x"] - x, resource["y"] - y) < resource["radius"] + size + 16:
            return False
    return True


def place_structure(room, player_id, kind, x, y, free=False):
    game = room["game"]
    player = room["players"][player_id]
    if kind not in STRUCTURE_TYPES or kind == "hq":
        raise ValueError("未知建筑")
    definition = STRUCTURE_TYPES[kind]
    map_w = game["map"]["width"]
    map_h = game["map"]["height"]
    x = clamp(float(x), definition["size"] + 12, map_w - definition["size"] - 12)
    y = clamp(float(y), definition["size"] + 12, map_h - definition["size"] - 12)
    for requirement in definition["requires"]:
        if not has_active_structure(game, player_id, requirement):
            raise ValueError("缺少前置建筑")
    if not construction_anchor_near(game, player_id, x, y):
        raise ValueError("建筑必须靠近已完成的核心基地建筑")
    if not outside_enemy_build_zone(game, player_id, x, y):
        raise ValueError("不能在敌方控制区内建造")
    if not position_clear(game, x, y, definition["size"]):
        raise ValueError("这里无法放置建筑")
    if not free:
        if player["cash"] < definition["cost"]:
            raise ValueError("资金不足")
        player["cash"] -= definition["cost"]
    structure = make_structure(kind, player_id, x, y, False)
    game["structures"].append(structure)
    return structure


def queue_structure(room, player_id, kind):
    game = room["game"]
    player = room["players"][player_id]
    definition = STRUCTURE_TYPES.get(kind)
    if not definition or kind == "hq":
        raise ValueError("未知建筑")
    for requirement in definition["requires"]:
        if not has_active_structure(game, player_id, requirement):
            raise ValueError("缺少前置建筑")
    if player.get("buildQueue"):
        raise ValueError("建筑生产队列已有任务")
    if player["cash"] < definition["cost"]:
        raise ValueError("资金不足")
    player["cash"] -= definition["cost"]
    item = {
        "id": new_id("c"), "kind": kind,
        "remaining": float(definition["build"]),
        "total": float(definition["build"]), "ready": False,
    }
    player["buildQueue"] = [item]
    return item


def place_prepared_structure(room, player_id, kind, x, y):
    player = room["players"][player_id]
    queue = player.get("buildQueue", [])
    if not queue or queue[0]["kind"] != kind or not queue[0].get("ready"):
        raise ValueError("该建筑尚未生产完成")
    structure = place_structure(room, player_id, kind, x, y, free=True)
    player["buildQueue"] = []
    return structure


def cancel_structure_queue(room, player_id):
    player = room["players"][player_id]
    queue = player.get("buildQueue", [])
    if not queue:
        raise ValueError("没有可取消的建筑任务")
    item = queue[0]
    player["cash"] += STRUCTURE_TYPES[item["kind"]]["cost"]
    player["buildQueue"] = []


def queue_unit(room, player_id, kind):
    game = room["game"]
    player = room["players"][player_id]
    definition = UNIT_TYPES.get(kind)
    if not definition:
        raise ValueError("未知单位")
    producer_kind = definition["producer"]
    producers = [s for s in game["structures"]
                 if s["owner"] == player_id and s["kind"] == producer_kind
                 and s["active"] and s["hp"] > 0]
    if not producers:
        raise ValueError("缺少对应生产建筑")
    # 高级兵种的二级科技门槛：光有生产建筑不够，还得有配套支援建筑在运转
    for requirement in definition.get("requires", []):
        if not has_active_structure(game, player_id, requirement):
            raise ValueError("缺少前置建筑：%s" % STRUCTURE_TYPES[requirement]["name"])
    producer = min(producers, key=lambda item: len(item["queue"]))
    if len(producer["queue"]) >= 5:
        raise ValueError("生产队列已满")
    if player["cash"] < definition["cost"]:
        raise ValueError("资金不足")
    player["cash"] -= definition["cost"]
    producer["queue"].append({
        "kind": kind, "remaining": float(definition["build"]),
        "total": float(definition["build"]),
    })


def cancel_unit_queue(room, player_id, kind):
    """从生产队列里撤下一个该兵种并全额退款。

    撤的是「最后排进去的那一个」：玩家点多了想退回来，直觉上退的是刚点的，
    而不是马上就要造好的那一个。
    """
    game = room["game"]
    player = room["players"][player_id]
    definition = UNIT_TYPES.get(kind)
    if not definition:
        raise ValueError("未知单位")
    best_producer = None
    best_index = -1
    for producer in game["structures"]:
        if (producer["owner"] != player_id
                or producer["kind"] != definition["producer"]
                or producer["hp"] <= 0):
            continue
        for index in range(len(producer["queue"]) - 1, -1, -1):
            if producer["queue"][index]["kind"] == kind:
                if index > best_index:
                    best_producer = producer
                    best_index = index
                break
    if best_producer is None:
        raise ValueError("没有该单位在生产")
    best_producer["queue"].pop(best_index)
    player["cash"] += definition["cost"]


def clear_repair_order(unit):
    unit["repairTargetId"] = None
    unit["repairing"] = False


def issue_move(game, player_id, unit_ids, x, y, attack_move=False):
    selected = [u for u in game["units"] if u["owner"] == player_id and u["id"] in unit_ids and u["hp"] > 0]
    if not selected:
        return
    terrain = game_terrain(game)
    target_x = clamp(float(x), 15, game["map"]["width"] - 15)
    target_y = clamp(float(y), 15, game["map"]["height"] - 15)
    origin_x = sum(unit["x"] for unit in selected) / float(len(selected))
    origin_y = sum(unit["y"] for unit in selected) / float(len(selected))
    group_clearance = max(8.0, max(unit["size"] for unit in selected) * 0.35)
    if terrain.blocked(target_x, target_y, group_clearance):
        target_x, target_y = terrain.nearest_open_point(
            target_x, target_y, origin_x, origin_y, group_clearance)
    columns = max(1, int(math.ceil(math.sqrt(len(selected)))))
    spacing = 52
    for index, unit in enumerate(selected):
        row = index // columns
        column = index % columns
        offset_x = (column - (columns - 1) / 2.0) * spacing
        offset_y = (row - (math.ceil(len(selected) / float(columns)) - 1) / 2.0) * spacing
        dest_x = clamp(target_x + offset_x, 15, game["map"]["width"] - 15)
        dest_y = clamp(target_y + offset_y, 15, game["map"]["height"] - 15)
        clearance = max(8.0, unit["size"] * 0.35)
        if terrain.blocked(dest_x, dest_y, clearance):
            dest_x, dest_y = terrain.nearest_open_point(
                dest_x, dest_y, unit["x"], unit["y"], clearance)
        unit["destX"] = dest_x
        unit["destY"] = dest_y
        unit["targetId"] = None
        clear_repair_order(unit)
        unit["order"] = "attackMove" if attack_move else "move"
        # A new command must never inherit the previous route merely because
        # both clicks happen to fall in the same navigation cell.
        unit["_path"] = None
        unit["_pathDest"] = None
        unit["_pathEnd"] = None
        unit["_pathDirect"] = False
        unit["_pathUnavailable"] = False
        unit["_routeRetry"] = 0.0
        unit["_stuck"] = 0.0
        if unit["kind"] == "harvester":
            unit["manualUntil"] = 0.0


def issue_attack(game, player_id, unit_ids, target_id):
    target = find_entity(game, target_id)
    if not target or is_friendly(game, target["owner"], player_id):
        raise ValueError("无效目标")
    for unit in game["units"]:
        if unit["owner"] == player_id and unit["id"] in unit_ids and unit["hp"] > 0:
            if UNIT_TYPES[unit["kind"]]["damage"] > 0:
                unit["targetId"] = target_id
                unit["destX"] = None
                unit["destY"] = None
                clear_repair_order(unit)
                unit["order"] = "attack"


def issue_repair(game, player_id, unit_ids, structure_id):
    repair_bay = find_entity(game, structure_id)
    if (not repair_bay or repair_bay.get("kind") != "repair"
            or repair_bay["owner"] != player_id or not repair_bay.get("active")):
        raise ValueError("请选择己方已启用的维修厂")
    selected = [
        unit for unit in game["units"]
        if unit["owner"] == player_id and unit["id"] in unit_ids
        and unit["hp"] > 0 and unit["kind"] in VEHICLE_KINDS
        and unit["hp"] < unit["maxHp"] - 0.1
    ]
    if not selected:
        raise ValueError("请选择受损载具")
    for index, unit in enumerate(selected):
        ring = index // REPAIR_DOCKS_PER_RING
        slot = index % REPAIR_DOCKS_PER_RING
        approach_angle = math.atan2(
            unit["y"] - repair_bay["y"], unit["x"] - repair_bay["x"])
        fan_offset = (slot - (REPAIR_DOCKS_PER_RING - 1) / 2.0) * 0.08
        unit["repairTargetId"] = repair_bay["id"]
        unit["repairAngle"] = approach_angle + fan_offset + ring * 0.11
        unit["repairRing"] = ring
        unit["repairing"] = False
        unit["targetId"] = None
        unit["destX"] = None
        unit["destY"] = None
        unit["order"] = "repair"


def command_unit_ids(payload):
    values = payload.get("unitIds")
    if not isinstance(values, list):
        return set()
    return set(value for value in values if isinstance(value, str))


def issue_deploy(game, player_id, unit_ids):
    deployed = False
    for unit in game["units"]:
        if unit["owner"] != player_id or unit["id"] not in unit_ids:
            continue
        if not UNIT_TYPES.get(unit["kind"], {}).get("canDeploy"):
            continue
        if not position_clear(game, unit["x"], unit["y"], 58):
            raise ValueError("此处无法展开：空间不足")
        if game_terrain(game).blocked(unit["x"], unit["y"], 30):
            raise ValueError("不能在水中或山地展开")
        # Transform MCV into HQ at current location
        new_hq = make_structure("hq", player_id, unit["x"], unit["y"], True)
        new_hq["packable"] = True
        game["structures"].append(new_hq)
        unit["hp"] = 0
        game["effects"].append({
            "id": new_id("e"), "type": "complete",
            "x": unit["x"], "y": unit["y"], "ttl": 1.4,
        })
        deployed = True
    if not deployed:
        raise ValueError("请选择可展开的基地车")


def issue_undeploy(game, player_id, structure_id):
    hq = find_entity(game, structure_id)
    if not hq or hq.get("kind") != "hq" or hq["owner"] != player_id:
        raise ValueError("请选择己方指挥中心")
    if not hq.get("packable"):
        raise ValueError("该指挥中心无法折叠")
    # 只检查地形和敌方建筑，自己的建筑不挡路
    mcv_size = UNIT_TYPES["mcv"]["size"]
    x, y = hq["x"], hq["y"]
    terrain = game_terrain(game)
    if terrain.point_in_water(x, y):
        raise ValueError("指挥中心处于水中，无法折叠")
    if terrain.point_in_mountain(x, y, mcv_size * 0.6):
        raise ValueError("周围地形崎岖，无法折叠")
    if terrain.blocked(x, y, mcv_size * 0.6):
        raise ValueError("指挥中心靠水域太近，无法折叠")
    for structure in game["structures"]:
        if structure["hp"] <= 0 or structure is hq:
            continue
        if is_friendly(game, structure["owner"], player_id):
            continue
        if math.hypot(structure["x"] - x, structure["y"] - y) < structure["size"] + mcv_size + 18:
            raise ValueError("敌方建筑距离过近，无法折叠")
    mcv = make_unit("mcv", player_id, x, y)
    mcv["hp"] = min(hq["hp"], mcv["maxHp"])
    game["units"].append(mcv)
    hq["hp"] = 0
    game["effects"].append({
        "id": new_id("e"), "type": "complete",
        "x": hq["x"], "y": hq["y"], "ttl": 1.2,
    })


def issue_strike(room, player_id, x, y):
    """消耗一次超级武器充能，向目标点呼叫轨道打击。"""
    game = room["game"]
    player = room["players"].get(player_id)
    if not player or player.get("eliminated"):
        raise ValueError("无法释放")
    if player.get("strikeCharges", 0) <= 0:
        raise ValueError("没有超级武器充能")
    map_w = game["map"]["width"]
    map_h = game["map"]["height"]
    tx = clamp(float(x), 0, map_w)
    ty = clamp(float(y), 0, map_h)
    player["strikeCharges"] -= 1
    base = game["elapsed"] + STRIKE_WARNING
    # 预先把弹着点散布好，落弹时按节奏依次结算
    impacts = []
    for _ in range(STRIKE_IMPACTS):
        rr = math.sqrt(random.random()) * STRIKE_RADIUS
        ang = random.random() * math.pi * 2.0
        impacts.append({
            "x": tx + math.cos(ang) * rr,
            "y": ty + math.sin(ang) * rr,
            "fireAt": base + (len(impacts)) * STRIKE_IMPACT_STEP + random.random() * 0.05,
        })
    fire_until = impacts[-1]["fireAt"] if impacts else base
    game.setdefault("pendingStrikes", []).append({
        "owner": player_id, "x": tx, "y": ty,
        "warnUntil": base, "fireUntil": fire_until,
        "impacts": impacts, "fired": 0,
    })
    add_chat(room, "作战系统", "%s 呼叫了轨道打击！" % player.get("name", "指挥官"), True)


def handle_game_command(room, player, payload):
    if room["status"] != "playing" or not room.get("game"):
        raise ValueError("战斗尚未开始")
    if player.get("eliminated"):
        raise ValueError("你已被击败")
    game = room["game"]
    command = payload.get("command")
    if command in ("move", "attackMove"):
        unit_ids = command_unit_ids(payload)
        issue_move(game, player["id"], unit_ids, payload.get("x", 0), payload.get("y", 0), command == "attackMove")
    elif command == "attack":
        issue_attack(game, player["id"], command_unit_ids(payload), payload.get("targetId"))
    elif command == "repair":
        issue_repair(
            game, player["id"], command_unit_ids(payload),
            payload.get("structureId"))
    elif command == "deploy":
        issue_deploy(game, player["id"], command_unit_ids(payload))
    elif command == "undeploy":
        issue_undeploy(game, player["id"], payload.get("structureId"))
    elif command == "stop":
        unit_ids = command_unit_ids(payload)
        for unit in game["units"]:
            if unit["owner"] == player["id"] and unit["id"] in unit_ids:
                unit["destX"] = None
                unit["destY"] = None
                unit["targetId"] = None
                clear_repair_order(unit)
                unit["order"] = "guard"
    elif command == "train":
        queue_unit(room, player["id"], str(payload.get("unitType", "")))
    elif command == "prepareBuild":
        queue_structure(room, player["id"], str(payload.get("structureType", "")))
    elif command == "placeBuild":
        place_prepared_structure(room, player["id"], str(payload.get("structureType", "")), payload.get("x", 0), payload.get("y", 0))
    elif command == "cancelBuild":
        cancel_structure_queue(room, player["id"])
    elif command == "cancelTrain":
        cancel_unit_queue(room, player["id"], str(payload.get("unitType", "")))
    elif command == "sell":
        structure_id = payload.get("structureId")
        structure = next((s for s in game["structures"] if s["id"] == structure_id and s["owner"] == player["id"]), None)
        if not structure or structure["kind"] == "hq":
            raise ValueError("该建筑不可出售")
        refund = int(STRUCTURE_TYPES[structure["kind"]]["cost"] * 0.5 * max(0.25, structure["hp"] / structure["maxHp"]))
        player["cash"] += refund
        structure["hp"] = 0
        game["effects"].append({"id": new_id("e"), "type": "sell", "x": structure["x"], "y": structure["y"], "ttl": 0.8})
    elif command == "ping":
        map_w = room["game"]["map"]["width"]
        map_h = room["game"]["map"]["height"]
        game["pings"].append({
            "id": new_id("g"), "owner": player["id"],
            "x": clamp(float(payload.get("x", 0)), 0, map_w),
            "y": clamp(float(payload.get("y", 0)), 0, map_h), "ttl": 4.0,
        })
    elif command == "setRally":
        structure_id = payload.get("structureId")
        structure = next((s for s in game["structures"] if s["id"] == structure_id and s["owner"] == player["id"] and s["hp"] > 0), None)
        if not structure or structure["kind"] not in ("barracks", "factory"):
            raise ValueError("只能为兵营或重装工厂设置集结点")
        rally_x = clamp(float(payload.get("x", 0)), 30, game["map"]["width"] - 30)
        rally_y = clamp(float(payload.get("y", 0)), 30, game["map"]["height"] - 30)
        structure["rally"] = (rally_x, rally_y)
    elif command == "callStrike":
        issue_strike(room, player["id"], payload.get("x", 0), payload.get("y", 0))
    else:
        raise ValueError("未知指令")


# --- terrain & navigation ---

PATH_CELL_SIZE = 80.0
# A cell is considered blocked when a mountain reaches its square, not only
# when it covers the exact centre. This keeps A* edges from cutting a circular
# mountain corner that the continuous movement collision will later reject.
PATH_MOUNTAIN_CLEARANCE = PATH_CELL_SIZE * 0.71
_PATH_CACHE_MAX = 800
# 道路：寻路代价打折（部队会自发沿路行军）+ 实际行军加速
ROAD_PATH_COST = 0.55
ROAD_SPEED_BONUS = 1.35
_PATH_NEIGHBORS = ((-1, 0), (1, 0), (0, -1), (0, 1), (-1, -1), (-1, 1), (1, -1), (1, 1))
_CIRCLE8 = ((1.0, 0.0), (0.70710678, 0.70710678), (0.0, 1.0),
            (-0.70710678, 0.70710678), (-1.0, 0.0),
            (-0.70710678, -0.70710678), (0.0, -1.0),
            (0.70710678, -0.70710678))
MOVING_TARGET_REPATH_DISTANCE = 32.0


def _path_heuristic(ax, ay, bx, by):
    dx = abs(ax - bx)
    dy = abs(ay - by)
    return dx + dy + (1.414 - 2.0) * min(dx, dy)


class Terrain(object):
    """Per-map terrain: water, mountains, roads and A* navigation.

    One instance is shared by every room playing the same map. This state used
    to live in module globals that ``tick_game`` overwrote for whichever room
    ticked last, which meant command handlers on HTTP threads validated builds
    against another room's rivers, and two rooms on different maps rebuilt the
    navigation grid -- flushing the path cache -- on every single tick.

    地形分三类：
      rivers   —— 水面，除桥梁外不可通行
      mountains—— 山体，完全不可通行、不可建造（无桥可绕）
      roads    —— 道路，可通行且加速；A* 代价更低，所以部队会自然沿路行军
    """

    __slots__ = ("rivers", "bridges", "mountains", "roads", "width", "height",
                 "_river_shapes", "_bridge_boxes", "_mountain_shapes", "_road_shapes",
                 "_grid", "_cost", "_grid_w", "_grid_h", "_path_cache",
                 "_near_cache")

    def __init__(self, rivers, bridges, width, height, mountains=None, roads=None):
        self.rivers = list(rivers or [])
        self.bridges = list(bridges or [])
        self.mountains = list(mountains or [])
        self.roads = list(roads or [])
        self.width = float(width)
        self.height = float(height)
        # 热路径只读紧凑 tuple，避免每个单位、每一帧重复做 dict 查找、
        # min/max、线段长度和半径平方。大军团移动时这部分原先占模拟的一半。
        self._river_shapes = []
        for river in self.rivers:
            x1, y1 = float(river["x1"]), float(river["y1"])
            dx = float(river["x2"]) - x1
            dy = float(river["y2"]) - y1
            half = float(river["width"]) * 0.5
            self._river_shapes.append((
                min(x1, x1 + dx) - half, max(x1, x1 + dx) + half,
                min(y1, y1 + dy) - half, max(y1, y1 + dy) + half,
                x1, y1, dx, dy, dx * dx + dy * dy, half * half))
        self._bridge_boxes = [
            (float(bridge["x"]) - float(bridge["w"]) * 0.5,
             float(bridge["x"]) + float(bridge["w"]) * 0.5,
             float(bridge["y"]) - float(bridge["h"]) * 0.5,
             float(bridge["y"]) + float(bridge["h"]) * 0.5)
            for bridge in self.bridges
        ]
        self._mountain_shapes = [
            (float(m["x"]), float(m["y"]), float(m["r"]))
            for m in self.mountains
        ]
        self._road_shapes = []
        for road in self.roads:
            x1, y1 = float(road["x1"]), float(road["y1"])
            dx = float(road["x2"]) - x1
            dy = float(road["y2"]) - y1
            half = float(road["width"]) * 0.5
            self._road_shapes.append((
                min(x1, x1 + dx) - half, max(x1, x1 + dx) + half,
                min(y1, y1 + dy) - half, max(y1, y1 + dy) + half,
                x1, y1, dx, dy, dx * dx + dy * dy, half * half))
        self._grid = None
        self._cost = None
        self._grid_w = 0
        self._grid_h = 0
        self._path_cache = {}
        self._near_cache = {}

    # --- water ---

    def point_in_water(self, x, y):
        for shape in self._river_shapes:
            if x < shape[0] or x > shape[1] or y < shape[2] or y > shape[3]:
                continue
            rx1, ry1, seg_dx, seg_dy, length_sq = shape[4:9]
            if length_sq < 0.001:
                closest_x, closest_y = rx1, ry1
            else:
                t = ((x - rx1) * seg_dx + (y - ry1) * seg_dy) / length_sq
                if t < 0.0:
                    t = 0.0
                elif t > 1.0:
                    t = 1.0
                closest_x = rx1 + t * seg_dx
                closest_y = ry1 + t * seg_dy
            wx = x - closest_x
            wy = y - closest_y
            if wx * wx + wy * wy < shape[9]:
                for box in self._bridge_boxes:
                    if box[0] <= x <= box[1] and box[2] <= y <= box[3]:
                        return False
                return True
        return False

    # --- mountains ---

    def point_in_mountain(self, x, y, padding=0.0):
        for mx, my, radius in self._mountain_shapes:
            dx = x - mx
            dy = y - my
            r = radius + padding
            if dx * dx + dy * dy < r * r:
                return True
        return False

    def blocked(self, x, y, padding=0.0):
        """能否落脚：水面和山体都不行。

        padding 对水面同样生效 —— 只查中心点的话，一个半径 48 的矿区中心是干
        的、边缘却泡在河里，采矿车会一直够不到。所以带 padding 时沿一圈采样。
        """
        if self.point_in_mountain(x, y, padding):
            return True
        if self.point_in_water(x, y):
            return True
        if padding > 0 and self._river_shapes:
            for dx, dy in _CIRCLE8:
                if self.point_in_water(x + dx * padding, y + dy * padding):
                    return True
        return False

    def near_blocker(self, x, y, padding=0.0):
        """缓存式阻挡物宽相位；仅命中时才调用 blocked 做精确检查。

        分离阶段的密集军团一帧会产生数千次碰撞对。阻挡物是静态的，所以按
        64 单位网格和向上取整的 padding 档位缓存包围盒结果；格子整体参与判定，
        不会因为缓存把真正靠近山河的点误判为安全。
        """
        cell_size = SEPARATION_CELL_SIZE
        cell_x = int(x // cell_size)
        cell_y = int(y // cell_size)
        pad_step = 8.0
        pad_bucket = int(math.ceil(max(0.0, padding) / pad_step))
        key = (cell_x, cell_y, pad_bucket)
        cached = self._near_cache.get(key)
        if cached is not None:
            return cached
        pad = pad_bucket * pad_step
        min_x = cell_x * cell_size - pad
        max_x = (cell_x + 1) * cell_size + pad
        min_y = cell_y * cell_size - pad
        max_y = (cell_y + 1) * cell_size + pad
        for mx, my, radius in self._mountain_shapes:
            if (mx + radius >= min_x and mx - radius <= max_x
                    and my + radius >= min_y and my - radius <= max_y):
                self._near_cache[key] = True
                return True
        for shape in self._river_shapes:
            if (shape[1] >= min_x and shape[0] <= max_x
                    and shape[3] >= min_y and shape[2] <= max_y):
                self._near_cache[key] = True
                return True
        self._near_cache[key] = False
        return False

    def cell_open(self, x, y):
        """该点所在的寻路格是否可通行（判断「部队到底能不能过来」用这个）。"""
        grid = self._ensure_grid()
        cx = clamp(int(x / PATH_CELL_SIZE), 0, self._grid_w - 1)
        cy = clamp(int(y / PATH_CELL_SIZE), 0, self._grid_h - 1)
        return grid[cx][cy]

    # --- roads ---

    def on_road(self, x, y):
        for shape in self._road_shapes:
            if x < shape[0] or x > shape[1] or y < shape[2] or y > shape[3]:
                continue
            x1, y1, dx, dy, length_sq = shape[4:9]
            if length_sq < 0.001:
                cx, cy = x1, y1
            else:
                t = ((x - x1) * dx + (y - y1) * dy) / length_sq
                if t < 0.0:
                    t = 0.0
                elif t > 1.0:
                    t = 1.0
                cx = x1 + t * dx
                cy = y1 + t * dy
            rx = x - cx
            ry = y - cy
            if rx * rx + ry * ry < shape[9]:
                return True
        return False

    def speed_scale(self, x, y):
        """道路上的行军加成。没有道路的地图恒为 1，开销可以忽略。"""
        if not self.roads:
            return 1.0
        return ROAD_SPEED_BONUS if self.on_road(x, y) else 1.0

    def segment_blocked(self, x1, y1, x2, y2, samples=24):
        if not self.rivers and not self.mountains:
            return False

        # Mountains are circles, so test them analytically. The old 24-sample
        # cap could skip a mountain on a long diagonal minimap command; the
        # unit would then run straight into it and the stuck timer ended the
        # order as though the destination had been reached.
        seg_dx = x2 - x1
        seg_dy = y2 - y1
        seg_len_sq = seg_dx * seg_dx + seg_dy * seg_dy
        for mx, my, radius in self._mountain_shapes:
            if seg_len_sq < 0.001:
                closest_x, closest_y = x1, y1
            else:
                t = ((mx - x1) * seg_dx + (my - y1) * seg_dy) / seg_len_sq
                t = clamp(t, 0.0, 1.0)
                closest_x = x1 + seg_dx * t
                closest_y = y1 + seg_dy * t
            dx = mx - closest_x
            dy = my - closest_y
            if dx * dx + dy * dy < radius * radius:
                return True

        if not self.rivers:
            return False
        # Legacy water primitives still use sampling; live maps no longer
        # contain rivers. Use a correctness-oriented interval without making
        # the hot mountain path pay for it.
        distance = math.hypot(x2 - x1, y2 - y1)
        samples = min(96, max(samples, int(distance / 40.0) + 1))
        step_x = (x2 - x1) / samples
        step_y = (y2 - y1) / samples
        for i in range(samples + 1):
            if self.point_in_water(x1 + step_x * i, y1 + step_y * i):
                return True
        return False

    def nearest_bridge_waypoint(self, unit_x, unit_y, dest_x, dest_y):
        if not self.rivers or not self.bridges:
            return None
        if not self.segment_blocked(unit_x, unit_y, dest_x, dest_y):
            return None
        best_bridge = None
        best_cost = float("inf")
        for bridge in self.bridges:
            bx, by = bridge["x"], bridge["y"]
            cost = (math.hypot(bx - unit_x, by - unit_y)
                    + math.hypot(dest_x - bx, dest_y - by))
            if cost < best_cost:
                best_cost = cost
                best_bridge = bridge
        if not best_bridge:
            return None
        return (best_bridge["x"], best_bridge["y"])

    # --- A* navigation ---

    def _ensure_grid(self):
        if self._grid is not None:
            return self._grid
        gw = int(math.ceil(self.width / PATH_CELL_SIZE))
        gh = int(math.ceil(self.height / PATH_CELL_SIZE))
        grid = [[True] * gh for _ in range(gw)]
        # 每格的通行代价：道路更便宜，于是 A* 会自发沿路走
        cost = [[1.0] * gh for _ in range(gw)]
        if self.rivers or self.mountains or self.roads:
            for cx in range(gw):
                column = grid[cx]
                cost_column = cost[cx]
                wx = cx * PATH_CELL_SIZE + PATH_CELL_SIZE / 2.0
                for cy in range(gh):
                    wy = cy * PATH_CELL_SIZE + PATH_CELL_SIZE / 2.0
                    if (self.point_in_mountain(wx, wy, PATH_MOUNTAIN_CLEARANCE)
                            or self.point_in_water(wx, wy)):
                        column[cy] = False
                    elif self.on_road(wx, wy):
                        cost_column[cy] = ROAD_PATH_COST
        self._grid = grid
        self._cost = cost
        self._grid_w = gw
        self._grid_h = gh
        self._path_cache.clear()
        return grid

    def find_path(self, start_x, start_y, end_x, end_y):
        grid = self._ensure_grid()
        cost = self._cost
        gw = self._grid_w
        gh = self._grid_h
        if gw == 0 or gh == 0:
            return [(end_x, end_y)]

        # Make the public method safe even when a caller passes a mountain
        # point directly. Prefer the side facing the moving unit.
        if self.blocked(end_x, end_y):
            end_x, end_y = self.nearest_open_point(
                end_x, end_y, start_x, start_y)

        start_cell = (clamp(int(start_x / PATH_CELL_SIZE), 0, gw - 1),
                      clamp(int(start_y / PATH_CELL_SIZE), 0, gh - 1))
        end_cell = (clamp(int(end_x / PATH_CELL_SIZE), 0, gw - 1),
                    clamp(int(end_y / PATH_CELL_SIZE), 0, gh - 1))

        if not grid[end_cell[0]][end_cell[1]]:
            projected = self._nearest_open(
                end_cell, gw, gh, start_x, start_y)
            if not projected:
                return []
            end_cell = projected
            # The exact click may be just outside a mountain but live in a
            # conservative blocked grid cell. Stop at the safe cell centre
            # instead of appending a final segment back through the mountain.
            end_x = end_cell[0] * PATH_CELL_SIZE + PATH_CELL_SIZE / 2.0
            end_y = end_cell[1] * PATH_CELL_SIZE + PATH_CELL_SIZE / 2.0
        if not grid[start_cell[0]][start_cell[1]]:
            # 单位被推进了阻挡格（分离力/部署），先找最近的可通行格作为起点
            projected = self._nearest_open(
                start_cell, gw, gh, start_x, start_y)
            if not projected:
                return []
            start_cell = projected

        if start_cell == end_cell:
            return [(end_x, end_y)]

        cache_key = (start_cell, end_cell)
        cached = self._path_cache.get(cache_key)
        if cached is not None:
            # Cache grid-centre waypoints only. Exact endpoints differ even
            # when two minimap clicks land in the same 80px cell.
            result = list(cached)
            if not result or result[-1] != (end_x, end_y):
                result.append((end_x, end_y))
            return result

        open_heap = [(0.0, start_cell)]
        came_from = {}
        g_score = {start_cell: 0.0}

        while open_heap:
            _, current = heapq.heappop(open_heap)
            if current == end_cell:
                path_cells = []
                while current in came_from:
                    path_cells.append(current)
                    current = came_from[current]
                path_cells.reverse()
                world_path = [
                    (c[0] * PATH_CELL_SIZE + PATH_CELL_SIZE / 2.0,
                     c[1] * PATH_CELL_SIZE + PATH_CELL_SIZE / 2.0)
                    for c in path_cells
                ]
                if len(self._path_cache) < _PATH_CACHE_MAX:
                    self._path_cache[cache_key] = list(world_path)
                if not world_path or world_path[-1] != (end_x, end_y):
                    world_path.append((end_x, end_y))
                return world_path

            current_g = g_score[current]
            cx, cy = current
            for dgx, dgy in _PATH_NEIGHBORS:
                nnx = cx + dgx
                nny = cy + dgy
                if not (0 <= nnx < gw and 0 <= nny < gh):
                    continue
                if not grid[nnx][nny]:
                    continue
                if dgx != 0 and dgy != 0:
                    if not grid[cx + dgx][cy] or not grid[cx][cy + dgy]:
                        continue
                nn = (nnx, nny)
                step = 1.414 if dgx != 0 and dgy != 0 else 1.0
                tg = current_g + step * cost[nnx][nny]
                if tg < g_score.get(nn, float("inf")):
                    came_from[nn] = current
                    g_score[nn] = tg
                    heapq.heappush(
                        open_heap,
                        (tg + _path_heuristic(nnx, nny, end_cell[0], end_cell[1]) * ROAD_PATH_COST,
                         nn))

        # Never fall back to a straight line through an obstacle. The caller
        # keeps the order and can retry instead of silently declaring success.
        return []

    def _nearest_open(self, cell, gw, gh, prefer_x=None, prefer_y=None):
        """在阻挡格附近做环形搜索，找最近的可通行格。"""
        grid = self._grid
        for ring in range(1, max(gw, gh) + 1):
            candidates = []
            for dx in range(-ring, ring + 1):
                for dy in range(-ring, ring + 1):
                    if max(abs(dx), abs(dy)) != ring:
                        continue
                    nx = cell[0] + dx
                    ny = cell[1] + dy
                    if 0 <= nx < gw and 0 <= ny < gh and grid[nx][ny]:
                        wx = nx * PATH_CELL_SIZE + PATH_CELL_SIZE / 2.0
                        wy = ny * PATH_CELL_SIZE + PATH_CELL_SIZE / 2.0
                        if prefer_x is None:
                            score = dx * dx + dy * dy
                        else:
                            score = ((wx - prefer_x) * (wx - prefer_x)
                                     + (wy - prefer_y) * (wy - prefer_y))
                        candidates.append((score, nx, ny))
            if candidates:
                candidates.sort()
                return (candidates[0][1], candidates[0][2])
        return None

    def nearest_open_point(self, x, y, origin_x=None, origin_y=None, padding=0.0):
        """距 (x,y) 最近的可行世界坐标。

        玩家点到山脚/河岸时，终点中心本身压在阻挡里——单位一路走过去、最后
        一步永远踩不进阻挡，就会贴着边卡死。这里把这种终点外推到最近的可
        行点，使「贴边点击」也能正常抵达。
        """
        self._ensure_grid()
        if not self.blocked(x, y, padding):
            return (x, y)
        cx = clamp(int(x / PATH_CELL_SIZE), 0, self._grid_w - 1)
        cy = clamp(int(y / PATH_CELL_SIZE), 0, self._grid_h - 1)
        # 先在原地附近做精确外推：格子中心可行、但精确点压边的情况
        if origin_x is None:
            base_angle = 0.0
        else:
            base_angle = math.atan2(origin_y - y, origin_x - x)
        angle_order = (0, 1, -1, 2, -2, 3, -3, 4)
        for step in range(1, 14):
            for offset in angle_order:
                angle = base_angle + offset * (math.pi / 4.0)
                nx = clamp(x + math.cos(angle) * step * 18, 0.0, self.width)
                ny = clamp(y + math.sin(angle) * step * 18, 0.0, self.height)
                if not self.blocked(nx, ny, padding):
                    return (nx, ny)
        # 整格都被阻挡：退到最近的可通行格中心
        prefer_x = origin_x if origin_x is not None else x
        prefer_y = origin_y if origin_y is not None else y
        cell = self._nearest_open(
            (cx, cy), self._grid_w, self._grid_h, prefer_x, prefer_y)
        if cell:
            return (cell[0] * PATH_CELL_SIZE + PATH_CELL_SIZE / 2.0,
                    cell[1] * PATH_CELL_SIZE + PATH_CELL_SIZE / 2.0)
        return (x, y)


_TERRAIN_BY_MAP = {}
FLAT_TERRAIN = Terrain([], [], 9600, 6000)


def terrain_for_map(map_def):
    """Return the shared Terrain for a map definition, building it on demand."""
    key = map_def["id"]
    cached = _TERRAIN_BY_MAP.get(key)
    if cached is None:
        cached = Terrain(map_def.get("rivers"), map_def.get("bridges"),
                         map_def["width"], map_def["height"],
                         map_def.get("mountains"), map_def.get("roads"))
        _TERRAIN_BY_MAP[key] = cached
    return cached


def game_terrain(game):
    """Terrain context for a running game (falls back to open ground)."""
    return (game or {}).get("terrainCtx") or FLAT_TERRAIN


def move_toward(terrain, entity, target_x, target_y, speed, dt, stop_distance=0.0):
    # pathDest 存的是调用方传入的原始目标，用来判断「是不是还在去同一个地方」。
    path = entity.get("_path")
    path_dest = entity.get("_pathDest")
    if path_dest is None:
        same_dest = False
    elif entity.get("targetId"):
        drift_x = target_x - path_dest[0]
        drift_y = target_y - path_dest[1]
        same_dest = (drift_x * drift_x + drift_y * drift_y
                     <= MOVING_TARGET_REPATH_DISTANCE * MOVING_TARGET_REPATH_DISTANCE)
    else:
        same_dest = path_dest == (target_x, target_y)

    # 移动目标在 32 距离内的小幅漂移不值得重新做地形射线；直线路径只把
    # 末端跟随目标更新，累计漂移超过阈值时再完整重算。
    if (same_dest and path is not None and entity.get("targetId")
            and entity.get("_pathDirect")):
        entity["_pathEnd"] = (target_x, target_y)
        if path:
            path[-1] = (target_x, target_y)

    if not same_dest or path is None:
        end_x, end_y = target_x, target_y
        # 终点压在山脚/河岸时外推到最近可行点：否则最后一步永远踩不进阻挡，
        # 单位会贴着边卡死，再也到不了。
        destination_clearance = max(8.0, entity.get("size", 20.0) * 0.35)
        if terrain.blocked(end_x, end_y, destination_clearance):
            end_x, end_y = terrain.nearest_open_point(
                end_x, end_y, entity["x"], entity["y"],
                destination_clearance)
        path_blocked = terrain.segment_blocked(entity["x"], entity["y"], end_x, end_y)
        if path_blocked:
            path = terrain.find_path(entity["x"], entity["y"], end_x, end_y)
            if path:
                # find_path may conservatively project an edge click to a
                # safe grid centre; that effective endpoint is authoritative.
                end_x, end_y = path[-1]
        else:
            path = [(end_x, end_y)]
        entity["_path"] = path
        entity["_pathDest"] = (target_x, target_y)
        entity["_pathEnd"] = (end_x, end_y)
        entity["_pathDirect"] = not path_blocked
        entity["_pathUnavailable"] = path_blocked and not path
        entity["_routeRetry"] = 0.0
        entity["_stuck"] = 0.0
    else:
        end_x, end_y = entity.get("_pathEnd", (target_x, target_y))

    if entity.get("_pathUnavailable"):
        # Keep the player's order alive. Retry at a low rate in case the unit
        # was displaced into a bad grid cell; never convert failure into a
        # fake arrival/guard order.
        entity["_routeRetry"] = entity.get("_routeRetry", 0.0) + dt
        if entity["_routeRetry"] >= 0.75:
            entity["_path"] = None
            entity["_pathDest"] = None
            entity["_pathUnavailable"] = False
        return False

    dx = end_x - entity["x"]
    dy = end_y - entity["y"]
    dist = math.hypot(dx, dy)
    if dist <= stop_distance + 0.5:
        entity["_path"] = None
        entity["_stuck"] = 0.0
        return True

    # 当前要走的航点：多段路径取第一段，单段路径直接走终点
    move_target_x, move_target_y = end_x, end_y
    if path:
        move_target_x, move_target_y = path[0][0], path[0][1]

    before_x, before_y = entity["x"], entity["y"]
    intended = 0.0
    mdx = move_target_x - entity["x"]
    mdy = move_target_y - entity["y"]
    mdist = math.hypot(mdx, mdy)
    if mdist > 0.01:
        entity["dir"] = math.atan2(mdy, mdx)
        # 走在路上更快
        intended = min(speed * terrain.speed_scale(entity["x"], entity["y"]) * dt,
                       max(0.0, mdist))
        if intended > 0.0:
            nx = mdx / mdist
            ny = mdy / mdist
            new_x = entity["x"] + nx * intended
            new_y = entity["y"] + ny * intended
            if not terrain.blocked(new_x, new_y):
                entity["x"] = clamp(new_x, entity["size"], terrain.width - entity["size"])
                entity["y"] = clamp(new_y, entity["size"], terrain.height - entity["size"])
            else:
                # 正前方被山/河挡住（贴边行军或被挤出路径）：沿单轴滑行，
                # 避免一贴边就整个停住。
                step_x = entity["x"] + nx * intended
                if not terrain.blocked(step_x, entity["y"]):
                    entity["x"] = clamp(step_x, entity["size"], terrain.width - entity["size"])
                step_y = entity["y"] + ny * intended
                if not terrain.blocked(entity["x"], step_y):
                    entity["y"] = clamp(step_y, entity["size"], terrain.height - entity["size"])

    new_dx = move_target_x - entity["x"]
    new_dy = move_target_y - entity["y"]
    wp_reached = math.hypot(new_dx, new_dy) <= 8.0

    if wp_reached and path:
        path.pop(0)
        entity["_stuck"] = 0.0
        if not path:
            entity["_path"] = None
            return True
        entity["_path"] = path
    else:
        # 卡死检测：想走的步子有明显意义、却只走了不到一半，说明连续地形
        # 与导航路线不一致。旧逻辑会跳过航点，最后直接把命令当成“已抵达”；
        # 现在保留玩家命令并从当前位置重算。
        progress = math.hypot(entity["x"] - before_x, entity["y"] - before_y)
        if intended > 1.0 and progress < intended * 0.5:
            entity["_stuck"] = entity.get("_stuck", 0.0) + dt
            if entity["_stuck"] > 0.5:
                entity["_stuck"] = 0.0
                entity["_path"] = None
                entity["_pathDest"] = None
                entity["_pathDirect"] = False
                return False
        else:
            entity["_stuck"] = 0.0

    return False


def nearest_enemy(game, owner, x, y, max_distance, spatial_index=None):
    best = None
    best_dist_sq = max_distance * max_distance
    candidates = (spatial_candidates(
        spatial_index, x, y, max_distance, 16.0)
        if spatial_index else game["units"] + game["structures"])
    for entity in candidates:
        if is_friendly(game, entity["owner"], owner) or entity["hp"] <= 0:
            continue
        dx = entity["x"] - x
        dy = entity["y"] - y
        current_sq = dx * dx + dy * dy
        if current_sq < best_dist_sq:
            best = entity
            best_dist_sq = current_sq
    return best


def nearest_enemy_structure(game, owner, x, y, max_distance, spatial_index=None):
    best = None
    best_dist_sq = max_distance * max_distance
    # 与 nearest_enemy 一样走共享的战术空间网格，只在候选里筛出敌方建筑，
    # 不再每次线性扫整张结构表（网格里混着单位，靠 id 前缀挑出建筑）。
    candidates = (spatial_candidates(
        spatial_index, x, y, max_distance, 16.0)
        if spatial_index else game["structures"])
    for entity in candidates:
        if not entity["id"].startswith("s"):
            continue
        if is_friendly(game, entity["owner"], owner) or entity["hp"] <= 0:
            continue
        dx = entity["x"] - x
        dy = entity["y"] - y
        current_sq = dx * dx + dy * dy
        if current_sq < best_dist_sq:
            best = entity
            best_dist_sq = current_sq
    return best


def nearest_enemy_infantry(game, owner, x, y, max_distance, spatial_index=None):
    """军犬专用：只扑步兵。克制表里 bite 对载具/建筑全是 ×0，追上去也是白送，
    所以自动索敌时干脆只看装甲为 infantry 的敌方单位（含敌方军犬）。"""
    best = None
    best_dist_sq = max_distance * max_distance
    candidates = (spatial_candidates(
        spatial_index, x, y, max_distance, 16.0)
        if spatial_index else game["units"])
    for entity in candidates:
        if not entity["id"].startswith("u"):
            continue
        if UNIT_TYPES.get(entity.get("kind"), {}).get("armor") != "infantry":
            continue
        if is_friendly(game, entity["owner"], owner) or entity["hp"] <= 0:
            continue
        dx = entity["x"] - x
        dy = entity["y"] - y
        current_sq = dx * dx + dy * dy
        if current_sq < best_dist_sq:
            best = entity
            best_dist_sq = current_sq
    return best


def launch_projectile(game, attacker, target, definition, damage_mult=1.0):
    span = math.hypot(target["x"] - attacker["x"], target["y"] - attacker["y"])
    game["projectiles"].append({
        "id": new_id("q"), "owner": attacker["owner"],
        "sourceId": attacker["id"],
        "x": attacker["x"], "y": attacker["y"],
        "span": max(1.0, span),
        "targetId": target["id"], "targetX": target["x"], "targetY": target["y"],
        "damage": definition["damage"] * damage_mult, "speed": definition["projectileSpeed"],
        "splash": definition.get("splash", 0.0), "kind": definition["projectile"],
        "damageType": definition.get("damageType", "bullet"),
        "ttl": 3.5,
    })
    game["effects"].append({
        "id": new_id("e"), "type": "muzzle", "x": attacker["x"], "y": attacker["y"], "ttl": 0.16,
    })


def apply_damage(room, target, damage, source_owner, damage_type=None, game=None, source_id=None):
    if target["hp"] <= 0:
        return
    applied = max(0.0, damage)
    # Apply damage-type vs armor multiplier
    if damage_type and game:
        target_def = None
        if target["id"].startswith("u"):
            target_def = UNIT_TYPES.get(target.get("kind", ""), {})
        elif target["id"].startswith("s"):
            target_def = STRUCTURE_TYPES.get(target.get("kind", ""), {})
        armor = target_def.get("armor", "structure") if target_def else "structure"
        multiplier = DAMAGE_MULTIPLIER.get(damage_type, {}).get(armor, 1.0)
        applied *= multiplier
    target["hp"] -= applied
    if target["id"].startswith("s") and not target.get("active", True):
        target["constructionDamage"] = target.get("constructionDamage", 0.0) + applied
    if target["hp"] <= 0:
        target["hp"] = 0
        owner = room["players"].get(target["owner"])
        source = room["players"].get(source_owner)
        if owner and target["id"].startswith("u"):
            owner["unitsLost"] += 1
        if source and source_owner != target["owner"]:
            source["kills"] += 1
        if source_id and game and source_owner != target["owner"]:
            source_unit = None
            for u in game["units"]:
                if u["id"] == source_id:
                    source_unit = u
                    break
            if source_unit:
                new_kills = source_unit.get("kills", 0) + 1
                source_unit["kills"] = new_kills
                # 升军衔瞬间（3/8/16 杀，与 tick_units 的分级阈值一致）发一个晋升
                # 特效，客户端据此画金色礼花并播晋升音。
                if new_kills in (3, 8, 16):
                    game["effects"].append({
                        "id": new_id("e"), "type": "promote",
                        "x": source_unit["x"], "y": source_unit["y"], "ttl": 1.0,
                    })


def tick_projectiles(room, dt, entity_index=None, combat_spatial=None):
    game = room["game"]
    remaining = []
    for projectile in game["projectiles"]:
        projectile["ttl"] -= dt
        target = find_entity(game, projectile["targetId"], entity_index)
        if target:
            projectile["targetX"] = target["x"]
            projectile["targetY"] = target["y"]
        dx = projectile["targetX"] - projectile["x"]
        dy = projectile["targetY"] - projectile["y"]
        dist = math.hypot(dx, dy)
        move = projectile["speed"] * dt
        if dist <= move + 7 or projectile["ttl"] <= 0:
            impact_x, impact_y = projectile["targetX"], projectile["targetY"]
            if target:
                apply_damage(room, target, projectile["damage"], projectile["owner"],
                             projectile.get("damageType"), game,
                             projectile.get("sourceId"))
            splash = projectile.get("splash", 0)
            if splash > 0:
                candidates = (spatial_candidates(
                    combat_spatial, impact_x, impact_y, splash)
                    if combat_spatial else game["units"] + game["structures"])
                for entity in candidates:
                    if entity is target or is_friendly(game, entity["owner"], projectile["owner"]) or entity["hp"] <= 0:
                        continue
                    dx = entity["x"] - impact_x
                    dy = entity["y"] - impact_y
                    radius_sq = dx * dx + dy * dy
                    if radius_sq < splash * splash:
                        radius = math.sqrt(radius_sq)
                        apply_damage(room, entity, projectile["damage"] * 0.45 * (1.0 - radius / splash), projectile["owner"],
                                     projectile.get("damageType"), game,
                                     projectile.get("sourceId"))
            game["effects"].append({
                "id": new_id("e"), "type": "impact", "x": impact_x, "y": impact_y,
                "ttl": 0.65 if projectile["kind"] != "bullet" else 0.22,
            })
        else:
            if dist > 0:
                projectile["x"] += dx / dist * move
                projectile["y"] += dy / dist * move
            remaining.append(projectile)
    game["projectiles"] = remaining


def tick_repair_unit(room, unit, dt, entity_index, power_cache, terrain):
    game = room["game"]
    repair_bay = find_entity(game, unit.get("repairTargetId"), entity_index)
    if (not repair_bay or repair_bay.get("kind") != "repair"
            or repair_bay["owner"] != unit["owner"]
            or not repair_bay.get("active")):
        clear_repair_order(unit)
        unit["order"] = "guard"
        return
    if unit["hp"] >= unit["maxHp"] - 0.1:
        unit["hp"] = unit["maxHp"]
        clear_repair_order(unit)
        unit["order"] = "guard"
        return

    # 维修范围：维修厂半径 + 自身半径 + 20 的缓冲，在范围内直接修
    repair_radius = repair_bay["size"] + unit["size"] + 20.0
    dist_to_bay = math.hypot(unit["x"] - repair_bay["x"], unit["y"] - repair_bay["y"])

    if dist_to_bay > repair_radius:
        # 还没走到维修范围，先移动到维修厂旁边
        ring = max(0, int(unit.get("repairRing", 0)))
        dock_radius = repair_bay["size"] + unit["size"] + 13.0 + ring * 24.0
        angle = unit.get("repairAngle", 0.0)
        dock_x = clamp(
            repair_bay["x"] + math.cos(angle) * dock_radius,
            unit["size"], terrain.width - unit["size"])
        dock_y = clamp(
            repair_bay["y"] + math.sin(angle) * dock_radius,
            unit["size"], terrain.height - unit["size"])
        definition = UNIT_TYPES[unit["kind"]]
        move_toward(terrain, unit, dock_x, dock_y, definition["speed"], dt, 5.0)
        return

    # 在维修范围内：开始维修
    player = room["players"].get(unit["owner"])
    if not player or player.get("cash", 0.0) <= 0:
        return
    power_factor = power_cache.get(unit["owner"])
    if power_factor is None:
        supply, usage = player_power(room, unit["owner"])
        power_factor = 1.0 if supply >= usage else 0.35
        power_cache[unit["owner"]] = power_factor
    missing = unit["maxHp"] - unit["hp"]
    affordable = player["cash"] / REPAIR_COST_PER_HP
    healed = min(REPAIR_RATE * power_factor * dt, missing, affordable)
    if healed <= 0:
        return
    unit["hp"] += healed
    unit["repairing"] = True
    unit["dir"] = math.atan2(repair_bay["y"] - unit["y"], repair_bay["x"] - unit["x"])
    player["cash"] = max(0.0, player["cash"] - healed * REPAIR_COST_PER_HP)
    if unit["hp"] >= unit["maxHp"] - 0.1:
        unit["hp"] = unit["maxHp"]
        clear_repair_order(unit)
        unit["order"] = "guard"


def tick_harvester(room, unit, dt, entity_index=None, terrain=None):
    game = room["game"]
    terrain = terrain or game_terrain(game)
    definition = UNIT_TYPES["harvester"]
    if unit.get("order") in ("move", "attackMove"):
        if unit["destX"] is not None:
            if move_toward(terrain, unit, unit["destX"], unit["destY"], definition["speed"], dt):
                unit["destX"] = None
                unit["destY"] = None
                unit["order"] = "guard"
        else:
            unit["order"] = "guard"
        return

    if unit["cargo"] >= unit["capacity"] - 0.1 or unit.get("returnTarget"):
        refinery = find_entity(game, unit.get("returnTarget"), entity_index)
        if not refinery or refinery["owner"] != unit["owner"] or refinery["kind"] != "refinery" or not refinery["active"]:
            candidates = [s for s in game["structures"] if s["owner"] == unit["owner"] and s["kind"] == "refinery" and s["active"] and s["hp"] > 0]
            refinery = min(candidates, key=lambda s: distance(s, unit)) if candidates else None
            unit["returnTarget"] = refinery["id"] if refinery else None
        if refinery:
            reached = move_toward(
                terrain, unit, refinery["x"], refinery["y"],
                definition["speed"], dt, refinery["size"] + 8)
            # 只有真正开到精炼厂卸矿范围内才结算。满载只会切换返程状态，
            # 不再改写坐标，因此客户端不会看到采矿车瞬移。
            if reached:
                player = room["players"].get(unit["owner"])
                if player:
                    delivered = int(unit["cargo"])
                    player["cash"] += delivered
                    player["harvested"] += delivered
                unit["cargo"] = 0.0
                unit["returnTarget"] = None
                unit["harvestTarget"] = None
        return

    resource = next((r for r in game["resources"]
                     if r["id"] == unit.get("harvestTarget")
                     and r["amount"] > 0
                     and not resource_is_guarded(game, r)), None)
    if not resource:
        # 公共矿的最后一名守军阵亡前都不会成为自动采集候选；即便玩家
        # 手动把采矿车开进矿圈，服务端也不会结算一分钱。
        candidates = [r for r in game["resources"]
                      if r["amount"] > 1 and not resource_is_guarded(game, r)]
        resource = min(candidates, key=lambda r: math.hypot(r["x"] - unit["x"], r["y"] - unit["y"])) if candidates else None
        unit["harvestTarget"] = resource["id"] if resource else None
    if resource:
        reached = move_toward(terrain, unit, resource["x"], resource["y"], definition["speed"], dt, resource["radius"] + 5)
        if reached:
            mined = min(definition["harvestRate"] * dt, resource["amount"], unit["capacity"] - unit["cargo"])
            resource["amount"] -= mined
            unit["cargo"] += mined
            if unit["cargo"] >= unit["capacity"] - 0.1 or resource["amount"] <= 0:
                unit["returnTarget"] = "pending"


def separate_units(terrain, units):
    cells = {}
    has_blockers = bool(terrain.rivers or terrain.mountains)
    for first in units:
        cell_x, cell_y = spatial_cell(first["x"], first["y"], SEPARATION_CELL_SIZE)
        for near_x in range(cell_x - 1, cell_x + 2):
            for near_y in range(cell_y - 1, cell_y + 2):
                for second in cells.get((near_x, near_y), ()):
                    dx = second["x"] - first["x"]
                    dy = second["y"] - first["y"]
                    dist_sq = dx * dx + dy * dy
                    minimum = (first["size"] + second["size"]) * 1.15
                    if 0.01 < dist_sq < minimum * minimum:
                        dist = math.sqrt(dist_sq)
                        push = (minimum - dist) * 0.35
                        nx, ny = dx / dist, dy / dist
                        old_fx, old_fy = first["x"], first["y"]
                        old_sx, old_sy = second["x"], second["y"]
                        check_first = (has_blockers and terrain.near_blocker(
                            old_fx, old_fy, push + 4.0))
                        check_second = (has_blockers and terrain.near_blocker(
                            old_sx, old_sy, push + 4.0))
                        first["x"] -= nx * push
                        first["y"] -= ny * push
                        second["x"] += nx * push
                        second["y"] += ny * push
                        # 绝大多数碰撞发生在开阔地，不再为每一对单位扫描全图
                        # 山河；宽相位命中障碍物包围盒时才做精确 blocked 检查。
                        if ((check_first and terrain.blocked(first["x"], first["y"]))
                                or (check_second and terrain.blocked(
                                    second["x"], second["y"]))):
                            first["x"], first["y"] = old_fx, old_fy
                            second["x"], second["y"] = old_sx, old_sy
        key = spatial_cell(first["x"], first["y"], SEPARATION_CELL_SIZE)
        cells.setdefault(key, []).append(first)

    for unit in units:
        unit["x"] = clamp(unit["x"], unit["size"], terrain.width - unit["size"])
        unit["y"] = clamp(unit["y"], unit["size"], terrain.height - unit["size"])


def tick_neutral_guard(game, unit, definition, dt, entity_index, terrain, speed_mult):
    """处理中立矿区守军的缰绳与回防；返回 True 表示本帧已接管。"""
    if unit.get("owner") != NEUTRAL_OWNER or not unit.get("neutralCampId"):
        return False

    center_x = unit.get("guardCenterX", unit.get("guardPostX", unit["x"]))
    center_y = unit.get("guardCenterY", unit.get("guardPostY", unit["y"]))
    post_x = unit.get("guardPostX", center_x)
    post_y = unit.get("guardPostY", center_y)
    target = find_entity(game, unit.get("targetId"), entity_index)
    unit_from_center = math.hypot(unit["x"] - center_x, unit["y"] - center_y)
    target_from_center = (math.hypot(target["x"] - center_x, target["y"] - center_y)
                          if target else None)

    # 目标越过矿区缰绳，或守军自身已经被拉出警戒圈：立刻脱战。
    if (unit_from_center > NEUTRAL_GUARD_LEASH
            or (target_from_center is not None
                and target_from_center > NEUTRAL_GUARD_LEASH)):
        unit["targetId"] = None
        target = None
        unit["order"] = "neutralReturn"

    distance_to_post = math.hypot(unit["x"] - post_x, unit["y"] - post_y)
    if target is None and distance_to_post > NEUTRAL_GUARD_POST_RADIUS:
        unit["targetId"] = None
        unit["order"] = "neutralReturn"

    if unit.get("order") != "neutralReturn":
        return False

    unit["targetId"] = None
    unit["destX"] = post_x
    unit["destY"] = post_y
    reached = move_toward(
        terrain, unit, post_x, post_y,
        definition["speed"] * speed_mult * 1.12, dt,
        NEUTRAL_GUARD_POST_RADIUS * 0.55)
    if reached:
        unit["destX"] = None
        unit["destY"] = None
        unit["order"] = "guard"
        unit["scan"] = 0.0
    return True


def tick_units(room, dt, entity_index=None, combat_spatial=None):
    game = room["game"]
    terrain = game_terrain(game)
    repair_power_cache = {}
    # Automatic target acquisition is deliberately time-sliced. A mass move,
    # guard return or newly spawned army can otherwise make hundreds of units
    # all scan in one 50ms tick, producing a visible one-frame hitch even though
    # the average simulation cost is low. Direct attack orders already carry a
    # target and are not delayed by this budget.
    scan_budget = min(96, max(48, len(game["units"]) // 3))
    scans_used = 0
    for unit in list(game["units"]):
        if unit["hp"] <= 0:
            continue
        definition = UNIT_TYPES[unit["kind"]]
        kills = unit.get("kills", 0)
        if kills >= 16:
            rank = 3
            dam_mult = 1.6
            spd_mult = 1.3
            cd_mult = 0.55
            heal_rate = 1.0
        elif kills >= 8:
            rank = 2
            dam_mult = 1.4
            spd_mult = 1.2
            cd_mult = 0.7
            heal_rate = 0.5
        elif kills >= 3:
            rank = 1
            dam_mult = 1.2
            spd_mult = 1.1
            cd_mult = 0.85
            heal_rate = 0.0
        else:
            rank = 0
            dam_mult = 1.0
            spd_mult = 1.0
            cd_mult = 1.0
            heal_rate = 0.0
        if heal_rate > 0:
            unit["hp"] = min(unit["maxHp"], unit["hp"] + heal_rate * dt)
        unit["repairing"] = False
        unit["cooldown"] = max(0.0, unit["cooldown"] - dt * (1.0 / cd_mult))
        unit["scan"] = max(0.0, unit["scan"] - dt)
        if unit.get("order") == "repair":
            tick_repair_unit(room, unit, dt, entity_index, repair_power_cache, terrain)
            continue
        if unit["kind"] == "harvester":
            tick_harvester(room, unit, dt, entity_index, terrain)
            continue

        if tick_neutral_guard(
                game, unit, definition, dt, entity_index, terrain, spd_mult):
            continue

        # A plain move is an explicit player order. It always interrupts
        # combat and remains authoritative until the destination is reached.
        if unit.get("order") == "move":
            unit["targetId"] = None
            if unit["destX"] is not None:
                if move_toward(terrain, unit, unit["destX"], unit["destY"], definition["speed"] * spd_mult, dt):
                    unit["destX"] = None
                    unit["destY"] = None
                    unit["order"] = "guard"
            else:
                unit["order"] = "guard"
            continue

        target = find_entity(game, unit.get("targetId"), entity_index)
        if target and is_friendly(game, target["owner"], unit["owner"]):
            target = None
            unit["targetId"] = None
        if not target and unit["scan"] <= 0:
            if scans_used >= scan_budget:
                # Retry on a nearby tick with jitter so the deferred tail does
                # not become another synchronized spike.
                unit["scan"] = 0.035 + random.random() * 0.035
            else:
                scans_used += 1
                if unit.get("owner") == NEUTRAL_OWNER:
                    aggro = NEUTRAL_GUARD_AGGRO
                else:
                    aggro = (330.0 if unit.get("order") == "attackMove"
                             else 255.0)
                target = nearest_enemy(
                    game, unit["owner"], unit["x"], unit["y"], aggro,
                    combat_spatial)
                # 攻城炮优先打建筑，附近没有建筑时才打单位
                if (target and unit["kind"] == "artillery"
                        and target["kind"] not in STRUCTURE_TYPES):
                    building = nearest_enemy_structure(
                        game, unit["owner"], unit["x"], unit["y"], aggro,
                        combat_spatial)
                    if building:
                        target = building
                # 军犬只扑步兵：对载具/建筑零伤害，追上去等于送死。
                # 覆盖自动索敌结果；玩家手点的目标（上面 find_entity）不受影响。
                if unit["kind"] == "dog":
                    target = nearest_enemy_infantry(
                        game, unit["owner"], unit["x"], unit["y"], aggro,
                        combat_spatial)
                unit["targetId"] = target["id"] if target else None
                unit["scan"] = 0.28 + random.random() * 0.22
        if target:
            attack_distance = math.hypot(target["x"] - unit["x"], target["y"] - unit["y"])
            desired = definition["range"] + target.get("size", 0) * 0.35
            if attack_distance <= desired:
                unit["dir"] = math.atan2(target["y"] - unit["y"], target["x"] - unit["x"])
                if unit["cooldown"] <= 0:
                    launch_projectile(game, unit, target, definition, dam_mult)
                    unit["cooldown"] = definition["cooldown"]
            else:
                move_toward(terrain, unit, target["x"], target["y"], definition["speed"] * spd_mult, dt, max(8, desired - 12))
        elif unit["destX"] is not None:
            if move_toward(terrain, unit, unit["destX"], unit["destY"], definition["speed"] * spd_mult, dt):
                unit["destX"] = None
                unit["destY"] = None
                unit["order"] = "guard"

    # A local spatial grid limits separation checks to neighboring cells. Unit
    # movement and combat stay at 20Hz, while collision relaxation runs at
    # 10Hz. In a four-player blob this halves the dominant O(local pairs)
    # workload without changing pathfinding, weapon timing or command latency.
    game["separationClock"] = game.get("separationClock", 0.0) - dt
    if game["separationClock"] <= 0.0:
        live_units = [u for u in game["units"] if u["hp"] > 0]
        separate_units(terrain, live_units)
        game["separationClock"] = 0.10


def tick_build_queues(room, dt):
    for player in room["players"].values():
        queue = player.get("buildQueue", [])
        if not queue or player.get("eliminated"):
            continue
        item = queue[0]
        if item.get("ready"):
            continue
        supply, usage = player_power(room, player["id"])
        production_rate = 1.0 if supply >= usage else 0.4
        item["remaining"] = max(0.0, item["remaining"] - dt * production_rate)
        if item["remaining"] <= 0:
            item["ready"] = True


def tick_structures(room, dt, combat_spatial=None):
    game = room["game"]
    terrain = game_terrain(game)
    for structure in game["structures"]:
        if structure["hp"] <= 0:
            continue
        if not structure["active"]:
            supply, usage = player_power(room, structure["owner"])
            rate = 1.0 if supply >= usage else 0.55
            structure["buildRemaining"] = max(0.0, structure["buildRemaining"] - dt * rate)
            progress = 1.0 - structure["buildRemaining"] / max(0.01, structure["buildTotal"])
            material_hp = structure["maxHp"] * clamp(progress, 0.22, 1.0)
            structure["hp"] = max(0.0, material_hp - structure.get("constructionDamage", 0.0))
            if structure["hp"] <= 0:
                continue
            if structure["buildRemaining"] <= 0:
                structure["active"] = True
                structure["hp"] = max(1.0, structure["maxHp"] - structure.get("constructionDamage", 0.0))
                game["effects"].append({"id": new_id("e"), "type": "complete", "x": structure["x"], "y": structure["y"], "ttl": 1.2})
                # New refinery comes with a free harvester
                if structure["kind"] == "refinery":
                    spawn_angle = random.random() * math.pi * 2
                    spawn_x = structure["x"] + math.cos(spawn_angle) * 70
                    spawn_y = structure["y"] + math.sin(spawn_angle) * 70
                    if not terrain.blocked(spawn_x, spawn_y):
                        gift = make_unit("harvester", structure["owner"], spawn_x, spawn_y)
                        game["units"].append(gift)
            continue

        if structure["queue"]:
            supply, usage = player_power(room, structure["owner"])
            production_rate = 1.0 if supply >= usage else 0.35
            item = structure["queue"][0]
            item["remaining"] = max(0.0, item["remaining"] - dt * production_rate)
            if item["remaining"] <= 0:
                angle = random.random() * math.pi * 2
                radius = structure["size"] + UNIT_TYPES[item["kind"]]["size"] + 16
                unit = make_unit(item["kind"], structure["owner"],
                                 structure["x"] + math.cos(angle) * radius,
                                 structure["y"] + math.sin(angle) * radius)
                game["units"].append(unit)
                structure["queue"].pop(0)
                game["effects"].append({"id": new_id("e"), "type": "complete", "x": unit["x"], "y": unit["y"], "ttl": 0.8})
                if structure.get("rally"):
                    unit["destX"], unit["destY"] = structure["rally"]
                    unit["order"] = "move"

        if structure["kind"] in ("turret", "missile"):
            definition = STRUCTURE_TYPES[structure["kind"]]
            structure["cooldown"] = max(0.0, structure["cooldown"] - dt)
            target = nearest_enemy(
                game, structure["owner"], structure["x"], structure["y"],
                definition["range"], combat_spatial)
            if target:
                structure["dir"] = math.atan2(target["y"] - structure["y"], target["x"] - structure["x"])
                if structure["cooldown"] <= 0:
                    launch_projectile(game, structure, target, definition)
                    structure["cooldown"] = definition["cooldown"]


def bot_place_prepared(room, bot, kind):
    game = room["game"]
    anchors = [s for s in game["structures"]
               if s["owner"] == bot["id"] and s["active"] and s["hp"] > 0
               and s["kind"] in BUILD_ANCHOR_RANGES]
    random.shuffle(anchors)
    for anchor in anchors:
        maximum = BUILD_ANCHOR_RANGES[anchor["kind"]] - 20
        minimum = anchor["size"] + STRUCTURE_TYPES[kind]["size"] + 35
        for _ in range(18):
            angle = random.random() * math.pi * 2
            radius = minimum + random.random() * max(1, maximum - minimum)
            x = anchor["x"] + math.cos(angle) * radius
            y = anchor["y"] + math.sin(angle) * radius
            try:
                place_prepared_structure(room, bot["id"], kind, x, y)
                return True
            except ValueError:
                pass
    return False


def tick_bots(room):
    game = room["game"]
    for bot in [p for p in room["players"].values() if p["isBot"] and not p["eliminated"]]:
        own_structures = [s for s in game["structures"] if s["owner"] == bot["id"] and s["hp"] > 0]
        kinds = set(s["kind"] for s in own_structures if s["active"])
        supply, usage = player_power(room, bot["id"])
        build_queue = bot.get("buildQueue", [])
        if build_queue and build_queue[0].get("ready"):
            bot_place_prepared(room, bot, build_queue[0]["kind"])
        elif not build_queue:
            try:
                if supply < usage + 35 and bot["cash"] >= STRUCTURE_TYPES["power"]["cost"]:
                    queue_structure(room, bot["id"], "power")
                elif "barracks" not in kinds and bot["cash"] >= STRUCTURE_TYPES["barracks"]["cost"]:
                    queue_structure(room, bot["id"], "barracks")
                elif "refinery" not in kinds and bot["cash"] >= STRUCTURE_TYPES["refinery"]["cost"]:
                    queue_structure(room, bot["id"], "refinery")
                elif "factory" not in kinds and bot["cash"] >= STRUCTURE_TYPES["factory"]["cost"]:
                    queue_structure(room, bot["id"], "factory")
                elif ("factory" in kinds and "repair" not in kinds
                      and random.random() < 0.30
                      and bot["cash"] >= STRUCTURE_TYPES["repair"]["cost"]):
                    queue_structure(room, bot["id"], "repair")
                elif random.random() < 0.14 and bot["cash"] >= STRUCTURE_TYPES["turret"]["cost"]:
                    queue_structure(room, bot["id"], "turret")
            except ValueError:
                pass

        try:
            roll = random.random()
            if "factory" in kinds and roll < 0.58:
                if "repair" in kinds and roll < 0.16:
                    # 维修厂撑起二级科技后，掺高级装甲：天启抗线 / 光棱远程点杀
                    queue_unit(room, bot["id"], "overlord" if roll < 0.08 else "prism")
                else:
                    queue_unit(room, bot["id"], "tank" if roll < 0.4 else "scout")
            elif "barracks" in kinds:
                if "factory" in kinds and roll < 0.72:
                    # 工厂开了二级科技，兵营开始出磁暴步兵专电载具
                    queue_unit(room, bot["id"], "tesla")
                else:
                    # 基础混编：火箭兵为主，掺突击兵，偶尔放条军犬（便宜、咬步兵、能侦察）
                    queue_unit(room, bot["id"],
                               "rocket" if roll < 0.80 else ("rifle" if roll < 0.93 else "dog"))
        except ValueError:
            pass

        repair_bays = [
            structure for structure in own_structures
            if structure["kind"] == "repair" and structure["active"]
        ]
        damaged = [
            unit for unit in game["units"]
            if unit["owner"] == bot["id"] and unit["kind"] in VEHICLE_KINDS
            and unit["hp"] > 0 and unit["hp"] / unit["maxHp"] < 0.62
            and unit.get("order") != "repair"
        ]
        if repair_bays and damaged:
            try:
                issue_repair(
                    game, bot["id"], set(unit["id"] for unit in damaged[:12]),
                    repair_bays[0]["id"])
            except ValueError:
                pass

        combat = [
            unit for unit in game["units"]
            if unit["owner"] == bot["id"] and unit["kind"] != "harvester"
            and unit["hp"] > 0 and unit.get("order") != "repair"
            and unit["hp"] / unit["maxHp"] >= 0.45
        ]
        enemies = [s for s in game["structures"] if not is_friendly(game, s["owner"], bot["id"]) and s["kind"] == "hq" and s["hp"] > 0]
        if len(combat) >= 5 and enemies and random.random() < 0.48:
            target = min(enemies, key=lambda s: math.hypot(s["x"] - combat[0]["x"], s["y"] - combat[0]["y"]))
            issue_attack(game, bot["id"], set(u["id"] for u in combat), target["id"])


def remove_destroyed(room):
    """把刚阵亡的单位/建筑移出列表并补大爆炸特效，每 tick 都跑。

    过去清理跟胜负判定一起按 0.45s 节奏走，于是阵亡单位会以 hp=0 在原地继续
    留在快照里近半秒，爆炸火球也要等清理周期到了才出现。死亡反馈本该即时；
    没东西死时两个列表推导直接早退，开销可忽略。
    """
    game = room["game"]
    destroyed_units = [u for u in game["units"] if u["hp"] <= 0]
    destroyed_structures = [s for s in game["structures"] if s["hp"] <= 0]
    if not destroyed_units and not destroyed_structures:
        return
    for entity in destroyed_units + destroyed_structures:
        game["effects"].append({
            "id": new_id("e"), "type": "explosion", "x": entity["x"], "y": entity["y"],
            "ttl": 1.15 if entity in destroyed_structures else 0.75,
        })
    game["units"] = [u for u in game["units"] if u["hp"] > 0]
    game["structures"] = [s for s in game["structures"] if s["hp"] > 0]


def check_elimination_and_victory(room):
    """淘汰与胜负判定。仍按 victoryClock 的 0.45s 节奏跑，不需要 20Hz 的精度。"""
    game = room["game"]
    for player in room["players"].values():
        if player["eliminated"]:
            continue
        has_structure = any(s["owner"] == player["id"] for s in game["structures"])
        if not has_structure:
            player["eliminated"] = True
            game["units"] = [u for u in game["units"] if u["owner"] != player["id"]]
            add_chat(room, "作战系统", "%s 的所有建筑已被摧毁，彻底战败。" % player["name"], True)

    alive = [p for p in room["players"].values() if not p["eliminated"]]
    if game["elapsed"] > 15 and len(alive) <= 1:
        winner = alive[0] if alive else None
        game["winnerId"] = winner["id"] if winner else None
        room["status"] = "finished"
        add_chat(room, "作战系统", "%s 赢得了本局战斗！" % (winner["name"] if winner else "无人"), True)
    elif game["elapsed"] > 15:
        surviving_teams = set()
        for p in alive:
            t = p.get("team", 0)
            surviving_teams.add(t if t > 0 else p["id"])
        if len(surviving_teams) <= 1:
            winner = alive[0]
            game["winnerId"] = winner["id"]
            room["status"] = "finished"
            team_winners = [p["name"] for p in alive]
            add_chat(room, "作战系统", "队伍 %s 赢得了本局战斗！" % ("、".join(team_winners)), True)


def remove_destroyed_and_check(room):
    """清理 + 判定合并入口（保留给直接调用它的旧代码与测试）。"""
    remove_destroyed(room)
    check_elimination_and_victory(room)


def spawn_crates(game, terrain, dt):
    """每 60 秒在随机可通行位置生成一个补给箱。"""
    if game["elapsed"] < 18:
        return
    next_at = game.get("nextCrateAt")
    if next_at is None:
        game["nextCrateAt"] = game["elapsed"] + 60
        return
    if game["elapsed"] < next_at:
        return
    # 最多同时存在 3 个箱子
    if len(game.get("crates", [])) >= 3:
        game["nextCrateAt"] = game["elapsed"] + 60
        return
    mw = game["map"]["width"]
    mh = game["map"]["height"]
    for _ in range(30):
        x = random.uniform(200, mw - 200)
        y = random.uniform(200, mh - 200)
        if terrain.blocked(x, y):
            continue
        # 不放建筑物上
        too_close = False
        for s in game["structures"]:
            if math.hypot(s["x"] - x, s["y"] - y) < s["size"] + 50:
                too_close = True
                break
        if too_close:
            continue
        kind = random.choice(list(CRATE_TYPES.keys()))
        game.setdefault("crates", []).append({
            "id": new_id("cr"), "x": round(x, 1), "y": round(y, 1),
            "kind": kind, "ttl": 90.0,
        })
        break
    game["nextCrateAt"] = game["elapsed"] + 60


def tick_crates(room, dt):
    game = room["game"]
    crates = game.get("crates", [])
    if not crates:
        return
    terrain = game_terrain(game)
    live = []
    for crate in crates:
        crate["ttl"] -= dt
        if crate["ttl"] <= 0:
            continue
        picked = False
        for unit in game["units"]:
            if unit["hp"] <= 0 or unit["owner"] not in room["players"]:
                continue
            if math.hypot(unit["x"] - crate["x"], unit["y"] - crate["y"]) < 35:
                apply_crate(room, unit["owner"], crate)
                game["effects"].append({
                    "id": new_id("e"), "type": "complete",
                    "x": crate["x"], "y": crate["y"], "ttl": 0.8,
                })
                picked = True
                break
        if not picked:
            live.append(crate)
    game["crates"] = live


def apply_crate(room, player_id, crate):
    game = room["game"]
    player = room["players"].get(player_id)
    if not player:
        return
    kind = crate["kind"]
    if kind == "cash":
        player["cash"] += 1500
        add_chat(room, "补给系统", "%s 拾取了资金补给 +1500" % player["name"], True)
    elif kind == "heal":
        healed = 0
        for unit in game["units"]:
            if unit["owner"] == player_id and unit["hp"] > 0:
                amount = unit["maxHp"] * 0.30
                if unit["hp"] + amount > unit["maxHp"]:
                    amount = unit["maxHp"] - unit["hp"]
                unit["hp"] += amount
                healed += amount
        add_chat(room, "补给系统",
            "%s 拾取了战地医疗，回复 %.0f 生命" % (player["name"], healed), True)
    elif kind == "strike":
        before = player.get("strikeCharges", 0)
        player["strikeCharges"] = min(STRIKE_MAX_CHARGES, before + 1)
        if player["strikeCharges"] > before:
            add_chat(room, "补给系统",
                     "%s 拾取了超级武器充能（瞄准后释放）" % player["name"], True)
        else:
            # 已满充能：折算成资金，免得白捡
            player["cash"] += 800
            add_chat(room, "补给系统",
                     "%s 超级武器已满，转为资金 +800" % player["name"], True)


def tick_pending_strikes(room, dt, combat_spatial=None):
    """推进轨道打击：到点的弹着依次结算范围伤害 + 爆炸特效，全部走完即移除。"""
    game = room["game"]
    strikes = game.get("pendingStrikes")
    if not strikes:
        return
    now_e = game["elapsed"]
    # 复用 tick_game 在 tick_projectiles 前建好的索引，不再每 tick 第三次重建。
    # 两者之间没有实体移动，坐标仍然准确；被炮弹打死的实体下面按 hp<=0 跳过。
    if combat_spatial is None:
        _entity_index, combat_spatial = build_combat_indexes(game)
    for strike in strikes:
        impacts = strike["impacts"]
        idx = strike["fired"]
        while idx < len(impacts) and now_e >= impacts[idx]["fireAt"]:
            imp = impacts[idx]
            ix, iy = imp["x"], imp["y"]
            # 友伤：不判阵营，圈内谁都炸
            for entity in spatial_candidates(combat_spatial, ix, iy, STRIKE_SPLASH):
                if entity.get("hp", 0) <= 0:
                    continue
                if math.hypot(entity["x"] - ix, entity["y"] - iy) <= STRIKE_SPLASH:
                    apply_damage(room, entity, STRIKE_DAMAGE, strike["owner"],
                                 "super", game)
            game["effects"].append({
                "id": new_id("e"), "type": "explosion", "x": ix, "y": iy,
                "ttl": 0.9,
            })
            idx += 1
        strike["fired"] = idx
    game["pendingStrikes"] = [s for s in strikes if s["fired"] < len(s["impacts"])]


def tick_game(room, dt):
    if room["status"] != "playing" or not room.get("game"):
        return
    game = room["game"]
    game["elapsed"] += dt
    terrain = game_terrain(game)
    # 采矿结算前先刷新守军存活状态，保证最后一名守卫阵亡后的下一帧即解锁。
    refresh_neutral_camps(game)
    spawn_crates(game, terrain, dt)
    tick_crates(room, dt)
    entity_index, combat_spatial = build_combat_indexes(game)
    tick_units(room, dt, entity_index, combat_spatial)
    tick_build_queues(room, dt)
    tick_structures(room, dt, combat_spatial)
    entity_index, combat_spatial = build_combat_indexes(game)
    tick_projectiles(room, dt, entity_index, combat_spatial)
    tick_pending_strikes(room, dt, combat_spatial)

    for effect in game["effects"]:
        effect["ttl"] -= dt
    game["effects"] = [effect for effect in game["effects"] if effect["ttl"] > 0]
    for ping in game["pings"]:
        ping["ttl"] -= dt
    game["pings"] = [ping for ping in game["pings"] if ping["ttl"] > 0]

    game["botClock"] -= dt
    if game["botClock"] <= 0:
        tick_bots(room)
        game["botClock"] = 2.25

    # 每 tick 及时清掉尸体，让爆炸在倒下那一瞬就出现；淘汰/胜负判定仍按
    # 0.45s 的节奏走，不需要逐 tick 的精度。
    remove_destroyed(room)
    game["victoryClock"] -= dt
    if game["victoryClock"] <= 0:
        check_elimination_and_victory(room)
        game["victoryClock"] = 0.45

    # Expire alliance proposals after 45 seconds
    proposals = room.get("allianceProposals")
    if proposals:
        cutoff = now() - 45
        expired = [tid for tid, p in list(proposals.items()) if p["time"] < cutoff]
        for tid in expired:
            proposals.pop(tid, None)
    # 网络层按这一版本共享实体序列化和同队视野结果；所有玩法更新结束后一次
    # 失效即可，避免六条 SSE 连接重复转换同一批单位。
    invalidate_game_snapshot(game)


def game_loop():
    global RUNNING
    previous = time.time()
    cleanup_clock = 0.0
    while RUNNING:
        current = time.time()
        dt = min(0.12, max(0.001, current - previous))
        previous = current
        with LOCK:
            for room in list(ROOMS.values()):
                tick_game(room, dt)
            cleanup_clock += dt
            if cleanup_clock > 30:
                cleanup_clock = 0
                cutoff = now() - 60 * 60 * 3
                stale = []
                for room_id, room in ROOMS.items():
                    humans = [p for p in room["players"].values() if not p["isBot"]]
                    newest = max([p.get("lastSeen", room["createdAt"]) for p in humans] or [room["createdAt"]])
                    if not humans or (room["status"] == "finished" and newest < cutoff):
                        stale.append(room_id)
                for room_id in stale:
                    ROOMS.pop(room_id, None)
        elapsed = time.time() - current
        time.sleep(max(0.005, 0.05 - elapsed))


def static_entry(target):
    """读静态文件并按 (mtime, size) 缓存进内存，返回 (content, content_type, last_modified)。

    过去每次请求都从磁盘重读整份文件 —— terrain-ground.png 有 3.5MB，多名玩家
    同时开局就是几次整读。改成只在文件真的变了（mtime 或大小不同）时才重读；
    os.stat 本身只是一次廉价系统调用，不读文件内容，开发时改完文件也能立即生效。
    """
    try:
        stat = os.stat(target)
    except OSError:
        return None
    key = (stat.st_mtime, stat.st_size)
    with _STATIC_LOCK:
        cached = _STATIC_CACHE.get(target)
        if cached is not None and cached[0] == key:
            return cached[1]
        try:
            with open(target, "rb") as handle:
                content = handle.read()
        except OSError:
            return None
        content_type = mimetypes.guess_type(target)[0] or "application/octet-stream"
        if target.endswith(".js"):
            content_type = "application/javascript"
        entry = (content, content_type, formatdate(stat.st_mtime, usegmt=True))
        _STATIC_CACHE[target] = (key, entry)
        return entry


class ThreadedHTTPServer(socketserver.ThreadingMixIn, HTTPServer):
    daemon_threads = True
    allow_reuse_address = True


class GameHandler(BaseHTTPRequestHandler):
    server_version = "SteelFrontLAN/%s" % VERSION
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):
        sys.stdout.write("[%s] %s\n" % (time.strftime("%H:%M:%S"), fmt % args))
        sys.stdout.flush()

    def send_json(self, status, payload):
        encoded = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(encoded)

    def read_json(self):
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            length = 0
        if length <= 0 or length > 65536:
            return {}
        raw = self.rfile.read(length)
        try:
            value = json.loads(raw.decode("utf-8"))
            return value if isinstance(value, dict) else {}
        except (ValueError, UnicodeDecodeError):
            raise ValueError("请求格式无效")

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Allow", "GET, POST, OPTIONS")
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        query = parse_qs(parsed.query)
        if path == "/api/health":
            with LOCK:
                payload = {"ok": True, "version": VERSION, "uptime": int(now() - STARTED_AT), "rooms": len(ROOMS), "port": PORT}
            self.send_json(200, payload)
        elif path == "/api/rooms":
            with LOCK:
                payload = {"rooms": room_list(), "serverTime": now()}
            self.send_json(200, payload)
        elif path == "/api/state":
            room_id = (query.get("roomId") or [""])[0]
            player_id = (query.get("playerId") or [""])[0]
            token = (query.get("token") or [""])[0]
            with LOCK:
                room, player = authenticate(room_id, player_id, token)
                if not room or not player:
                    self.send_json(403, {"ok": False, "error": "会话已失效"})
                    return
                payload = {"ok": True, "room": public_room(room, viewer_id=player["id"])}
            self.send_json(200, payload)
        elif path == "/api/events":
            self.handle_events(query)
        elif path == "/api/give":
            # 安全：调试/测试接口，仅服务器本机（跑 give_cash.py 的机器）可用，
            # 除非显式设了 IFL_CHEATS=1。行为：调用即给指定玩家【随机减钱】。
            if not CHEATS_OPEN and self.client_address[0] not in ("127.0.0.1", "::1", "localhost"):
                self.send_json(403, {"ok": False, "error": "刷钱接口仅服务器本机可用"})
                return
            player_name = (query.get("name") or [""])[0]
            cash_str = (query.get("cash") or ["0"])[0]
            try:
                amount = max(0.0, float(cash_str))
            except ValueError:
                self.send_json(400, {"ok": False, "error": "金额无效"})
                return
            with LOCK:
                found = False
                for room in ROOMS.values():
                    for player in room["players"].values():
                        if player["name"] == player_name:
                            # 随机减去 [0, 请求金额] 之间的一笔；现金最低减到 0，不变负
                            removed = min(player["cash"], random.uniform(0.0, amount))
                            player["cash"] -= removed
                            found = True
                            self.send_json(200, {"ok": True, "name": player_name, "removed": removed, "cash": player["cash"]})
                            break
                    if found:
                        break
                if not found:
                    self.send_json(404, {"ok": False, "error": "玩家 " + player_name + " 未找到"})
        else:
            self.serve_static(path)

    def do_POST(self):
        parsed = urlparse(self.path)
        try:
            data = self.read_json()
            if parsed.path == "/api/create":
                self.create_room(data)
            elif parsed.path == "/api/join":
                self.join_room(data)
            elif parsed.path == "/api/action":
                self.room_action(data)
            else:
                self.send_json(404, {"ok": False, "error": "接口不存在"})
        except ValueError as exc:
            self.send_json(400, {"ok": False, "error": str(exc)})
        except (BrokenPipeError, ConnectionResetError):
            pass
        except Exception as exc:
            self.log_message("Unhandled error: %r", exc)
            self.send_json(500, {"ok": False, "error": "服务器内部错误"})

    def create_room(self, data):
        with LOCK:
            room_id = new_room_code()
            player = create_human(data.get("playerName"), COLORS[0])
            selected_map = data.get("mapId", DEFAULT_MAP)
            if selected_map not in MAPS:
                selected_map = DEFAULT_MAP
            room = {
                "id": room_id,
                "name": clean_text(data.get("roomName"), 24, "%s 的战场" % player["name"]),
                "status": "lobby", "hostId": player["id"],
                "players": {player["id"]: player}, "chat": [], "game": None,
                "createdAt": now(),
                "selectedMap": selected_map,
            }
            ROOMS[room_id] = room
            add_chat(room, "作战系统", "%s 创建了房间。" % player["name"], True)
            payload = {"ok": True, "session": {"roomId": room_id, "playerId": player["id"], "token": player["token"]}, "room": public_room(room, viewer_id=player["id"])}
        self.send_json(201, payload)

    def join_room(self, data):
        room_id = str(data.get("roomId", "")).strip().upper()
        with LOCK:
            room = ROOMS.get(room_id)
            if not room:
                raise ValueError("房间不存在")
            if room["status"] != "lobby":
                raise ValueError("该房间已开始战斗")
            room_map = MAPS.get(room.get("selectedMap", DEFAULT_MAP), MAPS[DEFAULT_MAP])
            if len(room["players"]) >= room_map["maxPlayers"]:
                raise ValueError("房间已满")
            used_colors = set(p["color"] for p in room["players"].values())
            color = next((item for item in COLORS if item not in used_colors), COLORS[len(room["players"])])
            player = create_human(data.get("playerName"), color)
            room["players"][player["id"]] = player
            add_chat(room, "作战系统", "%s 加入了房间。" % player["name"], True)
            payload = {"ok": True, "session": {"roomId": room_id, "playerId": player["id"], "token": player["token"]}, "room": public_room(room, viewer_id=player["id"])}
        self.send_json(200, payload)

    def room_action(self, data):
        action = data.get("action")
        payload = data.get("payload") if isinstance(data.get("payload"), dict) else {}
        with LOCK:
            room, player = authenticate(data.get("roomId"), data.get("playerId"), data.get("token"))
            if not room or not player:
                self.send_json(403, {"ok": False, "error": "会话已失效"})
                return
            if action == "ready":
                if room["status"] != "lobby":
                    raise ValueError("战斗已经开始")
                player["ready"] = bool(payload.get("ready"))
            elif action == "selectMap":
                if room["hostId"] != player["id"] or room["status"] != "lobby":
                    raise ValueError("只有房主可以选择地图")
                map_id = payload.get("mapId", DEFAULT_MAP)
                if map_id not in MAPS:
                    raise ValueError("地图不存在")
                if room["selectedMap"] != map_id:
                    max_players = MAPS[map_id]["maxPlayers"]
                    if len(room["players"]) > max_players:
                        raise ValueError("当前玩家数超过该地图上限")
                    room["selectedMap"] = map_id
                    for p in room["players"].values():
                        p["spawn"] = -1
                    add_chat(room, "作战系统", "地图已切换为「%s」。" % MAPS[map_id]["name"], True)
            elif action == "addBot":
                if room["hostId"] != player["id"] or room["status"] != "lobby":
                    raise ValueError("只有房主可以添加 AI")
                room_map = MAPS.get(room.get("selectedMap", DEFAULT_MAP), MAPS[DEFAULT_MAP])
                if len(room["players"]) >= room_map["maxPlayers"]:
                    raise ValueError("房间已满")
                bot = create_bot(room)
                add_chat(room, "作战系统", "%s AI 已加入。" % bot["name"], True)
            elif action == "removeBot":
                if room["hostId"] != player["id"] or room["status"] != "lobby":
                    raise ValueError("只有房主可以移除 AI")
                bot = room["players"].get(payload.get("botId"))
                if not bot or not bot["isBot"]:
                    raise ValueError("AI 不存在")
                room["players"].pop(bot["id"], None)
            elif action == "setTeam":
                if room["hostId"] != player["id"] or room["status"] != "lobby":
                    raise ValueError("只有房主可以设置队伍")
                target_id = payload.get("playerId")
                target = room["players"].get(target_id)
                if not target:
                    raise ValueError("玩家不存在")
                target["team"] = int(payload.get("team", 0))
            elif action == "setSpawn":
                if room["hostId"] != player["id"] or room["status"] != "lobby":
                    raise ValueError("只有房主可以设置出生地")
                target_id = payload.get("playerId")
                target = room["players"].get(target_id)
                if not target:
                    raise ValueError("玩家不存在")
                sp = int(payload.get("spawn", -1))
                if sp >= 0:
                    max_spawns = len(MAPS.get(room.get("selectedMap", DEFAULT_MAP), MAPS[DEFAULT_MAP])["spawnPoints"])
                    if sp >= max_spawns:
                        raise ValueError("无效的出生地")
                target["spawn"] = sp
            elif action == "start":
                if room["hostId"] != player["id"]:
                    raise ValueError("只有房主可以开始")
                if room["status"] != "lobby":
                    raise ValueError("战斗已经开始")
                guests = [p for p in room["players"].values() if not p["isBot"] and p["id"] != player["id"]]
                if any(not p["ready"] for p in guests):
                    raise ValueError("仍有玩家未准备")
                start_game(room)
            elif action == "chat":
                message = clean_text(payload.get("message"), 100, "")
                if not message:
                    raise ValueError("消息不能为空")
                add_chat(room, player["name"], message)
            elif action == "command":
                handle_game_command(room, player, payload)
            elif action == "proposeAlliance":
                if room["status"] != "playing":
                    raise ValueError("只能在战斗中进行")
                if player.get("eliminated"):
                    raise ValueError("你已被击败")
                target_id = payload.get("playerId")
                target = room.get("players", {}).get(target_id)
                if not target or target["isBot"] or target.get("eliminated"):
                    raise ValueError("无效的结盟目标")
                if is_friendly(room.get("game", {}), player["id"], target["id"]):
                    raise ValueError("已经处于同一队伍")
                room.setdefault("allianceProposals", {})
                room["allianceProposals"][target["id"]] = {"from": player["id"], "time": now()}
                add_chat(room, "作战系统", "%s 向 %s 发起了结盟提议。" % (player["name"], target["name"]), True)
            elif action == "acceptAlliance":
                if room["status"] != "playing":
                    raise ValueError("只能在战斗中进行")
                proposals = room.get("allianceProposals", {})
                proposal = proposals.get(player["id"])
                if not proposal:
                    raise ValueError("没有待处理的结盟提议")
                proposer = room["players"].get(proposal["from"])
                if not proposer or proposer.get("eliminated"):
                    proposals.pop(player["id"], None)
                    raise ValueError("提议者已不可用")
                team_id = proposer.get("team", 0)
                if team_id <= 0:
                    team_id = max((p.get("team", 0) for p in room["players"].values()), default=0) + 1
                    proposer["team"] = team_id
                player["team"] = team_id
                if room.get("game"):
                    room["game"]["playerTeams"] = {p["id"]: p.get("team", 0) for p in room["players"].values()}
                proposals.pop(player["id"], None)
                add_chat(room, "作战系统", "%s 接受了 %s 的结盟，共同作战！" % (player["name"], proposer["name"]), True)
            elif action == "rejectAlliance":
                proposals = room.get("allianceProposals", {})
                proposal = proposals.pop(player["id"], None)
                if not proposal:
                    raise ValueError("没有待处理的结盟提议")
                proposer = room["players"].get(proposal["from"])
                if proposer:
                    add_chat(room, "作战系统", "%s 拒绝了 %s 的结盟提议。" % (player["name"], proposer["name"]), True)
            elif action == "breakAlliance":
                if room["status"] != "playing":
                    raise ValueError("只能在战斗中进行")
                if player.get("eliminated"):
                    raise ValueError("你已被击败")
                if not player.get("team") or player["team"] <= 0:
                    raise ValueError("你没有加入任何队伍")
                player["team"] = 0
                if room.get("game"):
                    room["game"]["playerTeams"] = {p["id"]: p.get("team", 0) for p in room["players"].values()}
                add_chat(room, "作战系统", "%s 退出了当前队伍。" % player["name"], True)
            elif action == "leave":
                name = player["name"]
                if room["status"] == "lobby":
                    room["players"].pop(player["id"], None)
                    add_chat(room, "作战系统", "%s 离开了房间。" % name, True)
                    if not any(not p["isBot"] for p in room["players"].values()):
                        ROOMS.pop(room["id"], None)
                    elif room["hostId"] == player["id"]:
                        room["hostId"] = next(p["id"] for p in room["players"].values() if not p["isBot"])
                else:
                    player["connections"] = 0
                    player["lastSeen"] = 0
                self.send_json(200, {"ok": True})
                return
            else:
                raise ValueError("未知操作")
            # 指令可能在两个模拟 tick 之间直接改变建筑/队列；REST 响应必须看到
            # 新状态，不能复用刚才 SSE 建出的旧快照。
            invalidate_game_snapshot(room.get("game"))
            # 战斗中的指令响应只回动态数据。地图、地形、矿点布局、视距表一局
            # 之内不变，客户端在首帧就缓存好了；过去每条移动指令都附一份 full
            # 快照，客户端收到后会把整个 3D 世界推倒重建 —— 两万顶点的地形
            # 网格、近三千株草木、两张迷雾画布、全部道路与矿脉，点一下卡一下。
            in_battle = action == "command" and room["status"] == "playing"
            response = {"ok": True, "room": public_room(
                room, viewer_id=player["id"], full=not in_battle)}
        self.send_json(200, response)

    def handle_events(self, query):
        room_id = (query.get("roomId") or [""])[0]
        player_id = (query.get("playerId") or [""])[0]
        token = (query.get("token") or [""])[0]
        with LOCK:
            room, player = authenticate(room_id, player_id, token)
            if not room or not player:
                self.send_json(403, {"ok": False, "error": "会话已失效"})
                return
            player["connections"] += 1
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-cache, no-transform")
        self.send_header("Connection", "keep-alive")
        self.send_header("X-Accel-Buffering", "no")
        self.end_headers()
        try:
            # The first frame of a stream carries the match's static data
            # (map, terrain, ore layout, map catalogue); later frames omit it
            # and the client keeps its cached copy. A reconnect starts a new
            # stream, so it always gets a fresh full frame.
            first_frame = True
            full_game_uid = None
            while RUNNING:
                with LOCK:
                    room, player = authenticate(room_id, player_id, token)
                    if not room or not player:
                        break
                    game = room.get("game")
                    game_uid = game.get("uid") if game else None
                    # A stream opened in the lobby must send the static block
                    # again once the match actually starts.
                    full = first_frame or (game_uid is not None
                                           and game_uid != full_game_uid)
                    snapshot = public_room(room, viewer_id=player["id"], full=full)
                    status = room["status"]
                # Encoding stays outside the lock so it never blocks the sim.
                payload = json.dumps(snapshot, ensure_ascii=False, separators=(",", ":"))
                message = ("event: state\ndata: %s\n\n" % payload).encode("utf-8")
                self.wfile.write(message)
                self.wfile.flush()
                first_frame = False
                if full and game_uid is not None:
                    full_game_uid = game_uid
                time.sleep(0.125 if status == "playing" else 0.45)
        except (BrokenPipeError, ConnectionResetError, OSError):
            pass
        finally:
            with LOCK:
                room = ROOMS.get(str(room_id).upper())
                if room and player_id in room["players"]:
                    room["players"][player_id]["connections"] = max(0, room["players"][player_id]["connections"] - 1)

    def serve_static(self, path):
        if path == "/":
            path = "/index.html"
        relative = os.path.normpath(path.lstrip("/")).replace("\\", "/")
        if relative.startswith("../") or relative == "..":
            self.send_json(403, {"ok": False, "error": "禁止访问"})
            return
        target = os.path.abspath(os.path.join(PUBLIC_ROOT, relative))
        if not target.startswith(os.path.abspath(PUBLIC_ROOT) + os.sep) or not os.path.isfile(target):
            self.send_json(404, {"ok": False, "error": "页面不存在"})
            return
        entry = static_entry(target)
        if entry is None:
            self.send_json(404, {"ok": False, "error": "页面不存在"})
            return
        content, content_type, last_modified = entry
        # 浏览器持有的副本仍新鲜就直接 304，整张贴图不必再发一遍
        if self.headers.get("If-Modified-Since") == last_modified:
            self.send_response(304)
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Last-Modified", last_modified)
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            return
        self.send_response(200)
        self.send_header("Content-Type", content_type + ("; charset=utf-8" if content_type.startswith("text/") or "javascript" in content_type else ""))
        self.send_header("Content-Length", str(len(content)))
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Last-Modified", last_modified)
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(content)


def shutdown_handler(_signum, _frame):
    global RUNNING
    RUNNING = False


def lan_address():
    """本机局域网地址，优先 10.18 网段，供其他玩家连接。"""
    try:
        hostname = socket.gethostname()
        ips = socket.gethostbyname_ex(hostname)[2]
        # 10.18 最优先
        for ip in ips:
            if ip.startswith("10.18."):
                return ip
        # 其它 10.x 段次之
        for ip in ips:
            if ip.startswith("10."):
                return ip
    except OSError:
        pass
    # 回退：UDP 探测 10.x 方向路由（不发送数据，只读本地出口地址）
    probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        probe.settimeout(0.2)
        probe.connect(("10.255.255.255", 1))
        return probe.getsockname()[0]
    except OSError:
        return None
    finally:
        probe.close()


def explain_bind_failure(exc, host, port):
    """把 bind 失败翻译成能直接照做的排查步骤。

    Windows 上装了 WSL2 / Hyper-V / Docker 之后，系统会在开机时预留大段动态
    TCP 端口。如果监听端口正好落在里面，bind 会返回 WinError 10013（权限不允
    许），而不是常见的 10048（端口已被占用）—— 两者的处理办法完全不同，所以
    这里分开说明。
    """
    winerror = getattr(exc, "winerror", None)
    print("")
    print("!" * 58)
    print("  无法监听 %s:%d" % (host, port))
    print("  %s" % exc)
    print("!" * 58)

    if winerror == 10013:
        print("")
        print("  这是 Windows 的端口预留，不是端口被别的程序占用。")
        print("  装了 WSL2 / Hyper-V / Docker 后，系统会预留大段动态端口。")
        print("")
        print("  1) 确认 %d 是否落在预留范围内（普通 cmd 即可）：" % port)
        print("       netsh int ipv4 show excludedportrange protocol=tcp")
        print("")
        print("  2) 换一个端口先玩起来：")
        print("       set PORT=8090 && python server.py")
        print("")
        print("  3) 想继续用 %d，用管理员 cmd 把它固定预留给自己：" % port)
        print("       net stop winnat")
        print("       netsh int ipv4 add excludedportrange protocol=tcp"
              " startport=%d numberofports=1" % port)
        print("       net start winnat")
        print("     （改端口后记得同步更新防火墙规则和其他玩家的地址）")
    elif winerror == 10048 or getattr(exc, "errno", None) in (48, 98):
        print("")
        print("  端口已被占用，多半是上一个服务器窗口还开着。")
        print("  关掉它，或者换端口：set PORT=8090 && python server.py")
        print("")
        print("  查是谁占着（cmd）：  netstat -ano | findstr :%d" % port)
    else:
        print("")
        print("  换个端口试试：set PORT=8090 && python server.py")
    print("")


def main():
    global RUNNING
    signal.signal(signal.SIGINT, shutdown_handler)
    if hasattr(signal, "SIGTERM"):
        signal.signal(signal.SIGTERM, shutdown_handler)
    try:
        server = ThreadedHTTPServer((HOST, PORT), GameHandler)
    except OSError as exc:
        explain_bind_failure(exc, HOST, PORT)
        return 1
    # 端口绑定成功后再开模拟线程，避免失败退出时留下后台线程
    loop_thread = threading.Thread(target=game_loop, name="game-loop")
    loop_thread.daemon = True
    loop_thread.start()
    server.timeout = 0.5
    print("=" * 58)
    print("  赤潮：钢铁前线 LAN 服务器 v%s" % VERSION)
    print("  本机访问:   http://127.0.0.1:%d" % PORT)
    lan_ip = lan_address()
    if lan_ip:
        print("  局域网地址: http://%s:%d   <- 发这个给队友" % (lan_ip, PORT))
    else:
        print("  监听地址:   %s:%d（未能探测到局域网 IP）" % (HOST, PORT))
    print("  按 Ctrl+C 停止")
    print("=" * 58)
    try:
        while RUNNING:
            server.handle_request()
    finally:
        RUNNING = False
        server.server_close()
        print("服务器已停止。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
