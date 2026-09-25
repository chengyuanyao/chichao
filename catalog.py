#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Unit, structure, and faction tables for Steel Front LAN.

server.py re-exports these names so existing tests and imports keep working.
"""

from __future__ import print_function


# 保留每个兵种原有的基础视野；只有武器射程超过基础视野时，才把视野扩到
# 射程的 110%。这样远程单位一定看得到自己能打到的目标，近战/侦察单位也
# 不会因为短攻击距离被压成几十点视野。
UNIT_SIGHT_RANGE_MULTIPLIER = 1.10


# 军衔数值只在目录里维护一份：服务端战斗结算与客户端选中面板都读取这里。
# 回血是每秒最大生命值比例，并且只有连续脱战一段时间后才会启动。
VETERAN_REGEN_DELAY = 6.0
VETERAN_RANKS = (
    {
        "level": 0, "name": "新兵", "minKills": 0,
        "damageMultiplier": 1.0, "cooldownMultiplier": 1.0,
        "speedMultiplier": 1.0, "regenMaxHpPerSecond": 0.0,
    },
    {
        "level": 1, "name": "老兵", "minKills": 3,
        "damageMultiplier": 1.2, "cooldownMultiplier": 0.85,
        "speedMultiplier": 1.1, "regenMaxHpPerSecond": 0.0,
    },
    {
        "level": 2, "name": "精英", "minKills": 8,
        "damageMultiplier": 1.4, "cooldownMultiplier": 0.7,
        "speedMultiplier": 1.2, "regenMaxHpPerSecond": 0.0025,
    },
    {
        "level": 3, "name": "王牌", "minKills": 16,
        "damageMultiplier": 1.6, "cooldownMultiplier": 0.55,
        "speedMultiplier": 1.3, "regenMaxHpPerSecond": 0.005,
    },
)


def veteran_rank(kills):
    """Return the authoritative veterancy row for a kill count."""
    kills = max(0, int(kills or 0))
    for rank in reversed(VETERAN_RANKS):
        if kills >= rank["minKills"]:
            return rank
    return VETERAN_RANKS[0]


# 可进维修厂/圣泉的单位。步兵、法师、影豹不算；构装、巨龙、晶簇与科技载具对位。
# 晶铠卫士是轻甲反甲构装（对位磁暴），仍留在本表：圣泉可修，军犬 bite ×0。
VEHICLE_KINDS = frozenset((
    "tank", "scout", "harvester", "artillery", "tank_destroyer", "mcv",
    "v3", "overlord", "prism", "bomb_truck",
    "golem", "behemoth", "dragon", "warden", "colossus", "comet",
    "mharvester", "mmcv",
    "tharvester", "tmcv",
))

# 死亡/贴脸引爆的玻璃大炮。钢铁是轻甲载具，秘法会对位是轻甲活体（非载具）。
SUICIDE_KINDS = frozenset(("bomb_truck", "hexling"))

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
        "name": "坦克歼击车", "cost": 1050, "hp": 400, "speed": 66.0,
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
        "name": "天启坦克", "cost": 1700, "hp": 1700, "speed": 57.6,
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
    # 自爆卡车：中期玻璃大炮。工厂就能出，不卡维修厂。无常规火力，
    # 贴近或阵亡时炸开。轻甲载具：军犬咬不动，磁暴/火箭能拆。
    # 造价 1000 / 训练 8.5 / 移速 97.9，与爆裂魔仆对齐（贵、慢造、慢走）。
    # 爆炸 700 / 半径 120。爆破专攻建筑与采矿单位 ×1.5，其余单位固定 ×0.8：
    # 步兵堆照样一发清，但天启、巨龙这类高血单位不再被自爆当成兑子答案。
    # 单车仍拆不掉满血指挥中心，避免兼任清兵、反甲与拆家三种角色。
    # 邻近自爆只吃 700 溅射，不会连带引爆。
    "bomb_truck": {
        "name": "自爆卡车", "cost": 1000, "hp": 160, "speed": 97.9,
        "damage": 0.0, "range": 22.0, "cooldown": 0.0,
        "size": 16.0, "build": 8.5, "producer": "factory",
        "projectile": "none", "projectileSpeed": 0.0, "splash": 0.0,
        "sight": 350.0, "armor": "light", "damageType": "explosive",
        "deathExplosion": {
            "damage": 700.0, "radius": 120.0,
            "damageType": "explosive",
            "targetMultipliers": {
                "default": 0.8,
                "structure": 1.5,
                "harvester": 1.5,
                "mharvester": 1.5,
                "tharvester": 1.5,
            },
        },
        "detonateOnContact": True,
    },
    # ==================== 魔法阵营「秘法会」（faction=magic） ====================
    # 独立经济：自己的主堡/法力塔/精炼所/采矿/基地车，数值与科技对位、只换皮换名。
    # 采矿/迁徙与钢铁一样走 heavy：轻甲会让步枪/侦察/光棱多吃一层隐藏税。
    "mharvester": {
        "name": "浮游晶簇", "cost": 920, "hp": 680, "speed": 63.6,
        "damage": 0.0, "range": 0.0, "cooldown": 0.0,
        "size": 22.0, "build": 9.0, "producer": "mcircle",
        "projectile": "none", "projectileSpeed": 0.0, "splash": 0.0,
        "capacity": 850.0, "harvestRate": 145.0, "sight": 330.0,
        "armor": "heavy", "damageType": "none",
    },
    "mmcv": {
        "name": "迁徙法阵", "cost": 2500, "hp": 900, "speed": 45.6,
        "damage": 0.0, "range": 0.0, "cooldown": 0.0,
        "size": 24.0, "build": 14.0, "producer": "mcircle",
        "projectile": "none", "projectileSpeed": 0.0, "splash": 0.0,
        "sight": 320.0, "armor": "heavy", "damageType": "none",
        "canDeploy": True, "deploysInto": "mhq",
    },
    # ---- 军事：奥术圣殿(步兵与反甲晶击构装) / 召唤法阵(构装与魔兽) ----
    # 奥术法师：远程魔法弹，熔重甲的反坦克答案。160 血与魔仆同一口咬不死门槛
    # （咬 90，剩 70）；两口仍死。子弹有效血≈107，和突击兵 110 同档。
    "mage": {
        "name": "奥术法师", "cost": 500, "hp": 160, "speed": 78.0,
        "damage": 42.0, "range": 220.0, "cooldown": 1.1,
        "size": 10.0, "build": 5.0, "producer": "mtemple",
        "projectile": "arcane", "projectileSpeed": 800.0, "splash": 0.0,
        "sight": 410.0, "armor": "arcane", "damageType": "magic",
    },
    # 冰霜女巫：伤害低但命中挂减速，是魔法阵营的控制/拉扯核心。
    # 血量与法师对齐，一口军犬咬不死，两口仍死。
    "frost": {
        "name": "冰霜女巫", "cost": 550, "hp": 160, "speed": 74.0,
        "damage": 16.0, "range": 205.0, "cooldown": 1.3,
        "size": 10.0, "build": 6.0, "producer": "mtemple",
        "projectile": "frost", "projectileSpeed": 700.0, "splash": 40.0,
        "sight": 420.0, "armor": "arcane", "damageType": "magic",
        "slow": {"mult": 0.45, "duration": 2.5},
    },
    # 晶刺：圣殿廉价肉。短距晶刺，对位突击/军犬档，不是步枪抄数。
    # 95 血：军犬咬 90，一口剩 5，两口死。比 160 法师更脆，比一口死的步兵厚。
    "imp": {
        "name": "晶刺", "cost": 200, "hp": 95, "speed": 120.0,
        "damage": 18.0, "range": 90.0, "cooldown": 0.7,
        "size": 9.0, "build": 3.0, "producer": "mtemple",
        "projectile": "crystal", "projectileSpeed": 520.0, "splash": 0.0,
        "sight": 360.0, "armor": "arcane", "damageType": "magic",
    },
    # 虹视使：圣殿远程点射。玻璃后排，对位狙击档，不用狙击伤种、不抄 420/75。
    # 射程与狙击手对齐 310；80 血低于一口咬 (90)，比法师更脆；无溅射，不卡圣泉。
    "oracle": {
        "name": "虹视使", "cost": 450, "hp": 80, "speed": 88.0,
        "damage": 48.0, "range": 310.0, "cooldown": 1.55,
        "size": 10.0, "build": 6.0, "producer": "mtemple",
        "projectile": "iris", "projectileSpeed": 1100.0, "splash": 0.0,
        "sight": 470.0, "armor": "arcane", "damageType": "magic",
    },
    # 岩石傀儡：构装前排，高血慢速，投掷巨石溅射，踩步兵/轻型。
    "golem": {
        "name": "岩石傀儡", "cost": 850, "hp": 760, "speed": 52.0,
        "damage": 52.0, "range": 130.0, "cooldown": 1.2,
        "size": 20.0, "build": 9.0, "producer": "mcircle",
        "projectile": "boulder", "projectileSpeed": 420.0, "splash": 34.0,
        "sight": 360.0, "armor": "arcane", "damageType": "magic",
    },
    # 玄岩巨像：傀儡进阶，新单位不是原地升级。圣泉后的地面重甲前排，
    # 短距巨石溅射推线，对位天启的地面存在；巨龙仍是远程溅射压轴。
    # 移速必须与岩石傀儡相同。heavy/light 混甲，磁暴/狙击/军犬不能当
    # 纯魔导一锅端。算载具，圣泉可修。
    "behemoth": {
        "name": "玄岩巨像", "cost": 1520, "hp": 1520, "speed": 52.0,
        "damage": 90.0, "range": 145.0, "cooldown": 1.15,
        "size": 26.0, "build": 14.0, "producer": "mcircle",
        "requires": ["mspring"],
        "projectile": "rune_boulder", "projectileSpeed": 400.0, "splash": 52.0,
        "sight": 380.0, "armor": ("heavy", "light"), "damageType": "magic",
    },
    # 影豹：全场最快的魔法兽，近战扑击(爪击瞬发)，侧翼包抄/切后排。
    # 轻甲、不算载具：军犬 bite ×0，不当猎物；狙击按轻甲变弱。法阵召唤。
    "panther": {
        "name": "影豹", "cost": 420, "hp": 240, "speed": 132.0,
        "damage": 34.0, "range": 34.0, "cooldown": 0.7,
        "size": 12.0, "build": 5.0, "producer": "mcircle",
        "projectile": "claw", "projectileSpeed": 1000.0, "splash": 0.0,
        "sight": 520.0, "armor": "light", "damageType": "magic",
    },
    # 秘法巨龙：远程大火球大溅射。圣泉二级后才许召唤，避免法阵一立就能出 1600 压轴。
    # 1100 血仍低于天启 1700；靠射程/溅射/熔甲换耐久，不当新的碾压前排。
    "dragon": {
        "name": "秘法巨龙", "cost": 1600, "hp": 1100, "speed": 60.0,
        "damage": 95.0, "range": 260.0, "cooldown": 1.7,
        "size": 24.0, "build": 15.0, "producer": "mcircle",
        "requires": ["mspring"],
        "projectile": "fireball", "projectileSpeed": 520.0, "splash": 60.0,
        "sight": 460.0, "armor": "arcane", "damageType": "magic",
    },
    # ---- 进阶：圣泉卡二级。不改开局 3 法师+傀儡，只补中后期缺口 ----
    # 晶铠卫士：对位磁暴步兵的反甲晶击构装，不是 1280 混甲前排。
    # 圣殿训练、仍卡圣泉。轻甲 + tesla 伤种（对轻/重/魔导同磁暴表），
    # 无溅射，快脉冲。比磁暴略贵略厚：圣泉门槛 + 轻甲（军犬 bite ×0，
    # 火箭/磁暴仍打）。仍算载具，圣泉可修。前排继续交给岩石傀儡 / 玄岩巨像。
    "warden": {
        "name": "晶铠卫士", "cost": 720, "hp": 220, "speed": 80.0,
        "damage": 28.0, "range": 155.0, "cooldown": 0.50,
        "size": 12.0, "build": 7.5, "producer": "mtemple",
        "requires": ["mspring"],
        "projectile": "crystal", "projectileSpeed": 900.0, "splash": 0.0,
        "sight": 380.0, "armor": "light", "damageType": "tesla",
    },
    # 坠星台：秘法会对位东风快递。超远曲射彗星，弹速慢能被看见躲。
    # missile ×1.50 拆建筑（190×1.5=285），满血 2400 总部一发拆不掉。
    # 轻甲发射台，圣泉二级后才许召唤。对机动步兵很差。
    "comet": {
        "name": "坠星台", "cost": 2000, "hp": 280, "speed": 36.0,
        "damage": 190.0, "range": 520.0, "cooldown": 5.2,
        "size": 22.0, "build": 18.0, "producer": "mcircle",
        "requires": ["mspring"],
        "projectile": "comet", "projectileSpeed": 165.0, "splash": 110.0,
        "sight": 300.0, "armor": "light", "damageType": "missile",
    },
    # 裂地晶兽：缺的攻城行。siege ×1.8 拆建筑，对单位很差，对位攻城炮/光棱。
    # 600 血不再一碰就碎，仍远低于傀儡 760 / 巨龙 1100 / 天启 1700。
    # 与玄岩巨像同走 heavy/light 混甲（晶铠已改为轻甲反甲脉冲）。
    "colossus": {
        "name": "裂地晶兽", "cost": 1280, "hp": 600, "speed": 48.0,
        "damage": 120.0, "range": 340.0, "cooldown": 2.10,
        "size": 24.0, "build": 12.0, "producer": "mcircle",
        "requires": ["mspring"],
        "projectile": "meteor", "projectileSpeed": 240.0, "splash": 58.0,
        "sight": 300.0, "armor": ("heavy", "light"), "damageType": "siege",
    },
    # 爆裂魔仆：秘法会对位自爆单位，不是卡车。符核活体，法阵召唤。
    # 造价/训练/移速/血/爆炸与卡车对齐（1000 / 8.5 / 97.9 / 160 / 700 / 120）。
    # 目标倍率也与卡车一致：建筑/采矿单位 ×1.5，其余单位 ×0.8。
    # 邻近自爆不连带。轻甲、不算载具：军犬 bite ×0，不当猎物。
    # 狙击按轻甲 55×0.4=22 / 发。圣泉修不了。
    "hexling": {
        "name": "爆裂魔仆", "cost": 1000, "hp": 160, "speed": 97.9,
        "damage": 0.0, "range": 22.0, "cooldown": 0.0,
        "size": 11.0, "build": 8.5, "producer": "mcircle",
        "projectile": "none", "projectileSpeed": 0.0, "splash": 0.0,
        "sight": 350.0, "armor": "light", "damageType": "explosive",
        "deathExplosion": {
            "damage": 700.0, "radius": 120.0,
            "damageType": "explosive",
            "targetMultipliers": {
                "default": 0.8,
                "structure": 1.5,
                "harvester": 1.5,
                "mharvester": 1.5,
                "tharvester": 1.5,
            },
        },
        "detonateOnContact": True,
    },
    # ==================== 部落阵营「原始部落」（faction=tribe）P0 ====================
    # 独立经济：大营/图腾/精炼棚/驮兽/迁徙驮队与钢铁对位，只换皮换名。
    # 驯兽围栏出驮兽与战狼；猎手营地出骨矛与驯兽师。P0 没有自爆对位。
    "tharvester": {
        "name": "驮兽", "cost": 920, "hp": 680, "speed": 63.6,
        "damage": 0.0, "range": 0.0, "cooldown": 0.0,
        "size": 22.0, "build": 9.0, "producer": "tpen",
        "projectile": "none", "projectileSpeed": 0.0, "splash": 0.0,
        "capacity": 850.0, "harvestRate": 145.0, "sight": 330.0,
        "armor": "heavy", "damageType": "none",
    },
    "tmcv": {
        "name": "迁徙驮队", "cost": 2500, "hp": 900, "speed": 45.6,
        "damage": 0.0, "range": 0.0, "cooldown": 0.0,
        "size": 24.0, "build": 14.0, "producer": "tpen",
        "projectile": "none", "projectileSpeed": 0.0, "splash": 0.0,
        "sight": 320.0, "armor": "heavy", "damageType": "none",
        "canDeploy": True, "deploysInto": "thq",
    },
    # 骨矛猎手：廉价前期步兵，对位突击兵档。短中距骨矛，伤种复用子弹。
    "spear": {
        "name": "骨矛猎手", "cost": 190, "hp": 115, "speed": 108.0,
        "damage": 14.0, "range": 115.0, "cooldown": 0.68,
        "size": 10.0, "build": 3.0, "producer": "tcamp",
        "projectile": "bullet", "projectileSpeed": 620.0, "splash": 0.0,
        "sight": 350.0, "armor": "infantry", "damageType": "bullet",
    },
    # 驯兽师：营地出的脆弱辅助。只能招降中立作战单位，耗时+矿；
    # 大厅关闭 neutrals 时动作不可用，围栏战狼不受影响。
    "tamer": {
        "name": "驯兽师", "cost": 260, "hp": 70, "speed": 100.0,
        "damage": 8.0, "range": 80.0, "cooldown": 1.1,
        "size": 10.0, "build": 5.0, "producer": "tcamp",
        "projectile": "bullet", "projectileSpeed": 560.0, "splash": 0.0,
        "sight": 360.0, "armor": "infantry", "damageType": "bullet",
        "canTame": True, "tameCost": 150, "tameTime": 4.0, "tameRange": 48.0,
    },
    # 战狼：围栏出的轻型野兽，扑咬步兵。兽甲，不算载具，无自爆。
    "wolf": {
        "name": "战狼", "cost": 380, "hp": 200, "speed": 138.0,
        "damage": 36.0, "range": 32.0, "cooldown": 0.75,
        "size": 11.0, "build": 5.0, "producer": "tpen",
        "projectile": "bite", "projectileSpeed": 1000.0, "splash": 0.0,
        "sight": 420.0, "armor": "beast", "damageType": "bite",
    },
    # 蛛网巨蛛：围栏进阶控制兽。血祭坛后才许驯养，对位冰霜女巫的单目标锁腿。
    # 中距吐丝，直伤一般；命中挂定身（slow.mult 0）+ 可复用的毒丝 DoT。
    # 刷新只续时，不叠乘。兽甲、非载具、无自爆。比战狼慢、比女巫厚。
    "spider": {
        "name": "蛛网巨蛛", "cost": 720, "hp": 340, "speed": 108.0,
        "damage": 18.0, "range": 170.0, "cooldown": 1.45,
        "size": 14.0, "build": 8.0, "producer": "tpen",
        "requires": ["taltar"],
        "projectile": "web", "projectileSpeed": 520.0, "splash": 0.0,
        "sight": 400.0, "armor": "beast", "damageType": "venom",
        "slow": {"mult": 0.0, "duration": 2.2},
        "dot": {"dps": 14.0, "duration": 3.0, "damageType": "venom"},
    },
    # 穿甲巨蝎：围栏进阶玻璃大炮。血祭坛后才许驯养，对位歼击车的兽甲短距穿甲手。
    # 中短距尾刺，伤种复用 ap（重甲 ×2.10），无溅射、无定身、无 DoT。
    # 造价低于歼击车，血更薄，射程更短。兽甲、非载具、无自爆。
    "scorpion": {
        "name": "穿甲巨蝎", "cost": 820, "hp": 165, "speed": 100.0,
        "damage": 82.0, "range": 145.0, "cooldown": 1.80,
        "size": 13.0, "build": 7.5, "producer": "tpen",
        "requires": ["taltar"],
        "projectile": "sting", "projectileSpeed": 640.0, "splash": 0.0,
        "sight": 390.0, "armor": "beast", "damageType": "ap",
    },
    # 猛犸战象：围栏后期重兽。血祭坛后才许驯养，对位玄岩巨像 / 钢铁重甲的
    # 地面砸家前排。慢、厚、短距砸击，溅射拆建筑；兽甲、非载具、无自爆。
    # smash 伤种：建筑 ×1.50，对单位中性偏强，不当攻城炮那种对人 ×0.25。
    "mammoth": {
        "name": "猛犸战象", "cost": 1500, "hp": 1280, "speed": 76.0,
        "damage": 80.0, "range": 52.0, "cooldown": 1.35,
        "size": 24.0, "build": 13.0, "producer": "tpen",
        "requires": ["taltar"],
        "projectile": "smash", "projectileSpeed": 1000.0, "splash": 28.0,
        "sight": 380.0, "armor": "beast", "damageType": "smash",
    },
}


def unit_sight_radius(definition):
    """Return base sight, extended when needed to cover weapon range +10%."""
    base_sight = float(definition.get(
        "_baseSight", definition.get("sight", 350.0)) or 350.0)
    attack_range = float(definition.get("range", 0.0) or 0.0)
    if attack_range > 0.0:
        return round(max(
            base_sight, attack_range * UNIT_SIGHT_RANGE_MULTIPLIER), 3)
    return base_sight


# 保持 UNIT_TYPES 本身也是已经归一化的公开定义，旧代码/测试即使直接读取
# definition["sight"]，得到的也和服务端迷雾、客户端视野表完全一致。
for _unit_definition in UNIT_TYPES.values():
    _unit_definition["_baseSight"] = float(
        _unit_definition.get("sight", 350.0) or 350.0)
    _unit_definition["sight"] = unit_sight_radius(_unit_definition)

# ---- 战功换装：天启坦克的老兵弹种 ----
# 纯表现层映射。伤害、射速、溅射与护甲判定仍走 UNIT_TYPES 和既有军衔倍率；
# 这里不额外叠加数值，只决定客户端画哪一种弹道，好让「一星换弹、二星换形态」
# 在战场上一眼看得出来。阈值与 VETERAN_RANKS 的 3/8/16 军衔线保持一致。
VETERAN_PROJECTILES = {
    # 天启坦克：三杀(一星)换等离子穿甲弹，八杀(二星)展开人形态改用双臂炮。
    "overlord": ((8, "plasmalance"), (3, "plasma")),
}


def veteran_projectile(kind, kills, fallback):
    """Return the veteran-skinned projectile name, or `fallback` below rank."""
    for threshold, projectile in VETERAN_PROJECTILES.get(kind, ()):
        if kills >= threshold:
            return projectile
    return fallback


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
        "damage": 80.0, "range": 320.0, "cooldown": 0.70,
        "projectile": "shell", "projectileSpeed": 460.0, "splash": 51.0,
        "armor": "structure", "damageType": "shell",
    },
    "missile": {
        "name": "导弹炮塔", "cost": 1200, "hp": 1050, "size": 34.0,
        "build": 16.0, "deploy": 3.5, "power": -30, "requires": ["barracks", "power"],
        "sight": 580.0, "damage": 120.0, "range": 420.0, "cooldown": 1.6,
        "projectile": "shell", "projectileSpeed": 420.0, "splash": 45.0,
        "armor": "structure", "damageType": "shell",
    },
    # ==================== 魔法阵营「秘法会」建筑（faction=magic） ====================
    # 与科技对位：主堡=hq / 法力塔=power / 精炼所=refinery / 圣殿=barracks /
    # 法阵=factory / 圣泉=repair / 奥术塔+雷暴塔=defense。role 字段让经济与维修逻辑跨阵营复用。
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
    # 奥术塔：对位哨戒炮塔的近距基地防空。略加射程回答钢铁点射，
    # DPS 仍低于哨戒（80/0.9≈89 vs 80/0.70≈114）。远程压线另有雷暴塔。
    "mtower": {
        "name": "奥术塔", "cost": 950, "hp": 1300, "size": 30.0,
        "build": 12.0, "deploy": 3.0, "power": -25, "requires": ["mpower"], "sight": 560.0,
        "damage": 80.0, "range": 360.0, "cooldown": 0.9,
        "projectile": "arcane", "projectileSpeed": 700.0, "splash": 30.0,
        "armor": "structure", "damageType": "magic",
    },
    # 雷暴塔：对位钢铁远程塔的秘法联网防空，红警光棱支援 + 雷电主题。
    # 单塔 70/1.1，比导弹炮塔（120/1.6）单体更弱、射更快。射程仍锁 420。
    # 伤种 tesla：克载具/魔导，拆建筑只有 ×0.50（拆家仍归钢铁导弹炮塔）。
    # 支援：同阵营/友军已建成的雷暴塔在 supportRadius 内、且冷却就绪时
    # 把这一发喂给开火塔，公式 damage = 70 + 35 * extras（extras 上限 3 → 175）。
    # 支援塔本轮不再独立开火。命中单位挂 0.5× / 1.8s 麻痹，刷新不叠乘。
    # 圣殿≈兵营门槛，法力塔供电。不改奥术塔、不改钢铁双塔。
    "mstorm": {
        "name": "雷暴塔", "cost": 1200, "hp": 1050, "size": 34.0,
        "build": 16.0, "deploy": 3.5, "power": -30, "requires": ["mtemple", "mpower"],
        "sight": 580.0, "damage": 70.0, "range": 420.0, "cooldown": 1.1,
        "projectile": "storm", "projectileSpeed": 900.0, "splash": 0.0,
        "armor": "structure", "damageType": "tesla",
        "slow": {"mult": 0.5, "duration": 1.8},
        "supportRadius": 420.0, "supportBonus": 35.0, "supportMax": 3,
    },
    # ==================== 部落阵营「原始部落」建筑（faction=tribe）P0 ====================
    # 与科技/秘法对位：大营=hq / 图腾柱=power / 精炼棚=refinery / 营地=barracks /
    # 围栏=factory / 血祭坛=repair。P1 补棘矛哨塔/毒矢高台与陷阱毒坑，仍无自爆。
    # 血祭坛门槛严格镜像圣泉/维修厂：必须先有工厂角色（驯兽围栏）+ 电力角色（图腾柱）。
    "thq": {
        "name": "部落大营", "cost": 0, "hp": 2400, "size": 58.0,
        "build": 0.0, "deploy": 0.0, "power": 35, "requires": [], "sight": 650.0,
        "armor": "structure", "packsInto": "tmcv",
    },
    "tpower": {
        "name": "图腾柱", "cost": 600, "hp": 760, "size": 40.0,
        "build": 8.0, "deploy": 2.2, "power": 120, "requires": ["thq"], "sight": 350.0,
        "armor": "structure",
    },
    "trefinery": {
        "name": "兽骨精炼棚", "cost": 1400, "hp": 1350, "size": 52.0,
        "build": 14.0, "deploy": 3.2, "power": -30, "requires": ["thq"], "sight": 390.0,
        "armor": "structure",
    },
    "tcamp": {
        "name": "猎手营地", "cost": 700, "hp": 900, "size": 42.0,
        "build": 10.0, "deploy": 2.8, "power": -20, "requires": ["tpower"], "sight": 410.0,
        "armor": "structure",
    },
    "tpen": {
        "name": "驯兽围栏", "cost": 1600, "hp": 1600, "size": 58.0,
        "build": 18.0, "deploy": 4.2, "power": -45, "requires": ["trefinery", "tpower"], "sight": 460.0,
        "armor": "structure",
    },
    "taltar": {
        "name": "血祭坛", "cost": 1250, "hp": 1280, "size": 50.0,
        "build": 15.0, "deploy": 3.6, "power": -35,
        "requires": ["tpen", "tpower"], "sight": 440.0,
        "armor": "structure",
    },
    # ==================== 部落 P1：哨塔 / 陷阱毒 / 不引入自爆 ====================
    # 棘矛哨塔：早期基地通用防空档，对位钢铁哨戒 / 秘法奥术塔，更便宜更脆更短。
    # 骨矛弹走 bullet，中距点射 + 小溅射，营地+图腾即可。填 bot defense。
    "tspiketower": {
        "name": "棘矛哨塔", "cost": 720, "hp": 820, "size": 28.0,
        "build": 10.0, "deploy": 2.6, "power": -20,
        "requires": ["tcamp", "tpower"], "sight": 420.0,
        "damage": 40.0, "range": 195.0, "cooldown": 0.72,
        "projectile": "spike", "projectileSpeed": 540.0, "splash": 16.0,
        "armor": "structure", "damageType": "bullet",
    },
    # 毒矢高台：后期远程支援塔，对位导弹炮塔 / 雷暴塔档，但不做联网。
    # 单发更低，射程更长，命中挂毒 DoT（复用蛛网毒丝刷新规则）。祭坛+图腾。
    "ttoxtower": {
        "name": "毒矢高台", "cost": 1000, "hp": 880, "size": 32.0,
        "build": 14.0, "deploy": 3.2, "power": -25,
        "requires": ["taltar", "tpower"], "sight": 500.0,
        "damage": 24.0, "range": 275.0, "cooldown": 1.30,
        "projectile": "dart", "projectileSpeed": 500.0, "splash": 0.0,
        "armor": "structure", "damageType": "venom",
        "dot": {"dps": 12.0, "duration": 3.2, "damageType": "venom"},
    },
    # 兽夹陷阱：便宜地面夹。建成后短延时上膛，敌军地面单位进圈一次
    # 定身+爆发，然后拆除。走 buildQueue（role=trap），不是炮塔。
    "ttrap": {
        "name": "兽夹陷阱", "cost": 320, "hp": 140, "size": 16.0,
        "build": 5.0, "deploy": 1.2, "power": -4,
        "requires": ["tcamp"], "sight": 160.0,
        "armor": "structure", "damageType": "shell",
        "trapRadius": 44.0, "trapDamage": 75.0, "trapArm": 2.2,
        "trapExpire": True,
        "slow": {"mult": 0.0, "duration": 2.0},
    },
    # 毒雾坑：区域拒止。脉冲给圈内敌军挂毒 DoT，不伤友军、不伤建筑。
    # 低血中价，血祭坛门槛。
    "tpit": {
        "name": "毒雾坑", "cost": 580, "hp": 260, "size": 22.0,
        "build": 8.0, "deploy": 2.0, "power": -8,
        "requires": ["taltar"], "sight": 200.0,
        "armor": "structure", "damageType": "venom",
        "auraRadius": 88.0, "auraPulse": 0.90,
        "dot": {"dps": 16.0, "duration": 1.6, "damageType": "venom"},
    },
}

# ---- 阵营与角色分类 ----
# faction：tech(钢铁军团) / magic(秘法会) / tribe(原始部落)，
# 建造与生产按 player["faction"] 校验。
# role：跨阵营的功能角色。经济逻辑（出生配置、采矿返回、精炼厂赠车、基地车
# 展开、出售保护、bot 寻目标）一律按 role 判定而不是写死 kind —— 新阵营出
# 同 role 的换皮建筑即可整套复用。新增兵种/建筑 = 加定义 + 在下面登记 role。
MAGIC_STRUCTURES = frozenset((
    "mhq", "mpower", "mrefinery", "mtemple", "mcircle", "mspring", "mtower",
    "mstorm",
))
MAGIC_UNITS = frozenset((
    "mharvester", "mmcv", "mage", "frost", "imp", "oracle",
    "golem", "behemoth", "panther", "dragon", "warden", "colossus", "comet",
    "hexling",
))
TRIBE_STRUCTURES = frozenset((
    "thq", "tpower", "trefinery", "tcamp", "tpen", "taltar",
    "tspiketower", "ttoxtower", "ttrap", "tpit",
))
TRIBE_UNITS = frozenset((
    "tharvester", "tmcv", "spear", "tamer", "wolf", "spider", "scorpion",
    "mammoth",
))
VALID_FACTIONS = frozenset(("tech", "magic", "tribe"))

_STRUCTURE_ROLES = {
    "hq": "hq", "mhq": "hq", "thq": "hq",
    "power": "power", "mpower": "power", "tpower": "power",
    "refinery": "refinery", "mrefinery": "refinery", "trefinery": "refinery",
    "barracks": "barracks", "mtemple": "barracks", "tcamp": "barracks",
    "factory": "factory", "mcircle": "factory", "tpen": "factory",
    "repair": "repair", "mspring": "repair", "taltar": "repair",
    "turret": "defense", "missile": "defense", "mtower": "defense",
    "mstorm": "defense",
    "tspiketower": "defense", "ttoxtower": "defense",
    "ttrap": "trap", "tpit": "trap",
}
_UNIT_ROLES = {
    "harvester": "harvester", "mharvester": "harvester", "tharvester": "harvester",
    "mcv": "mcv", "mmcv": "mcv", "tmcv": "mcv",
}


def kind_faction(kind):
    if kind in MAGIC_STRUCTURES or kind in MAGIC_UNITS:
        return "magic"
    if kind in TRIBE_STRUCTURES or kind in TRIBE_UNITS:
        return "tribe"
    return "tech"


for _kind, _def in STRUCTURE_TYPES.items():
    _def["role"] = _STRUCTURE_ROLES.get(_kind)
    _def["faction"] = kind_faction(_kind)
for _kind, _def in UNIT_TYPES.items():
    _def["role"] = _UNIT_ROLES.get(_kind)
    _def["faction"] = kind_faction(_kind)


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
            "range": float(definition.get("range", 0) or 0),
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
            "canVeteran": float(definition.get("damage", 0.0) or 0.0) > 0.0,
            "canTame": bool(definition.get("canTame")),
        }
    return {
        "buildings": buildings,
        "units": units,
        "veterancy": {
            "regenDelay": VETERAN_REGEN_DELAY,
            "ranks": [dict(rank) for rank in VETERAN_RANKS],
        },
    }


PUBLIC_CATALOG = public_catalog()


# 各阵营的出生与经济基础 kind。start_game 出生配置、精炼厂赠车都从这里取，
# 日后要加第三个阵营只需在 UNIT/STRUCTURE 表加定义、在这里登记一行。
FACTION_LOADOUT = {
    "tech": {"hq": "hq", "power": "power", "refinery": "refinery",
             "harvester": "harvester", "mcv": "mcv", "infantry": "rifle", "armor": "tank"},
    "magic": {"hq": "mhq", "power": "mpower", "refinery": "mrefinery",
              "harvester": "mharvester", "mcv": "mmcv", "infantry": "mage", "armor": "golem"},
    "tribe": {"hq": "thq", "power": "tpower", "refinery": "trefinery",
              "harvester": "tharvester", "mcv": "tmcv", "infantry": "spear", "armor": "wolf"},
}


def faction_loadout(faction):
    return FACTION_LOADOUT.get(faction, FACTION_LOADOUT["tech"])


# AI 按 role 取的建造 kind（role→具体建筑）。魔法换皮复用同一套决策：
# 圣殿=兵营 / 法阵=工厂 / 圣泉=维修厂 / 奥术塔=近距防御；
# defense_long 是后期远程塔（钢铁导弹炮塔 / 秘法会雷暴塔），开局 rush 不走这条。
FACTION_BUILDINGS = {
    "tech": {"power": "power", "barracks": "barracks", "refinery": "refinery",
             "factory": "factory", "repair": "repair", "defense": "turret",
             "defense_long": "missile"},
    "magic": {"power": "mpower", "barracks": "mtemple", "refinery": "mrefinery",
              "factory": "mcircle", "repair": "mspring", "defense": "mtower",
              "defense_long": "mstorm"},
    # P1 补齐近距/远程塔，以及陷阱/毒坑。defense_long 仍走后期补塔。
    "tribe": {"power": "tpower", "barracks": "tcamp", "refinery": "trefinery",
              "factory": "tpen", "repair": "taltar",
              "defense": "tspiketower", "defense_long": "ttoxtower",
              "trap": "ttrap", "pit": "tpit"},
}


def faction_buildings(faction):
    return FACTION_BUILDINGS.get(faction, FACTION_BUILDINGS["tech"])
