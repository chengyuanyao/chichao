# 写实旷野材质资产 · 2026-09-08

本轮使用内置 ImageGen 生成游戏实际使用的 bitmap 材质。没有使用红警素材、
第三方摄影下载或 Python 绘制/抠图。生成后仅用 Sharp 等比例缩小并编码为 WebP。
浏览器验收截图是运行游戏渲染器的直接截图，不是 ImageGen 生成的效果图。

## 地表图集

- 文件：`wilderness-atlas-v2.webp`，1024×1024 RGB，559,594 字节。
- 四区：左上草地，右上砂砾土，左下风化岩，右下林下腐殖土。
- 原图：`C:/Users/39463/.codex/generated_images/01a032d2-bfdf-7f03-a158-3a1230e8b0db/exec-3948765d-718d-400f-91d0-6311c115fbca.png`。
- 生成原图实际为 1254×1254；下述请求中的 2048 是目标，不是实际交付尺寸。
- 工具：内置 `image_gen.imagegen`。

实际提示词：

> Use case: photorealistic-natural. Asset type: production game terrain albedo texture atlas, not a concept illustration. Create a square 2x2 atlas made of exactly FOUR equally sized square seamless material textures, edge-to-edge with no margins or dividers. All four regions photographed straight down orthographically, flat neutral diffuse lighting, no cast shadows, no perspective, no horizon, no objects. Top LEFT: realistic temperate wild meadow ground, irregular thin olive green grass blades mixed with straw and tiny dry earth gaps, natural varied small clusters, not a perfectly mown lawn, muted realistic green. Top RIGHT: compacted light brown loamy dirt with irregular grains, small gravel embedded in soil, occasional fine cracks and grit, slightly dry natural earth, not cobblestones. Bottom LEFT: weathered slate/limestone bedrock in gray-brown neutral tones with strata and rough fractured fine mineral surfaces, not separate big boulders. Bottom RIGHT: dark forest floor leaf litter, finely shredded brown leaves, pine needles, moss patches and dark humus. Consistent physical scale: each quadrant shows approximately 3 by 3 meters of ground from exactly overhead. Photographic surface detail, natural earthy colors, no painted/cartoon/stylized/low-poly appearance. Preserve subtle micro occlusion between blades and mineral grains, no baked directional light or large shadows. Each quadrant independently tileable with uniform overall exposure but irregular nonrepeating local distribution; no large distinctive stones or centered focal elements. NO text, NO labels, NO frames, NO logos. This is one packed color material image that will be UV sampled for a real-time strategy game's realistic landscape. Aim high quality 2048x2048.

## 树冠与灌木叶片

- 文件：`woodland-leaves-v2.webp`，768×512 RGBA，190,636 字节。
- 原图：`C:/Users/39463/.codex/generated_images/01a032d2-bfdf-7f03-a158-3a1230e8b0db/exec-8f7b88cf-3e86-4aea-a675-d0f971e30cf4.png`。
- 原图实际为 1536×1024，有真实 alpha；alpha 范围 0–254，均值约 101。
- 工具：内置 `image_gen.imagegen`。

实际提示词：

> Use case: photorealistic-natural. Asset type: real-time game tree foliage alpha-cutout card texture. A single natural cluster of leafy twigs from a mature deciduous woodland tree, photographed straight from above against a GENUINELY TRANSPARENT background. Photorealistic leaves, individual narrow oval leaf shapes, branching fine brown twigs, irregular ragged outer silhouette, many small transparent gaps between leaves and twigs. Cluster is roughly oval but asymmetric, widest across middle, no trunk, no roots, no ground, no entire tree silhouette. Several branching sprays point outward with airy tips, richer dense overlapping olive/moss/deep green leaves in the middle, some pale muted new leaves on edges. Low saturation realistic forest green, diffuse even neutral illumination, subtle contact shading between overlapping leaves only, no cast shadow. Centered with transparent margin on every edge. Crisp alpha edges, no white halo, no checkerboard painted into image, no solid backdrop, no text, no frame, no watermark. This will be mapped onto angled planes to form realistic 3D tree crowns viewed from a strategy-game camera. Natural photographic microtexture, not illustration, not plastic, not a green blob.

## 接入约束

四种地表共用一张图集；草地使用三角网格随机错位混合，避免生成图非完美平铺
产生的重复格纹。岩石、河岸、桥面、土路继续复用图集。树冠/灌木共用叶片图，
alpha-test 写入深度，按 640 世界单位分块合批并进行视锥剔除。
旧材质文件保留，供旧版对比及回退使用；没有增加运行时图片生成或网络依赖。
