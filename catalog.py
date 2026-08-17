#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Unit, structure, and faction tables for Steel Front LAN.

server.py re-exports these names so existing tests and imports keep working.
"""

from __future__ import print_function


# 可进维修厂/圣泉的单位。步兵、法师、影豹不算；构装、巨龙、晶簇与科技载具对位。
VEHICLE_KINDS = frozenset((
    "tank", "scout", "harvester", "artillery", "tank_destroyer", "mcv",
    "v3", "overlord", "prism",
    "golem", "dragon", "mharvester", "mmcv",
))

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
        "canDeploy": True, "deploysInto": "hq",
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
    # ==================== 魔法阵营「秘法会」（faction=magic） ====================
    # 独立经济：自己的主堡/法力塔/精炼所/采矿/基地车，数值与科技对位、只换皮换名。
    "mharvester": {
        "name": "浮游晶簇", "cost": 920, "hp": 680, "speed": 63.6,
        "damage": 0.0, "range": 0.0, "cooldown": 0.0,
        "size": 22.0, "build": 9.0, "producer": "mcircle",
        "projectile": "none", "projectileSpeed": 0.0, "splash": 0.0,
        "capacity": 850.0, "harvestRate": 145.0, "sight": 330.0,
        "armor": "light", "damageType": "none",
    },
    "mmcv": {
        "name": "迁徙法阵", "cost": 2500, "hp": 900, "speed": 45.6,
        "damage": 0.0, "range": 0.0, "cooldown": 0.0,
        "size": 24.0, "build": 14.0, "producer": "mcircle",
        "projectile": "none", "projectileSpeed": 0.0, "splash": 0.0,
        "sight": 320.0, "armor": "light", "damageType": "none",
        "canDeploy": True, "deploysInto": "mhq",
    },
    # ---- 军事：奥术圣殿(步兵) / 召唤法阵(构装与魔兽) ----
    # 奥术法师：远程魔法弹，熔重甲的反坦克答案；魔导甲怕磁暴/狙击/子弹。
    "mage": {
        "name": "奥术法师", "cost": 500, "hp": 90, "speed": 78.0,
        "damage": 42.0, "range": 220.0, "cooldown": 1.1,
        "size": 10.0, "build": 5.0, "producer": "mtemple",
        "projectile": "arcane", "projectileSpeed": 800.0, "splash": 0.0,
        "sight": 410.0, "armor": "arcane", "damageType": "magic",
    },
    # 冰霜女巫：伤害低但命中挂减速，是魔法阵营的控制/拉扯核心。
    "frost": {
        "name": "冰霜女巫", "cost": 550, "hp": 85, "speed": 74.0,
        "damage": 16.0, "range": 205.0, "cooldown": 1.3,
        "size": 10.0, "build": 6.0, "producer": "mtemple",
        "projectile": "frost", "projectileSpeed": 700.0, "splash": 40.0,
        "sight": 420.0, "armor": "arcane", "damageType": "magic",
        "slow": {"mult": 0.45, "duration": 2.5},
    },
    # 岩石傀儡：构装前排，高血慢速，投掷巨石溅射，踩步兵/轻型。
    "golem": {
        "name": "岩石傀儡", "cost": 850, "hp": 760, "speed": 52.0,
        "damage": 52.0, "range": 130.0, "cooldown": 1.2,
        "size": 20.0, "build": 9.0, "producer": "mcircle",
        "projectile": "boulder", "projectileSpeed": 420.0, "splash": 34.0,
        "sight": 360.0, "armor": "arcane", "damageType": "magic",
    },
    # 影豹：全场最快的魔法兽，近战扑击(爪击瞬发)，侧翼包抄/切后排。
    "panther": {
        "name": "影豹", "cost": 420, "hp": 180, "speed": 132.0,
        "damage": 26.0, "range": 34.0, "cooldown": 0.7,
        "size": 12.0, "build": 5.0, "producer": "mcircle",
        "projectile": "claw", "projectileSpeed": 1000.0, "splash": 0.0,
        "sight": 520.0, "armor": "arcane", "damageType": "magic",
    },
    # 秘法巨龙：魔法阵营的重炮，远程大火球大溅射，压轴质量兵种。
    "dragon": {
        "name": "秘法巨龙", "cost": 1600, "hp": 900, "speed": 60.0,
        "damage": 95.0, "range": 260.0, "cooldown": 1.7,
        "size": 24.0, "build": 15.0, "producer": "mcircle",
        "projectile": "fireball", "projectileSpeed": 520.0, "splash": 60.0,
        "sight": 460.0, "armor": "arcane", "damageType": "magic",
    },
}

STRUCTURE_TYPES = {
    "hq": {
        "name": "指挥中心", "cost": 0, "hp": 2400, "size": 58.0,
        "build": 0.0, "deploy": 0.0, "power": 35, "requires": [], "sight": 650.0,
        "armor": "structure", "packsInto": "mcv",
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
    # ==================== 魔法阵营「秘法会」建筑（faction=magic） ====================
    # 与科技对位：主堡=hq / 法力塔=power / 精炼所=refinery / 圣殿=barracks /
    # 法阵=factory / 圣泉=repair / 奥术塔=defense。role 字段让经济与维修逻辑跨阵营复用。
    "mhq": {
        "name": "魔法主堡", "cost": 0, "hp": 2400, "size": 58.0,
        "build": 0.0, "deploy": 0.0, "power": 35, "requires": [], "sight": 650.0,
        "armor": "structure", "packsInto": "mmcv",
    },
    "mpower": {
        "name": "法力塔", "cost": 600, "hp": 760, "size": 40.0,
        "build": 8.0, "deploy": 2.2, "power": 120, "requires": ["mhq"], "sight": 350.0,
        "armor": "structure",
    },
    "mrefinery": {
        "name": "水晶精炼所", "cost": 1400, "hp": 1350, "size": 52.0,
        "build": 14.0, "deploy": 3.2, "power": -30, "requires": ["mhq"], "sight": 390.0,
        "armor": "structure",
    },
    "mtemple": {
        "name": "奥术圣殿", "cost": 700, "hp": 900, "size": 42.0,
        "build": 10.0, "deploy": 2.8, "power": -20, "requires": ["mpower"], "sight": 410.0,
        "armor": "structure",
    },
    "mcircle": {
        "name": "召唤法阵", "cost": 1600, "hp": 1600, "size": 58.0,
        "build": 18.0, "deploy": 4.2, "power": -45, "requires": ["mrefinery", "mpower"], "sight": 460.0,
        "armor": "structure",
    },
    "mspring": {
        "name": "圣泉", "cost": 1250, "hp": 1280, "size": 50.0,
        "build": 15.0, "deploy": 3.6, "power": -35,
        "requires": ["mcircle", "mpower"], "sight": 440.0,
        "armor": "structure",
    },
    "mtower": {
        "name": "奥术塔", "cost": 950, "hp": 1300, "size": 30.0,
        "build": 12.0, "deploy": 3.0, "power": -25, "requires": ["mpower"], "sight": 560.0,
        "damage": 55.0, "range": 300.0, "cooldown": 0.9,
        "projectile": "arcane", "projectileSpeed": 700.0, "splash": 30.0,
        "armor": "structure", "damageType": "magic",
    },
}

# ---- 阵营与角色分类 ----
# faction：tech(钢铁军团) / magic(秘法会)，建造与生产按 player["faction"] 校验。
# role：跨阵营的功能角色。经济逻辑（出生配置、采矿返回、精炼厂赠车、基地车
# 展开、出售保护、bot 寻目标）一律按 role 判定而不是写死 kind —— 魔法阵营出
# 同 role 的换皮建筑即可整套复用。新增兵种/建筑 = 加定义 + 在下面登记 role。
MAGIC_STRUCTURES = frozenset((
    "mhq", "mpower", "mrefinery", "mtemple", "mcircle", "mspring", "mtower",
))
MAGIC_UNITS = frozenset(("mharvester", "mmcv", "mage", "frost", "golem", "panther", "dragon"))

_STRUCTURE_ROLES = {
    "hq": "hq", "mhq": "hq",
    "power": "power", "mpower": "power",
    "refinery": "refinery", "mrefinery": "refinery",
    "barracks": "barracks", "mtemple": "barracks",
    "factory": "factory", "mcircle": "factory",
    "repair": "repair", "mspring": "repair",
    "turret": "defense", "missile": "defense", "mtower": "defense",
}
_UNIT_ROLES = {
    "harvester": "harvester", "mharvester": "harvester",
    "mcv": "mcv", "mmcv": "mcv",
}

for _kind, _def in STRUCTURE_TYPES.items():
    _def["role"] = _STRUCTURE_ROLES.get(_kind)
    _def["faction"] = "magic" if _kind in MAGIC_STRUCTURES else "tech"
for _kind, _def in UNIT_TYPES.items():
    _def["role"] = _UNIT_ROLES.get(_kind)
    _def["faction"] = "magic" if _kind in MAGIC_UNITS else "tech"


def structure_role(kind):
    return STRUCTURE_TYPES.get(kind, {}).get("role")


def unit_role(kind):
    return UNIT_TYPES.get(kind, {}).get("role")


def public_catalog():
    """Presentation fields the client HUD needs. Python tables are the source."""
    buildings = {}
    for kind, definition in STRUCTURE_TYPES.items():
        buildings[kind] = {
            "name": definition["name"],
            "cost": int(definition["cost"]),
            "build": definition.get("build", 0),
            "size": definition.get("size", 40),
            "requires": list(definition.get("requires") or []),
            "faction": definition.get("faction", "tech"),
            "role": definition.get("role"),
        }
    units = {}
    for kind, definition in UNIT_TYPES.items():
        units[kind] = {
            "name": definition["name"],
            "cost": int(definition["cost"]),
            "build": definition.get("build", 0),
            "size": definition.get("size", 10),
            "producer": definition.get("producer"),
            "requires": list(definition.get("requires") or []),
            "faction": definition.get("faction", "tech"),
            "role": definition.get("role"),
            "canDeploy": bool(definition.get("canDeploy")),
            "damageType": definition.get("damageType"),
            "repairable": kind in VEHICLE_KINDS,
        }
    return {"buildings": buildings, "units": units}


PUBLIC_CATALOG = public_catalog()


# 各阵营的出生与经济基础 kind。start_game 出生配置、精炼厂赠车都从这里取，
# 日后要加第三个阵营只需在 UNIT/STRUCTURE 表加定义、在这里登记一行。
FACTION_LOADOUT = {
    "tech": {"hq": "hq", "power": "power", "refinery": "refinery",
             "harvester": "harvester", "mcv": "mcv", "infantry": "rifle", "armor": "tank"},
    "magic": {"hq": "mhq", "power": "mpower", "refinery": "mrefinery",
              "harvester": "mharvester", "mcv": "mmcv", "infantry": "mage", "armor": "golem"},
}


def faction_loadout(faction):
    return FACTION_LOADOUT.get(faction, FACTION_LOADOUT["tech"])


# AI 按 role 取的建造 kind（role→具体建筑）。魔法换皮复用同一套决策：
# 圣殿=兵营 / 法阵=工厂 / 圣泉=维修厂 / 奥术塔=防御塔；魔法不造导弹塔。
FACTION_BUILDINGS = {
    "tech": {"power": "power", "barracks": "barracks", "refinery": "refinery",
             "factory": "factory", "repair": "repair", "defense": "turret"},
    "magic": {"power": "mpower", "barracks": "mtemple", "refinery": "mrefinery",
              "factory": "mcircle", "repair": "mspring", "defense": "mtower"},
}


def faction_buildings(faction):
    return FACTION_BUILDINGS.get(faction, FACTION_BUILDINGS["tech"])
