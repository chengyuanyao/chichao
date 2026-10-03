# Implementation Plan

## Overview

按功能纵向切片实现 design.md 与 requirements.md：同一功能的目录数值、服务端行为、下发字段与旧测试断言在同一任务内改完，每个 Checkpoint 时 `python run_tests.py` 与全部 `tests/*.mjs` 都必须通过。按编号顺序执行是安全的；标了「依赖」的任务必须等前序任务完成。所有性质测试开头打印 `Feature: tribe-faction-redesign, Property N: <标题>`，用固定种子循环 ≥ 200 次（Property 9 为完整枚举）。只有需要浏览器与 GPU 的验收任务标为可选（`*`）。数值以 design.md 为准；实现中发现与代码事实冲突时先记录并报告，不擅自改平衡数值。

## Tasks

- [x] 1. 基础集合与常量（无行为变化）
  - [x] 1.1 在 catalog.py 定义部落集合与常量
    - 新增 `TRIBE_BEAST_KINDS`（wolf、spider、scorpion、mammoth、panda）与 `REPAIRABLE_KINDS = VEHICLE_KINDS | TRIBE_BEAST_KINDS`，本任务只定义、不接入维修逻辑
    - 新增 `HUNT_MARK_SECONDS = 4.0`、`HUNT_MARK_BONUS = 1.15`、`TRIBE_BONUS_CAP = 1.45`、`ROOT_RESIST_SECONDS = 1.0`、`ROOT_RESIST_SLOW_MULT = 0.5`（design.md §1.3）
    - server.py 的 `from catalog import (...)` 追加并再导出上述名字
    - _Requirements: 6.1, 6.2, 9.1, 31.5, 31.8_
  - [x] 1.2 新建 tests/tribe_redesign_test.py 骨架
    - 沿用现有 tests/*_test.py 的纯 assert 脚本风格（make_room、give、isolate 等辅助函数），`run_tests.py` 自动收录
    - 断言 `TRIBE_BEAST_KINDS` 等于目录中全部 `armor == "beast"` 的 kind、`REPAIRABLE_KINDS` 的组成、新常量取值，以及 server 再导出
    - 运行 `python tests/tribe_redesign_test.py`
    - _Requirements: 6.1, 6.2, 9.1, 31.8_

- [x] 2. 跨阵营控制规则 H
  - [x] 2.1 实现状态计时与强者优先规则
    - server.py 新增 `tick_status_timers(unit, dt)`（design.md §2.1），`tick_units` 原减速计时处改为调用它；定身到期时写入 `rootResist = ROOT_RESIST_SECONDS`
    - 按 §2.2 决策表重写 `apply_slow`：强者优先、同强度取 max(剩余, 新时长)、定身期间不续时、抗性期定身降为 ×0.5 减速、时长 ≤ 0 或目标为建筑/已死单位时忽略
    - 重写 `apply_dot`：强度 = dps × `damage_armor_multiplier(dot 伤种, 目标护甲)`，强者优先，同强度且剩余不短于新时长时忽略，否则整组覆盖来源字段
    - `make_unit` 初始化 `rootResist = 0.0`；`public_unit` 在 `rootResist > 0` 时下发 `rootResist: true`
    - _Requirements: 11.1, 11.2, 11.3, 11.4, 11.5, 11.6, 11.7, 11.8, 11.9, 11.10, 12.1, 12.2, 12.3, 12.4, 12.5, 12.6, 12.7, 12.8, 17.4, 17.7, 17.9_
  - [x] 2.2 新建 tests/control_rules_test.py（Property 1、2、3）
    - Property 1：用 `apply_slow` + `tick_status_timers` 驱动，与测试内的参考模型逐步对照 `(slowMult, slowTimer, rootResist)`
    - Property 2：固定步长 dt ≤ 0.05，单段定身时长与相邻间隔各留一个 dt 容差；单蛛 1.45 s 冷却持续命中 60 s 时定身占比 ≤ 55%
    - Property 3：用 `apply_dot` + `tick_dot` 驱动，验证强者优先、同强度取较长、来源字段归属、到期清空与击杀归属
    - 示例：冰霜命中已定身目标仍定身、雷暴不把冰霜 0.45 降为 0.5、冰霜覆盖雷暴为 0.45/2.5、毒雾坑 16 不被蛛毒 14 降级、建筑与已死单位免疫
    - 运行 `python tests/control_rules_test.py`
    - _Requirements: 11.2, 11.3, 11.4, 11.5, 11.6, 11.7, 11.8, 11.10, 11.11, 11.12, 11.13, 11.14, 11.15, 12.3, 12.4, 12.5, 12.6, 12.7, 12.9_
  - [x] 2.3 更新受影响的旧测试
    - tests/tribe_spider_test.py：T4 定身中再施加保持 `slowTimer == 0.4`，计时走完后 `rootResist == 1.0`，抗性期再施加得到 0.5 减速；T7 改为冰霜命中已定身目标仍定身（`slowMult == 0`、`slowTimer == 2.2`、`rooted is True`），定身到期后冰霜正常生效
    - tests/magic_storm_tower_test.py：原断言保留，追加「冰霜 0.45 中被雷暴命中仍为 0.45」「雷暴 0.5 中被冰霜命中变 0.45/2.5」
    - tests/faction_test.py：原断言保留，追加「已定身目标被冰霜命中仍定身」
    - 检查 tests/tribe_p1_test.py 与其他调用 `apply_slow`/`apply_dot` 的测试是否受影响并修正
    - 运行 `python tests/tribe_spider_test.py`、`python tests/magic_storm_tower_test.py`、`python tests/faction_test.py`、`python tests/tribe_p1_test.py`
    - _Requirements: 11.6, 11.7, 11.8, 11.13, 11.14, 11.15_

- [x] 3. Checkpoint：控制规则
  - 运行 `python tests/control_rules_test.py` 与 `python run_tests.py`，全部通过后再继续；有失败先修复，有疑问先问用户

- [x] 4. 猎印、驯兽号令与加成封顶
  - [x] 4.1 目录字段
    - catalog.py：spear、slinger 加 `"huntMark": True`；tamer hp 70 → 90，加 `"commandAura": {"radius": 220.0, "mult": 1.10}`，招降参数不变；派生 `HUNT_MARK_SOURCES` 与 `COMMAND_AURA_QUERY`（§1.3），server 再导出
    - `public_catalog()` 单位条目下发 `huntMark` 与 `commandAuraRadius`（§1.4），只进首帧静态目录
    - 更新现有测试中对 tamer hp 的断言
    - _Requirements: 7.1, 7.2, 7.7, 8.1, 17.1, 17.6_
  - [x] 4.2 服务端结算（依赖 2.1）
    - server.py 新增 `apply_hunt_mark`、`hunt_mark_multiplier`；`apply_hit_status` 追加猎印；`tick_projectiles` 在直击与每个溅射目标的 `apply_damage` 前乘猎印倍率（§2.3）
    - 新增 `command_aura_multiplier`、`tribe_attack_bonus`（§2.4）；`tick_units` 中 `update_panda_rage` 的结果不再直接乘进 `dam_mult`，改为开火时计算 `tribeBonus` 并传给 `launch_projectile(..., tribe_bonus=...)`，弹丸记录 `tribeBonus`，缺省 1.0
    - `tick_status_timers` 递减 `huntMarkTimer`；`make_unit` 初始化 `huntMarkTimer = 0.0`；`public_unit` 在 `huntMarkTimer > 0` 时下发 `marked: true`，字段随实体经过迷雾过滤
    - 保持「未受号令的狂暴熊猫弹丸伤害 72.5」的现有断言成立
    - _Requirements: 7.3, 7.4, 7.5, 7.6, 8.2, 8.3, 8.4, 8.5, 8.6, 8.7, 8.8, 9.2, 9.3, 9.4, 9.5, 9.6, 17.3, 17.8, 17.9, 31.7_
  - [x] 4.3 测试（Property 4、5 与示例）
    - tests/tribe_redesign_test.py 加 Property 4（猎印只由猎手挂在存活单位上、重复命中重置为 4.0、建筑不带印）
    - 加 Property 5（连乘与封顶）：用 `launch_projectile` + `tick_projectiles` 结算单发，驯兽师随机放在 0–300 距离、随机属于己方/盟友/敌方，与参考公式比较（误差 1e-6）
    - 示例：受号令且目标带印时巨蝎打坦克约 217.8、3 刺击毁；狂暴熊猫 + 号令 + 猎印合计倍率 1.45；DoT 不吃猎印与号令；驯兽师被坦克炮 3 发击毁
    - 运行 `python tests/tribe_redesign_test.py`、`python tests/tribe_p2_test.py`、`python tests/tribe_test.py`
    - _Requirements: 7.3, 7.4, 7.5, 7.6, 7.8, 8.2, 8.3, 8.4, 8.5, 8.7, 8.8, 9.3, 9.5, 9.6, 9.7_

- [x] 5. 塔与兽夹
  - [x] 5.1 目录数值与兽夹充能逻辑（同一任务内完成，依赖 2.1）
    - catalog.py：tspiketower 改为 cost 800 / hp 1050 / damage 62 / range 270 / cooldown 0.85 / splash 20 / damageType shell；ttoxtower 改为 cost 1100 / hp 1000 / damage 34 / range 360 / cooldown 1.20 / splash 28 / damageType ap，dot 为 venom 16 × 3.2；ttrap 改为 `trapExpire: False`、`trapCharges: 2`、`trapCooldown: 8.0`（§1.2），同步改写条目注释
    - server.py：`make_structure` 为陷阱写入 `charges`；`tick_trap_structure` 按 §2.5 实现充能递减、上膛冷却与最后一次静默拆除，保留未定义 `trapCharges` 时的无限上膛语义与缺字段回退；`public_structure` 下发 `charges`
    - `public_catalog()` 建筑条目下发 `trapCharges`
    - _Requirements: 3.1, 3.2, 3.3, 4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 5.1, 5.2, 5.3, 5.4, 5.5, 5.6, 5.7, 5.8, 17.2, 17.5_
  - [x] 5.2 测试（Property 6、7）与旧测试更新
    - tests/tribe_redesign_test.py 加 Property 6（毒矢直伤按 ap 结算，venom 毒只落在溅射半径 28 内的敌方单位）与 Property 7（兽夹充能状态机）
    - tests/tribe_p1_test.py 按 design.md「需更新的现有测试」表修改：T1 数值断言、T3 `damageType == "shell"`、T4 `dotDps == 16`、T5 首次触发后 `hp > 0`、`charges == 1`、`armed is False`、`armTimer == 8`，推进上膛后第二次触发才移除
    - 运行 `python tests/tribe_redesign_test.py`、`python tests/tribe_p1_test.py`
    - _Requirements: 3.1, 3.2, 4.2, 4.3, 4.4, 4.5, 4.6, 5.2, 5.3, 5.4, 5.5, 5.8_

- [x] 6. Checkpoint：猎印、号令、塔与兽夹
  - 运行 `python tests/tribe_redesign_test.py` 与 `python run_tests.py`，全部通过后再继续；有失败先修复，有疑问先问用户

- [x] 7. 血祭坛治疗野兽
  - [x] 7.1 接入维修集合
    - server.py：`issue_repair` 改用 `REPAIRABLE_KINDS`，错误文案改为「请选择受损载具或野兽」（保留「受损载具」子串）；`tick_repair_unit` 开头加 kind 守卫（不可修则清维修单转 guard、不扣钱）；`tick_bots` 送修改用 `REPAIRABLE_KINDS`
    - ai_commander/commander.py 的 `_repair` 改用 `REPAIRABLE_KINDS`（仍排除矿车）；`codex.counter` 保持 `VEHICLE_KINDS`
    - catalog.py `public_catalog()` 的 `repairable` 改读 `REPAIRABLE_KINDS`
    - 扑咬 ×0、`hold_target_valid`、`is_dog_prey`、`BOT_SCOUT_VEHICLES` 保持读取 `VEHICLE_KINDS`（§2.6）
    - _Requirements: 6.3, 6.4, 6.5, 6.6, 6.7, 6.8, 15.13, 16.4, 16.5_
  - [x] 7.2 测试
    - tests/tribe_redesign_test.py 加 Property 8（维修集合与扑咬集合分离）与祭坛治疗战狼全流程（下单 → 走位 → 扣钱 → 回满 → guard），速率与费用同载具
    - 更新 tribe_spider_test T1、tribe_p1_test（猛犸）、tribe_p2_test（熊猫）、presentation_rules_test 301–333 行的 `repairable` 断言为 `True`（投石猎手仍为 `False`）；tests/repair_test.py 不改
    - 运行 `python tests/tribe_redesign_test.py`、`python tests/repair_test.py`、`python tests/tribe_spider_test.py`、`python tests/tribe_p1_test.py`、`python tests/tribe_p2_test.py`、`python tests/presentation_rules_test.py`、`python ai_commander/selftest.py`
    - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5, 6.6, 6.7, 6.8_

- [x] 8. 新单位与巨蝎调整（含客户端必需条目）
  - [x] 8.1 服务端目录与接线
    - catalog.py 按 Data Models 新增 `javelin`、`catapult`，加入 `TRIBE_UNITS`；`catapult` 加入 `VEHICLE_KINDS`；`javelin` 带 `huntMark`
    - scorpion 改为 hp 250、range 165、`requires: []`，改写注释
    - server.py 攻城单位优先打建筑的索敌元组追加 `catapult`（§2.7）
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 10.1, 10.2, 10.3, 10.4, 10.5, 10.6, 10.7, 10.8, 10.9_
  - [x] 8.2 客户端必需条目（与 8.1 在同一 Checkpoint 前完成）
    - public/render3d.js：新增 `UNIT_BUILDERS.javelin`、`UNIT_BUILDERS.catapult` 专属基础 builder，注释首行分别为「燧石标枪手：」「巨石投石车：」，不得直接返回其他 builder 的结果（§4.9）
    - `simpleUnitParts` 为两者各加一条远景盒模（≤ 200 三角，带一块约 0.9 的队色面）；`UNIT_VISUAL_SCALE` 加 `javelin: 2.15`、`catapult: 1.28`；javelin 加入 `CLOTH_UNIT_KINDS`，catapult 在 `unitSurfaceFamily` 与材质选择中并入 tharvester/tmcv 的兽皮族
    - public/app.js 的 `TRIBE_KINDS` 加入两种新单位
    - _Requirements: 22.4, 24.1, 24.2, 24.3, 24.4, 24.5_
  - [x] 8.3 测试与旧测试更新
    - tests/tribe_redesign_test.py：标枪手目录与阵营、营地即可训、跨阵营拒绝、对重甲/轻甲/步兵 60/52/30；巨蝎仅围栏即可排产、坦克 5 发击毁、尾刺 172.2；投石车需祭坛、优先打建筑、服从手动目标、对建筑 171、军犬 0 伤害、祭坛可修、`megalith` 不重名
    - 更新 tribe_scorpion_test（T1、T2、T6）、tribe_test（TRIBE_UNITS 遍历列表、巨蝎 requires）、presentation_rules_test（巨蝎 requires、新 builder 注释首行、不 alias 他人 builder）；弹道 look、HUD 与 README 字符串的断言留到任务 12、24、25 再加
    - 运行上述 Python 测试与 `node tests/unit_geometry_test.mjs`、`node tests/model_picker_test.mjs`、`node tests/river_art_test.mjs`
    - _Requirements: 1.2, 1.3, 1.4, 1.5, 1.6, 2.2, 2.3, 2.4, 2.5, 10.2, 10.3, 10.4, 10.5, 10.7, 10.8, 10.9, 24.1, 24.2, 24.3_

- [x] 9. 开局守军
  - [x] 9.1 实现
    - catalog.py：`FACTION_LOADOUT["tribe"]["garrison"] = ("spear", "spear", "spear", "wolf", "javelin")`、`START_GARRISON_OFFSETS`、`faction_start_garrison(faction)`（§1.5）；tech、magic 不加 garrison，`infantry`/`armor` 全部保持；server 再导出
    - server.py `start_game` 按 §2.9 落位；packedStart 地图仍只发基地车
    - _Requirements: 13.1, 13.2, 13.3, 13.4, 13.5, 13.6, 13.7, 13.8, 13.9_
  - [x] 9.2 测试
    - tests/tribe_test.py：保留 infantry/armor 断言，新增 garrison 与 `faction_start_garrison("tribe")` 断言，出生单位精确断言为 `sorted(["spear"] * 3 + ["javelin", "wolf", "tharvester"])`
    - tests/tribe_redesign_test.py：钢铁、秘法守军的 kind、创建顺序与坐标和改动前一致；每个阵营守军数 ≤ 落位格数且阵营正确
    - 运行 `python run_tests.py`，排查是否有测试依赖单位 id 序号（部落开局多 1 个单位），有则修正该测试
    - _Requirements: 13.1, 13.2, 13.3, 13.5, 13.6, 13.7, 13.8, 13.9_

- [x] 10. Checkpoint：玩法核心
  - 运行 `python run_tests.py`、`node tests/unit_geometry_test.mjs`、`node tests/model_picker_test.mjs`、`node tests/river_art_test.mjs`、`node tests/visual_benchmark_test.mjs`，全部通过后再继续；有失败先修复，有疑问先问用户

- [x] 11. 内置 bot 与 ai_commander
  - [x] 11.1 bot 驯兽师过滤与选兵
    - server.py 新增 `BOT_TAMER_CAP = 2`、`BOT_TAMER_MIN_BEASTS = 3`、`bot_tame_targets_available`、`bot_filter_choices`，在 `bot_try_choices` 入口先过滤再去重排序（§3.2），`bot_support_choices`/`bot_unit_choices` 签名不变
    - 按 §3.1 更新 tribe 分支选兵列表（support、inbound、vehicles ≥ 3、defend、late 以及 `bot_queue_unit` 的 late_choices），inbound 与反载具分支去掉 wolf 和 tamer
    - 按 §3.3 调整 `BOT_CHEAP_KINDS`、`BOT_INFANTRY_KINDS`、`BOT_LATE_UNITS`
    - _Requirements: 14.1, 14.2, 14.3, 14.4, 14.5, 14.6, 14.7, 14.8, 15.1, 15.2, 15.3, 15.4, 15.5, 15.6, 15.7, 15.8, 15.9, 15.10, 15.11, 15.12_
  - [x] 11.2 ai_commander 部落模板
    - ai_commander/templates.py 按 §3.4 更新 tribe 模板（每格 ≤ 4 种、不含 tamer、light 与 heavy 桶每格含 javelin 或 scorpion），注释写明倍率
    - 运行 `python ai_commander/selftest.py` 与 `python tests/ai_commander_test.py`
    - _Requirements: 16.1, 16.2, 16.3, 16.6_
  - [x] 11.3 测试（Property 9 与冒烟）
    - tests/tribe_redesign_test.py 加 Property 9：对 (中立开关 × 可驯目标 × 野兽数 0–6 × tamer 存量 0–3 × 候选列表) 完整枚举 `bot_filter_choices`；各分支选兵列表断言
    - 在中立关闭的地图上跑 `tick_bots` 若干轮冒烟，断言 tamer 存量（含队列）不超过规则上限
    - 更新 tribe_p1_test、tribe_p2_test、tribe_spider_test、tribe_scorpion_test 中与 bot 选兵相关的断言（如巨蝎不再需要祭坛）
    - 运行上述测试与 `python tests/bot_test.py`
    - _Requirements: 14.2, 14.3, 14.4, 14.5, 14.6, 14.7, 15.1, 15.2, 15.3, 15.4, 15.5, 15.6, 15.7, 15.8_

- [x] 12. HUD 文案、克制表与肖像
  - [x] 12.1 app.js 文案与选中面板
    - 按 §4.8 更新 `UNIT_VFX`、`BUILDING_VFX`、`FACTION_COPY.tribe`；选中兽夹时按实体帧 `charges` 显示「剩余 n/2 次」，选中带 `marked` 的单位显示「猎印」
    - _Requirements: 26.1, 26.2, 26.3, 26.4, 26.5, 26.6, 26.7_
  - [x] 12.2 新单位肖像
    - `PORTRAIT_PAINTERS` 新增 javelin 与 catapult（§4.8）
    - _Requirements: 26.8_
  - [x] 12.3 克制表
    - public/index.html 按需求 27 更新营地、围栏、塔、兽夹各行，并在说明区加猎印与号令、控制规则两行
    - _Requirements: 27.1, 27.2, 27.3, 27.4_
  - [x] 12.4 测试
    - presentation_rules_test 追加：两种新单位名称出现在 HUD、克制表新行与说明、两个肖像 painter 存在
    - 运行 `python tests/presentation_rules_test.py`
    - _Requirements: 26.1, 26.8, 27.1, 27.2, 27.3, 27.4_

- [x] 13. 确定性交战回归
  - [x] 13.1 新建 tests/tribe_combat_test.py（Property 10）
    - 按需求 18 与 design.md「交战回归表」搭建环境与场景，种子 11、23、37、41、53，建单位前 `random.seed`
    - 先跑一遍拿实测值写进注释：决定性场景区间取实测 ±0.15（截断到 [0, 1]），胜负方向与场景类别按表保持；均势场景只断言 |margin| 上限（1v1 0.30、混战 0.60），不随实测收紧
    - 猎印 A/B：临时把 `HUNT_MARK_BONUS` 置 1.0 对比，finally 中恢复
    - 若实测胜负方向或场景类别与表不一致，停下记录差异并报告，不擅自改平衡数值
    - 运行 `python tests/tribe_combat_test.py`
    - _Requirements: 18.1, 18.2, 18.3, 18.4, 18.5, 18.6, 18.7_

- [x] 14. Checkpoint：玩法完成
  - 运行 `python run_tests.py` 与 `python ai_commander/selftest.py`，全部通过后再进入美术阶段；有失败先修复，有疑问先问用户

- [x] 15. 近景美术基础设施
  - [x] 15.1 rig 扩展与脏检查
    - public/river_art_models.js：`artJointAngle(rig, time, travel, motion, sinceFire = Infinity)` 支持 strike、roll 与 walk 参数（rate、amp、gain、phase），wing 公式不变，未知 mode 返回 0（§4.3）
    - public/render3d.js 的 rig 循环传入 `sinceFire`、支持 `axis === 'y'`；加实例版本脏检查，变换与角度未变时不重写 rig 矩阵、无写入时不置 `needsUpdate`
    - _Requirements: 20.1, 20.2, 20.3, 20.4, 20.5, 20.6, 20.7, 20.8, 20.9, 20.11_
  - [x] 15.2 tribe_art_models.js 骨架与分派
    - 新建 public/tribe_art_models.js（只 import three），导出 `TRIBE_ART_KINDS`、`TRIBE_ART_STRUCTURES`（本任务先为空集合）、`tribeUnitModel`、`tribeStructureDetails`，以及工具 `uprightShell`、`rig`、`paintTeam`（§4.1）
    - river_art_models.js：`RIVER_ART_KINDS` 并入 `TRIBE_ART_KINDS`，`riverUnitModel` 与 `riverStructureDetails` 按集合分派并注入原语；render3d.js 调用处扩充注入的原语
    - _Requirements: 19.1, 19.2_
  - [x] 15.3 新建 tests/tribe_art_test.mjs（Property 12 与检查框架）
    - 按 river_art_test.mjs 的方式抽取源码构建几何
    - Property 12：确定性 LCG 生成 1000 组输入，检查关节角有限、walk 有界且在 travel 环绕处连续、strike 区间与归位、静止归位、side 对称、roll 公式、未知 mode 返回 0
    - 建立按 `TRIBE_ART_KINDS` 遍历的 Property 11 检查框架（预算、rig 数与参数、有限属性、可拾取、远景一致、队色、毛皮零件），集合为空时跳过
    - 运行 `node tests/tribe_art_test.mjs`、`node tests/river_art_test.mjs`、`node tests/model_picker_test.mjs`、`node tests/unit_geometry_test.mjs`
    - _Requirements: 20.2, 20.3, 20.4, 20.5, 20.6, 20.7, 20.9_

- [x] 16. 兽毛材质（依赖 15）
  - [x] 16.1 实现
    - render3d.js 冻结对象 `SURF` 加 `fur: 3.25`；river_art_materials.js 的 `applyRiverPBR` 按 §4.5 注入程序化毛流、粗糙度 0.9、视距 600 → 1400 淡出；PBR 程序缓存键 `-river-pbr-v3` → `-river-pbr-v4`
    - 烘焙图集保持 2×2、宽 512，不新增纹理与采样；`HIDE_UNIT_KINDS` 源码字符串不动
    - _Requirements: 21.1, 21.2, 21.3, 21.4, 21.5, 21.6, 21.8_
  - [x] 16.2 测试
    - tribe_art_test.mjs 加：`riverFur` 注入存在、缓存键为 v4、图集宽度仍为 512、3.25 在非样板着色器里不进入晶体与金属度分支；如 river_art_test 或 render_quality_test 断言了旧缓存键，同步更新
    - 运行 `node tests/tribe_art_test.mjs`、`node tests/river_art_test.mjs`、`node tests/render_quality_test.mjs`、`node tests/asset_warmup_test.mjs`
    - _Requirements: 21.1, 21.2, 21.4, 21.5, 21.6_

- [x] 17. 双足近景：spear、javelin、slinger、tamer（依赖 15、16）
  - [x] 17.1 模型
    - tribe_art_models.js 按 §4.2 实现四个兵种的近景主体（uprightShell 躯干、头部、武器与服饰），各带 2 个 walk 腿 rig（§4.3 参数），队色落在腰布、羽饰、斗篷镶边等大面积织物上，三角 ≤ 1600
    - javelin 的后举标枪与背后三支标枪要和骨矛手、投石手第一眼可区分；皮肤与木头用石纹（kind 1）
    - 完成后把四个 kind 加入 `TRIBE_ART_KINDS`
    - _Requirements: 19.3, 19.4, 19.5, 19.6, 19.7, 19.9, 20.10, 22.1, 22.2_
  - [x] 17.2 测试
    - tribe_art_test.mjs 的 Property 11 覆盖这四个 kind
    - 运行 `node tests/tribe_art_test.mjs`、`node tests/river_art_test.mjs`、`node tests/model_picker_test.mjs`、`node tests/unit_geometry_test.mjs`、`python tests/presentation_rules_test.py`
    - _Requirements: 19.4, 19.5, 19.6, 19.7, 20.10, 22.1_

- [x] 18. 四足近景：wolf、tharvester、mammoth（依赖 16、17）
  - [x] 18.1 模型
    - 按 §4.2 实现，4 个腿 rig 对角同相（左前与右后 side +1，右前与左后 −1），毛皮零件 aSurf 3.25，队色落在战纹、背毯、筐罩布、轿旗等处
    - 预算：wolf ≤ 2600、tharvester ≤ 3000、mammoth ≤ 4800；完成后加入 `TRIBE_ART_KINDS`
    - _Requirements: 19.3, 19.4, 19.5, 19.6, 19.7, 20.9, 20.10, 21.7, 22.1, 22.2_
  - [x] 18.2 测试
    - Property 11 覆盖这三个 kind，并断言各自至少有一个 aSurf 3.25 的零件
    - 运行同 17.2 的命令
    - _Requirements: 19.4, 20.9, 21.7, 22.1_

- [x] 19. Checkpoint：美术第一批
  - 运行全部 `tests/*.mjs` 与 `python run_tests.py`，全部通过后再继续；有失败先修复，有疑问先问用户

- [x] 20. 蛛与蝎近景：spider、scorpion（依赖 15）
  - [x] 20.1 模型
    - 按 §4.2 与 §4.3：8 条腿分 A、B 两组，绕竖直轴（axis 'y'）的 walk rig（rate 0.5）；蝎尾用 strike rig；甲壳用鳞片（kind 3），刚毛 3.25，骨饰用石纹
    - 预算各 ≤ 3200；完成后加入 `TRIBE_ART_KINDS`
    - _Requirements: 19.3, 19.4, 19.5, 19.6, 19.7, 19.9, 20.4, 20.10, 22.1, 22.2_
  - [x] 20.2 测试
    - Property 11 覆盖这两个 kind；运行同 17.2 的命令
    - _Requirements: 19.4, 20.10, 22.1_

- [x] 21. 熊猫近景（依赖 16）
  - [x] 21.1 模型
    - 保持已确认的功夫熊猫造型与配色（圆滚黑白、眼斑、腰封、左臂护体右掌抬、0.90 条带），改用连续体积；2 个 walk 腿 rig 加双掌 strike rig；黑白毛 aSurf 3.25，腰封走布料
    - 预算 ≤ 3000；完成后加入 `TRIBE_ART_KINDS`
    - _Requirements: 19.3, 19.4, 19.5, 19.6, 19.7, 19.8, 20.4, 20.10, 21.7, 22.1, 22.2_
  - [x] 21.2 测试
    - Property 11 覆盖 panda；运行同 17.2 的命令，另跑 `python tests/tribe_p2_test.py`
    - _Requirements: 19.4, 19.8, 21.7, 22.1_

- [x] 22. 投石车与迁徙驮队近景（依赖 16、18）
  - [x] 22.1 模型
    - catapult：实心木轮、A 字框、扭绳束、抛臂 strike rig 与轮轴 roll rig（radius 4.0），皮兜与框上队旗走队色
    - tmcv：两头驮畜拉兽皮篷橇，同位腿共用 4 个 walk rig，篷面条纹与旗幡走队色，毛皮 aSurf 3.25
    - 预算各 ≤ 3500；完成后加入 `TRIBE_ART_KINDS`
    - _Requirements: 19.3, 19.4, 19.5, 19.6, 19.7, 20.4, 20.6, 20.8, 20.10, 21.7, 22.1, 22.2_
  - [x] 22.2 测试
    - Property 11 覆盖这两个 kind，并检查 roll rig 的半径约束；运行同 17.2 的命令
    - _Requirements: 19.4, 20.6, 20.8, 21.7, 22.1_

- [x] 23. 部落建筑近景细节（依赖 15）
  - [x] 23.1 实现
    - `tribeStructureDetails` 为 thq、tspiketower、ttoxtower 按 §4.6 实现细节，完整替换近景主体，炮塔头与旋转件沿用现有；薄夯土地基使 `mergeParts` 写入负破拆半径；每座至少一处队色；GLOW 零件不参与 AO
    - 预算 thq ≤ 6000、tspiketower ≤ 3000、ttoxtower ≤ 3200；完成后加入 `TRIBE_ART_STRUCTURES`；`structureParts` 基础分支不改
    - _Requirements: 22.3, 23.1, 23.2, 23.3, 23.4, 23.5, 23.6, 23.7_
  - [x] 23.2 测试（Property 13）
    - tribe_art_test.mjs：aBreak 条目数等于顶点数且有限、至少一个 aTeam = 1 的顶点、存在负破拆半径的地基零件、三角预算、关闭样板时几何不变
    - 运行 `node tests/tribe_art_test.mjs`、`node tests/river_art_test.mjs`、`node tests/battlefield_finish_test.mjs`、`node tests/model_picker_test.mjs`、`python tests/presentation_rules_test.py`
    - _Requirements: 22.3, 23.2, 23.3, 23.4, 23.6_

- [x] 24. 战斗特效
  - [x] 24.1 弹道与登记
    - render3d.js 新增 `PROJECTILE_STYLE.javelin` 与 `PROJECTILE_STYLE.megalith`（§4.7），每发弹丸最多 4 个 tracer、2 个 orb、2 个 shard；开火高度白名单与 `emitProjectileTrail` 加入两种弹种；未知弹种回退 bullet
    - battle_feedback.js 的 `weaponFamily` 登记 `javelin` → sting、`megalith` → heavy，`MUZZLE_POINTS` 登记 `javelin: [10, 14]`、`catapult: [-4, 34]`
    - _Requirements: 25.1, 25.2, 25.3, 25.8, 25.9_
  - [x] 24.2 状态标记、光环与治疗微粒
    - 猎印爪痕标记（同屏 ≤ 128）、号令光环（按目录 `commandAuraRadius`，同屏 ≤ 32，缺字段不画，不硬编码 220）、祭坛治疗暖红金光点（受 `particleBudget × 0.62` 约束）、带 `rootResist` 时定身光点改淡白
    - 保持实例化与合并几何，不为每个标记新建 Mesh
    - _Requirements: 25.4, 25.5, 25.6, 25.7, 25.10, 31.6_
  - [x] 24.3 测试
    - tribe_art_test.mjs：新弹道样式存在、每弹实例数不超容量、爪痕与光环网格上限；presentation_rules_test 追加 `look: 'javelin'`、`look: 'megalith'`
    - 运行 `node tests/tribe_art_test.mjs`、`node tests/battle_feedback_test.mjs`、`python tests/presentation_rules_test.py`
    - _Requirements: 25.1, 25.2, 25.3, 25.4, 25.5, 25.8_

- [x] 25. 可视基准与 README
  - [x] 25.1 visual_benchmark 部落档
    - tests/visual_benchmark.html 的 `profiles` 加入 `tribe` 档（12 个部落 kind）；tests/visual_benchmark_test.mjs 追加对应断言
    - 运行 `node tests/visual_benchmark_test.mjs`
    - _Requirements: 29.1_
  - [x] 25.2 README
    - 按 design.md §4.10 更新部落段落，另起一行写跨阵营控制规则；presentation_rules_test 追加两种新单位名称出现在 README 的断言
    - 运行 `python tests/presentation_rules_test.py`
    - _Requirements: 28.1, 28.2, 28.3, 28.4, 28.5, 28.6_

- [x] 26. Checkpoint：最终回归
  - 运行 `python run_tests.py`、`python ai_commander/selftest.py`、`node tests/tribe_art_test.mjs`、`node tests/river_art_test.mjs`、`node tests/unit_geometry_test.mjs`、`node tests/model_picker_test.mjs`、`node tests/visual_benchmark_test.mjs` 以及其余全部 `tests/*.mjs`
  - 确认 Python 3.6 兼容（无 3.7+ 语法与库特性）、无新依赖、无新位图、钢铁与秘法数值除控制规则外未变
  - _Requirements: 31.1, 31.2, 31.3, 31.4, 31.9_

- [x]* 27. 渲染性能对照（需浏览器与 GPU）
  - 按需求 29.2 至 29.6 与 design.md「手动验收」执行，结果写入 tests/tribe_redesign_acceptance.md（Acceptance_Log）；出现回退时按需求 29.6 的两级回退处理
  - 无浏览器时在 Acceptance_Log 中把 29.2 至 29.6 记为「未验证」
  - _Requirements: 29.2, 29.3, 29.4, 29.5, 29.6, 29.7_

- [x]* 28. 画面手动验收（需浏览器）
  - 按需求 30 的清单近看 12 个部落单位与 3 座建筑，结果写入同一 Acceptance_Log
  - 无浏览器时把 30.1 至 30.8 记为「未验证」
  - _Requirements: 30.1, 30.2, 30.3, 30.4, 30.5, 30.6, 30.7, 30.8, 30.9_

## Notes

- 均势场景（巨蝎单挑坦克、2 标枪打 1 坦克、大混战）只断言 |margin| 上限；决定性场景按实测 ±0.15 标定，胜负方向不符时停下报告。
- 部落开局多 1 个单位，之后的单位 id 序号整体后移 1；任务 9.2 必须跑全量测试排查。
- PBR 缓存键升级到 v4 会让相关着色器重新编译一次，程序数量应保持不变；任务 16.2 与最终回归要确认预热测试通过。
- 近景 rig 最多新增约 34 个批次（全阴影时 68）；性能回退按需求 29.6 的两级回退处理。
- 棘矛加毒矢组合、巨蝎加骨矛与大混战的离线估算未按新数值重估，以任务 13 的实测为准。

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1"] },
    { "id": 1, "tasks": ["1.2"] },
    { "id": 2, "tasks": ["2.1"] },
    { "id": 3, "tasks": ["2.2"] },
    { "id": 4, "tasks": ["2.3"] },
    { "id": 5, "tasks": ["4.1"] },
    { "id": 6, "tasks": ["4.2"] },
    { "id": 7, "tasks": ["4.3"] },
    { "id": 8, "tasks": ["5.1"] },
    { "id": 9, "tasks": ["5.2"] },
    { "id": 10, "tasks": ["7.1"] },
    { "id": 11, "tasks": ["7.2"] },
    { "id": 12, "tasks": ["8.1"] },
    { "id": 13, "tasks": ["8.2"] },
    { "id": 14, "tasks": ["8.3"] },
    { "id": 15, "tasks": ["9.1"] },
    { "id": 16, "tasks": ["9.2"] },
    { "id": 17, "tasks": ["11.1"] },
    { "id": 18, "tasks": ["11.2"] },
    { "id": 19, "tasks": ["11.3"] },
    { "id": 20, "tasks": ["12.1"] },
    { "id": 21, "tasks": ["12.2"] },
    { "id": 22, "tasks": ["12.3"] },
    { "id": 23, "tasks": ["12.4"] },
    { "id": 24, "tasks": ["13.1"] },
    { "id": 25, "tasks": ["15.1"] },
    { "id": 26, "tasks": ["15.2"] },
    { "id": 27, "tasks": ["15.3"] },
    { "id": 28, "tasks": ["16.1"] },
    { "id": 29, "tasks": ["16.2"] },
    { "id": 30, "tasks": ["17.1"] },
    { "id": 31, "tasks": ["17.2"] },
    { "id": 32, "tasks": ["18.1"] },
    { "id": 33, "tasks": ["18.2"] },
    { "id": 34, "tasks": ["20.1"] },
    { "id": 35, "tasks": ["20.2"] },
    { "id": 36, "tasks": ["21.1"] },
    { "id": 37, "tasks": ["21.2"] },
    { "id": 38, "tasks": ["22.1"] },
    { "id": 39, "tasks": ["22.2"] },
    { "id": 40, "tasks": ["23.1"] },
    { "id": 41, "tasks": ["23.2"] },
    { "id": 42, "tasks": ["24.1"] },
    { "id": 43, "tasks": ["24.2"] },
    { "id": 44, "tasks": ["24.3"] },
    { "id": 45, "tasks": ["25.1"] },
    { "id": 46, "tasks": ["25.2"] },
    { "id": 47, "tasks": ["27", "28"] }
  ]
}
```


## Codex 接续完成记录（2026-10-03）

接手时基础集合、常量和跨阵营控制规则已实现，旧测试已有更新。接续完成猎印、号令、塔与双次兽夹、野兽治疗、标枪手/投石车、守军、bot/AI 模板、HUD/肖像/克制表、交战回归、12 单位/3 建筑近景模型与特效，以及浏览器验收。

- Python 离线脚本 76 项、JavaScript 脚本 28 项、AI 自检 70 项全部通过。
- 14 个交战场景 × 5 种子符合设计方向；钢铁/秘法目录逐条未变，Python 3.6 语法检查通过。
- 全目录加载后按设计启用关节不额外投影和中距离静态合并，保留近景动作与中距离攻击动作；队色初始化避免额外缓存程序。
- 完整目录预热后，400 单位部落档和全目录混编档各进行两轮新旧对照；FPS、帧时间和绘制批次达标。
- 验收依据与实测表见 tests/tribe_redesign_acceptance.md；截图保留在本地 artifacts/river-art-captures/。
