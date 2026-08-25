# ai_commander — 会看克制关系的内置 AI

给游戏里的 AI 玩家换一套大脑。**这个包不修改仓库里任何既有文件**：整个实现
都在这个文件夹里，靠运行时替换 `server.tick_bots` 接管；想跑回原版直接
`python server.py`，什么都不用还原。

> 仓库里另有一条 AI 路线——`/api/attach` 配对码，给跑在玩家自己机器上的外部
> agent（`rts-agent`，不在本仓库）接管人类玩家席位用。那条路确实动了
> `server.py` / `public/`，和这个包没有关系，两者可以同时开着。见根 README
> 的「AI 玩法」。

有 LLM 就让 LLM 定策略，没有 LLM 就按固定模板打——**没有 API Key 也是完整
可玩的**，不是降级演示。

## 怎么跑

```bash
python ai_commander/start.py            # 启动时问一次 API Key，回车＝不用
python ai_commander/start.py --no-llm   # 不问，直接固定模板
python ai_commander/start.py --mode first   # 一个房间里新旧 AI 各来一个
./ai_commander/start-ai.sh 18081        # Linux/macOS，带端口
ai_commander\start-ai.bat 18081         # Windows 双击也行
```

服务器本体、端口、静态文件、房间流程全部沿用 `server.py`；这里只是在
`server.main()` 之前把 AI 换掉。房间里照常「添加 AI」，加进来的就是新 AI。

自检（不需要 LLM，也不需要起服务器）：

```bash
python ai_commander/selftest.py
```

## API Key 从哪来

一律由你自己提供，仓库里不留任何密钥。四个来源，优先级从高到低：

| 来源 | 用法 |
|---|---|
| 命令行 | `--key sk-xxx --base https://... --model gpt-4o-mini --provider openai` |
| 环境变量 | `AI_LLM_KEY` / `AI_LLM_BASE` / `AI_LLM_MODEL` / `AI_LLM_PROVIDER` / `AI_LLM_INTERVAL` |
| 本地文件 | 复制 `ai_commander/llm.example.json` 为 `llm.json` 后填写；`llm.json` 已 gitignore |
| 交互输入 | 启动时问一次，直接回车＝不接 LLM |

示例文件只有字段结构和占位值，可以提交到版本库；真正使用的 `llm.json` 只留在
本机，不要改名上传。也可以继续用 `--save` 或在交互里选择「记住」，程序会在
本地生成 `llm.json`。

后端支持 OpenAI 兼容端点（含自部署网关）和 Anthropic。私网地址（10./192.168./
127./172.16-31.）会自动绕开系统代理——内网端点被代理劫持时不会报错，只会挂死
到超时，排查很贵。

启动时会先探活一次；调不通就打印原因并**自动切回固定模板模式**，游戏照常开。

## 三个模块在干什么

```
codex.py      克制计算：护甲、倍率、有效 DPS、单兵性价比
templates.py  固定模板表：局势 -> 出什么兵（没有 LLM 时唯一的来源）
planner.py    把模板/LLM 指令拧成一份可执行计划，并做克制安全过滤
commander.py  每个 AI 的大脑：建造、生产、战斗指挥
llm.py        可选的 LLM 顾问（后台线程 + 纯标准库 HTTP）
hook.py       运行时替换 server.tick_bots
```

### 克制：直接读服务端的表，不抄副本

`codex.py` 不维护任何数值，全部现读 `catalog.UNIT_TYPES`（armor / damage /
cooldown / range）和 `server.DAMAGE_MULTIPLIER`（`apply_damage` 真正查的那张
表），连两条特判也复用同一套规则：

* 混甲（晶铠卫士、裂地晶兽的 `("heavy","light")`）取两种倍率的平均；
* 扑咬对**载具**是硬 0——秘法巨龙、岩石傀儡的护甲是 `arcane`，只看护甲类
  会以为军犬能咬，实际是零伤害。

所以 `catalog.py` 改平衡，这里自动跟上，不需要同步任何副本。

### 固定模板：局势 → 出兵

没有 LLM 时，AI 就按 `templates.py` 那张表打。局势由三个离散量决定，都能在
一 tick 内从战场状态直接读出来：

```
我方阵营(tech/magic) × 敌方主护甲(unknown/infantry/light/heavy/arcane/mixed) × 阶段(open/mid/late)
```

阶段用建筑进度判定（有工厂＝mid，有维修厂/圣泉＝late），比掐秒表稳。
敌方主护甲来自**敌军普查表**：记录每个兵种「同时见到过最多几个」，比即时
视野稳定得多——对方进出迷雾不会让生产在两套兵之间来回横跳。

普查只算**真正的敌方玩家**。中立矿营的守军（`rifle`×2 + `rocket`×1，owner 是
`NEUTRAL_OWNER`）虽然 `is_friendly` 返回 False，但它们有 leash、不会离开矿营，
而且全是步兵甲；放进普查会把整张表带偏——对面明明是全魔导甲的秘法会，却因为
家门口那座公共矿而去出反步兵的军犬。同理，「老家被入侵」的判定也自己实现而不
用 `server.bot_needs_defense`：公共矿常常就落在老家 700 半径内，照搬的话 AI
会一整局卡在防守状态不出门。

表是手写的，就是给人读和改的。举两个格子：

| 局势 | 配比 | 为什么 |
|---|---|---|
| tech / arcane / mid | `tesla:4 rifle:3 tank:2` | 磁暴对魔导甲 ×1.60、子弹 ×1.50；**穿甲只有 ×1.00，别造歼击车** |
| tech / heavy / mid | `tank_destroyer:4 rocket:3 tank:2` | 穿甲对重甲 ×2.10，是硬克星 |

### 克制安全过滤（LLM 也改不动的硬约束）

不管配比是模板给的还是 LLM 给的，落地前都会跑一遍 `planner.sanitize_mix`：

1. 对**当前真正看见的敌军**有效 dps ≈ 0 的兵一律换掉（军犬撞上一队构装体
   就是这种情况），换成同产地里评分最高的；
2. 阵营不对、前置永远补不上的兵剔掉；
3. 配比里一个「现在就能排」的兵都没有时补一个——判定要同时看产地和前置科技，
   只看 `requires` 会漏：坦克歼击车没有 `requires`，产地却是工厂，工厂没立起来
   之前它一样一个都排不出；
4. 配比需要的产地和**前置科技建筑**自动进建造序列。

建造序列另有一条硬约束（`planner.sanitize_build`）：**精炼厂和矿车产地必须在，
缺了就补到序列最前面**。`build_order` 是 LLM 能整段替换的字段，而少了这两样
这一局的经济当场判死刑——没有矿车就没有收入，没有收入就永远补不上矿车
（钢铁军团的 `harvester.producer` 就是 `factory`）。电力另有 `POWER_BUFFER`
兜底，不必列进这条。

### LLM 顾问：永远不在 tick 里等它

`tick_bots` 是 20Hz 模拟的一部分，跑在 `room_lock(room)` 里。一次 LLM 往返
几秒钟，等回来整局都卡住了。所以分工是：

```
主循环（持锁）  : 生成一份很小的战场快照，塞给顾问，立刻读走上一次的结论
顾问线程（无锁）: 慢慢调 LLM，解析出 JSON 指令，覆盖到自己的槽位上
```

顾问只能改 `army_mix / build_order / attack_at / harvesters / max_turrets`
这几个字段，而且逐项校验：别的阵营的兵、不存在的兵、越界数值全部丢掉
（`attack_at` 上限压到 60——模型很容易顺口给个 200，那等于叫 AI 永远别出门）。
调不通、超时、返回的不是合法 JSON，统统当作「这次没有建议」，继续按模板打。

顾问线程会在**闲置 5 分钟后自己退出**（`llm.IDLE_EXIT_SECONDS`）。不能指望外面
显式 `stop()`：`tick_game` 在 `status != "playing"` 时第一行就 return，房间一打完
`tick_bots` 再也不会被调用，写在那里的清理跑不到；不自退的话每打一局就漏一个
4Hz 空转的线程，直到进程结束。局又打起来时 `hook._ensure_advisor` 会重新拉一个。

## 三种接管范围

环境变量 `AI_COMMANDER` 或 `--mode`：

| 模式 | 行为 |
|---|---|
| `all`（默认） | 所有 AI 都换新大脑 |
| `first` | 每个房间只换第一个 AI，其余留给原版，方便同场对比 |
| `off` | 完全不接管 |

任何一个 AI 在新逻辑里抛异常，都会被就地标记并**退回内置逻辑**，一个 bug
卡不死整局。异常按签名去重打印：同一个 bug 被六个 bot 一起撞上只报一行，但换
一个 bug 仍然报得出来——全进程只报一次的话，第二个 bot 因为别的原因静默退回，
现象就是「新 AI 好像没生效」，非常难查。

接管的是整个 `tick_bots`，所以内置 AI 那几件事也得自己接着做，别丢：自爆单位
**单独按波次砸建筑**（`_launch_suicides`，不进野战编制——`_score_target` 会把它
送去撞步兵，1000 块换一个步兵）、躲开进家的敌方自爆车（`bot_evade_suicide`）、
基地车折叠转移（`bot_maybe_pack`）、血量低于 45% 的兵不跟着推进。

## 离线对战结果

在离线对局台上让新 AI 打内置 AI，四种阵营组合各 3 局，每局上限 15 分钟：

| 阵营组合 | 结果 |
|---|---|
| 新 AI tech vs 内置 magic | 3 战全胜，430s / 645s / 768s 淘汰对手 |
| 新 AI magic vs 内置 tech | 2 胜 + 1 场超时领先（存量 68000:11910） |
| 同族 tech 内战 | 2 胜（290s / 551s）+ 1 场超时领先 |
| 同族 magic 内战 | 3 场超时领先，存量均在 5~7 倍 |
| **合计** | **12 战 12 胜 0 负，总存量比 8.71:1，交换比 3.32:1，零崩溃** |

同一个对局台上让**内置 AI 打内置 AI**做对照：12 局全部 700 秒未分胜负。所以
「能在 15 分钟内把对面打掉」这件事本身就是差距，不只是存量数字好看。

> 跑对局台时注意一个坑：`--mode first` 接管的永远是房间里**插入顺序第一个**
> bot。想「换边」就换插入顺序的话，换掉的其实是标签——被接管的还是第一个，
> 只不过你把它记成了对照组，于是会读出一份完全反过来的结论。要换边应该固定
> 新 AI 是第一个创建的 bot，靠 seed 让 `start_game` 去随机洗出生点。

## 改这里要注意什么

* 只用 Python 3.6 标准库，和仓库其他部分一致，不引入依赖；
* 改完跑 `python ai_commander/selftest.py`（`run_tests.py` 也会通过
  `tests/ai_commander_test.py` 带上它），再跑一次完整的 `python run_tests.py`
  确认没影响原版；
* 数值不要往这个包里抄——需要什么就从 `catalog.py` / `server.py` 现读；
* 要调「要质量还是要数量」，改 `codex.COST_EXPONENT`（1.0 偏贵兵，
  2.0 偏便宜兵暴兵，现在取几何中值 1.5）。
