# Requirements Document

## Introduction

本文由 `design.md`（原始部落重设计，design-first）派生，描述可验收的行为与约束。范围：决策 A–K（新单位、数值调整、祭坛治疗、驯兽号令、猎印与封顶、跨阵营控制规则、开局守军、bot 与 ai_commander、交战回归）、已确认决策 1–4，以及部落美术升级（近景模型、关节动画、兽毛材质、队色、建筑细节、特效、HUD、肖像、克制表、README）与性能、画面验收。

约定：

- 数值与 `design.md` 一致；运行时以 `catalog.py` 为唯一来源。
- 除特别说明外，伤害数值指零军衔攻击者一次结算的值，护甲倍率取 `DAMAGE_MULTIPLIER`（缺项按 1.0）。
- 引用 `design.md §x.y` 的验收标准以该节表格为准。
- 需求 29、30 需要浏览器与 GPU；无浏览器环境时记为「未验证」。
- 非目标：不加自爆、不做超远程炮、不改地图与中立营编制、不加依赖、不生成新位图；除控制规则外不改钢铁与秘法数值。

| 范围 | 需求 |
|---|---|
| A 燧石标枪手 | 1 |
| B 穿甲巨蝎（已确认决策 2） | 2 |
| C 塔与兽夹（已确认决策 1、4） | 3、4、5 |
| D 祭坛治疗 | 6 |
| E 驯兽师与 bot | 7、14 |
| F 猎印与封顶 | 8、9 |
| G 巨石投石车 | 10 |
| H 跨阵营控制规则 | 11、12 |
| I 开局守军（已确认决策 3） | 13 |
| J bot 与 ai_commander | 15、16 |
| 状态与目录下发 | 17 |
| K 交战回归 | 18 |
| 美术：近景管线与三角预算、rig 动画、兽毛材质、队色、建筑细节、新单位基础资产 | 19–24 |
| 特效、HUD 与肖像、克制表、README | 25–28 |
| 性能与画面手动验收 | 29、30 |
| 工程约束 | 31 |

## Glossary

- **System**：本次改动涉及的全部服务端、客户端代码、测试与文档。
- **Catalog**：`catalog.py` 中的单位/建筑目录、常量、集合、`FACTION_LOADOUT` 与 `public_catalog()`，全部数值的唯一来源。
- **Server**：`server.py` 的权威结算层（伤害、状态计时、生产、维修、开局与实体下发）。
- **Bot**：`server.py` 中的内置 AI（`tick_bots` 与 `bot_*` 函数）。
- **AI_Commander**：`ai_commander/` 插件（`templates.py`、`commander.py`、`codex.py`）。
- **Renderer**：客户端表现层，包括 `public/render3d.js`、`public/tribe_art_models.js`（新）、`public/river_art_models.js`、`public/river_art_materials.js`、`public/battle_feedback.js`。
- **HUD**：`public/app.js` 与 `public/index.html` 中的文案、选中面板、肖像与克制表。
- **README**：仓库根目录的 `README.md`。
- **Test_Suite**：`tests/` 下的 Python 与 Node 测试、`run_tests.py`、`ai_commander/selftest.py` 与 `tests/visual_benchmark.html`。
- **Acceptance_Log**：需要浏览器与 GPU 的手动验收结论记录。
- **部落**：`faction=tribe` 的阵营「原始部落」。
- **野兽**：kind 属于 `TRIBE_BEAST_KINDS`（`wolf`、`spider`、`scorpion`、`mammoth`、`panda`）的单位。
- **猎手**：kind 属于 `HUNT_MARK_SOURCES`（`spear`、`slinger`、`javelin`）的单位。
- **猎印**：猎手命中存活单位后写入的 `huntMarkTimer`（4.0 s）；野兽对带猎印单位的伤害 ×1.15，受封顶约束。
- **驯兽号令**：驯兽师 `commandAura` 为 220 半径内己方或盟友野兽提供的 ×1.10 攻击倍率，多名驯兽师不叠加。
- **部落加成（tribeBonus）**：野兽开火时确定并写入弹丸的攻方倍率 min(`TRIBE_BONUS_CAP`, 狂暴倍率 × 号令倍率)。
- **封顶**：狂暴 × 号令 × 猎印连乘的上限 `TRIBE_BONUS_CAP` = 1.45；军衔倍率与 `fielded_combat_multiplier` 在封顶之外。
- **减速强度**：`slowMult` 的数值，越小越强。
- **定身**：`slowMult` 为 0 且 `slowTimer` 大于 0 的状态。
- **定身抗性**：定身结束时写入的 `rootResist` 计时（1.0 s），期间新施加的定身降为 ×0.5 减速。
- **持续伤害（DoT）**：由 `dotDps`、`dotTimer` 等字段描述、由 `tick_dot` 结算的伤害；强度 = dps × 伤种对目标护甲的倍率。
- **零军衔**：`kills` 低于首个军衔门槛（3）、伤害倍率为 1.0 的单位。
- **可驯中立作战单位**：owner 为 `NEUTRAL_OWNER` 且 `is_tameable_combat_unit` 为真的单位。
- **inbound**：bot 检测到敌方自爆单位逼近己方基地的状态。
- **packedStart 地图**：开局只发一辆行营的地图（五车争霸、裂谷旷野）。
- **开局守军**：非 packedStart 地图开局时在总部旁生成的作战单位。
- **近景样板**：`RIVER_ART_KINDS` 使用的近景高精度模型与 PBR 材质管线；关闭时回到基础 builder 与原材质。
- **远景 LOD**：`simpleUnitParts` 生成的远距简模。
- **rig**：近景模型中绕枢轴转动的零件组（腿、尾、掌、抛臂、轮轴），每兵种每 rig 一个 InstancedMesh。
- **队色通道**：零件 paint 为数字时写入 `aTeam = 1`、按 owner 颜色着色的通道。
- **剩余价值比**：一方 Σ cost × hp/maxHp ÷ 该方初始造价。
- **margin**：部落方（含部落防御塔）剩余价值比 − 对手方剩余价值比。
- **决定性场景**：离线估算中各种子胜负一致、且胜方剩余价值比 ≥ 0.15 的回归场景。
- **均势场景**：不满足决定性场景条件的回归场景。

## Requirements

### Requirement 1: 燧石标枪手（决策 A）

**User Story:** 作为部落玩家，我想在猎手营地训练反甲步兵，以便在建成血祭坛之前就能正面对抗坦克。

#### Acceptance Criteria

1. THE Catalog SHALL 定义单位 `javelin`：name「燧石标枪手」、cost 360、hp 110、speed 96、damage 40、range 200、cooldown 1.25、projectile `javelin`、projectileSpeed 560、splash 0、damageType `rocket`、armor `infantry`、producer `tcamp`、requires 为空、build 5、size 10.5、基础 sight 390、`huntMark` 为真。
2. THE Catalog SHALL 把 `javelin` 加入 `TRIBE_UNITS`，使 `kind_faction("javelin")` 返回 `tribe`。
3. WHEN 拥有已建成猎手营地、没有血祭坛的部落玩家排产 `javelin`，THE Server SHALL 接受该排产。
4. IF 非部落阵营的玩家排产 `javelin`，THEN THE Server SHALL 拒绝该排产并返回错误。
5. WHEN 零军衔 `javelin` 的弹丸直击重甲、轻甲、步兵单位，THE Server SHALL 分别结算 60、52、30 伤害（40 × rocket 倍率 1.50、1.30、0.75）。
6. WHEN `javelin` 的弹丸命中，THE Server SHALL 只对直击目标结算伤害。

### Requirement 2: 穿甲巨蝎调整（决策 B，已确认决策 2）

**User Story:** 作为部落玩家，我想只靠驯兽围栏就能驯养穿甲巨蝎，并让它单挑坦克不再必亏，以便在血祭坛之前拥有野兽反甲手段。

#### Acceptance Criteria

1. THE Catalog SHALL 定义 `scorpion` 的 hp 为 250、range 为 165、`requires` 为空列表（保留该键），其余字段保持 cost 820、speed 100、damage 82、cooldown 1.80、projectile `sting`、projectileSpeed 640、splash 0、damageType `ap`、armor `beast`、producer `tpen`、build 7.5、size 13、sight 390。
2. WHEN 拥有已建成驯兽围栏、没有血祭坛的部落玩家排产 `scorpion`，THE Server SHALL 接受该排产。
3. THE Catalog SHALL 保持 hp 次序 `wolf`（200）< `scorpion`（250）< `spider`（340），并使 `scorpion` 的 hp 与 range 低于 `tank_destroyer`（400、230）。
4. WHEN 零军衔 `tank` 的炮弹连续直击满血 `scorpion`（期间无回血），THE Server SHALL 在前 4 次直击后保持 `scorpion` 存活（剩余 hp 18.8），并在第 5 次直击时击毁 `scorpion`。
5. WHEN 零军衔 `scorpion` 的尾刺直击 `tank`，THE Server SHALL 结算 172.2 伤害（82 × ap 对重甲 2.10）。
6. THE Catalog SHALL 在 `public_catalog()` 中下发 `scorpion` 的 `requires` 为空列表。

### Requirement 3: 棘矛哨塔（决策 C，已确认决策 4）

**User Story:** 作为部落玩家，我想要一座比钢铁、秘法近防塔便宜一档的中距反甲塔，以便在营地阶段守住单辆坦克的骚扰。

#### Acceptance Criteria

1. THE Catalog SHALL 定义 `tspiketower`：cost 800、hp 1050、damage 62、range 270、cooldown 0.85、splash 20、damageType `shell`，requires 保持 `["tcamp", "tpower"]`，projectile 保持 `spike`。
2. WHEN 棘矛哨塔的弹丸直击重甲单位，THE Server SHALL 结算 62 伤害（shell 对重甲 1.00）。
3. THE Catalog SHALL 使 `tspiketower` 的造价比 `turret` 与 `mtower`（均为 950）低 150。

### Requirement 4: 毒矢高台（决策 C，已确认决策 1）

**User Story:** 作为部落玩家，我想要一座既能单挑坦克、又能用扩散的毒压制步兵群的后期远程塔，以便部落后期防线不被装甲突破。

#### Acceptance Criteria

1. THE Catalog SHALL 定义 `ttoxtower`：cost 1100、hp 1000、damage 34、range 360、cooldown 1.20、splash 28、damageType `ap`、`dot` 为 `{"dps": 16.0, "duration": 3.2, "damageType": "venom"}`，requires 保持 `["taltar", "tpower"]`，projectile 保持 `dart`，projectileSpeed 保持 500。
2. WHEN 毒矢高台的弹丸直击护甲为 X 的单位，THE Server SHALL 结算 34 × `DAMAGE_MULTIPLIER["ap"][X]` 的直击伤害（重甲 71.4、轻甲 22.1、步兵 8.5）。
3. WHEN 毒矢高台的弹丸命中，THE Server SHALL 对与落点距离 r < 28 的每个非友方存活实体（直击目标除外）结算 34 × 0.45 × (1 − r/28) × ap 倍率的溅射伤害。
4. WHEN 毒矢高台的弹丸直击或溅射命中敌方存活单位，THE Server SHALL 按 Requirement 12 的规则为该单位施加 16/s、持续 3.2 s 的 venom 持续伤害。
5. THE Server SHALL 以 `dot.damageType`（`venom`）结算毒矢高台施加的持续伤害，与直击伤种 `ap` 无关。
6. IF 毒矢高台的溅射覆盖建筑，THEN THE Server SHALL 只对该建筑结算溅射伤害，不写入持续伤害。

### Requirement 5: 兽夹陷阱充能（决策 C）

**User Story:** 作为部落玩家，我想让一个兽夹触发两次，以便一次布置能拦截两波冲锋，同时无法形成连锁定身。

#### Acceptance Criteria

1. THE Catalog SHALL 定义 `ttrap` 的 `trapExpire` 为假、`trapCharges` 为 2、`trapCooldown` 为 8.0，并保持 cost 320、hp 140、trapDamage 75（shell）、trapRadius 44、trapArm 2.2、定身 0/2.0 不变。
2. WHEN Server 创建兽夹实体，THE Server SHALL 把该兽夹的 `charges` 设为 `trapCharges`（2）。
3. WHEN 已上膛兽夹的触发半径内出现敌方地面单位且 `charges` 大于 1，THE Server SHALL 对半径内每个敌方地面单位结算 75 伤害并按 Requirement 11 施加 2.0 s 定身，随后把 `charges` 减 1、`armed` 设为假、`armTimer` 设为 8.0，并保持兽夹 hp 大于 0。
4. WHILE 兽夹的 `armed` 为假，THE Server SHALL 只递减 `armTimer`，不对触发半径内的单位结算伤害或定身。
5. WHEN 兽夹以最后 1 次充能触发，THE Server SHALL 在同一帧经静默拆除路径（`_combatDestroyed` 与 `_silentRemoval`）移除该兽夹。
6. WHERE 陷阱定义 `trapExpire` 为假且未定义 `trapCharges`，THE Server SHALL 保持无限次重新上膛的现有行为。
7. IF 兽夹实体缺少 `charges` 字段，THEN THE Server SHALL 以目录 `trapCharges` 作为剩余次数。
8. THE Server SHALL 只让敌方地面单位触发兽夹。

### Requirement 6: 血祭坛治疗野兽（决策 D）

**User Story:** 作为部落玩家，我想把受伤的野兽送到血祭坛治疗，以便祭坛像维修厂一样养住主力。

#### Acceptance Criteria

1. THE Catalog SHALL 定义 `TRIBE_BEAST_KINDS` = {`wolf`, `spider`, `scorpion`, `mammoth`, `panda`}，且该集合等于目录中全部 `armor == "beast"` 的单位 kind。
2. THE Catalog SHALL 定义 `REPAIRABLE_KINDS` = `VEHICLE_KINDS` ∪ `TRIBE_BEAST_KINDS`。
3. WHEN 玩家对选中单位下达维修指令，THE Server SHALL 只接受 kind 属于 `REPAIRABLE_KINDS` 的受损单位。
4. IF 选中单位中没有可维修的受损单位，THEN THE Server SHALL 拒绝该指令并返回错误文案「请选择受损载具或野兽」。
5. IF 执行维修单的单位 kind 不属于 `REPAIRABLE_KINDS`，THEN THE Server SHALL 清除该维修单并把该单位转为 `guard`，不扣除资金。
6. WHEN 受损野兽在己方血祭坛维修，THE Server SHALL 按与载具相同的 `REPAIR_RATE`（105）与 `REPAIR_COST_PER_HP`（0.35）回血并扣除资金，回满后把该单位转为 `guard`。
7. THE Server SHALL 继续以 `VEHICLE_KINDS` 判定 bite ×0、`hold_target_valid`、`is_dog_prey` 与 `BOT_SCOUT_VEHICLES`，结果与改动前相同（`VEHICLE_KINDS` 唯一新增成员为 `catapult`）。
8. THE Catalog SHALL 在 `public_catalog()` 中为每个单位下发 `repairable`，取值等于该 kind 是否属于 `REPAIRABLE_KINDS`。

### Requirement 7: 驯兽师与驯兽号令（决策 E）

**User Story:** 作为部落玩家，我想让驯兽师在没有中立单位的地图上也能强化野兽，以便驯兽师在所有地图都有出场价值。

#### Acceptance Criteria

1. THE Catalog SHALL 定义 `tamer` 的 hp 为 90，并新增 `commandAura` = `{"radius": 220.0, "mult": 1.10}`，其余字段不变。
2. THE Catalog SHALL 把 `COMMAND_AURA_QUERY` 定义为全部单位 `commandAura.radius` 的最大值（220）。
3. WHEN 野兽开火，THE Server SHALL 在该帧查找中心距离 ≤ 220 的己方或盟友存活驯兽师，找到时把号令倍率取为 1.10，否则取 1.0。
4. WHILE 多名驯兽师同时覆盖同一野兽，THE Server SHALL 只取其中最大的号令倍率，不叠加。
5. THE Server SHALL 把正在读条招降的驯兽师计入号令，并把已阵亡、已移除或敌方的驯兽师排除在号令之外。
6. THE Server SHALL 只对野兽攻击者应用号令倍率，其他单位与建筑的号令倍率为 1.0。
7. THE Server SHALL 保持驯兽师招降中立作战单位的现有参数（`tameCost` 150、`tameTime` 4.0、`tameRange` 48）以及中立关闭时不可招降的现有行为。
8. WHEN 零军衔 `tank` 的炮弹连续直击满血驯兽师（期间无回血），THE Server SHALL 在第 3 次直击时击毁驯兽师（37.4 × 2 = 74.8 < 90）。

### Requirement 8: 猎印（决策 F）

**User Story:** 作为部落玩家，我想让猎手先给目标挂猎印、野兽再收割，以便步兵与野兽的配合有清楚可读的收益。

#### Acceptance Criteria

1. THE Catalog SHALL 为 `spear`、`slinger`、`javelin` 设置 `huntMark` 为真，并把 `HUNT_MARK_SOURCES` 派生为全部 `huntMark` 为真的单位 kind。
2. WHEN 来源 kind 属于 `HUNT_MARK_SOURCES` 的弹丸直击或溅射命中存活单位，THE Server SHALL 把该单位的 `huntMarkTimer` 设为 4.0（`HUNT_MARK_SECONDS`）。
3. WHEN 带猎印的单位再次被猎手命中，THE Server SHALL 把 `huntMarkTimer` 重置为 4.0，不累加。
4. IF 猎手命中的目标是建筑或已阵亡单位，THEN THE Server SHALL 不写入猎印。
5. IF 弹丸来源 kind 不属于 `HUNT_MARK_SOURCES`，THEN THE Server SHALL 保持目标的 `huntMarkTimer` 不变。
6. WHILE 单位的 `huntMarkTimer` 大于 0，THE Server SHALL 按经过时间递减 `huntMarkTimer`，下限为 0。
7. WHEN 来源 kind 属于 `TRIBE_BEAST_KINDS` 的弹丸直击或溅射命中 `huntMarkTimer` 大于 0 的单位，THE Server SHALL 把该次伤害乘以猎印倍率 max(1.0, min(1.15, 1.45 / `tribeBonus`))。
8. THE Server SHALL 对持续伤害结算以及非野兽来源的伤害使用猎印倍率 1.0。

### Requirement 9: 部落攻击加成连乘与封顶（决策 E、F）

**User Story:** 作为平衡设计者，我想让狂暴、号令与猎印的连乘有统一上限，以便组合收益可读且不会失控。

#### Acceptance Criteria

1. THE Catalog SHALL 定义 `TRIBE_BONUS_CAP` = 1.45、`HUNT_MARK_BONUS` = 1.15、`HUNT_MARK_SECONDS` = 4.0。
2. WHEN 野兽开火，THE Server SHALL 计算 `tribeBonus` = min(1.45, 狂暴倍率 × 号令倍率)，把弹丸伤害乘以 `tribeBonus` 并在弹丸上记录 `tribeBonus`；狂暴倍率在熊猫狂暴时为 1.25（`PANDA_RAGE_DAMAGE`），其余情况为 1.0。
3. THE Server SHALL 使一次直击的伤害等于 base × 军衔倍率 × `fielded_combat_multiplier` × min(1.45, 狂暴 × 号令 × 猎印) × 护甲倍率，溅射伤害再乘 0.45 × (1 − r/splash)。
4. IF 弹丸缺少 `tribeBonus` 字段，THEN THE Server SHALL 按 1.0 处理。
5. WHEN 未受号令覆盖的狂暴熊猫开火，THE Server SHALL 使弹丸伤害等于 72.5（58 × 1.25，与现有行为一致）。
6. WHEN 受号令覆盖的狂暴熊猫直击带猎印的单位，THE Server SHALL 使狂暴、号令、猎印三者的合计倍率等于 1.45（1.25 × 1.10 × 1.15 ≈ 1.58 被截断）。
7. WHEN 受号令覆盖的零军衔 `scorpion` 直击带猎印的 `tank`，THE Server SHALL 结算约 217.8 伤害（172.2 × 1.10 × 1.15），使 3 次直击击毁满血 `tank`。

### Requirement 10: 巨石投石车（决策 G）

**User Story:** 作为部落玩家，我想在血祭坛之后获得一种需要护送、能被反制的攻城器械，以便拆掉敌方近防塔而不依赖超远程炮。

#### Acceptance Criteria

1. THE Catalog SHALL 定义单位 `catapult`：name「巨石投石车」、cost 1000、hp 340、speed 48、damage 95、range 350、cooldown 2.4、projectile `megalith`、projectileSpeed 240、splash 60、damageType `siege`、armor `light`、producer `tpen`、requires `["taltar"]`、build 11、size 22、基础 sight 300（有效视野 385）。
2. THE Catalog SHALL 把 `catapult` 加入 `TRIBE_UNITS` 与 `VEHICLE_KINDS`，并使弹种名 `megalith` 不与其他单位或建筑的弹种重名。
3. IF 部落玩家在没有已建成血祭坛时排产 `catapult`，THEN THE Server SHALL 拒绝该排产。
4. WHEN `catapult` 自动索敌，THE Server SHALL 与 `artillery`、`colossus`、`comet` 相同地优先选择敌方建筑。
5. WHEN 玩家手动指定 `catapult` 的攻击目标，THE Server SHALL 攻击玩家指定的目标。
6. THE Catalog SHALL 使 `catapult` 的 range（350）大于 `artillery`（340）、`turret`（320）与 `tspiketower`（270），并小于 `mtower`、`ttoxtower`（360）与 `missile`、`mstorm`（420）。
7. WHEN 零军衔 `catapult` 的巨石直击建筑，THE Server SHALL 结算 171 伤害（95 × siege 对建筑 1.80）。
8. WHEN 军犬扑咬 `catapult`，THE Server SHALL 结算 0 伤害。
9. WHEN 受损 `catapult` 在己方血祭坛维修，THE Server SHALL 按 Requirement 6 的速率与费用为 `catapult` 回血。

### Requirement 11: 跨阵营减速与定身规则（决策 H）

**User Story:** 作为任意阵营的玩家，我想让减速与定身遵循「强者优先、定身不续时、结束后短暂抗性」，以便控制效果不会被对手的弱控制解除，也不会被连锁成永久定身。

#### Acceptance Criteria

1. THE Server SHALL 对全部阵营的减速与定身来源（冰霜女巫 0.45/2.5、雷暴塔 0.5/1.8、蛛网巨蛛 0/2.2、兽夹 0/2.0）应用本需求的规则，各来源数值不变。
2. THE Server SHALL 以 `slowMult` 比较减速强度：数值越小越强，0 表示定身。
3. WHEN 单位受到强度大于当前状态的减速或定身，THE Server SHALL 以新施加的倍率与时长覆盖当前状态。
4. WHEN 单位受到与当前减速同强度的减速，THE Server SHALL 把剩余时长设为 max(剩余时长, 新时长)。
5. IF 单位受到强度小于当前减速的减速，THEN THE Server SHALL 忽略该次施加。
6. WHILE 单位处于定身，THE Server SHALL 忽略新的定身施加，并保持定身剩余时长不变。
7. WHEN 单位的定身计时归零，THE Server SHALL 把 `slowMult` 恢复为 1.0，并写入 `rootResist` = 1.0 s（`ROOT_RESIST_SECONDS`）。
8. WHILE 单位的 `rootResist` 大于 0，THE Server SHALL 把新施加的定身改为倍率 0.5（`ROOT_RESIST_SLOW_MULT`）、时长不变的减速，再按 11.3–11.5 处理。
9. WHILE 单位的 `rootResist` 大于 0，THE Server SHALL 按经过时间递减 `rootResist`，下限为 0。
10. IF 减速施加的时长 ≤ 0，或目标是建筑、已阵亡单位，THEN THE Server SHALL 忽略该次施加。
11. THE Server SHALL 使任一连续定身段的时长不超过触发该段的那次施加时长，且相邻两段定身之间至少间隔 1.0 s（以固定步长 dt 推进时，两项各容差一个 dt）。
12. WHEN 单只蛛网巨蛛以 1.45 s 冷却持续命中同一目标 60 s，THE Server SHALL 使该目标处于定身的时间占比不超过 55%。
13. WHEN 冰霜女巫命中已定身单位，THE Server SHALL 保持该单位的定身与定身剩余时长。
14. WHEN 雷暴塔命中处于冰霜减速（0.45）的单位，THE Server SHALL 保持倍率 0.45 与原剩余时长。
15. WHEN 冰霜女巫命中处于雷暴塔减速（0.5）的单位，THE Server SHALL 把减速改为倍率 0.45、时长 2.5 s。

### Requirement 12: 跨阵营持续伤害规则（决策 H）

**User Story:** 作为任意阵营的玩家，我想让持续伤害强者优先、击杀归属清楚，以便多种毒源叠加时伤害不会被弱毒降级。

#### Acceptance Criteria

1. THE Server SHALL 对全部持续伤害来源（蛛网巨蛛 14/3.0、毒矢高台 16/3.2、毒雾坑 16/1.6）应用本需求的规则，各来源数值不变。
2. THE Server SHALL 以 dps × `DAMAGE_MULTIPLIER[dot 伤种][目标护甲]` 定义持续伤害强度。
3. IF 目标已有强度更大的持续伤害，THEN THE Server SHALL 忽略新的施加。
4. IF 目标已有同强度且剩余时长 ≥ 新时长的持续伤害，THEN THE Server SHALL 忽略新的施加。
5. WHEN 新施加的持续伤害强度更大，或强度相同且目标剩余时长短于新时长，THE Server SHALL 整组覆盖 `dotDps`、`dotTimer`、`dotDamageType`、`dotOwner`、`dotSourceId`、`dotSourceKind`。
6. WHEN 持续伤害计时归零，THE Server SHALL 清空全部持续伤害来源字段。
7. WHEN 持续伤害击杀目标，THE Server SHALL 把击杀归属给当时的 `dotOwner`（来源单位已移除时同样记给 `dotOwner`）。
8. IF 持续伤害施加的时长 ≤ 0，或目标是建筑、已阵亡单位，THEN THE Server SHALL 忽略该次施加。
9. WHEN 处于毒雾坑持续伤害（16）中的单位被蛛网巨蛛（14）命中，THE Server SHALL 保持 16 dps。

### Requirement 13: 开局守军（决策 I，已确认决策 3）

**User Story:** 作为部落玩家，我想要与钢铁守军价值相当、且不含血祭坛档单位的开局守军，以便开局防守不吃亏也不跨档。

#### Acceptance Criteria

1. THE Catalog SHALL 为 `FACTION_LOADOUT["tribe"]` 增加 `garrison` = (`spear`, `spear`, `spear`, `wolf`, `javelin`)，并保持 `infantry` = `spear`、`armor` = `wolf`。
2. THE Catalog SHALL 保持 `tech` 与 `magic` 的装备表不含 `garrison`，`infantry`/`armor` 分别为 `rifle`/`tank` 与 `mage`/`golem`。
3. THE Catalog SHALL 提供 `faction_start_garrison(faction)`：阵营定义了 `garrison` 时按原顺序返回该列表，否则返回 3 个 `infantry` 加 1 个 `armor`。
4. THE Catalog SHALL 定义 `START_GARRISON_OFFSETS` = ((75, 70), (91, 70), (107, 70), (92, 112), (123, 70), (124, 112))。
5. WHEN 非 packedStart 地图开局，THE Server SHALL 按 `faction_start_garrison` 的顺序创建守军，第 i 名位于出生点（总部）坐标加 (toward_x × dx_i, toward_y × dy_i)，(dx_i, dy_i) 取 `START_GARRISON_OFFSETS[i]`。
6. WHEN 钢铁或秘法玩家在非 packedStart 地图开局，THE Server SHALL 创建与改动前 kind、创建顺序与坐标都相同的 4 名守军。
7. WHEN 部落玩家在非 packedStart 地图开局，THE Server SHALL 创建 3 名 `spear`、1 名 `wolf` 与 1 名 `javelin`，守军造价合计 1310。
8. WHILE 地图为 packedStart 地图，THE Server SHALL 只为每名玩家发放一辆行营，不创建守军。
9. THE Catalog SHALL 使每个阵营的守军数量不超过 `START_GARRISON_OFFSETS` 的格数，且每名守军的 `kind_faction` 等于该阵营。

### Requirement 14: 内置 bot 驯兽师过滤（决策 E）

**User Story:** 作为与部落 bot 对战的玩家，我想让 bot 只在驯兽师有用时才训练驯兽师，以便部落 bot 在无中立地图上不浪费资金。

#### Acceptance Criteria

1. THE Bot SHALL 定义 `BOT_TAMER_CAP` = 2 与 `BOT_TAMER_MIN_BEASTS` = 3。
2. WHEN bot 尝试从候选列表排产，THE Bot SHALL 先用 `bot_filter_choices` 过滤候选，再去重并按存量排序。
3. WHEN 候选列表含 `tamer`，THE Bot SHALL 仅在「bot 的 tamer 存量（含队列）< 2」且「存在可驯中立作战单位，或 bot 存活野兽 ≥ 3」时保留 `tamer`。
4. THE Bot SHALL 仅在 `neutrals_enabled(room, game)` 为真且场上仍有可驯中立作战单位时判定「存在可驯中立作战单位」。
5. THE Bot SHALL 使过滤后除 `tamer` 以外的兵种成员与相对顺序和过滤前相同。
6. THE Bot SHALL 使部落 inbound 选兵列表不含 `tamer`。
7. WHILE `neutrals_enabled(room, game)` 为假，THE Bot SHALL 使部落 bot 的 tamer 存量（含队列）不超过 2，并在存活野兽少于 3 名时不新增 tamer 排产。
8. THE Bot SHALL 保持 `bot_support_choices` 与 `bot_unit_choices` 的函数签名不变。

### Requirement 15: 内置 bot 选兵与集合（决策 J）

**User Story:** 作为与部落 bot 对战的玩家，我想让部落 bot 使用新单位并按克制选兵，以便部落 bot 在各阶段都能形成有效威胁。

#### Acceptance Criteria

1. THE Bot SHALL 使部落 `bot_support_choices` 在营地开局阶段返回 `spear, spear`，在营地非开局阶段返回 `spear, slinger, javelin, tamer`。
2. THE Bot SHALL 使部落 `bot_support_choices` 的围栏候选为 `wolf, scorpion`；有血祭坛时追加 `spider, panda, mammoth`；有血祭坛且处于 late 时再追加 `catapult`。
3. WHILE bot 处于 inbound，THE Bot SHALL 使部落选兵在有营地时为 `javelin, slinger, spear`，否则为 `scorpion`（有血祭坛时追加 `panda, mammoth`）。
4. WHEN 侦察到的敌方载具 ≥ 3（`scout["vehicles"] >= 3`），THE Bot SHALL 使部落选兵为围栏 `scorpion`（有血祭坛时追加 `panda, mammoth`）与营地 `javelin, spear`。
5. WHILE bot 处于 defend，THE Bot SHALL 使部落选兵为营地 `javelin, spear, slinger, tamer` 与围栏 `wolf, scorpion`（有血祭坛时追加 `spider, panda, mammoth`）。
6. WHILE bot 处于 late 且拥有血祭坛，THE Bot SHALL 使部落选兵为围栏 `spider, scorpion, panda, mammoth, catapult, wolf` 与营地 `javelin, slinger, spear, tamer`。
7. THE Bot SHALL 使 `bot_queue_unit` 的部落 late 候选为围栏 `spider, scorpion, panda, mammoth, catapult` 与营地 `javelin, slinger, spear, tamer`。
8. THE Bot SHALL 使部落 inbound 与「敌方载具 ≥ 3」两个分支的候选不含 `wolf`。
9. THE Bot SHALL 保持 `dogs ≥ 4`、`infantry ≥ 5 or mages ≥ 3` 与兜底分支的部落候选不变。
10. THE Bot SHALL 把 `javelin`、`slinger` 加入 `BOT_CHEAP_KINDS`，并把 `slinger`、`javelin`、`tamer` 加入 `BOT_INFANTRY_KINDS`。
11. THE Bot SHALL 从 `BOT_LATE_UNITS` 移除 `scorpion`，并加入 `panda` 与 `catapult`。
12. THE Bot SHALL 使 `BOT_SCOUT_VEHICLES` 继续由 `VEHICLE_KINDS` 派生，并因此包含 `catapult`。
13. WHEN 内置 bot 送修，THE Bot SHALL 按 `REPAIRABLE_KINDS` 挑选受损单位。

### Requirement 16: ai_commander 部落模板与送修（决策 J）

**User Story:** 作为使用外部副官的玩家，我想让 ai_commander 的部落模板使用新单位并能送修野兽，以便插件与内置 bot 的部落打法一致。

#### Acceptance Criteria

1. THE AI_Commander SHALL 采用 `design.md §3.4` 表中的部落模板（6 个护甲桶 × open/mid/late），每格不超过 `MIX_SLOTS`（4）种兵种。
2. THE AI_Commander SHALL 使部落模板不含 `tamer`。
3. THE AI_Commander SHALL 使部落 `light` 与 `heavy` 护甲桶的 open、mid、late 各格至少包含 `javelin` 或 `scorpion` 之一。
4. WHEN ai_commander 挑选送修单位，THE AI_Commander SHALL 按 `REPAIRABLE_KINDS` 判定可修，并继续排除矿车。
5. THE AI_Commander SHALL 使 `codex.counter` 的 bite 判定继续读取 `VEHICLE_KINDS`。
6. WHEN 运行 `python ai_commander/selftest.py`，THE AI_Commander SHALL 通过「54 格兵种存在且阵营正确、总数 > 80」的模板检查。

### Requirement 17: 状态与目录下发

**User Story:** 作为客户端开发者，我想从服务端拿到猎印、定身抗性、兽夹次数与号令半径等字段，以便表现层只读服务端数据、不自行判定。

#### Acceptance Criteria

1. THE Catalog SHALL 在 `public_catalog()` 的每个单位条目下发 `huntMark`（布尔）与 `commandAuraRadius`（`tamer` 为 220，无号令的单位为 0）。
2. THE Catalog SHALL 在 `public_catalog()` 的每个建筑条目下发 `trapCharges`（`ttrap` 为 2，未定义为 0）。
3. WHILE 单位的 `huntMarkTimer` 大于 0，THE Server SHALL 在该单位的实体帧中写入 `marked: true`，其余时刻省略该字段。
4. WHILE 单位的 `rootResist` 大于 0，THE Server SHALL 在该单位的实体帧中写入 `rootResist: true`，其余时刻省略该字段。
5. WHERE 陷阱定义了 `trapCharges`，THE Server SHALL 在该陷阱的实体帧中写入整数 `charges`。
6. THE Server SHALL 只在首帧静态目录中下发新增目录字段，增量帧不重发目录。
7. THE Server SHALL 保持既有 `slow`、`rooted`、`dot`、`rage` 实体字段的含义不变。
8. THE Server SHALL 让新增实体字段随实体一起经过现有迷雾过滤。
9. WHEN Server 创建单位，THE Server SHALL 把 `huntMarkTimer` 与 `rootResist` 初始化为 0.0。

### Requirement 18: 确定性交战回归（决策 K）

**User Story:** 作为平衡维护者，我想用固定种子的小规模交战锁住关键对位结果，以便日后改数值时立刻发现平衡回退，又不因接近均势的场景在种子间翻转而误报。

#### Acceptance Criteria

1. THE Test_Suite SHALL 在 `tests/tribe_combat_test.py` 中按以下环境运行交战：`FLAT_TERRAIN`；清空单位、建筑、中立营与弹丸；`nextCrateAt`、`victoryClock`、`botClock` 设为 1e9；`neutrals` 为假；双方相距 420 互相攻击移动（攻城场景用攻击指令）；以 `tick_game(room, 0.05)` 推进，直到一方没有作战单位与防御塔或满 90 s。
2. THE Test_Suite SHALL 对每个场景使用种子 11、23、37、41、53，并在建单位前调用 `random.seed`。
3. THE Test_Suite SHALL 为每个种子计算双方剩余价值比与 margin。
4. WHEN 场景属于决定性场景，THE Test_Suite SHALL 对每个种子断言胜负方向，以及胜方剩余价值比（塔场景为塔的 hp 比）落在该场景区间内。
5. WHEN 场景属于均势场景，THE Test_Suite SHALL 对每个种子只断言 |margin| 不超过该场景的均势上限，不断言胜负。
6. THE Test_Suite SHALL 覆盖下表全部场景；实现完成后以实测值 ±0.15（截断到 [0, 1]）重标定决定性场景区间，均势上限不随实测收紧，胜负方向与场景类别保持不变。
7. WHEN 把 `HUNT_MARK_BONUS` 临时置为 1.0，对「2 javelin + 2 spear + 2 scorpion + tamer vs 3 tank + 2 rifle」做 A/B，THE Test_Suite SHALL 断言开启猎印时部落 5 个种子的剩余价值比合计不低于置 1.0 时的合计。

回归场景（18.6）。均势上限：1v1 场景 0.30（均势阈值 0.15 + 容差 0.15），多兵种混战 0.60。

| 场景 | 类别 | 每个种子的断言 | 离线估算 |
|---|---|---|---|
| 4 javelin vs 1 tank | 决定性 | 部落胜，剩余 ∈ [0.60, 0.92] | 0.78 |
| 2 javelin vs 1 tank | 均势 | \|margin\| ≤ 0.30 | 坦克剩 0.13（8/8 坦克胜） |
| 1 tspiketower vs 1 tank | 决定性 | 塔存活，hp 比 ∈ [0.45, 0.78] | 0.61 |
| 1 tspiketower vs 2 tank | 决定性 | 塔毁，坦克剩余 ∈ [0.15, 0.55] | 0.30–0.40 |
| 1 ttoxtower vs 6 rifle | 决定性 | 塔存活，hp 比 ∈ [0.62, 0.92] | 0.77 |
| 1 ttoxtower vs 1 tank | 决定性 | 塔存活，hp 比 ∈ [0.44, 0.74] | 0.59 |
| 1 scorpion vs 1 tank | 均势 | \|margin\| ≤ 0.30 | 巨蝎剩 0.08 |
| 1 scorpion + 1 spear vs 1 tank | 决定性 | 部落胜，剩余 ≥ 0.55 | 0.78（巨蝎 220 时估算） |
| 3 spear + 2 javelin + 2 wolf vs 3 rifle + 2 rocket + 1 tank | 决定性 | 部落胜，剩余 ∈ [0.25, 0.65] | 0.43–0.45 |
| 同一部落编队 vs 3 imp + mage + golem | 决定性 | 部落胜，剩余 ∈ [0.25, 0.65] | 0.39–0.48 |
| 2 javelin + 2 spear + 2 scorpion + tamer vs 3 tank + 2 rifle | 均势 | \|margin\| ≤ 0.60，并做 18.7 的猎印 A/B | 胜场 1/8 → 4/8（巨蝎 220 时估算） |
| 守军 3 spear + javelin + wolf vs 3 rifle + tank | 决定性 | 部落胜，剩余 ∈ [0.12, 0.42] | 0.27 |
| catapult vs turret | 决定性 | 30 s 内拆塔，投石车 hp 比 ≥ 0.99 | 23.7 s |
| catapult vs mtower | 决定性 | 投石车被毁 | — |

### Requirement 19: 部落近景模型管线与三角预算（美术）

**User Story:** 作为玩家，我想在拉近镜头时看到统一石器风格、比例粗壮、辨识度高的部落单位，以便部落在近景下与钢铁、秘法同样精致。

#### Acceptance Criteria

1. THE Renderer SHALL 定义 `TRIBE_ART_KINDS` = {`spear`, `javelin`, `slinger`, `tamer`, `wolf`, `spider`, `scorpion`, `panda`, `mammoth`, `tharvester`, `tmcv`, `catapult`} 与 `TRIBE_ART_STRUCTURES` = {`thq`, `tspiketower`, `ttoxtower`}，并把 `TRIBE_ART_KINDS` 并入 `RIVER_ART_KINDS`。
2. THE Renderer SHALL 在新模块 `public/tribe_art_models.js` 中实现 `tribeUnitModel` 与 `tribeStructureDetails`，该模块只 import three，形体原语由调用方注入。
3. WHERE 近景样板开启，THE Renderer SHALL 在近景距离用 `tribeUnitModel` 生成的主体与 rig 绘制 `TRIBE_ART_KINDS` 单位。
4. THE Renderer SHALL 使每个 `TRIBE_ART_KINDS` 单位近景主体与全部 rig 的三角形合计不超过上限：`spear`、`javelin`、`slinger`、`tamer` 各 1600，`wolf` 2600，`spider` 3200，`scorpion` 3200，`panda` 3000，`mammoth` 4800，`tharvester` 3000，`tmcv` 3500，`catapult` 3500。
5. THE Renderer SHALL 使部落近景几何的 position、normal、uv、aTeam、aOcc、aSurf 属性全部为有限值。
6. THE Renderer SHALL 使部落近景主体与每个 rig 都能被模型拾取命中。
7. THE Renderer SHALL 保持 `simpleUnitParts` 中既有部落条目不变，并使近景样板开启与关闭时的远景 LOD 几何逐字节一致。
8. THE Renderer SHALL 保持竹甲熊猫为圆滚黑白兽、黑眼斑与肩上竹甲，不得使用腰封或功夫架势。
9. THE Renderer SHALL 让皮肤与木头使用石纹（kind 1）低频起伏，并只让甲壳类（`spider`、`scorpion`）使用鳞片（kind 3）。

### Requirement 20: 关节动画（美术）

**User Story:** 作为玩家，我想看到部落单位行走、四足对角步态，以及蝎尾、熊猫双掌、投石车抛臂的开火动作，以便从动作读出单位状态。

#### Acceptance Criteria

1. THE Renderer SHALL 支持 rig 描述字段 `axis`（x/y/z）、`mode`（walk/wing/strike/roll）、walk 参数 `rate`/`amp`/`gain`/`phase`、strike 参数 `rest`/`swing`/`attack`/`duration` 与 roll 参数 `radius`，缺省值与现有 rifle rig 行为一致。
2. THE Renderer SHALL 使 `artJointAngle` 对任意 time、travel ∈ [0, 8π)、motion ∈ [0, 1]、sinceFire ∈ [−1, 5] ∪ {∞} 返回有限值。
3. WHILE rig 处于 walk 模式，THE Renderer SHALL 使关节角绝对值不超过 `amp`，并在 travel = 0 与 travel → 8π 处连续。
4. WHEN strike 模式 rig 所属单位开火，THE Renderer SHALL 在 `attack` 时长内把关节角从 `rest` 推到 `rest + swing`，并在 `duration` 结束时回到 `rest`；sinceFire 不在 [0, duration) 内时返回 `rest`。
5. WHILE 单位静止（motion = 0）且不在开火动作期，THE Renderer SHALL 使全部 walk 与 strike rig 返回静止角。
6. WHILE rig 处于 roll 模式，THE Renderer SHALL 返回 −travel / `radius`。
7. IF rig 的 mode 或 axis 未知，THEN THE Renderer SHALL 返回角度 0 并按 z 轴处理，不抛出异常。
8. THE Renderer SHALL 使 walk rig 的 `rate` 为 0.25 的整数倍，并使 roll rig 满足 8π / `radius` 为 2π 的整数倍。
9. THE Renderer SHALL 让四足单位的左前与右后腿 `side` 取 +1、右前与左后腿取 −1，并使 walk 模式下 `side` 相反的两个 rig 在同一输入下取值互为相反数。
10. THE Renderer SHALL 使每个 `TRIBE_ART_KINDS` 单位的 rig 数不超过 4，并按 `design.md §4.3` 表设置各 rig 的 pivot、axis、mode 与参数。
11. WHEN 主网格实例槽位的变换版本未变、rig 角度变化不超过 1e-4 且实例 id 未变，THE Renderer SHALL 跳过该 rig 实例矩阵的重写，并在没有写入时不置 `needsUpdate`。

### Requirement 21: 兽毛材质（美术）

**User Story:** 作为玩家，我想让狼、猛犸、熊猫与驮兽在近景下呈现毛流而不是鳞片，以便野兽材质与巨龙鳞甲区分开。

#### Acceptance Criteria

1. THE Renderer SHALL 在冻结对象 `SURF` 中新增 `fur: 3.25`。
2. WHERE 近景样板开启，THE Renderer SHALL 对 aSurf 位于 [3.2, 3.3] 的片元以织物格（kind 2）作底并把图集法线扰动压到 30%，叠加沿模型局部坐标的毛流法线扰动与 ±4% 毛尖提亮，并把粗糙度设为 0.9。
3. WHILE 视距在 600 到 1400 之间，THE Renderer SHALL 按 smoothstep 把毛流扰动从完整强度淡出到 0。
4. THE Renderer SHALL 把 PBR 程序缓存键由 `-river-pbr-v3` 改为 `-river-pbr-v4`，且程序数量不变。
5. THE Renderer SHALL 保持烘焙图集为 2×2、宽度 512，不新增纹理与采样。
6. WHERE 近景样板关闭，THE Renderer SHALL 让 aSurf 3.25 落入既有兽皮分支（2.5 < gMode < 3.5），不进入晶体分支（gMode > 3.5）与金属度分支（gMode < 0.5）。
7. THE Renderer SHALL 使 `wolf`、`mammoth`、`panda`、`tharvester`、`tmcv` 的近景各至少有一个 aSurf 为 3.25 的零件。
8. THE Renderer SHALL 保持 `HIDE_UNIT_KINDS` 的源码字符串不变。

### Requirement 22: 队色（美术）

**User Story:** 作为玩家，我想在常用缩放与近景下都能从部落单位与建筑上认出所属队伍，以便混战时不认错敌我。

#### Acceptance Criteria

1. THE Renderer SHALL 使每个 `TRIBE_ART_KINDS` 单位的近景至少有一个零件走队色通道。
2. THE Renderer SHALL 把部落单位的队色放在 `design.md §4.2` 表列出的大面积织物或饰物上（例如腰布、斗篷镶边、背毯、轿旗、皮兜）。
3. THE Renderer SHALL 使每座 `TRIBE_ART_STRUCTURES` 建筑的近景至少有一个顶点 aTeam = 1。
4. THE Renderer SHALL 使 `javelin` 与 `catapult` 的远景 LOD 各带一块 paint 约 0.9 的队色面。

### Requirement 23: 部落建筑近景细节（美术）

**User Story:** 作为玩家，我想在近景下看到部落大营、棘矛哨塔与毒矢高台的茅草、兽皮、骨饰与图腾细节，以便部落基地有鲜明的石器风格。

#### Acceptance Criteria

1. WHERE 近景样板开启，THE Renderer SHALL 以 `tribeStructureDetails` 返回的零件完整替换 `thq`、`tspiketower`、`ttoxtower` 的近景主体，炮塔头与旋转件沿用现有实现。
2. THE Renderer SHALL 使 `thq`、`tspiketower`、`ttoxtower` 的近景三角形分别不超过 6000、3000、3200。
3. THE Renderer SHALL 为每座部落近景建筑提供 y 从 0 起、高度小于包围半径 × 0.25 的薄夯土地基零件，使 `mergeParts` 为该零件写入负破拆半径。
4. THE Renderer SHALL 使部落近景建筑几何的 `aBreak` 条目数等于顶点数且全部为有限值。
5. THE Renderer SHALL 使 GLOW 分量大于 1 的零件不参与 AO。
6. WHERE 近景样板关闭，THE Renderer SHALL 保持 `structureParts` 基础分支的几何与改动前一致。
7. THE Renderer SHALL 实现 `design.md §4.6` 表列出的建筑细节：大营的三层茅草檐带、屋脊交叉兽角、烟孔余烬、兽皮挂板、绳结立柱、门口图腾雕脸、削尖木桩与檐下骨饰；棘矛哨塔的四柱平台与斜撑绳结、兽皮挡风板、木桩裙、骨颅挂饰与台沿图腾脸；毒矢高台的骨木脚手架、陶毒壶滴痕、羽饰吹箭筒架与兽皮旗。

### Requirement 24: 新单位基础与远景资产（美术）

**User Story:** 作为玩家，我想在关闭近景样板或拉远镜头时也能认出燧石标枪手与巨石投石车，以便新单位在所有画质下都有专属外观。

#### Acceptance Criteria

1. THE Renderer SHALL 为 `javelin` 与 `catapult` 各提供专属 `UNIT_BUILDERS` 条目，不直接返回其他 builder（如 `UNIT_BUILDERS.spear()`、`UNIT_BUILDERS.artillery()`）的结果。
2. THE Renderer SHALL 使两个 builder 的注释首行分别以「燧石标枪手：」与「巨石投石车：」开头。
3. THE Renderer SHALL 为 `javelin` 与 `catapult` 在 `simpleUnitParts` 中各新增一条远景盒模，每条不超过 200 个三角形。
4. THE Renderer SHALL 设置 `UNIT_VISUAL_SCALE` 的 `javelin: 2.15` 与 `catapult: 1.28`。
5. THE Renderer SHALL 把 `javelin` 加入 `CLOTH_UNIT_KINDS`，并在 `unitSurfaceFamily` 与材质选择中把 `catapult` 并入 `tharvester`/`tmcv` 的兽皮表面族。

### Requirement 25: 战斗特效（美术）

**User Story:** 作为玩家，我想一眼看出标枪、巨石、猎印、驯兽号令、祭坛治疗与「这次没定住」，以便新机制在战斗中可读。

#### Acceptance Criteria

1. THE Renderer SHALL 定义 `PROJECTILE_STYLE.javelin` = {len 22, thick 0.9, color 0xc89a5a, arc 26, look `javelin`}，由燧石头 shard、木杆 tracer 与按 owner 队色的尾羽 orb 组成。
2. THE Renderer SHALL 定义 `PROJECTILE_STYLE.megalith` = {len 14, thick 4.2, color 0x9a8a70, arc 150, look `megalith`}，由巨石 orb、尘团 orb 与尘土拖尾组成，命中时走 heavy 爆点与既有地表焦痕。
3. THE Renderer SHALL 使 `javelin` 与 `megalith` 两种 look 每发弹丸最多使用 4 个 tracer、2 个 orb、2 个 shard 实例，满足 `ensureTracer*Mesh` 的容量公式。
4. WHILE 可见单位带 `marked`，THE Renderer SHALL 在该单位脚下 `gy + 2.6` 处绘制三道斜爪痕的猎印标记（约 12 个三角形，半径 size × 1.25 + 2，琥珀红 (1.0, 0.42, 0.12) 缓慢脉动），同屏最多 128 个。
5. THE Renderer SHALL 为每名可见驯兽师（不区分敌我）按目录 `commandAuraRadius` 绘制 owner 队色、不透明度 0.20 的号令光环，同屏最多 32 个，不硬编码 220。
6. WHILE 部落单位处于 `repairing`，THE Renderer SHALL 在该单位脚下以约 6 个/秒发射暖红金光点并偶发绿色生命光，数量受 `particleBudget × 0.62` 约束。
7. WHILE 单位同时带 `rootResist` 与 `slow`，THE Renderer SHALL 把定身光点改为淡白色。
8. THE Renderer SHALL 在 `battle_feedback.js` 的 `weaponFamily` 中登记 `javelin` → `sting`、`megalith` → `heavy`，在 `MUZZLE_POINTS` 中登记 `javelin: [10, 14]`、`catapult: [-4, 34]`，并把两种弹种加入 `render3d.js` 的开火高度白名单与 `emitProjectileTrail`。
9. IF 客户端收到未知弹种，THEN THE Renderer SHALL 回退为 `bullet` 样式。
10. IF 目录缺少 `commandAuraRadius`，THEN THE Renderer SHALL 不绘制号令光环。

### Requirement 26: HUD 文案、选中面板与肖像

**User Story:** 作为部落玩家，我想在 HUD 与选中面板中读到新单位、新机制与祭坛治疗的准确说明，以便不看文档也知道怎么用。

#### Acceptance Criteria

1. THE HUD SHALL 在 `UNIT_VFX` 中新增 `javelin`（「➶ 燧石标枪，营地反甲步兵，命中挂猎印」）与 `catapult`（「🪨 巨石弧线攻城，专拆建筑 · 需血祭坛」）。
2. THE HUD SHALL 在 `spear`、`slinger` 的描述中补充「命中挂猎印」，把 `tamer` 的描述改为「驯兽号令：220 内野兽伤害 ×1.10；开启中立时可招降」，并删去 `scorpion` 描述中的「需血祭坛」。
3. THE HUD SHALL 在 `BUILDING_VFX` 中为 tcamp、tpen 列出新单位，并把 taltar 改为「治疗驮兽、迁徙驮队、野兽与投石车；解锁进阶驯养」、tspiketower 改为「中距骨矛炮弹，反甲近防 · 需营地」、ttoxtower 改为「远距穿甲毒矢，溅射挂毒 · 需血祭坛」、ttrap 改为「上膛后夹住敌军，可触发 2 次 · 需营地」。
4. THE HUD SHALL 把 `FACTION_COPY.tribe` 的 `repairBtn` 与 `repairHint` 设为「祭坛治疗」、`repairSelect` 设为「请选择受损的驮兽、野兽或投石车」、`repairSent` 设为「个单位已前往血祭坛」。
5. THE HUD SHALL 把 `javelin` 与 `catapult` 加入 `TRIBE_KINDS`。
6. WHEN 玩家选中兽夹，THE HUD SHALL 按实体帧 `charges` 显示「剩余 n/2 次」。
7. WHEN 玩家选中带 `marked` 的单位，THE HUD SHALL 显示「猎印」。
8. THE HUD SHALL 在 `PORTRAIT_PAINTERS` 中为 `javelin`（`pBust(P_HIDE)`、骨环头、后举标枪、肩后三根短箭杆、两道 `P_BLOOD` 战纹）与 `catapult`（`pShadow`、`P_BARK` 实心木轮与 `P_BONE` 轮毂、A 字框、抛臂与皮兜 `P_STONE` 巨石、框上 `P_BLOOD` 小旗）绘制专属肖像。

### Requirement 27: 克制表

**User Story:** 作为玩家，我想在克制表里查到部落新单位与改动后的塔，以便快速判断对位。

#### Acceptance Criteria

1. THE HUD SHALL 在 `index.html` 克制表的营地段新增「➶ 燧石标枪手 → 重甲/轻甲 · 营地即可训 · 命中挂猎印」，倍率列为 ×1.5。
2. THE HUD SHALL 把穿甲巨蝎行改为「穿甲尾刺点杀重甲 · 围栏即可驯」（×2.1），并新增「🪨 巨石投石车 → 建筑 · 巨石弧线 · 需血祭坛」（×1.8）。
3. THE HUD SHALL 把棘矛哨塔行改为「中距骨矛炮弹 · 需营地」（×1.0）、毒矢高台行改为「远距穿甲毒矢 · 溅射挂毒 · 需血祭坛」（×2.1）、兽夹陷阱行改为「上膛后定身爆发 · 2 次 · 需营地」。
4. THE HUD SHALL 在克制表说明区新增两行：猎印与号令（×1.15 / ×1.10，连乘封顶 ×1.45）；控制规则（减速与持续伤害取最强；定身结束后 1 秒抗性，期间定身降为 ×0.5 减速）。

### Requirement 28: README

**User Story:** 作为新玩家或维护者，我想在 README 中读到部落的新单位、新机制与跨阵营控制规则，以便了解改动后的玩法。

#### Acceptance Criteria

1. THE README SHALL 在部落段落写明燧石标枪手（360/110，营地反甲步兵，命中挂猎印）与巨石投石车（1000/340，血祭坛后攻城，射程 350）。
2. THE README SHALL 写明穿甲巨蝎只需驯兽围栏（hp 250、射程 165）、棘矛哨塔改为中距反甲、毒矢高台直伤穿甲并溅射挂毒、兽夹可触发 2 次、血祭坛可治疗野兽与投石车。
3. THE README SHALL 写明猎印（×1.15、4 秒）、驯兽号令（220 内 ×1.10）与连乘封顶 ×1.45。
4. THE README SHALL 写明跨阵营控制规则：减速与持续伤害强者优先、定身不续时、定身结束后 1 秒抗性期内定身降为 ×0.5 减速。
5. THE README SHALL 写明部落开局守军为 3 名骨矛猎手、1 名燧石标枪手与 1 头战狼。
6. THE README SHALL 包含「燧石标枪手」与「巨石投石车」字样，供 `presentation_rules_test` 检索。

### Requirement 29: 渲染性能验收（需浏览器与 GPU）

**User Story:** 作为玩家，我想在部落大军近景下保持与改动前相当的帧率，以便美术升级不牺牲流畅度。

#### Acceptance Criteria

1. THE Test_Suite SHALL 在 `tests/visual_benchmark.html` 的 `profiles` 中加入 `tribe` 档，列出 `spear`、`javelin`、`slinger`、`tamer`、`wolf`、`spider`、`scorpion`、`panda`、`mammoth`、`catapult`、`tharvester`、`tmcv`。
2. WHEN 以 `tests/visual_benchmark.html?scenario=army&count=400&mix=tribe&fixedSimulation=1`、1280×720 DPR1、建筑阴影、轻量泛光、LOD 开、粒子 150、90 帧预热 + 300 帧，按「基线 → 候选 → 候选 → 基线」交替测量（基线为改动前 public 快照），THE Renderer SHALL 使两轮候选的平均 FPS 不低于两轮基线平均 FPS 的 95%。
3. WHEN 按 29.2 的条件测量，THE Renderer SHALL 使两轮候选的帧时间 p95 平均值不超过两轮基线平均值 + 2 ms。
4. WHEN 按 29.2 的条件测量，THE Renderer SHALL 使 draw call 增量不超过 34（`shadows='all'` 时不超过 68）。
5. WHEN 执行性能验收，THE Acceptance_Log SHALL 记录部落档与默认全目录混编两组的 FPS、帧 p95/p99、CPU p50/p95、GPU p50/p95、draw calls、三角形数与程序数。
6. IF 400 单位对照出现 29.2–29.4 的回退，THEN THE Renderer SHALL 依次启用「rig 不投影」与「中距离（camDist > 600）改画预合并的静止腿主体、不画 rig」两级回退，且不改变远景 LOD。
7. IF 验收环境没有浏览器与 GPU，THEN THE Acceptance_Log SHALL 把 29.2–29.6 记为「未验证」，不以离线几何测试结论代替帧率结论。

### Requirement 30: 画面手动验收（需浏览器）

**User Story:** 作为美术验收者，我想按清单近看全部部落单位与建筑，以便确认造型、动作、材质、队色与特效达到目标。

#### Acceptance Criteria

1. WHEN 验收者在常用缩放与近景下查看 12 个部落单位，THE Renderer SHALL 呈现 `design.md §4.2` 表的剪影要点，使燧石标枪手、骨矛猎手与投石猎手第一眼可区分。
2. WHEN 验收者在常用缩放下查看部落单位，THE Renderer SHALL 使各队队色可辨。
3. WHEN 验收者近看 `wolf`、`mammoth`、`panda`、`tharvester`、`tmcv`，THE Renderer SHALL 呈现毛流而非鳞片。
4. WHEN 验收者近看竹甲熊猫，THE Renderer SHALL 呈现与改动前相同的造型与配色。
5. WHEN `scorpion`、`panda`、`catapult` 开火或四足单位移动，THE Renderer SHALL 呈现蝎尾刺击、双掌前推、抛臂抛射与对角步态。
6. WHEN 战斗中出现猎印、驯兽号令与祭坛治疗，THE Renderer SHALL 使爪痕标记、号令光环与治疗微粒可读。
7. WHEN 部落建筑坍塌，THE Renderer SHALL 使地基保持锚定、不翻起。
8. WHEN 验收者近看 `thq`、`tspiketower`、`ttoxtower`，THE Renderer SHALL 呈现 `design.md §4.6` 表列出的细节。
9. IF 验收环境没有浏览器，THEN THE Acceptance_Log SHALL 把 30.1–30.8 记为「未验证」。

### Requirement 31: 工程约束与兼容

**User Story:** 作为维护者，我想让改动遵守现有技术约束并保持测试全绿，以便部署环境与既有功能不受影响。

#### Acceptance Criteria

1. THE System SHALL 兼容 Python 3.6：不使用 `dataclasses`、海象运算符等 3.7+ 语法与库特性，并沿用 `%` 格式化风格。
2. THE System SHALL 不新增 Python 或 JavaScript 依赖，也不生成新位图（只复用 `river-material-atlas-v1.png` 与既有烘焙图集）。
3. THE System SHALL 保持地图数据与中立营编制不变，且不新增自爆单位。
4. THE System SHALL 除 Requirement 11、12 的控制规则外，保持钢铁与秘法单位和建筑的数值不变。
5. THE Catalog SHALL 作为全部数值的唯一来源。
6. THE Renderer SHALL 只用 `public_catalog()` 与实体帧下发的字段做表现，不参与伤害、状态或生产判定。
7. THE Server SHALL 把号令、猎印与定身抗性的状态挂在实体上，在 `room_lock(room)` 保护下读写，不新增模块级可变状态。
8. THE Server SHALL 从 `catalog` 导入并再导出本次新增的常量、集合与函数。
9. WHEN 实现完成，THE Test_Suite SHALL 使 `python run_tests.py`、`python ai_commander/selftest.py`、`node tests/tribe_art_test.mjs`、`node tests/river_art_test.mjs`、`node tests/unit_geometry_test.mjs`、`node tests/model_picker_test.mjs` 与 `node tests/visual_benchmark_test.mjs` 全部通过。
