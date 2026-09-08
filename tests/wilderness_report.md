# 写实旷野升级验收 · 2026-09-08

目标：三张地图的草土、森林、岩石和河岸形成真实表面与自然轮廓，保持既有通路、
桥梁通行高度、出生区、矿区规则和模拟不变，并以 400 单位渲染测试约束性能。
这是现有实时渲染器的实作升级，不是离线概念图，也不是全套 AAA 扫描资产替换。

## 已实现

- 四种真实表面（草、砂砾土、层理岩、林下腐殖土）共用一张 1024×1024 图集。
  构建时计算湿度/森林/岩体/踩踏混合权重，片元细节打散交界；草地三角随机错位
  混合消除镜像格纹，远处减弱微法线以控制闪烁。
- 所有地图的树冠替换为真实 alpha 叶簇，7 张倾斜卡片/树，树冠仅 14 三角形。
  树木仍高于普通建筑，按 640 世界单位分块剔除，桥头净空保持。
- 3 种确定性的 108 面风化岩模板替换规则多面体石块；山石埋入坡面，取消假雪帽。
  地面草叶弯曲、灌木透空，修正草簇与横倒木悬空。
- 铁峡争渡的河岸改成连续侵蚀岩层与零散碎石，水面有浅深色差、流动法线和视角反光。
  桥面有磨损纹理，土路柔边露草，未改变桥面/引桥的高度公式。
- 矿区改为金脉岩体与柔边矿床，保留储量档位、缩放和开采消失逻辑；小地图图例不变。
- 草、灌木、岩石、树冠仍是静态合批；新增两张 WebP 合计 750,230 字节。
  运行时共享的美术纹理仍为 4 张，新图集/叶片替换原地表/森林图。

## 性能复现

仅监听本机的离线夹具，不运行房间、联网同步、AI 或完整游戏 UI：

```powershell
py -3.13 tests/visual_benchmark_server.py --port 8876 --baseline-public artifacts/terrain-before/public
```

浏览器：Codex 内置 Chromium、WebGL2、ANGLE D3D11、Intel Arc Graphics 0x00007D55。
1920×1080 视口，种子 90241；400 移动单位 + 15 建筑，自动 LOD。
以下三轮均为 **400 精细单位、0 远景单位**，不是用全场降模换帧率。
每轮预热 90 帧，采样 300 帧。FPS 约 60 受到刷新率限制，不代表无上限吞吐。

| 场景 / 版本 | 内部分辨率 | 平均 FPS | 帧间隔 p95 | CPU render p50 / p95 | 场景 draw calls / 三角形 |
| --- | --- | ---: | ---: | --- | --- |
| 铁峡争渡 / 本轮改动前 | 1920×1080 | 60.00 | 16.9 ms | 1.9 / 2.6 ms | 135 / 659645 |
| 铁峡争渡 / 最终版 | 1920×1080 | 60.00 | 16.9 ms | 2.4 / 3.4 ms | 184 / 576363 |
| 赤金陨坑密林旁 / 最终版 | 1920×1080 | 60.01 | 16.9 ms | 2.2 / 2.8 ms | 183 / 630959 |

铁峡争渡参数：`?scenario=army&count=400&moving=1`，建筑阴影、无泛光，
镜头 `(1000,1500)` / zoom 0.82 / yaw 0.14 / pitch 0.96。旧版额外传
`&renderer=/baseline/render3d.js`；基线是本轮开始前的工作树，**不是 Git HEAD**。

密林旁参数：`?scenario=army&map=gold_crater_small&count=400&moving=1&focusX=3800&focusY=1300&zoom=0.70&bloom=1`。
全地图 3471 棵树、44 个森林块，建筑阴影、轻量泛光（5 个后处理 pass）。

铁峡争渡三角形减少约 12.6%，但分块增加 draw calls 和少量 CPU 时间；
不能把单机离线测试解释成任何电脑或完整联网混战都保证 60 FPS。
现有动态分辨率与画质切换保留。中间版本还实测了 90% 内部分辨率的 60 FPS；
最终验收以上面的原生分辨率结果为准。

## 连续换图与回归

同一 renderer、三个地图循环 4 轮，共 12 次。每次等待 30 帧，以下数量在各轮完全一致：

| 地图 | GPU geometries | textures / sharedTextures | fog shaders | water shaders |
| --- | ---: | --- | ---: | ---: |
| 五车争霸 | 119 | 12 / 4 | 6 | 0 |
| 赤金陨坑·紧凑 | 138 | 12 / 4 | 9 | 0 |
| 铁峡争渡 | 160 | 12 / 4 | 18 | 2 |

这是资源计数稳定性检查，不是长期显存占用测量。浏览器日志无 WebGL/GLSL 错误。

- `py -3.13 run_tests.py`：全部 48 套离线回归通过，包括地图、桥梁水域、寻路、
  单位控制、矿量、阵营/胜负与房间生命周期。
- `node tests/wilderness_test.mjs`：生态混合范围与确定性、连续噪声、岩石模板面数/法线、
  真实 Three ShaderChunk 注入、父迷雾 hook、纹理预算、alpha 与分块接线。
- `node tests/unit_geometry_test.mjs`：30 种单位/形态、15 类建筑几何/AO/LOD 通过。
- `node tests/render_quality_test.mjs`、`postfx_test.mjs`、`render_resources_test.mjs` 通过。
- `git diff --check` 通过。地图模拟/数值未在本轮修改；工作区此前的其它功能改动保留。

## 直接渲染截图

全部为 1920×1080 JPEG，固定场景时间 18 秒，建筑阴影 + 轻量泛光，未做图片修饰。
电脑操作工具用于浏览器验收；图片生成工具只生成材质，**没有生成这些截图**。

- 河谷旧版：`artifacts/wilderness-river-before.jpg`
- 河谷新版：`artifacts/wilderness-river-after.jpg`
- 赤金陨坑旧版：`artifacts/wilderness-forest-before.jpg`
- 赤金陨坑新版：`artifacts/wilderness-forest-after.jpg`
- 五车争霸地表近景：`artifacts/wilderness-central-after.jpg`
- 五车争霸丘陵：`artifacts/wilderness-central-landscape.jpg`

河谷机位：`?scenario=river&bloom=1`。
密林机位：`?scenario=river&map=gold_crater_small&x=4630&y=1370&zoom=0.50&pitch=0.87&yaw=0.1&bloom=1`。
五车丘陵机位：`?scenario=map&map=central_scramble&x=900&y=900&zoom=0.66&pitch=0.91&yaw=0.20&bloom=1`。

## 五车争霸：中央无矿、高地与矿区迷雾修复（2026-09-08）

- 移除中央 46 万矿；仅保留外围五个方向各一片 23 万随机矿，无守军。
- 中央平整落地区缩至 320 半径。外围五处 100 高度的平顶发展高地，通过长缓坡
  连接中央低地；五组高耸林岩脊、干沟与侧翼缺口取代四角丘陵和随机孤山。
  十处岩核半径为 260/210，仍使用服务端山体碰撞。坡地可通行，高度与土石混合
  在建图时烘焙到原地面网格；没有额外增加战斗射程、视野或高地伤害规则。
- 中央驶离路线、五条宽出口、半径 1440 的环向绕行空间通过 55 半径载具余量检查。
  五向随机矿多种子检查、49 项离线回归及 6 组 Node 渲染测试通过。
- 矿石实例在坡面按实际位置落地，储量换档缩放时重新贴合地面；仅在换档时计算。
  地图裙边替换为贴合每个地面边缘顶点的单个静态网格，修复高地边缘露白缝隙。
- 三张地图的矿区仅在当前己方/盟友视野内显示；撤离后小地图与 3D 同时隐藏。
  服务端 full/delta 只下发当前可见的矿区坐标和储量，大厅预览不再暴露矿点。
  新局清空迷雾/探索状态；失败观战继续显示所有矿区。
- `resource_fog_test.py` 检查三图服务端隐藏、侦察、侦察兵死亡、盟友视野、解盟及观战。
  `resource_fog_test.mjs` 执行实际小地图/矿区更新/增量合并函数，覆盖隐藏、撤离、采空、
  首次发现和重开，并检查矿石储量换档后的坡面高度。
- 浏览器三图均实测“侦察显示 → 撤离隐藏 → 观战全显 → 重开归零”，无浏览器错误。
  独立夹具为验证渲染器即使知道坐标也不会泄露，故意预装全部测试矿点；它不代表
  正式对局的网络数据。两张对照截图：`artifacts/mineral-scouted.jpg`、
  `artifacts/mineral-out-of-sight.jpg`。
- 同一 Intel Arc / 1920×1080 / 建筑阴影 / 轻量泛光环境，90 帧预热、300 帧采样：
  中央 400 移动精细单位 + 15 建筑为 60 FPS，帧间隔 p95 16.8 ms，
  CPU p50/p95 为 1.6/2.3 ms，166 draw calls、570254 三角形。
  复现：`/tests/visual_benchmark.html?scenario=army&map=central_scramble&count=400&moving=1&bloom=1`。
  这是独立渲染夹具测量，不含联网与真实战斗模拟；并不承诺所有硬件都达到该帧率。
- 三图循环 4 轮，geometries 始终分别为 151/136/157，textures 均为 14，
  fog shaders 分别为 9/9/18；未出现逐轮增长（不是长期显存测量）。
- 近景复查机位：`?scenario=map&map=central_scramble&x=2750&y=1270&zoom=0.46&pitch=0.86&yaw=0.18&bloom=1`。
  当前本地实景：`artifacts/central-highlands-after.jpg`，地形展示视角、全图可见。

素材来源、实际提示词、生成尺寸和压缩记录：
`public/assets/textures/wilderness-prompts.md`（内置 ImageGen）。
`artifacts/` 为本机截图/基线归档，加入忽略，避免把整个比较构建提交进仓库。
