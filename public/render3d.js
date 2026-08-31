/**
 * 赤潮：钢铁前线 — 3D 渲染层
 *
 * 服务端仍是纯 2D 权威模拟（x/y 平面）。这一层只负责把快照画成 3D：
 *   世界 (x, y)  ->  场景 (x, 高度, y)      X 向东，Y 向上，Z 向南
 *
 * 单位用 InstancedMesh 按兵种合批（数百单位 = 每种一次 draw call），
 * 建筑数量少，用普通 Mesh 以便播放建造/受损动画。
 * 网格仍由代码生成；表面使用少量共享写实材质图，不改变合批边界。
 */

import * as THREE from './vendor/three.module.min.js';
import { createPostFX } from './postfx.js';

const TAU = Math.PI * 2;

// 矿量图例的唯一数据源。右侧详情、小地图与 3D 矿簇都使用同一组阈值，
// 避免出现“面板说富矿、地图却还是普通图标”的信息冲突。
export const ORE_RESERVE_TIERS = Object.freeze([
  Object.freeze({
    id: 'poor', level: 1, minAmount: 0,
    label: '贫瘠矿脉', shortLabel: '贫矿', color: '#b77a35',
    minimapRadius: 4, minimapPips: 2, crystalCount: 6,
    footprint: 0.68, height: 0.72
  }),
  Object.freeze({
    id: 'standard', level: 2, minAmount: 8000,
    label: '标准矿脉', shortLabel: '普通矿', color: '#ffc247',
    minimapRadius: 5.5, minimapPips: 4, crystalCount: 10,
    footprint: 0.84, height: 0.92
  }),
  Object.freeze({
    id: 'rich', level: 3, minAmount: 30000,
    label: '富集矿脉', shortLabel: '富矿', color: '#ffe06a',
    minimapRadius: 7, minimapPips: 6, crystalCount: 16,
    footprint: 1.02, height: 1.14
  }),
  Object.freeze({
    id: 'giant', level: 4, minAmount: 80000,
    label: '巨型矿脉', shortLabel: '巨矿', color: '#fff0a0',
    minimapRadius: 9, minimapPips: 8, crystalCount: 22,
    footprint: 1.20, height: 1.38
  })
]);

export function oreReserveTier(amount) {
  const reserve = Math.max(0, Number(amount) || 0);
  for (let i = ORE_RESERVE_TIERS.length - 1; i >= 0; i--) {
    if (reserve >= ORE_RESERVE_TIERS[i].minAmount) {
      return ORE_RESERVE_TIERS[i];
    }
  }
  return ORE_RESERVE_TIERS[0];
}

/* ------------------------------------------------------------------ *
 * 几何工具
 * ------------------------------------------------------------------ */

/**
 * 把若干带变换与颜色的零件合并成一个非索引 BufferGeometry。
 *
 * 顶点色在这里当作「团队色的明暗系数」使用：(1,1,1) 得到纯团队色，
 * (0.3,0.3,0.3) 得到很暗的同色。这样每个兵种只需要一个 InstancedMesh，
 * 而 instanceColor 负责乘上该玩家的颜色。
 */
function mergeParts(parts) {
  // 直接把源顶点按矩阵变换写进输出缓冲，不做 geometry.clone()。
  // 单位、建筑和山岩会合并大量零件，clone 一份 BufferGeometry 再
  // applyMatrix4 的开销和 GC 压力都很可观，手写这一段能省掉一半时间。
  const prepared = [];
  let total = 0;
  for (let i = 0; i < parts.length; i++) {
    const part = parts[i];
    let geo = part.geo;
    if (geo.index) {
      // 索引几何体没法直接按顶点拷贝，先摊平一次（模板几何体只会摊一次）
      geo = geo.toNonIndexed();
      part.geo = geo;
    }
    const count = geo.attributes.position.count;
    total += count;
    prepared.push({
      geo: geo, count: count,
      matrix: part.matrix,
      shade: part.shade == null ? 1 : part.shade,
      rgb: part.rgb || null,
      uv: geo.attributes.uv ? geo.attributes.uv.array : null
    });
  }

  const position = new Float32Array(total * 3);
  const normal = new Float32Array(total * 3);
  const color = new Float32Array(total * 3);
  const uv = new Float32Array(total * 2);
  // aTeam：0 = 这个零件用自己的固有色，1 = 乘上玩家的团队色。
  // 没有这条通道的话，所有零件都只能是团队色的深浅，整个基地就是一片单色。
  const teamFlag = new Float32Array(total);
  const nm = new THREE.Matrix3();
  let offset = 0;

  for (let k = 0; k < prepared.length; k++) {
    const item = prepared[k];
    const src = item.geo.attributes.position.array;
    const srcN = item.geo.attributes.normal.array;
    const m = item.matrix;
    const e = m ? m.elements : null;
    if (m) nm.setFromMatrix4(m).invert().transpose();
    const n = nm.elements;
    const rgb = item.rgb;
    const shade = item.shade;

    for (let i = 0; i < item.count; i++) {
      const si = i * 3;
      const di = (offset + i) * 3;
      const ui = (offset + i) * 2;
      const x = src[si], y = src[si + 1], z = src[si + 2];
      if (e) {
        position[di] = e[0] * x + e[4] * y + e[8] * z + e[12];
        position[di + 1] = e[1] * x + e[5] * y + e[9] * z + e[13];
        position[di + 2] = e[2] * x + e[6] * y + e[10] * z + e[14];
      } else {
        position[di] = x; position[di + 1] = y; position[di + 2] = z;
      }
      const nx = srcN[si], ny = srcN[si + 1], nz = srcN[si + 2];
      if (e) {
        let ox = n[0] * nx + n[3] * ny + n[6] * nz;
        let oy = n[1] * nx + n[4] * ny + n[7] * nz;
        let oz = n[2] * nx + n[5] * ny + n[8] * nz;
        const len = Math.sqrt(ox * ox + oy * oy + oz * oz) || 1;
        normal[di] = ox / len; normal[di + 1] = oy / len; normal[di + 2] = oz / len;
      } else {
        normal[di] = nx; normal[di + 1] = ny; normal[di + 2] = nz;
      }
      if (rgb) {
        color[di] = rgb[0]; color[di + 1] = rgb[1]; color[di + 2] = rgb[2];
        teamFlag[offset + i] = 0;
      } else {
        color[di] = shade; color[di + 1] = shade; color[di + 2] = shade;
        teamFlag[offset + i] = 1;
      }
      if (item.uv) {
        uv[ui] = item.uv[i * 2];
        uv[ui + 1] = item.uv[i * 2 + 1];
      }
    }
    offset += item.count;
  }

  const merged = new THREE.BufferGeometry();
  merged.setAttribute('position', new THREE.BufferAttribute(position, 3));
  merged.setAttribute('normal', new THREE.BufferAttribute(normal, 3));
  merged.setAttribute('uv', new THREE.BufferAttribute(uv, 2));
  merged.setAttribute('color', new THREE.BufferAttribute(color, 3));
  merged.setAttribute('aTeam', new THREE.BufferAttribute(teamFlag, 1));
  merged.computeBoundingSphere();
  return merged;
}

/**
 * 颜色参数统一走这里：传数字 = 团队色的明暗系数，传数组 = 零件的固有 RGB。
 * 履带、炮管、混凝土这些本来就不该跟着玩家颜色变，有了固有色，
 * 一个基地才不会是一整片同色。
 */
function tint(value) {
  return Array.isArray(value) ? { rgb: value } : { shade: value };
}

/**
 * 低面数倒角盒：仍是单个 BufferGeometry，但把矩形平面的四个垂直死角切掉。
 * 俯视时车辆、建筑和装备不再像一组积木；8 边截面又比高模圆角便宜得多。
 */
function chamferedBoxGeometry(w, h, d) {
  const radius = 0.5 / Math.cos(Math.PI / 8);
  const geo = new THREE.CylinderGeometry(radius, radius, h, 8, 1, false);
  geo.rotateY(Math.PI / 8);
  geo.scale(w, 1, d);
  return geo;
}

/** 远景 LOD 专用原始方盒：12 个三角面，避免看不见的倒角浪费填充预算。 */
function plainBox(w, h, d, x, y, z, paint, rotY) {
  const m = new THREE.Matrix4();
  if (rotY) m.makeRotationY(rotY);
  m.setPosition(x, y, z);
  return Object.assign({ geo: new THREE.BoxGeometry(w, h, d), matrix: m }, tint(paint));
}

function isEmissivePaint(paint) {
  if (Array.isArray(paint)) return Math.max(paint[0], paint[1], paint[2]) > 1.05;
  return typeof paint === 'number' && paint > 1.05;
}

/**
 * 近景盒状零件默认改成八边倒角截面。钢铁装甲仍保留应有的硬朗平面，
 * 但车舱、护板、背包和建筑梁柱不再暴露 90° 的“积木角”。发光灯条维持
 * 最便宜的 BoxGeometry；远景 simpleUnitParts 也会在局部把 box 指回
 * plainBox，因此这次升级只把顶点预算花在镜头附近。
 */
function box(w, h, d, x, y, z, paint, rotY) {
  const m = new THREE.Matrix4();
  if (rotY) m.makeRotationY(rotY);
  m.setPosition(x, y, z);
  const geo = isEmissivePaint(paint)
    ? new THREE.BoxGeometry(w, h, d)
    : chamferedBoxGeometry(w, h, d);
  return Object.assign({ geo: geo, matrix: m }, tint(paint));
}

/** 近景主体才调用倒角盒；小零件继续用 box，避免无效增加三角面。 */
function chamferedBox(w, h, d, x, y, z, paint, rotY) {
  const m = new THREE.Matrix4();
  if (rotY) m.makeRotationY(rotY);
  m.setPosition(x, y, z);
  return Object.assign({ geo: chamferedBoxGeometry(w, h, d), matrix: m }, tint(paint));
}

function cyl(rTop, rBottom, h, seg, x, y, z, paint, rot) {
  const m = new THREE.Matrix4();
  if (rot) m.multiply(rot);
  m.setPosition(x, y, z);
  return Object.assign({
    geo: new THREE.CylinderGeometry(rTop, rBottom, h, Math.max(6, seg || 8)),
    matrix: m
  }, tint(paint));
}

function sph(r, seg, x, y, z, paint) {
  const smoothSeg = Math.max(8, seg || 8);
  const m = new THREE.Matrix4();
  m.setPosition(x, y, z);
  return Object.assign({
    geo: new THREE.SphereGeometry(r, smoothSeg, Math.max(5, Math.round(smoothSeg * 0.6))), matrix: m
  }, tint(paint));
}

/** 低面数椭球：动物躯干和背包只多一份共享合并几何，不产生新 draw call。 */
function ellipsoid(rx, ry, rz, x, y, z, paint, rot) {
  const geo = new THREE.SphereGeometry(1, 10, 6);
  geo.scale(rx, ry, rz);
  const m = new THREE.Matrix4();
  if (rot) m.multiply(rot);
  m.setPosition(x, y, z);
  return Object.assign({ geo: geo, matrix: m }, tint(paint));
}

/**
 * 旋转剖面体：用 10~14 边的连续轮廓代替“方盒叠方盒”。剖面里的第一项是
 * 归一化半径、第二项是局部高度；X/Z 可分别缩放，所以既能做收腰长袍，
 * 也能做不规则岩躯、浮空底盘和有收分的塔身。只在兵种/建筑首次建缓存时
 * 生成并合并，运行时仍是一个 InstancedMesh，不增加 draw call。
 */
function profiledVolume(profile, radiusX, radiusZ, seg, x, y, z, paint, rotY) {
  const points = profile.map(function (p) { return new THREE.Vector2(p[0], p[1]); });
  const geo = new THREE.LatheGeometry(points, Math.max(8, seg || 12));
  geo.scale(radiusX, 1, radiusZ);
  geo.computeVertexNormals();
  const m = new THREE.Matrix4();
  if (rotY) m.makeRotationY(rotY);
  m.setPosition(x, y, z);
  return Object.assign({ geo: geo, matrix: m }, tint(paint));
}

/**
 * 两点之间的圆肢体。用 8 边圆柱连接关节，比横竖盒子更像弯曲手臂/腿，
 * 但仍会合并进兵种的同一个 InstancedMesh。
 */
function limb(rTop, rBottom, x1, y1, z1, x2, y2, z2, paint) {
  const a = new THREE.Vector3(x1, y1, z1);
  const b = new THREE.Vector3(x2, y2, z2);
  const dir = b.clone().sub(a);
  const length = Math.max(0.01, dir.length());
  const q = new THREE.Quaternion().setFromUnitVectors(
    new THREE.Vector3(0, 1, 0), dir.normalize());
  const m = new THREE.Matrix4().compose(
    a.add(b).multiplyScalar(0.5), q, new THREE.Vector3(1, 1, 1));
  return Object.assign({
    geo: new THREE.CylinderGeometry(rTop, rBottom, length, 8), matrix: m
  }, tint(paint));
}

/** 多轴旋转的方块：龙翼、冰棱这类斜置零件用，避免再叠一层 Group。 */
function boxOrient(w, h, d, x, y, z, paint, rx, ry, rz) {
  const m = new THREE.Matrix4();
  if (rx) m.multiply(new THREE.Matrix4().makeRotationX(rx));
  if (ry) m.multiply(new THREE.Matrix4().makeRotationY(ry));
  if (rz) m.multiply(new THREE.Matrix4().makeRotationZ(rz));
  m.setPosition(x, y, z);
  return Object.assign({ geo: chamferedBoxGeometry(w, h, d), matrix: m }, tint(paint));
}

/** 尖锥（冰棱 / 龙脊 / 喷火锥），默认沿 +Y；需要横置时传入 rot。 */
function pyr(r, h, seg, x, y, z, paint, rot) {
  return cyl(0.04, r, h, seg || 4, x, y, z, paint, rot);
}

/** 圆环：默认在 XY 面（孔朝 +Z）；地面符环传 ROT_X90。 */
function torus(r, tube, radSeg, tubSeg, x, y, z, paint, rot) {
  const m = new THREE.Matrix4();
  if (rot) m.multiply(rot);
  m.setPosition(x, y, z);
  return Object.assign({
    geo: new THREE.TorusGeometry(r, tube, radSeg || 6, tubSeg || 14),
    matrix: m
  }, tint(paint));
}

/**
 * 在几何合并前按世界轴缩放一组零件。缩放只在每个兵种首次建立缓存时执行，
 * 不增加零件、实例或 draw call；近景和远景也能复用同一套比例校正。
 */
function scalePartList(parts, sx, sy, sz) {
  const scale = new THREE.Matrix4().makeScale(sx, sy, sz);
  for (let i = 0; i < parts.length; i++) {
    const matrix = parts[i].matrix || new THREE.Matrix4();
    parts[i].matrix = scale.clone().multiply(matrix);
  }
  return parts;
}

/** 同时校正兵种主体与发光件，保持两条合批通道完全重合。 */
function scaleUnitModel(model, sx, sy, sz) {
  scalePartList(model.body, sx, sy, sz);
  scalePartList(model.glow || [], sx, sy, sz);
  return model;
}

/**
 * 军械配色表。零件按材质分色而不是统统跟着团队色走 ——
 * 履带是橡胶黑、炮管是枪铁灰、地基是混凝土，团队色只留给装甲板与灯带，
 * 这样既有辨识度又不会单调。
 */
const MAT = {
  steel: [0.40, 0.42, 0.45],
  darkSteel: [0.21, 0.23, 0.25],
  gunmetal: [0.15, 0.16, 0.18],
  track: [0.11, 0.11, 0.12],
  rubber: [0.08, 0.08, 0.09],
  olive: [0.25, 0.27, 0.19],
  sandArmor: [0.44, 0.40, 0.30],
  rust: [0.34, 0.20, 0.12],
  concrete: [0.44, 0.43, 0.40],
  concreteDark: [0.27, 0.27, 0.25],
  // 装甲板 / 铆钉条：比混凝土更冷，给钢铁军团甲板一层金属感
  plate: [0.34, 0.36, 0.39],
  rivet: [0.16, 0.16, 0.18],
  glass: [0.16, 0.24, 0.29],
  warnYellow: [0.66, 0.54, 0.12],
  copper: [0.48, 0.30, 0.15],
  // 军犬被毛：黄褐主色 + 深色背鞍/吻部/爪（天然色，不跟团队色走）
  furTan: [0.46, 0.34, 0.20],
  furDark: [0.23, 0.18, 0.14],
  // ---- 秘法会：建筑走暖金石 + 金饰 + 青符；作战单位走冷紫青，互不涂成同一片中紫 ----
  magicStone: [0.44, 0.38, 0.32],   // 傀儡/晶兽岩体：暖灰褐，不是紫晶
  magicHide: [0.18, 0.12, 0.26],    // 影豹近黑紫皮
  scaleHide: [0.30, 0.36, 0.24],    // 巨龙鳞皮
  crystal: [0.42, 0.38, 0.78],      // 冷紫青晶体（单位）
  miteCrystal: [0.52, 0.74, 0.98],  // 晶刺：更偏青的碎晶
  goldStone: [0.58, 0.44, 0.26],    // 建筑暖金砂石
  goldStoneDark: [0.38, 0.28, 0.16],
  goldTrim: [0.86, 0.66, 0.22],     // 奥术金饰
  slate: [0.32, 0.28, 0.24],        // 暖青灰岩
  marble: [0.62, 0.54, 0.40],       // 暖色石面
  bronze: [0.72, 0.52, 0.20],       // 金铜饰，跟建筑金饰一家
  robe: [0.16, 0.10, 0.28],         // 法师深紫袍（不跟团队色走）
  deepViolet: [0.14, 0.08, 0.26],   // 虹视使更瘦的冷紫袍
  frostRobe: [0.50, 0.72, 0.88],    // 冰霜袍：偏饱和苍蓝，远看和法师暗紫分开
  iceShard: [0.74, 0.90, 1.02],     // 冰棱（略亮，软件 GL 上也认得出来）
  plateViolet: [0.28, 0.24, 0.42],  // 晶铠冷紫板甲
  dragonScale: [0.20, 0.28, 0.16],  // 更深的背鳞
  dragonBelly: [0.50, 0.36, 0.20],  // 暖色腹甲
  wingMembrane: [0.16, 0.12, 0.22], // 翼膜
  cloth: [0.20, 0.22, 0.18],        // 步兵布甲
  sandbag: [0.40, 0.34, 0.22],      // 沙袋/夯土
  canvas: [0.38, 0.30, 0.18],       // 帐篷布 / 旗帜衬
  arcaneGlow: [1.35, 0.55, 2.15],   // 作战单位奥术紫（压饱和，避免和建筑青符糊成一片）
  runeCyan: [0.38, 1.90, 2.20],     // 建筑青蓝符文辉光
  frostGlow: [1.15, 1.95, 2.45],    // 冰霜蓝
  fireGlow: [2.45, 1.15, 0.42],     // 龙火橙 / 魔仆不稳核
  // 自发光（分量 > 1）
  exhaust: [2.4, 0.95, 0.28],
  furnace: [2.6, 1.35, 0.35],
  oreGlow: [2.5, 1.7, 0.42],
  hazard: [2.6, 0.5, 0.35],
  teslaArc: [0.55, 1.65, 2.6],
  prismGlow: [1.5, 2.3, 2.4]
};

const MAGIC_STRUCTURE_KINDS = {
  mhq: 1, mpower: 1, mrefinery: 1, mtemple: 1, mcircle: 1, mspring: 1, mtower: 1
};
const MAGIC_UNIT_KINDS = {
  mage: 1, frost: 1, imp: 1, oracle: 1, golem: 1, panther: 1, dragon: 1,
  warden: 1, colossus: 1, comet: 1, mharvester: 1, mmcv: 1, hexling: 1
};
// 一张共享军械图仍只产生四个材质变体。普通步兵/磁暴兵走织物粗糙度，
// 不再把军服照成钢板；其余车辆、石构和兽类分别复用 metal/stone/hide。
const CLOTH_UNIT_KINDS = {
  rifle: 1, rocket: 1, sniper: 1, tesla: 1,
  mage: 1, frost: 1, oracle: 1
};
const HIDE_UNIT_KINDS = { dog: 1, panther: 1, dragon: 1 };

const ROT_X90 = new THREE.Matrix4().makeRotationX(Math.PI / 2);
const ROT_Z90 = new THREE.Matrix4().makeRotationZ(Math.PI / 2);

/**
 * 方形棱台：顶面和底面可以是不同尺寸的矩形。
 *
 * 用 8 段圆柱得到切角矩形截面，再逐顶点按上下分别缩放。斜面装甲比纯方块
 * 更像军事载具，垂直轮廓也不会再是一组直角积木。
 */
function taperedBox(botW, botD, topW, topD, h, x, y, z, paint, rotY) {
  const radius = 0.5 / Math.cos(Math.PI / 8);
  const geo = new THREE.CylinderGeometry(radius, radius, 1, 8, 1);
  geo.rotateY(Math.PI / 8);
  const pos = geo.attributes.position;
  for (let i = 0; i < pos.count; i++) {
    const top = pos.getY(i) > 0;
    pos.setX(i, pos.getX(i) * (top ? topW : botW));
    pos.setZ(i, pos.getZ(i) * (top ? topD : botD));
    pos.setY(i, pos.getY(i) * h);
  }
  geo.computeVertexNormals();
  const m = new THREE.Matrix4();
  if (rotY) m.makeRotationY(rotY);
  m.setPosition(x, y, z);
  return Object.assign({ geo: geo, matrix: m }, tint(paint));
}

/** 远景棱台保留原来的 4 边截面；轮廓只有几像素时不支付 8 边成本。 */
function plainTaperedBox(botW, botD, topW, topD, h, x, y, z, paint, rotY) {
  const geo = new THREE.CylinderGeometry(Math.SQRT1_2, Math.SQRT1_2, 1, 4, 1);
  geo.rotateY(Math.PI / 4);
  const pos = geo.attributes.position;
  for (let i = 0; i < pos.count; i++) {
    const top = pos.getY(i) > 0;
    pos.setX(i, pos.getX(i) * (top ? topW : botW));
    pos.setZ(i, pos.getZ(i) * (top ? topD : botD));
    pos.setY(i, pos.getY(i) * h);
  }
  geo.computeVertexNormals();
  const m = new THREE.Matrix4();
  if (rotY) m.makeRotationY(rotY);
  m.setPosition(x, y, z);
  return Object.assign({ geo: geo, matrix: m }, tint(paint));
}

/* ------------------------------------------------------------------ *
 * 兵种模型
 *
 * 单位朝向 +X（世界 dir = 0 指向 +X），与服务端 atan2(dy, dx) 一致。
 *
 * 每个兵种返回 { body, glow } 两组零件：
 *   body —— 走 Lambert 材质，顶点色当作团队色的明暗系数（0.3 = 暗甲板，
 *           1.0 = 纯团队色）。
 *   glow —— 走 Basic 材质且系数 > 1，因此会被后处理的亮度提取捕捉到，
 *           形成发光条与传感器。这是「科技感」的主要来源。
 * ------------------------------------------------------------------ */

const GLOW_SOFT = 1.45;
const GLOW_WARM = 1.75;
const GLOW_HOT = 2.6;

function infantryParts(weapon) {
  const body = [
    // 20 米制单位里按约 1:7.5 的真人比例重做：小头、长腿、收腰，去掉“大头积木人”。
    taperedBox(5.8, 4.2, 6.2, 4.6, 7.0, 0.1, 11.0, 0, MAT.olive),
    taperedBox(5.2, 4.2, 4.7, 3.8, 2.4, -0.2, 6.7, 0, MAT.cloth),
    chamferedBox(3.8, 1.0, 7.2, -0.1, 14.0, 0, 0.88), // 窄肩章（团队色）
    chamferedBox(2.4, 2.3, 3.2, 2.3, 11.0, 0, 0.72), // 胸牌
    sph(1.85, 10, 0.4, 16.5, 0, MAT.sandArmor),       // 小比例圆头
    taperedBox(4.0, 3.8, 3.2, 3.0, 1.45, 0.4, 18.0, 0, MAT.sandArmor),
    chamferedBox(4.5, 0.38, 4.1, 0.45, 17.55, 0, MAT.darkSteel),
    cyl(0.32, 0.32, 1.3, 8, -1.15, 18.65, 0, MAT.gunmetal),
    // 两条腿轻微外撇，手臂在肘部转折后共同托枪。
    limb(1.05, 0.92, -0.3, 6.0, 1.65, -0.5, 1.45, 1.95, MAT.cloth),
    limb(1.05, 0.92, -0.3, 6.0, -1.65, -0.5, 1.45, -1.95, MAT.cloth),
    chamferedBox(2.9, 1.35, 2.35, 0.15, 0.8, 1.95, MAT.rubber),
    chamferedBox(2.9, 1.35, 2.35, 0.15, 0.8, -1.95, MAT.rubber),
    ellipsoid(1.65, 2.9, 2.25, -3.25, 11.0, 0, MAT.olive),
    limb(1.0, 0.82, 0.0, 13.2, 3.1, 1.45, 10.9, 3.55, MAT.olive),
    limb(0.84, 0.68, 1.45, 10.9, 3.55, 4.1, 9.9, 2.35, MAT.olive),
    limb(1.0, 0.82, 0.0, 13.2, -3.1, 1.25, 10.7, -3.5, MAT.olive),
    limb(0.84, 0.68, 1.25, 10.7, -3.5, 4.15, 9.8, -2.35, MAT.olive)
  ];
  const glow = [
    chamferedBox(0.35, 0.65, 2.4, 2.15, 16.4, 0, GLOW_HOT),
    box(1.8, 0.35, 0.35, -4.45, 11.8, 0, GLOW_SOFT)
  ];

  if (weapon === 'rifle') {
    body.push(cyl(0.48, 0.48, 10.5, 8, 5.2, 9.9, -2.35, MAT.gunmetal, ROT_Z90));
    body.push(chamferedBox(2.2, 1.55, 0.75, 2.0, 10.0, -2.35, MAT.darkSteel));
    glow.push(box(0.7, 0.35, 0.35, 10.25, 9.9, -2.35, GLOW_SOFT));
  } else if (weapon === 'rocket') {
    body.push(cyl(1.45, 1.45, 12.5, 8, 4.0, 11.0, -2.5, MAT.olive, ROT_Z90));
    body.push(cyl(2.0, 1.45, 2.2, 8, -2.6, 11.0, -2.5, MAT.gunmetal, ROT_Z90));
    glow.push(cyl(1.1, 1.1, 0.7, 8, -3.6, 11.0, -2.5, MAT.exhaust, ROT_Z90));
  } else if (weapon === 'sniper') {
    body.push(cyl(0.38, 0.38, 14.0, 8, 6.8, 10.1, -2.4, MAT.gunmetal, ROT_Z90));
    body.push(cyl(0.62, 0.62, 2.6, 8, 2.6, 11.0, -2.4, MAT.darkSteel, ROT_Z90));
    body.push(cyl(0.52, 0.30, 3.4, 8, 12.8, 10.1, -2.4, MAT.darkSteel, ROT_Z90));
    glow.push(sph(0.42, 8, 3.8, 11.0, -2.4, GLOW_HOT));
  } else if (weapon === 'tesla') {
    // 动力甲比普通步兵壮一圈：加宽肩甲 + 加厚胸甲
    body.push(box(4.4, 2.6, 10.6, -0.2, 11.2, 0, 0.5));
    body.push(box(5.2, 4.0, 7.0, -3.8, 8.8, 0, MAT.darkSteel));   // 线圈基座背包
    // 背部两根磁暴线圈（铜色），顶端各顶一颗电弧球
    body.push(cyl(1.2, 1.5, 7.0, 6, -4.4, 14.0, 2.2, MAT.copper));
    body.push(cyl(1.2, 1.5, 7.0, 6, -4.4, 14.0, -2.2, MAT.copper));
    // 电击叉：粗短叉杆 + 前端两根分叉电极
    body.push(box(9.0, 1.6, 1.6, 4.6, 8.4, 1.9, MAT.gunmetal));
    body.push(cyl(0.5, 0.9, 4.4, 6, 9.4, 9.0, 3.1, MAT.copper, ROT_Z90));
    body.push(cyl(0.5, 0.9, 4.4, 6, 9.4, 9.0, 0.7, MAT.copper, ROT_Z90));
    // 线圈球与叉尖的电弧蓝光（>1 自发光，走辉光）
    glow.push(sph(1.5, 6, -4.4, 18.0, 2.2, MAT.teslaArc));
    glow.push(sph(1.5, 6, -4.4, 18.0, -2.2, MAT.teslaArc));
    glow.push(sph(1.1, 6, 11.6, 9.0, 1.9, MAT.teslaArc));
  }
  return { body: body, glow: glow };
}

/** 履带底盘：侧裙 + 负重轮，比两条方条更像装甲车辆。 */
function trackedHull(len, wid, hullH, shade) {
  const half = wid / 2;
  const parts = [
    taperedBox(len, wid * 0.92, len * 0.86, wid * 0.78, hullH, 0, hullH / 2 + 3.4, 0, shade),
    box(len * 0.3, hullH * 0.8, wid * 0.9, len * 0.42, hullH / 2 + 3.0, 0, shade * 0.85)
  ];
  [1, -1].forEach(function (side) {
    parts.push(box(len * 1.04, 5.2, 3.8, 0, 3.0, side * (half + 0.6), MAT.track));
    parts.push(box(len * 0.98, 2.6, 1.6, 0, 6.4, side * (half + 1.0), 0.42));  // 侧裙留团队色
    for (let i = -1; i <= 1; i++) {
      parts.push(cyl(2.0, 2.0, 1.6, 8, i * len * 0.3, 2.8, side * (half + 0.6),
        MAT.darkSteel, ROT_X90));
    }
  });
  // 车尾排气口：一点橙色自发光，打破整车的单色
  parts.push(box(2.2, 2.0, 3.0, -len * 0.5, hullH * 0.7 + 3, wid * 0.22, MAT.gunmetal));
  parts.push(box(0.9, 1.2, 2.0, -len * 0.53, hullH * 0.7 + 3, wid * 0.22, MAT.exhaust));
  return parts;
}

const UNIT_BUILDERS = {
  rifle: function () { return infantryParts('rifle'); },
  rocket: function () { return infantryParts('rocket'); },
  sniper: function () { return infantryParts('sniper'); },

  dog: function () {
    // 军犬：贴地的四足轮廓，德牧式黄褐被毛 + 深色背鞍/吻/爪。
    // 团队色不给皮毛（荧光狗太出戏），只给战术背心与发光项圈做阵营识别。
    const tailRot = new THREE.Matrix4().makeRotationZ(0.9);   // 尾巴上翘
    const collarRot = new THREE.Matrix4().makeRotationY(Math.PI / 2);
    const body = [
      ellipsoid(8.0, 2.8, 2.8, 0, 6.8, 0, MAT.furTan),        // 圆润胸腹
      ellipsoid(3.4, 3.2, 3.1, 5.3, 7.2, 0, MAT.furTan),
      ellipsoid(5.5, 1.0, 2.85, -1.6, 9.0, 0, MAT.furDark),   // 黑背毛区
      ellipsoid(2.7, 2.35, 2.25, 9.2, 9.0, 0, MAT.furTan),
      ellipsoid(2.0, 1.25, 1.45, 12.1, 8.2, 0, MAT.furDark),
      pyr(0.95, 3.0, 6, 8.0, 12.0, 1.45, MAT.furDark),        // 竖耳
      pyr(0.95, 3.0, 6, 8.0, 12.0, -1.45, MAT.furDark),
      taperedBox(7.6, 6.1, 6.8, 5.6, 2.4, 1.0, 8.1, 0, 0.82), // 贴身战术背心
      cyl(0.9, 0.55, 6.0, 6, -9.2, 9.0, 0, MAT.furDark, tailRot) // 翘尾
    ];
    [5.2, -5.2].forEach(function (px) {
      [2.0, -2.0].forEach(function (pz) {
        body.push(limb(0.9, 0.68, px, 5.7, pz, px + 0.4, 0.7, pz, MAT.furDark));
      });
    });
    return {
      body: body,
      glow: [
        torus(2.6, 0.28, 6, 12, 7.1, 8.4, 0, GLOW_SOFT, collarRot),
        sph(0.6, 5, 11.6, 9.8, 1.5, GLOW_HOT),                 // 眼
        sph(0.6, 5, 11.6, 9.8, -1.5, GLOW_HOT)
      ]
    };
  },

  /* ==================== 秘法会（魔法阵营）模型 ==================== */
  mage: function () {
    // 奥术法师：高挑长袍施法者，暗紫袍 + 金饰法杖；肩饰和背部披挂用玩家色标明归属。
    // 长袍使用七段收腰剖面，而不是一只直线棱台；肩披、兜帽也改为圆润体块。
    const robeProfile = [
      [0.0, -6.6], [1.0, -6.6], [0.98, -5.7], [0.78, -1.8],
      [0.58, 3.0], [0.43, 6.3], [0.0, 6.6]
    ];
    const hoodProfile = [
      [0.0, -2.2], [1.0, -2.2], [0.82, -0.6], [0.48, 1.4], [0.0, 2.2]
    ];
    const body = [
      profiledVolume(robeProfile, 4.45, 4.05, 12, 0, 7.2, 0, MAT.robe),
      torus(4.28, 0.28, 6, 18, 0, 1.15, 0, MAT.goldTrim, ROT_X90), // 金袍摆
      ellipsoid(3.25, 0.92, 4.0, 0, 13.25, 0, 0.90),          // 圆肩披（团队色）
      ellipsoid(3.6, 0.48, 3.55, -1.65, 11.35, 0, 0.80),      // 俯视可见的玩家色披挂
      torus(2.35, 0.24, 6, 14, 0, 14.05, 0, MAT.goldTrim, ROT_X90),
      sph(1.85, 10, 0, 16.0, 0, MAT.sandArmor),
      profiledVolume(hoodProfile, 1.75, 1.75, 12, 0, 18.6, 0, MAT.robe),
      cyl(2.55, 2.75, 0.32, 12, 0, 16.8, 0, MAT.goldTrim),    // 金帽沿
      // 法杖保留后端配重，只收短前端，避免视觉轮廓远超点选范围。
      cyl(0.38, 0.38, 14.0, 6, 4.7, 9.2, 2.8, MAT.goldTrim, ROT_Z90),
      cyl(0.62, 0.62, 0.4, 8, 11.7, 9.2, 2.8, MAT.goldTrim, ROT_Z90),
      limb(0.88, 0.70, 0.0, 13.0, 3.2, 1.5, 10.8, 3.7, MAT.robe),
      limb(0.88, 0.70, 0.0, 13.0, -3.2, 1.4, 10.7, -3.3, MAT.robe),
      limb(0.72, 0.58, 1.5, 10.8, 3.7, 4.4, 9.4, 2.8, MAT.robe)
    ];
    return {
      body: body,
      glow: [
        sph(2.15, 8, 12.0, 9.2, 2.8, MAT.runeCyan),
        sph(0.7, 5, 10.2, 9.2, 2.8, MAT.arcaneGlow),
        cyl(0.22, 0.22, 2.6, 8, 0, 14.6, 0, MAT.runeCyan, ROT_Z90),
        cyl(3.4, 3.4, 0.28, 10, 0, 1.15, 0, MAT.runeCyan)
      ]
    };
  },

  frost: function () {
    // 冰霜女巫：宽檐帽 + 苍白斗篷 + 霜环，杖顶寒晶簇。宽帽剪影远看不是法师尖帽。
    const tipDn = new THREE.Matrix4().makeRotationZ(0.85);
    const tipSide = new THREE.Matrix4().makeRotationX(1.15).multiply(new THREE.Matrix4().makeRotationZ(Math.PI / 2));
    const mantleProfile = [
      [0.0, -5.8], [1.0, -5.8], [0.96, -4.7], [0.78, -1.2],
      [0.62, 2.8], [0.42, 5.3], [0.0, 5.8]
    ];
    const body = [
      profiledVolume(mantleProfile, 5.2, 5.2, 12, 0, 6.4, 0, MAT.frostRobe),
      cyl(5.6, 6.0, 0.55, 12, 0, 1.02, 0, MAT.iceShard),
      chamferedBox(4.2, 1.1, 7.0, 0, 12.4, 0, 0.72),
      chamferedBox(5.8, 0.55, 6.1, -2.0, 10.8, 0, 0.82),     // 玩家色披挂
      box(3.2, 1.6, 4.2, 0.4, 13.2, 3.6, MAT.iceShard),
      box(3.2, 1.6, 4.2, 0.4, 13.2, -3.6, MAT.iceShard),
      sph(1.8, 10, 0, 14.6, 0, [0.86, 0.94, 1.0]),
      cyl(7.4, 7.8, 0.48, 14, 0, 16.5, 0, MAT.frostRobe),      // 宽檐
      taperedBox(3.2, 3.2, 0.7, 0.7, 3.2, 0, 18.4, 0, MAT.frostRobe),
      pyr(0.95, 3.8, 4, 0, 20.4, 0, MAT.iceShard),
      pyr(0.7, 2.8, 4, 0.5, 19.4, 1.8, MAT.iceShard),
      pyr(0.7, 2.8, 4, 0.5, 19.4, -1.8, MAT.iceShard),
      cyl(0.32, 0.46, 13.2, 6, 5.0, 9.0, 2.8, MAT.iceShard, ROT_Z90),
      limb(0.86, 0.68, 0.0, 12.2, 3.2, 1.5, 10.0, 3.6, MAT.frostRobe),
      limb(0.86, 0.68, 0.0, 12.2, -3.2, 1.4, 9.9, -3.2, MAT.frostRobe),
      limb(0.70, 0.56, 1.5, 10.0, 3.6, 4.4, 8.8, 2.8, MAT.frostRobe)
    ];
    return {
      body: body,
      glow: [
        sph(2.15, 8, 12.0, 9.0, 2.8, MAT.frostGlow),
        pyr(1.15, 3.6, 4, 12.0, 11.6, 2.8, MAT.frostGlow),
        pyr(0.88, 2.6, 4, 12.0, 6.8, 2.8, MAT.frostGlow, tipDn),
        pyr(0.74, 2.3, 4, 12.0, 9.0, 4.7, MAT.frostGlow, tipSide),
        sph(0.55, 5, 0, 21.6, 0, MAT.frostGlow),
        cyl(4.2, 4.2, 0.24, 12, 0, 1.12, 0, MAT.frostGlow),
        sph(0.42, 5, 2.6, 3.0, 3.0, MAT.frostGlow),
        sph(0.36, 5, -2.0, 3.4, -2.8, MAT.frostGlow)
      ]
    };
  },

  imp: function () {
    // 晶刺：贴地锯齿晶螨。低矮六足碎晶，不是直立小人，也不是悬浮魔球。
    const body = [
      ellipsoid(4.5, 1.9, 3.25, 0.4, 3.5, 0, MAT.miteCrystal),
      ellipsoid(2.2, 1.45, 2.0, 4.3, 3.9, 0, MAT.crystal),
      pyr(0.72, 2.6, 4, 1.2, 6.6, 0, MAT.miteCrystal),
      pyr(0.55, 2.2, 4, -1.4, 6.2, 1.5, MAT.miteCrystal),
      pyr(0.55, 2.2, 4, -1.4, 6.2, -1.5, MAT.miteCrystal),
      pyr(0.48, 2.0, 4, -3.4, 5.8, 0, MAT.crystal),
      pyr(0.42, 2.4, 4, 6.2, 4.0, 0, MAT.miteCrystal, ROT_Z90),
      box(6.4, 0.70, 4.8, -0.4, 5.4, 0, 0.92)               // 玩家色背甲
    ];
    [3.2, 0.2, -2.8].forEach(function (px) {
      [2.4, -2.4].forEach(function (pz) {
        body.push(box(1.15, 2.6, 1.15, px, 1.4, pz, MAT.crystal));
      });
    });
    return {
      body: body,
      glow: [
        sph(1.05, 6, 1.4, 4.2, 0, MAT.runeCyan),
        sph(0.38, 5, 5.4, 4.4, 0.7, MAT.runeCyan),
        sph(0.38, 5, 5.4, 4.4, -0.7, MAT.runeCyan),
        cyl(2.6, 2.6, 0.18, 10, 0.4, 0.55, 0, MAT.runeCyan)
      ]
    };
  },

  oracle: function () {
    // 虹视使：细长棱晶杖 + 发光面罩。比法师更瘦更高，没有尖帽，面罩一眼是远视者。
    const seerProfile = [
      [0.0, -7.7], [1.0, -7.7], [0.86, -5.8], [0.61, -0.8],
      [0.47, 4.6], [0.34, 7.1], [0.0, 7.7]
    ];
    const body = [
      profiledVolume(seerProfile, 2.8, 2.8, 12, 0, 8.4, 0, MAT.deepViolet),
      chamferedBox(2.8, 0.9, 5.1, 0, 16.2, 0, 0.70),
      chamferedBox(5.0, 0.52, 5.5, -1.8, 13.8, 0, 0.82),     // 玩家色披肩
      sph(1.72, 10, 0, 18.0, 0, MAT.sandArmor),
      chamferedBox(4.5, 0.82, 2.0, 1.2, 18.2, 0, MAT.crystal), // 面罩骨
      limb(0.76, 0.60, 0.0, 15.3, 2.5, 1.2, 12.4, 2.8, MAT.deepViolet),
      limb(0.76, 0.60, 0.0, 15.3, -2.5, 1.1, 12.3, -2.8, MAT.deepViolet),
      limb(0.62, 0.50, 1.2, 12.4, 2.8, 4.0, 11.2, 2.2, MAT.deepViolet),
      // 虹视使原法杖占满近四个碰撞半径；保持细长辨识度但收短四分之一。
      cyl(0.22, 0.28, 16.5, 6, 4.65, 11.2, 2.4, MAT.goldTrim, ROT_Z90)
    ];
    return {
      body: body,
      glow: [
        box(4.6, 0.7, 1.7, 1.6, 18.2, 0, MAT.prismGlow),
        sph(1.25, 7, 13.0, 11.2, 2.4, MAT.prismGlow),
        pyr(0.62, 2.6, 5, 14.2, 12.8, 2.4, MAT.prismGlow),
        pyr(0.48, 2.0, 5, 14.2, 9.6, 2.4, MAT.runeCyan),
        sph(0.36, 5, 0.5, 18.0, 1.0, MAT.prismGlow),
        sph(0.36, 5, 0.5, 18.0, -1.0, MAT.prismGlow),
        cyl(2.2, 2.2, 0.18, 10, 0, 1.1, 0, MAT.prismGlow)
      ]
    };
  },

  golem: function () {
    // 岩石傀儡：厚重岩元素。暖灰褐岩躯 + 巨石双臂，水晶只作拳面/核心，不是紫晶人。
    const torsoProfile = [
      [0.0, -6.3], [0.68, -6.3], [0.92, -4.6], [1.0, -1.2],
      [0.90, 2.6], [0.66, 5.8], [0.0, 6.3]
    ];
    const body = [
      profiledVolume(torsoProfile, 7.0, 5.8, 10, 0, 10.8, 0, MAT.magicStone),
      ellipsoid(3.15, 2.75, 2.85, 3.25, 18.0, 0, MAT.slate),
      sph(1.8, 8, 4.8, 18.8, 0, MAT.slate),
      limb(2.75, 2.35, 0.2, 14.2, 6.0, 1.3, 9.2, 7.6, MAT.magicStone),
      limb(2.75, 2.35, 0.2, 14.2, -6.0, 1.3, 9.2, -7.6, MAT.magicStone),
      ellipsoid(4.55, 0.62, 3.4, -1.0, 16.15, 0, 0.88),       // 圆拱玩家色胸背甲
      limb(2.4, 2.85, 1.3, 9.2, 7.6, 2.8, 4.6, 7.8, MAT.goldStoneDark),
      limb(2.4, 2.85, 1.3, 9.2, -7.6, 2.8, 4.6, -7.8, MAT.goldStoneDark),
      limb(2.15, 2.55, -1.0, 7.2, 3.3, -0.5, 1.2, 3.8, MAT.slate),
      limb(2.15, 2.55, -1.0, 7.2, -3.3, -0.5, 1.2, -3.8, MAT.slate),
      ellipsoid(3.15, 1.45, 2.75, 0.5, 1.0, 3.9, MAT.slate),
      ellipsoid(3.15, 1.45, 2.75, 0.5, 1.0, -3.9, MAT.slate),
      sph(1.2, 7, 4.8, 4.5, 7.8, MAT.crystal),
      sph(1.2, 7, 4.8, 4.5, -7.8, MAT.crystal)
    ];
    return scaleUnitModel({
      body: body,
      glow: [
        sph(1.7, 7, 4.8, 11.2, 0, MAT.runeCyan),
        sph(0.55, 5, 5.8, 16.2, 1.05, MAT.runeCyan),
        sph(0.55, 5, 5.8, 16.2, -1.05, MAT.runeCyan)
      ]
    }, 1.35, 1.10, 1.35);
  },

  panther: function () {
    // 影豹：低矮四足疾行兽。近黑皮 + 青脊纹 + 金项圈，剪影是猫不是晶螨。
    const tailRot = new THREE.Matrix4().makeRotationZ(0.78);
    const collarRot = new THREE.Matrix4().makeRotationY(Math.PI / 2);
    const body = [
      ellipsoid(9.2, 2.1, 2.3, 0.2, 5.4, 0, MAT.magicHide),
      ellipsoid(3.5, 2.5, 2.5, 6.8, 6.0, 0, MAT.magicHide),
      ellipsoid(2.7, 1.75, 2.0, 10.4, 7.2, 0, MAT.magicHide),
      ellipsoid(1.7, 0.9, 1.1, 13.2, 6.6, 0, MAT.magicHide),
      pyr(0.72, 2.4, 6, 8.8, 9.7, 1.25, MAT.magicHide),
      pyr(0.72, 2.4, 6, 8.8, 9.7, -1.25, MAT.magicHide),
      taperedBox(10.0, 6.8, 8.2, 5.6, 1.2, -1.0, 8.8, 0, 0.94), // 玩家色鞍甲
      cyl(0.55, 0.32, 7.4, 6, -10.2, 7.0, 0, MAT.magicHide, tailRot),
      torus(2.15, 0.22, 6, 10, 8.4, 7.0, 0, MAT.goldTrim, collarRot)
    ];
    [5.8, -6.0].forEach(function (px) {
      [1.7, -1.7].forEach(function (pz) {
        body.push(limb(0.72, 0.52, px, 4.9, pz, px + 0.5, 0.5, pz, MAT.magicHide));
      });
    });
    return scaleUnitModel({
      body: body,
      glow: [
        sph(0.58, 5, 12.6, 7.8, 1.15, MAT.runeCyan),
        sph(0.58, 5, 12.6, 7.8, -1.15, MAT.runeCyan),
        limb(0.22, 0.22, -7.6, 7.7, 0, 7.2, 8.1, 0, MAT.runeCyan)
      ]
    }, 0.88, 1.0, 1.0);
  },

  dragon: function () {
    // 秘法巨龙：拉长的翼展剪影，RTS 俯视角一眼是龙而不是大傀儡
    const body = [
      ellipsoid(14.0, 4.0, 5.5, -2, 8.2, 0, MAT.scaleHide),
      ellipsoid(10.0, 1.8, 3.7, -1.2, 5.6, 0, MAT.dragonBelly),
      box(8.4, 3.0, 8.0, 4.2, 12.2, 0, MAT.dragonScale),
      taperedBox(7.4, 4.2, 5.4, 3.2, 4.0, 11.4, 11.5, 0, MAT.scaleHide),
      taperedBox(6.2, 3.6, 4.6, 2.8, 3.4, 16.6, 13.4, 0, MAT.scaleHide),
      taperedBox(6.6, 4.4, 5.0, 3.2, 3.6, 21.2, 14.8, 0, MAT.scaleHide),
      taperedBox(4.4, 2.4, 2.4, 1.5, 1.7, 25.2, 14.2, 0, MAT.scaleHide),
      box(3.8, 1.0, 2.2, 24.6, 13.1, 0, MAT.dragonScale),
      pyr(0.55, 3.4, 4, 19.6, 17.6, 1.5, MAT.goldTrim),
      pyr(0.55, 3.4, 4, 19.6, 17.6, -1.5, MAT.goldTrim),
      box(2.4, 0.4, 2.8, 20.4, 16.4, 2.5, MAT.goldTrim),
      box(2.4, 0.4, 2.8, 20.4, 16.4, -2.5, MAT.goldTrim),
      pyr(0.7, 3.0, 4, 6.2, 13.0, 0, MAT.goldTrim),
      pyr(0.62, 2.6, 4, 1.0, 12.7, 0, MAT.goldTrim),
      pyr(0.52, 2.2, 4, -4.2, 12.2, 0, MAT.goldTrim),
      pyr(0.42, 1.8, 4, -9.4, 11.4, 0, MAT.goldTrim),
      taperedBox(8.4, 2.8, 5.4, 1.8, 2.5, -16.4, 7.6, 0, MAT.scaleHide),
      taperedBox(7.2, 2.0, 4.0, 1.1, 1.9, -22.6, 7.2, 0, MAT.scaleHide),
      taperedBox(6.0, 1.2, 2.4, 0.4, 1.3, -27.6, 7.4, 0, MAT.scaleHide),
      box(0.45, 2.8, 3.8, -30.0, 8.5, 0, MAT.goldTrim),
      box(2.6, 5.0, 2.6, 6.2, 3.1, 4.3, MAT.dragonScale),
      box(2.6, 5.0, 2.6, 6.2, 3.1, -4.3, MAT.dragonScale),
      box(2.4, 4.5, 2.4, -8.4, 2.9, 3.6, MAT.dragonScale),
      box(2.4, 4.5, 2.4, -8.4, 2.9, -3.6, MAT.dragonScale),
      box(3.5, 1.15, 2.4, 7.8, 1.0, 4.3, MAT.dragonScale),
      box(3.5, 1.15, 2.4, 7.8, 1.0, -4.3, MAT.dragonScale),
      box(14.0, 0.75, 6.2, -2.0, 12.3, 0, 0.90)              // 玩家色背甲
    ];
    const glow = [
      sph(1.7, 7, 27.2, 14.3, 0, MAT.fireGlow),
      cyl(0.15, 2.4, 5.8, 6, 30.2, 14.1, 0, MAT.fireGlow, ROT_Z90),
      sph(0.85, 5, 22.2, 15.8, 1.55, MAT.fireGlow),
      sph(0.85, 5, 22.2, 15.8, -1.55, MAT.fireGlow),
      sph(1.05, 6, 2.2, 7.1, 0, MAT.runeCyan)
    ];
    const wingBody = [];
    const wingGlow = [];
    [1, -1].forEach(function (side) {
      wingBody.push(boxOrient(18, 1.05, 1.45, -1.6, 13.6, side * 12.4, MAT.dragonScale, side * 0.16, side * 0.52, 0.18));
      wingBody.push(boxOrient(16, 0.85, 1.15, -9.2, 15.0, side * 22.4, MAT.dragonScale, side * 0.24, side * 0.88, 0.10));
      wingBody.push(boxOrient(11, 0.55, 0.75, -4.6, 13.2, side * 17.2, MAT.dragonScale, side * 0.08, side * 0.66, -0.04));
      wingBody.push(boxOrient(22, 0.22, 15.0, -3.4, 13.4, side * 16.0, MAT.wingMembrane, side * 0.18, side * 0.48, 0.08));
      wingBody.push(boxOrient(14, 0.18, 11.4, -11.0, 14.4, side * 23.6, MAT.wingMembrane, side * 0.24, side * 0.82, 0.05));
      wingBody.push(boxOrient(14, 0.34, 3.4, -2.0, 13.9, side * 17.0, 0.86, side * 0.18, side * 0.48, 0.08));
      wingGlow.push(boxOrient(15, 0.14, 0.4, -2.0, 13.8, side * 14.6, MAT.fireGlow, side * 0.18, side * 0.48, 0.08));
    });
    // 只收短翼展，不压缩头、躯干与尾巴；依旧是同一份合并网格。
    body.push.apply(body, scalePartList(wingBody, 1.0, 1.0, 0.82));
    glow.push.apply(glow, scalePartList(wingGlow, 1.0, 1.0, 0.82));
    return { body: body, glow: glow };
  },

  warden: function () {
    // 晶铠卫士：天启级巨型持盾构装。宽肩重甲、晶冠、分层塔盾与晶锤组成
    // 清楚的圣骑士剪影；所有零件仍合进同一 InstancedMesh，不增加 draw call。
    const cuirassProfile = [
      [0.0, -6.2], [0.72, -6.2], [0.95, -4.2], [1.0, 0.9],
      [0.86, 4.1], [0.58, 6.2], [0.0, 6.2]
    ];
    const body = [
      profiledVolume(cuirassProfile, 6.6, 5.1, 10, 0, 11.4, 0, MAT.plateViolet),
      taperedBox(11.8, 8.8, 9.4, 7.0, 3.2, -0.3, 17.0, 0, MAT.slate),
      box(11.0, 0.55, 7.4, 0.3, 18.5, 0, MAT.goldTrim),
      box(10.4, 0.95, 6.8, -0.4, 17.8, 0, 0.92),              // 玩家色胸背甲
      taperedBox(6.2, 5.6, 4.4, 4.0, 4.6, 2.0, 21.1, 0, MAT.plateViolet),
      sph(1.9, 7, 3.3, 22.0, 0, MAT.slate),
      pyr(0.78, 3.8, 5, 2.7, 25.0, 0, MAT.crystal),           // 晶冠
      // 双层肩甲把上半身横向撑开，远景也有重型构装的压迫感。
      ellipsoid(3.4, 1.8, 3.0, 0.8, 16.2, 6.5, MAT.plateViolet),
      ellipsoid(3.4, 1.8, 3.0, 0.8, 16.2, -6.5, MAT.plateViolet),
      pyr(0.72, 2.8, 4, 0.6, 19.1, 6.5, MAT.goldTrim),
      pyr(0.72, 2.8, 4, 0.6, 19.1, -6.5, MAT.goldTrim),
      limb(2.1, 1.65, 0.6, 14.5, 5.7, 1.6, 8.0, 7.0, MAT.plateViolet),
      limb(2.1, 1.65, 0.6, 14.5, -5.7, 1.6, 8.0, -7.0, MAT.plateViolet),
      limb(1.9, 1.55, -0.8, 7.2, 3.2, 0.0, 0.9, 3.6, MAT.slate),
      limb(1.9, 1.55, -0.8, 7.2, -3.2, 0.0, 0.9, -3.6, MAT.slate),
      ellipsoid(2.9, 0.85, 2.4, 0.7, 0.9, 3.8, MAT.goldStoneDark),
      ellipsoid(2.9, 0.85, 2.4, 0.7, 0.9, -3.8, MAT.goldStoneDark),
      // 分层鸢盾：厚金边、玩家色盾面、中央晶脊，避免一整块平板。
      taperedBox(2.1, 13.8, 1.2, 10.2, 15.8, 2.4, 11.1, 10.2, MAT.goldTrim),
      taperedBox(1.05, 11.8, 0.72, 8.5, 13.8, 3.1, 11.2, 10.2, 0.84),
      box(0.65, 10.6, 1.15, 3.7, 11.5, 10.2, MAT.crystal),
      // 另一手改为厚重晶锤，短柄大锤头比细矛更符合前排卫士。
      cyl(0.48, 0.58, 17.5, 7, 6.8, 11.0, -5.1, MAT.goldTrim, ROT_Z90),
      taperedBox(5.8, 4.8, 4.5, 3.7, 5.4, 17.1, 11.0, -5.1, MAT.crystal, Math.PI / 2),
      pyr(0.9, 3.2, 4, 20.0, 11.0, -5.1, MAT.goldTrim, ROT_Z90)
    ];
    return scaleUnitModel({
      body: body,
      glow: [
        box(3.4, 0.65, 1.25, 4.0, 22.0, 0, MAT.runeCyan),
        sph(1.45, 7, 4.8, 13.0, 0, MAT.runeCyan),
        box(0.5, 10.2, 0.5, 3.8, 11.5, 10.2, MAT.runeCyan),
        sph(1.25, 7, 17.1, 11.0, -5.1, MAT.runeCyan),
        cyl(5.4, 5.4, 0.22, 10, 0, 0.32, 0, MAT.runeCyan)
      ]
    }, 1.18, 1.14, 1.18);
  },

  colossus: function () {
    // 裂地晶兽：四足晶兽驮晶陨鞍塔，俯视是攻城兽不是大傀儡/晶铠。
    const barrel = new THREE.Matrix4().makeRotationZ(Math.PI / 2 - 0.38);
    const beastProfile = [
      [0.0, -4.3], [0.72, -4.3], [0.94, -3.0], [1.0, 0.3],
      [0.88, 2.8], [0.58, 4.3], [0.0, 4.3]
    ];
    const body = [
      profiledVolume(beastProfile, 13.0, 7.2, 10, 0.2, 10.4, 0, MAT.magicStone),
      taperedBox(20, 10.4, 15.2, 8.2, 3.4, 0.6, 6.4, 0, MAT.slate),
      taperedBox(8.6, 12.4, 6.6, 10.2, 5.4, 8.4, 12.6, 0, MAT.slate),
      taperedBox(9.4, 13.2, 7.2, 11.0, 5.8, -8.6, 13.0, 0, MAT.magicStone),
      taperedBox(7.4, 6.6, 5.2, 4.8, 5.0, 16.0, 13.0, 0, MAT.slate),
      sph(1.9, 6, 19.0, 13.4, 0, MAT.slate),
      box(2.6, 1.4, 3.4, 19.8, 12.2, 0, MAT.miteCrystal),
      pyr(0.95, 4.0, 4, 17.2, 16.8, 1.7, MAT.goldTrim),
      pyr(0.95, 4.0, 4, 17.2, 16.8, -1.7, MAT.goldTrim),
      pyr(0.62, 2.6, 4, 4.8, 15.6, 0, MAT.goldTrim),
      pyr(0.52, 2.2, 4, -0.6, 15.2, 0, MAT.goldTrim),
      pyr(0.44, 1.8, 4, -6.0, 14.8, 0, MAT.goldTrim),
      taperedBox(10.4, 10.2, 8.2, 8.0, 4.4, -2.2, 17.0, 0, MAT.slate),
      taperedBox(15.2, 9.8, 12.4, 7.6, 1.1, -1.2, 15.2, 0, 0.88), // 玩家色鞍甲
      taperedBox(7.4, 7.0, 5.2, 5.0, 3.8, -1.4, 20.6, 0, MAT.miteCrystal),
      cyl(1.95, 2.45, 22, 8, 10.6, 23.0, 0, MAT.miteCrystal, barrel),
      cyl(2.9, 2.9, 3.4, 8, 20.6, 27.2, 0, MAT.goldTrim, barrel),
      taperedBox(2.8, 2.8, 1.15, 1.15, 4.2, -5.4, 19.8, 4.8, MAT.goldTrim),
      taperedBox(2.8, 2.8, 1.15, 1.15, 4.2, -5.4, 19.8, -4.8, MAT.goldTrim),
      limb(2.35, 2.0, 8.2, 8.5, 5.8, 9.0, 1.2, 6.0, MAT.magicStone),
      limb(2.35, 2.0, 8.2, 8.5, -5.8, 9.0, 1.2, -6.0, MAT.magicStone),
      limb(2.55, 2.15, -8.0, 8.7, 6.1, -8.6, 1.3, 6.4, MAT.magicStone),
      limb(2.55, 2.15, -8.0, 8.7, -6.1, -8.6, 1.3, -6.4, MAT.magicStone),
      taperedBox(5.4, 5.4, 3.6, 3.6, 2.2, 9.0, 1.2, 6.0, MAT.goldStoneDark),
      taperedBox(5.4, 5.4, 3.6, 3.6, 2.2, 9.0, 1.2, -6.0, MAT.goldStoneDark),
      taperedBox(5.8, 5.8, 3.8, 3.8, 2.4, -8.6, 1.3, 6.4, MAT.goldStoneDark),
      taperedBox(5.8, 5.8, 3.8, 3.8, 2.4, -8.6, 1.3, -6.4, MAT.goldStoneDark),
      taperedBox(6.8, 3.8, 2.6, 1.8, 2.6, -16.8, 9.4, 0, MAT.miteCrystal)
    ];
    return {
      body: body,
      glow: [
        sph(2.05, 7, -1.2, 14.2, 0, MAT.runeCyan),
        sph(1.35, 6, 23.0, 28.2, 0, MAT.runeCyan),
        cyl(1.15, 1.15, 0.55, 8, 12.6, 23.8, 0, MAT.frostGlow, barrel),
        sph(0.55, 5, 19.4, 13.8, 1.15, MAT.runeCyan),
        sph(0.55, 5, 19.4, 13.8, -1.15, MAT.runeCyan),
        cyl(9.2, 9.2, 0.22, 12, 0, 0.38, 0, MAT.runeCyan),
        cyl(2.35, 2.35, 0.26, 8, 9.0, 0.32, 6.0, MAT.runeCyan),
        cyl(2.35, 2.35, 0.26, 8, 9.0, 0.32, -6.0, MAT.runeCyan),
        cyl(2.55, 2.55, 0.26, 8, -8.6, 0.32, 6.4, MAT.runeCyan),
        cyl(2.55, 2.55, 0.26, 8, -8.6, 0.32, -6.4, MAT.runeCyan),
        box(8.4, 0.38, 0.38, -2.0, 17.4, 4.7, MAT.frostGlow),
        box(8.4, 0.38, 0.38, -2.0, 17.4, -4.7, MAT.frostGlow)
      ]
    };
  },

  comet: function () {
    // 坠星台：厚重发射底盘 + 竖直晶炮。曲射台不是法师，也不是裂地晶兽的四足鞍塔。
    const launchBaseProfile = [
      [0.0, -3.8], [0.82, -3.8], [1.0, -2.2], [0.96, 1.2],
      [0.76, 3.2], [0.0, 3.8]
    ];
    const body = [
      profiledVolume(launchBaseProfile, 18.0, 12.0, 12, 0, 7.2, 0, MAT.goldStoneDark),
      taperedBox(22, 20, 18, 16, 3.6, -1.0, 12.4, 0, MAT.slate),
      taperedBox(27, 16, 23, 13, 1.0, -1.0, 12.3, 0, 0.88),  // 玩家色发射平台顶板
      box(28, 3.2, 1.6, -2, 9.6, 11.2, MAT.goldTrim),
      box(28, 3.2, 1.6, -2, 9.6, -11.2, MAT.goldTrim),
      box(5.2, 7.6, 5.2, 10.6, 4.8, 7.4, MAT.goldStone),
      box(5.2, 7.6, 5.2, 10.6, 4.8, -7.4, MAT.goldStone),
      box(5.6, 8.0, 5.6, -10.6, 5.0, 7.8, MAT.goldStone),
      box(5.6, 8.0, 5.6, -10.6, 5.0, -7.8, MAT.goldStone),
      taperedBox(10.4, 9.6, 7.2, 6.8, 5.4, 0.6, 16.2, 0, MAT.slate),
      cyl(2.15, 2.85, 22, 8, 0.8, 28.4, 0, MAT.miteCrystal),
      cyl(3.4, 3.4, 3.0, 8, 0.8, 16.6, 0, MAT.goldTrim),
      box(2.0, 16, 2.4, 4.6, 18.8, 5.8, MAT.slate),
      box(2.0, 16, 2.4, 4.6, 18.8, -5.8, MAT.slate),
      box(2.0, 16, 2.4, -3.2, 18.8, 5.8, MAT.slate),
      box(2.0, 16, 2.4, -3.2, 18.8, -5.8, MAT.slate),
      sph(2.6, 8, 0.8, 40.2, 0, MAT.miteCrystal),
      pyr(1.05, 3.8, 4, 0.8, 43.6, 0, MAT.miteCrystal)
    ];
    return {
      body: body,
      glow: [
        sph(2.1, 7, 0.8, 40.2, 0, MAT.runeCyan),
        sph(0.95, 6, 0.8, 44.2, 0, MAT.frostGlow),
        cyl(1.15, 1.15, 0.5, 8, 0.8, 29.2, 0, MAT.runeCyan),
        cyl(10.4, 10.4, 0.22, 12, 0, 0.42, 0, MAT.runeCyan),
        box(16, 0.4, 0.4, -2, 11.2, 11.6, MAT.frostGlow),
        box(16, 0.4, 0.4, -2, 11.2, -11.6, MAT.frostGlow)
      ]
    };
  },

  mharvester: function () {
    // 浮游晶簇：暖金悬浮座托青晶簇，阵营色淡，不跟作战单位抢剪影。
    const floatBase = [
      [0.0, -3.0], [0.54, -3.0], [0.88, -1.6], [1.0, 0.2],
      [0.86, 2.1], [0.46, 2.8], [0.0, 2.8]
    ];
    const deckProfile = [
      [0.0, -0.65], [0.82, -0.65], [1.0, -0.20], [0.86, 0.55], [0.0, 0.65]
    ];
    const tallCrystal = [
      [0.0, -4.7], [0.76, -4.7], [1.0, -2.6], [0.70, 2.4], [0.0, 6.0]
    ];
    const sideCrystal = [
      [0.0, -3.6], [0.78, -3.6], [1.0, -1.7], [0.62, 1.8], [0.0, 4.5]
    ];
    const body = [
      profiledVolume(floatBase, 9.2, 8.0, 12, 0, 6, 0, MAT.goldStoneDark),
      profiledVolume(deckProfile, 7.8, 6.5, 12, 0, 8.5, 0, 0.90), // 玩家色浮台上盖
      torus(8.25, 0.46, 6, 18, 0, 8.55, 0, 0.96, ROT_X90),
      profiledVolume(tallCrystal, 3.5, 3.2, 7, -2, 14, 0, MAT.miteCrystal),
      profiledVolume(sideCrystal, 2.5, 2.3, 6, 5, 12, 3, MAT.miteCrystal),
      profiledVolume(sideCrystal, 2.5, 2.3, 6, 4, 12, -4, MAT.miteCrystal),
      profiledVolume(sideCrystal, 2.0, 1.9, 6, -7, 11, 3, MAT.goldTrim)
    ];
    return scaleUnitModel({
      body: body,
      glow: [
        sph(2.2, 7, 0, 8.5, 0, MAT.runeCyan),
        limb(0.26, 0.26, -7, 3.0, 7.5, 7, 3.0, 7.5, MAT.frostGlow),
        limb(0.26, 0.26, -7, 3.0, -7.5, 7, 3.0, -7.5, MAT.frostGlow),
        sph(1.2, 6, -2, 21, 0, MAT.runeCyan)
      ]
    }, 1.65, 1.25, 1.65);
  },

  hexling: function () {
    // 爆裂魔仆：脉冲不稳的符核魔球。悬浮晶核 + 细肢，不是晶螨也不是卡车。
    const body = [
      sph(3.6, 9, 0, 7.2, 0, MAT.crystal),
      sph(2.15, 8, 0, 7.2, 0, MAT.deepViolet),
      torus(4.2, 0.45, 6, 12, 0, 7.2, 0, 0.94, ROT_X90),     // 玩家色识别环
      pyr(0.7, 2.6, 4, 0, 11.6, 0, MAT.crystal),
      pyr(0.55, 2.2, 4, 2.4, 9.4, 1.6, MAT.crystal),
      pyr(0.55, 2.2, 4, -2.2, 9.2, -1.4, MAT.crystal),
      box(1.15, 3.4, 1.15, 1.6, 3.4, 1.8, MAT.deepViolet),
      box(1.15, 3.4, 1.15, -1.4, 3.4, -1.6, MAT.deepViolet),
      torus(3.4, 0.22, 6, 12, 0, 7.2, 0, MAT.goldTrim, ROT_X90)
    ];
    return scaleUnitModel({
      body: body,
      glow: [
        sph(2.35, 8, 0, 7.2, 0, MAT.fireGlow),
        sph(1.15, 6, 0, 7.2, 0, MAT.arcaneGlow),
        cyl(3.8, 3.8, 0.22, 12, 0, 6.4, 0, MAT.fireGlow),
        sph(0.55, 5, 0, 12.2, 0, MAT.fireGlow)
      ]
    }, 1.20, 1.20, 1.20);
  },

  mmcv: function () {
    // 迁徙法阵：暖金悬浮台 + 竖立金环，环心青符漩涡。经济载具，不是圣殿也非法阵平台。
    const migrateBaseProfile = [
      [0.0, -2.5], [0.72, -2.5], [0.96, -1.5], [1.0, 0.2],
      [0.82, 1.9], [0.42, 2.5], [0.0, 2.5]
    ];
    const body = [
      profiledVolume(migrateBaseProfile, 12.0, 9.0, 12, 0, 6, 0, MAT.goldStone),
      taperedBox(19, 13, 16, 10, 1.2, 0, 9.0, 0, 0.92),      // 玩家色平台上盖
      box(2.6, 7.4, 3.5, -8, 9.0, 0, 0.84),                 // 玩家色环架
      box(2.6, 7.4, 3.5, 8, 9.0, 0, 0.84),
      cyl(9, 9, 2, 12, 0, 16, 0, MAT.goldTrim, ROT_Z90),
      box(3, 8, 3, -8, 8, 0, MAT.goldStoneDark),
      box(3, 8, 3, 8, 8, 0, MAT.goldStoneDark)
    ];
    return scaleUnitModel({
      body: body,
      glow: [
        cyl(6.5, 6.5, 1.2, 12, 0, 16, 0, MAT.runeCyan, ROT_Z90),
        box(20, 0.6, 0.6, 0, 3.2, 8, MAT.frostGlow),
        box(20, 0.6, 0.6, 0, 3.2, -8, MAT.frostGlow)
      ]
    }, 1.65, 1.42, 1.65);
  },

  tank: function () {
    return {
      body: trackedHull(32, 20, 8, 0.85).concat([
        taperedBox(16, 14, 12, 10, 7.5, -0.5, 15.6, 0, 1.0),      // 炮塔
        taperedBox(5, 11, 3.4, 8, 4.6, 7.4, 15.2, 0, 0.75),       // 防盾
        cyl(1.5, 1.8, 21, 10, 14, 15.4, 0, MAT.gunmetal, ROT_Z90),   // 主炮
        cyl(2.3, 2.3, 3.2, 10, 25, 15.4, 0, MAT.darkSteel, ROT_Z90), // 炮口制退器
        box(4.4, 1.8, 1.8, 3.4, 20.2, 3.6, MAT.gunmetal),            // 并列机枪
        box(3.0, 2.6, 3.0, -5.4, 20.4, -3.2, MAT.steel),             // 指挥塔
        box(9, 0.9, 1.2, -1, 19.4, 6.6, MAT.warnYellow),             // 警示条
        box(5, 1.4, 5, 9, 12.0, 0, MAT.steel)                        // 前装甲附加块
      ]),
      glow: [
        box(14, 0.9, 0.6, -1, 11.2, 10.2, GLOW_SOFT),             // 车体侧灯带
        box(14, 0.9, 0.6, -1, 11.2, -10.2, GLOW_SOFT),
        box(1.4, 1.0, 1.0, 6.6, 20.4, -3.2, GLOW_HOT),            // 观瞄
        box(2.6, 0.7, 3.4, -7.4, 19.2, 0, GLOW_SOFT)              // 炮塔尾舱
      ]
    };
  },

  scout: function () {
    const body = [
      taperedBox(28, 15, 22, 12, 7.5, 0, 8.4, 0, 0.95),
      taperedBox(11, 11, 8.4, 8.4, 5.4, -1, 14.6, 0, 1.05),       // 小炮塔
      cyl(1.0, 1.2, 13, 8, 9, 15.0, 0, MAT.gunmetal, ROT_Z90),
      box(6, 3.2, 13, 11.0, 7.6, 0, MAT.steel),                   // 前装甲斜板
      box(3.0, 1.6, 2.4, -11, 10.4, 0, MAT.gunmetal),             // 尾部设备箱
      box(0.9, 1.0, 1.6, -12.6, 10.4, 0, MAT.exhaust)
    ];
    [1, -1].forEach(function (side) {
      [9.0, 0.0, -9.0].forEach(function (px) {
        body.push(cyl(3.4, 3.4, 3.0, 10, px, 3.6, side * 8.0, MAT.rubber, ROT_X90));
      });
    });
    return {
      body: body,
      glow: [
        box(18, 0.8, 0.5, 0, 11.4, 7.8, GLOW_SOFT),
        box(18, 0.8, 0.5, 0, 11.4, -7.8, GLOW_SOFT),
        cyl(3.0, 3.0, 0.5, 12, -6.5, 17.6, 0, GLOW_HOT),          // 雷达盘
        box(1.2, 0.9, 0.9, 4.4, 17.0, 0, GLOW_HOT)
      ]
    };
  },

  harvester: function () {
    return {
      body: trackedHull(35, 24, 9, 0.76).concat([
        // 后半部是巨大的锈色敞口矿斗，和基地车的封闭模块完全不同。
        taperedBox(20, 23, 16, 19, 15, -8, 19.5, 0, MAT.rust),
        box(18, 1.2, 21, -8, 27.4, 0, MAT.warnYellow),             // 矿斗黄边
        taperedBox(13, 17, 10, 13, 9, 10, 18, 0, 0.82),           // 低矮驾驶室
        box(7, 4, 17, 16, 12, 0, MAT.steel),                      // 采掘臂
        // 正前方横置的大型切削滚筒是采矿车的主剪影。
        cyl(6.5, 6.5, 25, 10, 21, 8.5, 0, MAT.rust, ROT_X90),
        cyl(2.0, 2.0, 27, 8, 21, 8.5, 0, MAT.warnYellow, ROT_X90),
        box(5, 2.2, 3.2, 25, 4.0, -8, MAT.warnYellow),
        box(5, 2.2, 3.2, 25, 4.0, 0, MAT.warnYellow),
        box(5, 2.2, 3.2, 25, 4.0, 8, MAT.warnYellow)
      ]),
      glow: [
        // 露天矿斗里直接堆出一簇金色矿石，从任何方向都能认出用途。
        sph(4.6, 7, -13, 29.5, -5.5, MAT.oreGlow),
        sph(5.4, 7, -7, 30.5, 1.0, MAT.oreGlow),
        sph(4.2, 7, -2, 29.3, -4.0, MAT.oreGlow),
        box(1.8, 1.3, 6, 15.5, 22, 0, GLOW_HOT),                  // 前照灯
        box(13, 0.8, 0.6, 2, 11.5, 12.2, GLOW_WARM),
        box(13, 0.8, 0.6, 2, 11.5, -12.2, GLOW_WARM)
      ]
    };
  },

  artillery: function () {
    return {
      body: trackedHull(34, 22, 9, 0.8).concat([
        taperedBox(15, 16, 12, 13, 7, -5, 16, 0, 0.95),           // 炮座
        cyl(2.2, 2.6, 32, 10, 13, 22, 0,
          MAT.gunmetal, new THREE.Matrix4().makeRotationZ(Math.PI / 2 - 0.34)),
        cyl(3.0, 3.0, 3.6, 10, 27.5, 27.0, 0,
          MAT.darkSteel, new THREE.Matrix4().makeRotationZ(Math.PI / 2 - 0.34)),
        box(7, 6, 18, -13, 14, 0, MAT.steel),                     // 驻锄
        box(4, 7, 3, -16, 8, 8, MAT.darkSteel),
        box(4, 7, 3, -16, 8, -8, MAT.darkSteel),
        box(11, 1.0, 1.4, -4, 20.6, 8.2, MAT.warnYellow)
      ]),
      glow: [
        box(2.2, 1.0, 12, -4, 20.4, 0, GLOW_SOFT),                // 炮闩指示
        box(10, 0.8, 0.5, -2, 12.4, 12.0, GLOW_SOFT),
        box(10, 0.8, 0.5, -2, 12.4, -12.0, GLOW_SOFT)
      ]
    };
  },

  v3: function () {
    return {
      body: trackedHull(36, 26, 9, 0.82).concat([
        taperedBox(20, 22, 20, 24, 4, 0, 11, 0, 0.9),             // 发射基座
        cyl(3.0, 3.5, 32, 10, 1, 30, 0, MAT.gunmetal),             // 竖直火箭弹体
        cyl(4.2, 4.2, 5, 10, 1, 14, 0, MAT.darkSteel),             // 底部加粗段
        cyl(3.2, 1.0, 7, 8, 1, 48, 0, MAT.warnYellow),             // 弹头锥
        // 发射架稳定臂
        box(1.5, 28, 2, 6, 16, 7, MAT.steel),
        box(1.5, 28, 2, 6, 16, -7, MAT.steel),
        box(26, 4, 1.5, -4, 11, 10.5, MAT.steel),                  // 侧装甲裙板
        box(26, 4, 1.5, -4, 11, -10.5, MAT.steel),
      ]),
      glow: [
        box(18, 0.6, 0.4, -2, 11, 11.5, GLOW_SOFT),
        box(18, 0.6, 0.4, -2, 11, -11.5, GLOW_SOFT),
        box(2.0, 1.0, 3.0, 1.5, 22, 0, GLOW_WARM)
      ]
    };
  },

  tank_destroyer: function () {
    return {
      body: trackedHull(33, 19, 7, 0.9).concat([
        // 低矮固定战斗室：前脸大倾角
        taperedBox(22, 15, 15, 11, 8, -2, 13.4, 0, 1.0),
        box(9, 5.5, 12, 9.5, 12.6, 0, 0.7),
        cyl(1.3, 1.6, 29, 10, 17, 14.2, 0, MAT.gunmetal, ROT_Z90),
        cyl(2.2, 2.2, 3.8, 10, 30, 14.2, 0, MAT.darkSteel, ROT_Z90),
        box(3.0, 2.2, 2.6, -8, 18.4, -3.0, MAT.steel),
        box(14, 0.9, 1.2, -2, 17.2, 7.4, MAT.warnYellow)
      ]),
      glow: [
        box(16, 0.8, 0.5, -2, 10.6, 9.8, GLOW_SOFT),
        box(16, 0.8, 0.5, -2, 10.6, -9.8, GLOW_SOFT),
        box(1.2, 1.0, 5.0, 6.6, 17.6, 0, GLOW_HOT)                // 观瞄条
      ]
    };
  },

  overlord: function () {
    return {
      body: trackedHull(40, 24, 10, 0.82).concat([
        // 宽扁炮塔比先锋坦克更矮更宽，压住整车重心
        taperedBox(22, 19, 18, 15, 8, 2, 16.5, 0, 1.0),
        taperedBox(7, 13, 5, 11, 4, 6, 21.0, 0, 0.8),           // 炮塔正面防盾
        // 招牌双联主炮：左右并排两根长管 + 各自制退器
        cyl(1.6, 1.9, 24, 10, 14, 16.4, 3.6, MAT.gunmetal, ROT_Z90),
        cyl(1.6, 1.9, 24, 10, 14, 16.4, -3.6, MAT.gunmetal, ROT_Z90),
        cyl(2.5, 2.5, 3.4, 10, 26, 16.4, 3.6, MAT.darkSteel, ROT_Z90),
        cyl(2.5, 2.5, 3.4, 10, 26, 16.4, -3.6, MAT.darkSteel, ROT_Z90),
        box(10, 1.0, 1.4, -4, 20.4, 8.0, MAT.warnYellow),       // 侧警示条
        box(10, 1.0, 1.4, -4, 20.4, -8.0, MAT.warnYellow),
        box(3.4, 3.0, 3.4, -6, 21.4, 0, MAT.steel),             // 指挥塔
        box(6, 2.0, 6, 12, 12.4, 0, MAT.steel)                  // 首上附加装甲
      ]),
      glow: [
        box(16, 1.0, 0.7, -2, 12.6, 11.4, GLOW_SOFT),
        box(16, 1.0, 0.7, -2, 12.6, -11.4, GLOW_SOFT),
        box(1.6, 1.2, 1.2, 8.5, 21.6, 0, GLOW_HOT),             // 车长观瞄
        box(2.8, 0.8, 3.8, -8.4, 20.0, 0, GLOW_SOFT)            // 炮塔尾舱
      ]
    };
  },

  tesla: function () { return infantryParts('tesla'); },

  bomb_truck: function () {
    // 自爆卡车：轮式药箱车。驾驶室在前、后斗码炸药桶，没有炮塔。
    const body = [
      taperedBox(30, 16, 24, 14, 7.2, -1, 8.2, 0, 0.92),
      taperedBox(12, 14, 10, 12, 8.0, 10, 13.0, 0, 0.78),       // 驾驶室
      box(6, 3.2, 14, 16.4, 8.0, 0, MAT.steel),                 // 前保险杠
      box(16, 2.4, 15, -6, 11.6, 0, MAT.warnYellow),            // 货斗底板
      cyl(3.6, 3.6, 7.2, 10, -4, 16.2, 3.2, MAT.rust),          // 炸药桶
      cyl(3.6, 3.6, 7.2, 10, -4, 16.2, -3.2, MAT.rust),
      cyl(3.2, 3.2, 6.4, 10, -11, 15.6, 0, MAT.rust),
      box(14, 1.2, 1.4, -6, 12.4, 7.8, MAT.warnYellow),
      box(14, 1.2, 1.4, -6, 12.4, -7.8, MAT.warnYellow),
      box(2.2, 1.6, 2.0, 14.6, 17.6, 0, MAT.gunmetal)           // 观瞄窗框
    ];
    [1, -1].forEach(function (side) {
      [10.0, 0.0, -10.0].forEach(function (px) {
        body.push(cyl(3.2, 3.2, 2.8, 10, px, 3.4, side * 8.4, MAT.rubber, ROT_X90));
      });
    });
    return {
      body: body,
      glow: [
        box(10, 0.7, 0.5, 8, 12.2, 7.4, GLOW_SOFT),
        box(10, 0.7, 0.5, 8, 12.2, -7.4, GLOW_SOFT),
        sph(1.15, 6, -4, 20.4, 3.2, GLOW_HOT),                  // 桶顶引信
        sph(1.15, 6, -4, 20.4, -3.2, GLOW_HOT),
        sph(1.05, 6, -11, 19.4, 0, GLOW_HOT),
        box(1.6, 1.0, 4.2, 15.8, 16.8, 0, GLOW_HOT)
      ]
    };
  },

  prism: function () {
    return {
      body: trackedHull(32, 18, 8, 0.9).concat([
        taperedBox(16, 14, 13, 11, 7, -1, 15, 0, 1.0),          // 车体上部
        // 竖起的棱镜支臂（略前倾）+ 基座
        box(3.0, 2.0, 3.0, 4, 15.5, 0, MAT.darkSteel),
        box(2.2, 14, 2.2, 4, 22, 0, MAT.gunmetal),
        // 聚焦棱镜：两段四棱锥扣出一枚菱形水晶
        cyl(0.6, 3.0, 3.4, 4, 4, 30.5, 0, MAT.glass),
        cyl(3.0, 0.6, 3.4, 4, 4, 33.9, 0, MAT.glass),
        box(1.0, 1.0, 5.0, -6, 16.5, 0, MAT.steel)              // 尾部散热排
      ]),
      glow: [
        box(15, 0.9, 0.6, -1, 11.8, 9.0, GLOW_SOFT),
        box(15, 0.9, 0.6, -1, 11.8, -9.0, GLOW_SOFT),
        // 棱镜核心是一团高亮青光，会被辉光单独提出来
        sph(2.0, 8, 4, 32.2, 0, MAT.prismGlow),
        box(1.2, 1.0, 1.2, 4, 22.5, 0, MAT.prismGlow)
      ]
    };
  },

  mcv: function () {
    return {
      body: trackedHull(48, 30, 14, 0.88).concat([
        // 基地车是一座封闭、竖高的移动建筑：中央指挥核心 + 两侧折叠平台。
        taperedBox(30, 27, 24, 22, 16, -5, 25, 0, 1.0),
        box(14, 13, 18, -7, 39, 0, MAT.steel),                    // 高耸指挥塔
        taperedBox(15, 20, 11, 16, 11, 16, 25, 0, 0.9),          // 独立前驾驶舱
        box(32, 11, 3.2, -4, 25, 17.5, 0.92),                    // 左折叠基地板
        box(32, 11, 3.2, -4, 25, -17.5, 0.92),                   // 右折叠基地板
        box(35, 2.5, 2.4, -4, 31, 19.2, MAT.warnYellow),
        box(35, 2.5, 2.4, -4, 31, -19.2, MAT.warnYellow),
        // 四个外伸液压支腿，展开前也清楚表明这是工程载具。
        box(6, 7, 6, -17, 8, 18, MAT.darkSteel),
        box(6, 7, 6, -17, 8, -18, MAT.darkSteel),
        box(6, 7, 6, 14, 8, 18, MAT.darkSteel),
        box(6, 7, 6, 14, 8, -18, MAT.darkSteel),
        cyl(1.4, 1.4, 16, 6, -14, 50, 0, MAT.darkSteel),          // 通信桅杆
        box(30, 3.2, 3.2, -1, 47, 0, MAT.steel)                  // 折叠吊臂
      ]),
      glow: [
        box(22, 1.0, 0.7, -6, 40.5, 9.5, GLOW_SOFT),
        box(22, 1.0, 0.7, -6, 40.5, -9.5, GLOW_SOFT),
        box(2.2, 1.5, 9, 22, 27, 0, GLOW_HOT),                   // 前灯组
        // 指挥塔顶的十字识别灯 + 高桅信标，拉远也和矿车金色矿斗区分。
        box(12, 0.8, 2.2, -7, 46, 0, GLOW_SOFT),
        box(2.2, 0.8, 12, -7, 46, 0, GLOW_SOFT),
        sph(2.2, 8, -14, 58, 0, GLOW_HOT)
      ]
    };
  }
};

/* ------------------------------------------------------------------ *
 * 建筑模型
 *
 * 零件按材质分三类，各自合并成一个几何体，于是一座建筑只有 3 次绘制调用：
 *   TEAM —— 玩家色装甲板（受光）
 *   HULL —— 中性混凝土/钢结构（受光）
 *   GLOW —— 自发光条与指示灯（不受光，系数 > 1，会被辉光提取）
 *
 * 另有两个可动子组：turretHead（跟随开火方向）与 spinner（持续旋转的雷达/
 * 转子），它们让基地在静止时也是「活」的。
 * ------------------------------------------------------------------ */

const TEAM = 'team';
const HULL = 'hull';
const GLOW = 'glow';

function partCollector() {
  const parts = [];
  // paint：数字 = 团队色明暗系数，数组 = 固有色。混凝土地基、钢梁、锈迹
  // 都该有自己的颜色，否则一整座基地只是团队色的深浅变化，非常单调。
  const add = function (material, geo, x, y, z, paint, rot) {
    // 建筑数量远少于单位，允许所有非发光 BoxGeometry 在首次缓存时换成
    // 八边倒角截面。几何仍会和其他零件合并为一张网格，运行时 draw call
    // 完全不变；灯条继续保留原始 12 三角面方盒。
    if (material !== GLOW && geo && geo.type === 'BoxGeometry' && geo.parameters) {
      const p = geo.parameters;
      geo = chamferedBoxGeometry(p.width, p.height, p.depth);
    }
    const m = new THREE.Matrix4();
    if (rot) m.multiply(rot);
    m.setPosition(x, y, z);
    parts.push(Object.assign({ material: material, geo: geo, matrix: m },
      tint(paint == null ? 1 : paint)));
  };
  // 棱台版本：斜面墙体比直墙更有工业感
  const taper = function (material, bw, bd, tw, td, h, x, y, z, paint) {
    const part = taperedBox(bw, bd, tw, td, h, x, y, z, paint == null ? 1 : paint);
    part.material = material;
    parts.push(part);
  };
  const profile = function (material, shape, radiusX, radiusZ, seg, x, y, z, paint, rotY) {
    const part = profiledVolume(shape, radiusX, radiusZ, seg, x, y, z,
      paint == null ? 1 : paint, rotY);
    part.material = material;
    parts.push(part);
  };
  return { parts: parts, add: add, taper: taper, profile: profile };
}

/**
 * 阵营地基：比旧版大方台小一圈，让 #7 的尘土垫露出来。
 * 钢铁军团是钢板甲板 + 黄黑警示角；秘法会是暖金石台 + 青符环，不再用四角青灯。
 */
function addStructureFoundation(c, kind, s) {
  const add = c.add;
  const taper = c.taper;
  if (MAGIC_STRUCTURE_KINDS[kind]) {
    // 奥术塔的高瘦轮廓需要更稳的视觉底座；只放大水平尺寸，零件数不变。
    const footprint = kind === 'mtower' ? s * 1.10 : s;
    // 暖金砂石台 + 金圈 + 青符环，和作战单位的冷紫青分开。
    taper(HULL, footprint * 1.18, footprint * 1.18,
      footprint * 1.06, footprint * 1.06, 3.2, 0, 1.6, 0, MAT.goldStoneDark);
    add(HULL, new THREE.TorusGeometry(footprint * 0.82, footprint * 0.08, 6, 16),
      0, 1.2, 0, MAT.goldTrim, ROT_X90);
    add(GLOW, new THREE.TorusGeometry(footprint * 0.70, footprint * 0.022, 6, 20),
      0, 1.55, 0, MAT.runeCyan, ROT_X90);
    [[1, 1], [-1, -1], [1, -1], [-1, 1]].forEach(function (q) {
      taper(HULL, footprint * 0.10, footprint * 0.10,
        footprint * 0.04, footprint * 0.04, s * 0.28,
        q[0] * footprint * 0.78, 1.7, q[1] * footprint * 0.78, MAT.goldTrim);
      add(GLOW, new THREE.SphereGeometry(footprint * 0.035, 6, 5),
        q[0] * footprint * 0.78, 1.7 + s * 0.16,
        q[1] * footprint * 0.78, MAT.runeCyan);
    });
    return;
  }
  // 钢铁军团：建筑正下方一块暗混凝土台，外围钢坎吃尘土，不再是整块浅灰大方板。
  taper(HULL, s * 1.18, s * 1.18, s * 1.06, s * 1.06, 3.2, 0, 1.6, 0, MAT.concreteDark);
  add(HULL, new THREE.BoxGeometry(s * 1.58, 0.85, s * 0.10), 0, 0.7, s * 0.80, MAT.plate);
  add(HULL, new THREE.BoxGeometry(s * 1.58, 0.85, s * 0.10), 0, 0.7, -s * 0.80, MAT.plate);
  add(HULL, new THREE.BoxGeometry(s * 0.10, 0.85, s * 1.58), s * 0.80, 0.7, 0, MAT.plate);
  add(HULL, new THREE.BoxGeometry(s * 0.10, 0.85, s * 1.58), -s * 0.80, 0.7, 0, MAT.plate);
  [[1, 1], [-1, -1], [1, -1], [-1, 1]].forEach(function (q) {
    add(HULL, new THREE.BoxGeometry(s * 0.16, 0.36, s * 0.05),
      q[0] * s * 0.80, 1.05, q[1] * s * 0.80, MAT.warnYellow);
    add(HULL, new THREE.BoxGeometry(s * 0.05, 0.36, s * 0.16),
      q[0] * s * 0.80, 1.05, q[1] * s * 0.80, MAT.warnYellow);
  });
}

function structureParts(kind, size) {
  const c = partCollector();
  const add = c.add;
  const taper = c.taper;
  const profile = c.profile;
  const s = size;
  addStructureFoundation(c, kind, s);

  if (kind === 'hq') {
    // 指挥中心：矮宽地堡 + 两侧翼楼 + 收束主塔，不再是三层灰方块。
    // 正面闸门朝 +Z（默认相机从南往北看），主塔加四棱斜顶，翼楼是独立碉堡。
    taper(HULL, s * 1.46, s * 1.22, s * 1.28, s * 1.04, s * 0.38, 0, s * 0.19 + 3.4, 0, MAT.concrete);
    taper(HULL, s * 0.44, s * 0.38, s * 0.34, s * 0.12, s * 0.22, 0, s * 0.11 + 3.4, s * 0.70, MAT.darkSteel);
    add(HULL, new THREE.BoxGeometry(s * 0.26, s * 0.28, s * 0.06), 0, s * 0.22 + 3.4, s * 0.64, MAT.gunmetal);
    add(GLOW, new THREE.BoxGeometry(s * 0.04, s * 0.20, s * 0.04), s * 0.09, s * 0.22 + 3.4, s * 0.68, GLOW_HOT);
    add(GLOW, new THREE.BoxGeometry(s * 0.04, s * 0.20, s * 0.04), -s * 0.09, s * 0.22 + 3.4, s * 0.68, GLOW_HOT);
    taper(HULL, s * 0.38, s * 0.78, s * 0.26, s * 0.58, s * 0.42,
      s * 0.78, s * 0.21 + 3.4, 0, MAT.darkSteel);
    taper(HULL, s * 0.38, s * 0.78, s * 0.26, s * 0.58, s * 0.42,
      -s * 0.78, s * 0.21 + 3.4, 0, MAT.darkSteel);
    add(HULL, new THREE.BoxGeometry(s * 0.06, s * 0.10, s * 0.36), s * 0.94, s * 0.28 + 3.4, 0, MAT.glass);
    add(HULL, new THREE.BoxGeometry(s * 0.06, s * 0.10, s * 0.36), -s * 0.94, s * 0.28 + 3.4, 0, MAT.glass);
    add(HULL, new THREE.BoxGeometry(s * 0.16, s * 0.10, s * 0.20), s * 0.28, s * 0.42 + 3.4, -s * 0.40, MAT.rivet);
    add(HULL, new THREE.BoxGeometry(s * 0.16, s * 0.10, s * 0.20), -s * 0.28, s * 0.42 + 3.4, -s * 0.40, MAT.rivet);
    add(HULL, new THREE.BoxGeometry(s * 0.22, s * 0.12, s * 0.36), 0, s * 0.08 + 3.4, s * 0.86, MAT.sandbag);
    // 主塔改为收束的十边观察塔：同样是低面数，远看却不再是层层方盒。
    add(HULL, new THREE.CylinderGeometry(s * 0.36, s * 0.54, s * 1.04, 10),
      0, s * 0.94 + 3.4, 0, MAT.steel);
    add(HULL, new THREE.ConeGeometry(s * 0.40, s * 0.30, 10),
      0, s * 1.60 + 3.4, 0, MAT.darkSteel);
    add(TEAM, new THREE.TorusGeometry(s * 0.43, s * 0.045, 5, 12),
      0, s * 1.02, 0, 0.86, ROT_X90);
    add(HULL, new THREE.CylinderGeometry(s * 0.20, s * 0.24, s * 0.22, 10),
      0, s * 1.64, 0, MAT.gunmetal);
    [0.78, 1.18].forEach(function (h) {
      add(HULL, new THREE.CylinderGeometry(s * 0.42, s * 0.42, s * 0.055, 10),
        0, s * h, 0, MAT.glass);
    });
    add(GLOW, new THREE.BoxGeometry(s * 0.12, s * 0.04, s * 0.12), 0, s * 1.72, 0, GLOW_HOT);
    [[1, 1], [-1, -1], [1, -1], [-1, 1]].forEach(function (q) {
      taper(HULL, s * 0.26, s * 0.26, s * 0.16, s * 0.16, s * 0.44,
        q[0] * s * 0.58, s * 0.22 + 3.4, q[1] * s * 0.58, MAT.concreteDark);
      add(HULL, new THREE.CylinderGeometry(s * 0.04, s * 0.05, s * 0.28, 6),
        q[0] * s * 0.58, s * 0.52, q[1] * s * 0.58, MAT.gunmetal);
    });
    add(HULL, new THREE.CylinderGeometry(s * 0.045, s * 0.07, s * 0.62, 8), 0, s * 1.92, 0, MAT.steel);
    add(HULL, new THREE.BoxGeometry(s * 0.28, s * 0.04, s * 0.04), s * 0.16, s * 2.16, 0, MAT.darkSteel);
  } else if (kind === 'power') {
    taper(HULL, s * 1.46, s * 1.16, s * 1.30, s * 1.02, s * 0.38, 0, s * 0.19 + 3.4, 0, MAT.concrete);
    add(HULL, new THREE.BoxGeometry(s * 0.72, s * 0.28, s * 0.70), 0, s * 0.38 + 3.4, s * 0.42, MAT.darkSteel);
    [-1, 1].forEach(function (side) {
      // 磁能塔：绝缘柱 + 多层铜线圈，剪影是双塔不是方盒。
      taper(HULL, s * 0.36, s * 0.36, s * 0.22, s * 0.22, s * 0.72,
        side * s * 0.42, s * 0.36 + 3.4, 0, MAT.concreteDark);
      taper(TEAM, s * 0.22, s * 0.22, s * 0.14, s * 0.14, s * 0.55,
        side * s * 0.42, s * 0.98 + 3.4, 0, 1.0);
      add(HULL, new THREE.TorusGeometry(s * 0.28, s * 0.048, 6, 12),
        side * s * 0.42, s * 1.08, 0, MAT.copper, ROT_X90);
      add(HULL, new THREE.TorusGeometry(s * 0.24, s * 0.042, 6, 12),
        side * s * 0.42, s * 1.26, 0, MAT.copper, ROT_X90);
      add(HULL, new THREE.TorusGeometry(s * 0.20, s * 0.036, 6, 12),
        side * s * 0.42, s * 1.42, 0, MAT.copper, ROT_X90);
      add(GLOW, new THREE.SphereGeometry(s * 0.14, 10, 6),
        side * s * 0.42, s * 1.62, 0, MAT.teslaArc);
      add(GLOW, new THREE.CylinderGeometry(s * 0.04, s * 0.04, s * 0.55, 6),
        side * s * 0.42, s * 1.32, 0, GLOW_SOFT);
    });
    add(GLOW, new THREE.BoxGeometry(s * 0.86, s * 0.05, s * 0.08), 0, s * 1.48, 0, MAT.teslaArc);
    add(HULL, new THREE.BoxGeometry(s * 0.22, s * 0.32, s * 0.22), 0, s * 0.42, -s * 0.48, MAT.steel);
    add(HULL, new THREE.BoxGeometry(s * 0.36, s * 0.22, s * 0.28), 0, s * 0.36 + 3.4, s * 0.58, MAT.rivet);
    add(HULL, new THREE.CylinderGeometry(s * 0.04, s * 0.04, s * 0.40, 6),
      0, s * 0.48 + 3.4, s * 0.38, MAT.copper, ROT_Z90);
  } else if (kind === 'refinery') {
    taper(HULL, s * 1.48, s * 1.18, s * 1.34, s * 1.06, s * 0.42, 0, s * 0.21 + 3.4, 0, MAT.concrete);
    add(TEAM, new THREE.CylinderGeometry(s * 0.40, s * 0.48, s * 1.05, 12), s * 0.40, s * 0.88, 0);
    add(HULL, new THREE.ConeGeometry(s * 0.44, s * 0.48, 12), s * 0.40, s * 1.64, 0, MAT.rust);
    add(HULL, new THREE.CylinderGeometry(s * 0.055, s * 0.055, s * 0.28, 6), s * 0.40, s * 1.98, 0, MAT.steel);
    add(GLOW, new THREE.SphereGeometry(s * 0.05, 8, 6), s * 0.40, s * 2.14, 0, GLOW_HOT);
    add(GLOW, new THREE.TorusGeometry(s * 0.46, s * 0.032, 6, 14), s * 0.40, s * 1.12, 0, GLOW_SOFT, ROT_X90);
    taper(HULL, s * 0.58, s * 0.62, s * 0.46, s * 0.50, s * 0.82, -s * 0.46, s * 0.41 + 3.4, 0, MAT.steel);
    add(GLOW, new THREE.BoxGeometry(s * 0.52, s * 0.055, s * 0.58), -s * 0.46, s * 0.70, 0, GLOW_SOFT);
    add(HULL, new THREE.BoxGeometry(s * 1.28, s * 0.09, s * 0.30), 0, s * 0.98, s * 0.42, MAT.rust);
    add(GLOW, new THREE.BoxGeometry(s * 1.10, s * 0.08, s * 0.18), 0, s * 1.05, s * 0.42, MAT.oreGlow);
    add(HULL, new THREE.CylinderGeometry(s * 0.07, s * 0.07, s * 0.64, 6), s * 0.86, s * 0.72, -s * 0.38, MAT.steel);
    add(HULL, new THREE.CylinderGeometry(s * 0.05, s * 0.05, s * 0.50, 6),
      s * 0.18, s * 0.70, -s * 0.36, MAT.darkSteel, ROT_Z90);
  } else if (kind === 'barracks') {
    taper(HULL, s * 1.42, s * 1.12, s * 1.28, s * 1.00, s * 0.40, 0, s * 0.20 + 3.4, 0, MAT.concrete);
    add(TEAM, new THREE.BoxGeometry(s * 1.22, s * 0.36, s * 0.92), 0, s * 0.42 + 3.4, 0, 1.0);
    add(HULL, new THREE.CylinderGeometry(s * 0.62, s * 0.62, s * 1.36, 3), 0, s * 0.72, 0, MAT.olive,
      new THREE.Matrix4().makeRotationZ(Math.PI / 2));
    add(HULL, new THREE.BoxGeometry(s * 0.12, s * 0.40, s * 0.50), s * 0.70, s * 0.24 + 3.4, 0, MAT.gunmetal);
    add(HULL, new THREE.BoxGeometry(s * 0.28, s * 0.32, s * 0.08), 0, s * 0.22 + 3.4, s * 0.54, MAT.darkSteel);
    add(GLOW, new THREE.BoxGeometry(s * 0.05, s * 0.40, s * 0.05), s * 0.74, s * 0.24 + 3.4, s * 0.26, GLOW_HOT);
    add(GLOW, new THREE.BoxGeometry(s * 0.05, s * 0.40, s * 0.05), s * 0.74, s * 0.24 + 3.4, -s * 0.26, GLOW_HOT);
    add(GLOW, new THREE.BoxGeometry(s * 1.10, s * 0.05, s * 0.96), 0, s * 0.50, 0, GLOW_SOFT);
    add(HULL, new THREE.CylinderGeometry(s * 0.025, s * 0.03, s * 0.72, 6), -s * 0.58, s * 1.18, 0, MAT.steel);
    add(HULL, new THREE.BoxGeometry(s * 0.22, s * 0.12, s * 0.02), -s * 0.46, s * 1.42, 0, MAT.hazard);
  } else if (kind === 'factory') {
    taper(HULL, s * 1.52, s * 1.32, s * 1.38, s * 1.18, s * 0.52, 0, s * 0.26 + 3.4, 0, MAT.concrete);
    add(TEAM, new THREE.BoxGeometry(s * 1.28, s * 0.12, s * 1.10), 0, s * 0.78, 0, 1.0);
    add(HULL, new THREE.CylinderGeometry(s * 0.58, s * 0.58, s * 1.28, 8, 1, false, 0, Math.PI),
      0, s * 0.82, 0, MAT.steel, new THREE.Matrix4().makeRotationZ(Math.PI / 2));
    add(HULL, new THREE.BoxGeometry(s * 0.14, s * 0.52, s * 0.96), s * 0.78, s * 0.28 + 3.4, 0, MAT.gunmetal);
    add(GLOW, new THREE.BoxGeometry(s * 0.05, s * 0.46, s * 0.80), s * 0.84, s * 0.28 + 3.4, 0, MAT.furnace);
    add(HULL, new THREE.BoxGeometry(s * 0.92, s * 0.06, s * 0.50), s * 1.18, 3.55, 0, MAT.warnYellow);
    for (let i = -1; i <= 1; i++) {
      add(HULL, new THREE.CylinderGeometry(s * 0.09, s * 0.12, s * 0.70, 6),
        i * s * 0.34, s * 1.16, -s * 0.40, MAT.rust);
      add(GLOW, new THREE.CylinderGeometry(s * 0.07, s * 0.07, s * 0.055, 6),
        i * s * 0.34, s * 1.52, -s * 0.40, MAT.furnace);
    }
    add(GLOW, new THREE.BoxGeometry(s * 1.22, s * 0.05, s * 0.07), 0, s * 0.58, s * 0.58, GLOW_SOFT);
    add(GLOW, new THREE.BoxGeometry(s * 1.22, s * 0.05, s * 0.07), 0, s * 0.58, -s * 0.58, GLOW_SOFT);
  } else if (kind === 'repair') {
    taper(HULL, s * 1.42, s * 1.24, s * 1.32, s * 1.14, s * 0.28, 0, s * 0.14 + 3.4, 0, MAT.concrete);
    [[-1, -1], [1, -1], [-1, 1], [1, 1]].forEach(function (q) {
      add(HULL, new THREE.BoxGeometry(s * 0.13, s * 0.98, s * 0.13),
        q[0] * s * 0.58, s * 0.52, q[1] * s * 0.52, MAT.warnYellow);
    });
    [-1, 1].forEach(function (side) {
      add(TEAM, new THREE.BoxGeometry(s * 1.32, s * 0.12, s * 0.16), 0, s * 1.02, side * s * 0.52);
      add(GLOW, new THREE.BoxGeometry(s * 1.18, s * 0.045, s * 0.06), 0, s * 0.95, side * s * 0.52, GLOW_SOFT);
    });
    add(TEAM, new THREE.BoxGeometry(s * 0.30, s * 0.26, s * 1.12), 0, s * 1.04, 0, 0.9);
    add(HULL, new THREE.BoxGeometry(s * 0.22, s * 0.10, s * 1.12), 0, s * 1.18, 0, MAT.steel);
    add(GLOW, new THREE.BoxGeometry(s * 0.68, s * 0.035, s * 0.14), 0, s * 0.34, 0, GLOW_HOT);
    add(GLOW, new THREE.BoxGeometry(s * 0.14, s * 0.035, s * 0.68), 0, s * 0.34, 0, GLOW_HOT);
    add(HULL, new THREE.BoxGeometry(s * 0.32, s * 0.46, s * 0.32), -s * 0.60, s * 0.40, 0, MAT.darkSteel);
  } else if (kind === 'turret') {
    taper(HULL, s * 1.28, s * 1.28, s * 0.92, s * 0.92, s * 0.36, 0, s * 0.18 + 3.4, 0, MAT.concrete);
    add(TEAM, new THREE.CylinderGeometry(s * 0.46, s * 0.52, s * 0.18, 10), 0, s * 0.58, 0);
    add(GLOW, new THREE.TorusGeometry(s * 0.46, s * 0.03, 6, 14), 0, s * 0.54, 0, GLOW_SOFT, ROT_X90);
  } else if (kind === 'missile') {
    taper(HULL, s * 1.34, s * 1.34, s * 0.98, s * 0.98, s * 0.38, 0, s * 0.19 + 3.4, 0, MAT.concrete);
    add(TEAM, new THREE.CylinderGeometry(s * 0.50, s * 0.55, s * 0.20, 10), 0, s * 0.62, 0);
    add(GLOW, new THREE.TorusGeometry(s * 0.50, s * 0.03, 6, 14), 0, s * 0.58, 0, GLOW_SOFT, ROT_X90);
    [[1, 1], [-1, -1], [1, -1], [-1, 1]].forEach(function (q) {
      add(HULL, new THREE.BoxGeometry(s * 0.08, s * 0.04, s * 0.08),
        q[0] * s * 0.52, s * 0.70, q[1] * s * 0.52, MAT.warnYellow);
    });
    /* ---------------- 秘法会（魔法阵营）建筑 ----------------
     * 暖金砂石 + 奥术金饰 + 青蓝符光，和钢铁的钢板盒子、作战单位的冷紫青分开。
     * 每种建筑必须有 50m 相机下认得出的独立剪影，不能再是同一套紫晶方块换缩放。
     */
  } else if (kind === 'mhq') {
    // 魔法主堡：双尖塔托浮空金冠，不是矮方堡。正面奥术门朝 +Z。
    // 主台和双塔使用连续收分剖面；门、旗与塔桥改成拱形/垂幔，不再叠矩形块。
    const keepProfile = [
      [0.0, -s * 0.21], [0.86, -s * 0.21], [1.0, -s * 0.10],
      [0.94, s * 0.08], [0.78, s * 0.21], [0.0, s * 0.21]
    ];
    const spireProfile = [
      [0.0, -s * 0.73], [0.82, -s * 0.73], [1.0, -s * 0.57],
      [0.83, -s * 0.08], [0.58, s * 0.46], [0.22, s * 0.68], [0.0, s * 0.73]
    ];
    profile(HULL, keepProfile, s * 0.74, s * 0.66, 14, 0, s * 0.21 + 3.4, 0, MAT.goldStone);
    const doorGeo = new THREE.SphereGeometry(1, 10, 7);
    doorGeo.scale(s * 0.16, s * 0.22, s * 0.035);
    add(HULL, doorGeo, 0, s * 0.24 + 3.4, s * 0.64, MAT.goldStoneDark);
    add(GLOW, new THREE.TorusGeometry(s * 0.145, s * 0.025, 5, 14, Math.PI),
      0, s * 0.24 + 3.4, s * 0.67, MAT.runeCyan);
    [-1, 1].forEach(function (side) {
      profile(HULL, spireProfile, s * 0.18, s * 0.16, 12,
        side * s * 0.34, s * 0.96 + 3.4, 0, MAT.goldStone);
      add(HULL, new THREE.TorusGeometry(s * 0.125, s * 0.022, 5, 12),
        side * s * 0.34, s * 1.55, 0, MAT.goldTrim, ROT_X90);
      add(HULL, new THREE.TorusGeometry(s * 0.135, s * 0.020, 5, 12),
        side * s * 0.34, s * 1.18, 0, MAT.goldTrim, ROT_X90);
      add(TEAM, new THREE.ConeGeometry(s * 0.13, s * 0.38, 5),
        side * s * 0.49, s * 0.76, s * 0.18, 1.0);
    });
    add(HULL, new THREE.TorusGeometry(s * 0.42, s * 0.045, 6, 18), 0, s * 2.00, 0, MAT.goldTrim, ROT_X90);
    add(HULL, new THREE.SphereGeometry(s * 0.16, 10, 7), 0, s * 2.00, 0, MAT.marble);
    add(GLOW, new THREE.TorusGeometry(s * 0.38, s * 0.022, 6, 18), 0, s * 2.00, 0, MAT.runeCyan, ROT_X90);
    add(GLOW, new THREE.SphereGeometry(s * 0.12, 8, 6), 0, s * 2.00, 0, MAT.runeCyan);
    add(TEAM, new THREE.TorusGeometry(s * 0.34, s * 0.045, 6, 18, Math.PI),
      0, s * 0.78, s * 0.52, 1.0);
  } else if (kind === 'mpower') {
    // 法力塔：细针晶柱 + 绕轨碎晶。单针剪影，不是主堡双塔，也不是钢铁双线圈。
    taper(HULL, s * 1.12, s * 0.92, s * 0.86, s * 0.70, s * 0.28, 0, s * 0.14 + 3.4, 0, MAT.goldStone);
    taper(TEAM, s * 1.02, s * 0.82, s * 0.82, s * 0.64, s * 0.10, 0, s * 0.36 + 3.4, 0, 0.92);
    add(HULL, new THREE.CylinderGeometry(s * 0.16, s * 0.20, s * 0.18, 8), 0, s * 0.32 + 3.4, 0, MAT.goldTrim);
    add(TEAM, new THREE.TorusGeometry(s * 0.20, s * 0.035, 6, 12), 0, s * 0.56 + 3.4, 0, 0.96, ROT_X90);
    taper(HULL, s * 0.16, s * 0.16, s * 0.035, s * 0.035, s * 1.92, 0, s * 1.12 + 3.4, 0, MAT.goldStone);
    [0.72, 1.12, 1.48].forEach(function (h) {
      add(HULL, new THREE.TorusGeometry(s * 0.12, s * 0.018, 6, 12), 0, s * h, 0, MAT.goldTrim, ROT_X90);
    });
    add(GLOW, new THREE.CylinderGeometry(s * 0.03, s * 0.03, s * 1.55, 6), 0, s * 1.18, 0, MAT.runeCyan);
    add(GLOW, new THREE.SphereGeometry(s * 0.08, 8, 6), 0, s * 2.12, 0, MAT.runeCyan);
  } else if (kind === 'mrefinery') {
    // 水晶精炼所：横置晶液大釜。宽扁水平剪影，不是竖塔。
    taper(HULL, s * 1.48, s * 1.18, s * 1.34, s * 1.04, s * 0.28, 0, s * 0.14 + 3.4, 0, MAT.goldStone);
    taper(TEAM, s * 1.34, s * 1.04, s * 1.22, s * 0.92, s * 0.10, 0, s * 0.34 + 3.4, 0, 0.90);
    add(HULL, new THREE.CylinderGeometry(s * 0.48, s * 0.48, s * 1.22, 14),
      0, s * 0.58 + 3.4, 0, MAT.goldStone, ROT_Z90);
    add(HULL, new THREE.TorusGeometry(s * 0.50, s * 0.05, 6, 16),
      s * 0.58, s * 0.58 + 3.4, 0, MAT.goldTrim, ROT_Z90);
    add(HULL, new THREE.TorusGeometry(s * 0.50, s * 0.05, 6, 16),
      -s * 0.58, s * 0.58 + 3.4, 0, MAT.goldTrim, ROT_Z90);
    add(TEAM, new THREE.BoxGeometry(s * 1.08, s * 0.10, s * 0.66), 0, s * 0.54 + 3.4, -s * 0.18, 0.94);
    add(GLOW, new THREE.BoxGeometry(s * 1.08, s * 0.10, s * 0.58), 0, s * 0.66 + 3.4, 0, MAT.runeCyan);
    add(GLOW, new THREE.SphereGeometry(s * 0.18, 10, 6), 0, s * 0.76 + 3.4, 0, MAT.frostGlow);
    taper(HULL, s * 0.42, s * 0.48, s * 0.32, s * 0.36, s * 0.52, -s * 0.62, s * 0.26 + 3.4, 0, MAT.goldStoneDark);
    add(HULL, new THREE.BoxGeometry(s * 1.18, s * 0.07, s * 0.24), 0, s * 0.86, s * 0.42, MAT.goldTrim);
  } else if (kind === 'mtemple') {
    // 奥术圣殿：露天新月门。竖立圆环门洞，训练出口朝 +Z，不是四柱石亭也不是平面法阵。
    taper(HULL, s * 1.28, s * 1.02, s * 1.12, s * 0.88, s * 0.22, 0, s * 0.11 + 3.4, 0, MAT.goldStone);
    add(HULL, new THREE.TorusGeometry(s * 0.50, s * 0.10, 8, 22), 0, s * 0.66 + 3.4, 0, MAT.goldStone);
    add(HULL, new THREE.TorusGeometry(s * 0.50, s * 0.035, 6, 20), 0, s * 0.66 + 3.4, 0, MAT.goldTrim);
    add(GLOW, new THREE.TorusGeometry(s * 0.42, s * 0.022, 6, 20), 0, s * 0.66 + 3.4, 0, MAT.runeCyan);
    add(HULL, new THREE.ConeGeometry(s * 0.10, s * 0.28, 6), s * 0.18, s * 1.22 + 3.4, 0, MAT.goldTrim);
    add(HULL, new THREE.ConeGeometry(s * 0.10, s * 0.28, 6), -s * 0.18, s * 1.22 + 3.4, 0, MAT.goldTrim);
    add(TEAM, new THREE.BoxGeometry(s * 0.18, s * 0.32, s * 0.03), s * 0.58, s * 0.70, 0, 1.0);
    add(TEAM, new THREE.BoxGeometry(s * 0.18, s * 0.32, s * 0.03), -s * 0.58, s * 0.70, 0, 1.0);
    add(HULL, new THREE.BoxGeometry(s * 0.20, s * 0.26, s * 0.06), 0, s * 0.18 + 3.4, s * 0.18, MAT.goldStoneDark);
    add(GLOW, new THREE.BoxGeometry(s * 0.10, s * 0.18, s * 0.03), 0, s * 0.18 + 3.4, s * 0.22, MAT.runeCyan);
  } else if (kind === 'mcircle') {
    // 召唤法阵：多层平面符环 + 悬浮核。极矮平台，竖向几乎没有体量，和圣殿月门对撞。
    taper(HULL, s * 1.82, s * 1.58, s * 1.62, s * 1.42, s * 0.18, 0, s * 0.09 + 3.4, 0, MAT.goldStone);
    add(HULL, new THREE.CylinderGeometry(s * 0.86, s * 0.92, s * 0.10, 20), 0, s * 0.22 + 3.4, 0, MAT.goldStoneDark);
    add(TEAM, new THREE.TorusGeometry(s * 0.94, s * 0.09, 6, 22), 0, s * 0.31 + 3.4, 0, 0.96, ROT_X90);
    add(HULL, new THREE.TorusGeometry(s * 0.98, s * 0.055, 6, 22), 0, s * 0.28 + 3.4, 0, MAT.goldTrim, ROT_X90);
    add(GLOW, new THREE.TorusGeometry(s * 0.82, s * 0.032, 6, 20), 0, s * 0.30 + 3.4, 0, MAT.runeCyan, ROT_X90);
    add(GLOW, new THREE.TorusGeometry(s * 0.50, s * 0.026, 6, 16), 0, s * 0.30 + 3.4, 0, MAT.frostGlow, ROT_X90);
    add(GLOW, new THREE.BoxGeometry(s * 1.78, s * 0.03, s * 0.05), 0, s * 0.30 + 3.4, 0, MAT.runeCyan);
    add(GLOW, new THREE.BoxGeometry(s * 0.05, s * 0.03, s * 1.78), 0, s * 0.30 + 3.4, 0, MAT.runeCyan);
    [[1, 0], [-1, 0], [0, 1], [0, -1]].forEach(function (q) {
      taper(HULL, s * 0.12, s * 0.12, s * 0.05, s * 0.05, s * 0.32,
        q[0] * s * 0.92, s * 0.22 + 3.4, q[1] * s * 0.82, MAT.goldTrim);
    });
  } else if (kind === 'mspring') {
    // 圣泉：石碗泉盆 + 上升泉光。碗形开口朝天，不是龙门也不是竖塔。
    taper(HULL, s * 1.32, s * 1.16, s * 1.18, s * 1.04, s * 0.20, 0, s * 0.10 + 3.4, 0, MAT.goldStone);
    add(HULL, new THREE.CylinderGeometry(s * 0.58, s * 0.42, s * 0.36, 16), 0, s * 0.34 + 3.4, 0, MAT.goldStone);
    add(TEAM, new THREE.TorusGeometry(s * 0.64, s * 0.095, 6, 18), 0, s * 0.51 + 3.4, 0, 0.96, ROT_X90);
    add(HULL, new THREE.TorusGeometry(s * 0.58, s * 0.07, 6, 18), 0, s * 0.50 + 3.4, 0, MAT.goldTrim, ROT_X90);
    add(GLOW, new THREE.CylinderGeometry(s * 0.48, s * 0.54, s * 0.08, 16), 0, s * 0.44 + 3.4, 0, MAT.frostGlow);
    add(GLOW, new THREE.CylinderGeometry(s * 0.10, s * 0.18, s * 0.72, 10), 0, s * 0.92, 0, MAT.runeCyan);
    add(GLOW, new THREE.SphereGeometry(s * 0.11, 10, 6), 0, s * 1.32, 0, MAT.frostGlow);
    [[1, 1], [-1, -1], [1, -1], [-1, 1]].forEach(function (q) {
      taper(HULL, s * 0.12, s * 0.12, s * 0.05, s * 0.05, s * 0.36,
        q[0] * s * 0.54, s * 0.22 + 3.4, q[1] * s * 0.48, MAT.goldTrim);
    });
  } else if (kind === 'mtower') {
    // 奥术塔：扭转尖塔 + 武器晶碟。旋转头是碟而不是一簇碎晶。
    taper(HULL, s * 1.18, s * 1.18, s * 0.82, s * 0.82, s * 0.28, 0, s * 0.14 + 3.4, 0, MAT.goldStone);
    taper(TEAM, s * 1.08, s * 1.08, s * 0.78, s * 0.78, s * 0.11, 0, s * 0.34 + 3.4, 0, 0.94);
    for (let i = 0; i < 5; i++) {
      const a = i * 0.55;
      add(HULL, new THREE.CylinderGeometry(s * (0.16 - i * 0.02), s * (0.18 - i * 0.02), s * 0.30, 8),
        Math.cos(a) * s * 0.055, s * (0.34 + i * 0.28) + 3.4, Math.sin(a) * s * 0.055, MAT.goldStone);
    }
    add(HULL, new THREE.TorusGeometry(s * 0.28, s * 0.03, 6, 12), 0, s * 0.72, 0, MAT.goldTrim, ROT_X90);
    add(GLOW, new THREE.CylinderGeometry(s * 0.035, s * 0.035, s * 1.15, 6), 0, s * 0.95, 0, MAT.runeCyan);
  }
  return c.parts;
}

/** 炮塔的可旋转头部：跟随开火方向。 */
function turretHeadParts(size) {
  const c = partCollector();
  const s = size;
  c.taper(TEAM, s * 0.92, s * 0.86, s * 0.72, s * 0.66, s * 0.5, 0, 0, 0, 1.0);
  c.add(HULL, new THREE.CylinderGeometry(s * 0.09, s * 0.1, s * 1.5, 8),
    s * 0.85, s * 0.08, s * 0.14, MAT.gunmetal, ROT_Z90);
  c.add(HULL, new THREE.CylinderGeometry(s * 0.09, s * 0.1, s * 1.5, 8),
    s * 0.85, s * 0.08, -s * 0.14, MAT.gunmetal, ROT_Z90);
  c.add(GLOW, new THREE.BoxGeometry(s * 0.12, s * 0.1, s * 0.5), s * 0.3, s * 0.3, 0, GLOW_HOT);
  return c.parts;
}

/** 导弹炮塔的可旋转头部：四联装发射箱。 */
function missileHeadParts(size) {
  const c = partCollector();
  const s = size;
  c.taper(TEAM, s * 0.85, s * 0.7, s * 0.7, s * 0.55, s * 0.6, 0, 0, 0, 1.0);
  c.add(HULL, new THREE.BoxGeometry(s * 0.82, s * 0.25, s * 0.68), 0, s * 0.35, 0, MAT.gunmetal);
  [-0.22, -0.07, 0.07, 0.22].forEach(function (x) {
    c.add(HULL, new THREE.CylinderGeometry(s * 0.055, s * 0.055, s * 0.66, 8),
      x * s * 0.9, s * 0.05, 0, MAT.darkSteel, ROT_Z90);
    c.add(GLOW, new THREE.CylinderGeometry(s * 0.04, s * 0.04, s * 0.04, 6),
      x * s * 0.9 + s * 0.36, s * 0.05, 0, GLOW_HOT, ROT_Z90);
  });
  c.add(HULL, new THREE.BoxGeometry(s * 0.08, s * 0.14, s * 0.58),
    s * 0.48, s * 0.08, 0, MAT.warnYellow);
  c.add(HULL, new THREE.BoxGeometry(s * 0.5, s * 0.04, s * 0.46), 0, s * 0.48, 0, MAT.steel);
  c.add(GLOW, new THREE.BoxGeometry(s * 0.4, s * 0.03, s * 0.04), 0, s * 0.48, s * 0.24, GLOW_SOFT);
  return c.parts;
}

/** 奥术塔的可旋转头部：武器晶碟指向开火方向（+X）。 */
function arcaneHeadParts(size) {
  const c = partCollector();
  const s = size;
  const dish = new THREE.Matrix4().makeRotationY(Math.PI / 2);
  c.add(HULL, new THREE.TorusGeometry(s * 0.32, s * 0.05, 6, 16),
    -s * 0.04, 0, 0, MAT.goldTrim, dish);
  c.add(TEAM, new THREE.TorusGeometry(s * 0.40, s * 0.075, 6, 16),
    -s * 0.04, 0, 0, 0.96, dish);
  c.add(HULL, new THREE.CylinderGeometry(s * 0.26, s * 0.08, s * 0.16, 12),
    s * 0.02, 0, 0, MAT.goldStone, ROT_Z90);
  c.add(GLOW, new THREE.CylinderGeometry(s * 0.10, s * 0.02, s * 0.72, 8),
    s * 0.38, 0, 0, MAT.runeCyan, ROT_Z90);
  c.add(GLOW, new THREE.SphereGeometry(s * 0.09, 8, 6), s * 0.74, 0, 0, MAT.frostGlow);
  return c.parts;
}

/** 持续旋转的部件：指挥中心雷达、精炼厂转筒等。 */
function spinnerParts(kind, size) {
  const s = size;
  if (kind === 'hq') {
    const c = partCollector();
    // 支臂 + 斜置抛物面 + 馈源，转起来像在扫描
    c.add(HULL, new THREE.BoxGeometry(s * 0.07, s * 0.07, s * 0.34), 0, 0, s * 0.12, MAT.steel);
    c.add(HULL, new THREE.BoxGeometry(s * 0.06, s * 0.2, s * 0.06), 0, s * 0.1, s * 0.26, MAT.steel);
    c.add(TEAM, new THREE.CylinderGeometry(s * 0.19, s * 0.19, s * 0.035, 14),
      0, s * 0.22, s * 0.28, 0.95, new THREE.Matrix4().makeRotationX(-1.35));
    c.add(HULL, new THREE.BoxGeometry(s * 0.02, s * 0.02, s * 0.14),
      0, s * 0.3, s * 0.34, MAT.darkSteel);
    c.add(GLOW, new THREE.SphereGeometry(s * 0.035, 8, 6), 0, s * 0.33, s * 0.38, GLOW_HOT);
    return { parts: c.parts, y: size * 1.96, speed: 0.55 };
  }
  if (kind === 'refinery') {
    const c = partCollector();
    c.add(HULL, new THREE.TorusGeometry(s * 0.3, s * 0.05, 6, 10), 0, 0, 0, MAT.copper, ROT_X90);
    for (let i = 0; i < 4; i++) {
      const a = (i / 4) * Math.PI * 2;
      c.add(GLOW, new THREE.BoxGeometry(s * 0.16, s * 0.04, s * 0.06),
        Math.cos(a) * s * 0.3, 0, Math.sin(a) * s * 0.3, GLOW_SOFT);
    }
    return { parts: c.parts, y: size * 1.42, x: size * 0.42, speed: 1.35 };
  }
  if (kind === 'power') {
    const c = partCollector();
    c.add(GLOW, new THREE.TorusGeometry(s * 0.34, s * 0.03, 6, 14), 0, 0, 0, GLOW_HOT,
      new THREE.Matrix4().makeRotationX(1.2));
    return { parts: c.parts, y: size * 1.56, speed: -2.4 };
  }
  // ---- 秘法会：浮空金冠、绕针碎晶、釜口符环、法阵悬浮核 ----
  if (kind === 'mpower') {
    const c = partCollector();
    c.add(HULL, new THREE.ConeGeometry(s * 0.10, s * 0.18, 6), s * 0.28, 0, 0, MAT.goldTrim);
    c.add(GLOW, new THREE.SphereGeometry(s * 0.05, 7, 5), s * 0.28, 0, 0, MAT.runeCyan);
    return { parts: c.parts, y: size * 1.72, speed: -2.4 };
  }
  if (kind === 'mrefinery') {
    const c = partCollector();
    c.add(GLOW, new THREE.TorusGeometry(s * 0.36, s * 0.03, 6, 14), 0, 0, 0, MAT.runeCyan, ROT_X90);
    for (let i = 0; i < 4; i++) {
      const a = (i / 4) * Math.PI * 2;
      c.add(GLOW, new THREE.BoxGeometry(s * 0.12, s * 0.03, s * 0.05),
        Math.cos(a) * s * 0.36, 0, Math.sin(a) * s * 0.36, MAT.frostGlow);
    }
    return { parts: c.parts, y: size * 0.58 + 3.4, speed: 1.15 };
  }
  if (kind === 'mhq') {
    const c = partCollector();
    for (let i = 0; i < 3; i++) {
      const a = (i / 3) * Math.PI * 2;
      c.add(HULL, new THREE.ConeGeometry(s * 0.055, s * 0.10, 5),
        Math.cos(a) * s * 0.42, 0, Math.sin(a) * s * 0.42, MAT.goldTrim);
      c.add(GLOW, new THREE.SphereGeometry(s * 0.03, 6, 5),
        Math.cos(a) * s * 0.42, 0, Math.sin(a) * s * 0.42, MAT.runeCyan);
    }
    return { parts: c.parts, y: size * 2.00, speed: 0.7 };
  }
  if (kind === 'mspring') {
    const c = partCollector();
    c.add(GLOW, new THREE.TorusGeometry(s * 0.28, s * 0.025, 6, 14), 0, 0, 0, MAT.runeCyan,
      new THREE.Matrix4().makeRotationX(1.2));
    return { parts: c.parts, y: size * 1.18, speed: -1.8 };
  }
  if (kind === 'mcircle') {
    const c = partCollector();
    c.add(HULL, new THREE.ConeGeometry(s * 0.12, s * 0.22, 6), 0, 0, 0, MAT.goldTrim);
    c.add(GLOW, new THREE.SphereGeometry(s * 0.09, 8, 6), 0, 0, 0, MAT.runeCyan);
    c.add(GLOW, new THREE.TorusGeometry(s * 0.20, s * 0.02, 6, 12), 0, 0, 0, MAT.frostGlow, ROT_X90);
    return { parts: c.parts, y: size * 1.06, speed: 1.35 };
  }
  if (kind === 'mtemple') {
    const c = partCollector();
    c.add(GLOW, new THREE.SphereGeometry(s * 0.06, 8, 6), 0, 0, 0, MAT.runeCyan);
    return { parts: c.parts, y: size * 0.66 + 3.4, speed: 1.6 };
  }
  return null;
}

// 每种建筑的几何体只生成一次，所有实例共享
const STRUCTURE_GEOMETRY_CACHE = new Map();

function structureGeometries(kind, size) {
  const key = kind + ':' + size;
  let entry = STRUCTURE_GEOMETRY_CACHE.get(key);
  if (entry) return entry;
  const parts = structureParts(kind, size);
  // 三个通道全部并进一个几何体：HULL 现在带固有色、GLOW 的顶点系数 > 1，
  // 着色器靠 aTeam 与色值量级就能区分，不再需要分材质。一座建筑因此只占
  // 一次绘制调用（原来是三次）。
  entry = {
    team: parts.length ? mergeParts(parts) : null,
    hull: null,
    head: null,
    spin: null
  };
  if (kind === 'turret') {
    const head = turretHeadParts(size);
    entry.head = {
      team: head.length ? mergeParts(head) : null,
      hull: null,
      y: size * 0.78
    };
  }
  if (kind === 'missile') {
    const head = missileHeadParts(size);
    entry.head = {
      team: head.length ? mergeParts(head) : null,
      hull: null,
      y: size * 0.82
    };
  }
  if (kind === 'mtower') {
    const head = arcaneHeadParts(size);
    entry.head = {
      team: head.length ? mergeParts(head) : null,
      hull: null,
      y: size * 1.72 + 3.4
    };
  }
  const spin = spinnerParts(kind, size);
  if (spin) {
    entry.spin = {
      team: spin.parts.length ? mergeParts(spin.parts) : null,
      hull: null,
      x: spin.x || 0,
      y: spin.y,
      speed: spin.speed
    };
  }
  STRUCTURE_GEOMETRY_CACHE.set(key, entry);
  return entry;
}

/**
 * 组装一座建筑：三种材质各一个 Mesh，外加可动的炮塔头与旋转件。
 * 几何体来自共享缓存，dispose 时不能连带释放。
 */
function structureGroup(kind, size, teamMaterial) {
  const geo = structureGeometries(kind, size);
  const group = new THREE.Group();
  const attach = function (geometry, material, parent, shadow) {
    if (!geometry) return null;
    const mesh = new THREE.Mesh(geometry, material);
    mesh.castShadow = !!shadow;
    mesh.receiveShadow = !!shadow;
    parent.add(mesh);
    return mesh;
  };
  attach(geo.team, teamMaterial, group, true);

  if (geo.head) {
    const head = new THREE.Group();
    attach(geo.head.team, teamMaterial, head, true);
    head.position.set(0, geo.head.y, 0);
    head.name = 'turretHead';
    group.add(head);
  }
  if (geo.spin) {
    const spin = new THREE.Group();
    attach(geo.spin.team, teamMaterial, spin, true);
    spin.position.set(geo.spin.x, geo.spin.y, 0);
    spin.name = 'spinner';
    spin.userData.speed = geo.spin.speed;
    group.add(spin);
  }
  return group;
}

/* ------------------------------------------------------------------ *
 * 渲染器
 * ------------------------------------------------------------------ */

const GROUND_SEG = 1.0;       // 地形网格密度系数

/**
 * 每张地图的战场观感。服务端 theme 只是一个标签，真正上色、天空、雾、
 * 小地图底色都走这里。同为 grassland 的图也不能画成同一块网球场绿。
 *
 * 颜色刻意压在 0.7 以下：地面走 Lambert + 2.3 倍阳光，再给后处理留余量，
 * 顶点色一旦把绿通道顶过 1.0 就会晒成荧光草坪。
 */
export const MAP_DISPLAY_THEMES = {
  grassland: {
    id: 'grassland',
    grass: [0.34, 0.44, 0.24],
    lush: [0.28, 0.42, 0.20],
    dry: [0.50, 0.44, 0.26],
    dirt: [0.40, 0.32, 0.20],
    packed: [0.38, 0.33, 0.24],
    rock: [0.46, 0.44, 0.40],
    forest: [0.20, 0.38, 0.15],
    skirt: 0x4a5638,
    pad: 0x5a4e3a,
    fog: 0x9ec8d8,
    horizon: 0xf2e4c4,
    mid: 0x9fd4ee,
    zenith: 0x3f8fd6,
    skyGround: 0x8fb2c0,
    hemiSky: 0xaed9ff,
    hemiGround: 0x55603a,
    sun: 0xffedc2,
    fill: 0x9ab4c4,
    rim: 0xa8e2f2,
    tex: [0.90, 1.00, 0.76],
    minimap: { base: '#3f5234', dry: 'rgba(196,176,96,.14)', light: 'rgba(232,236,196,', dark: 'rgba(8,16,6,', mountain: '#4d7a3c' }
  },
  arid: {
    id: 'arid',
    grass: [0.58, 0.44, 0.24],
    lush: [0.48, 0.38, 0.20],
    dry: [0.70, 0.52, 0.28],
    dirt: [0.56, 0.38, 0.18],
    packed: [0.52, 0.38, 0.22],
    rock: [0.56, 0.46, 0.34],
    forest: [0.30, 0.40, 0.13],
    skirt: 0x6a5a3a,
    pad: 0x6a5840,
    fog: 0xc8b894,
    horizon: 0xf0d8a8,
    mid: 0xd4c4a0,
    zenith: 0x6aa0c8,
    skyGround: 0xb8a078,
    hemiSky: 0xc8d8e8,
    hemiGround: 0x6a5a38,
    sun: 0xffe0a8,
    fill: 0xc4b090,
    rim: 0xe8d4a0,
    tex: [1.00, 0.90, 0.68],
    minimap: { base: '#6a5a38', dry: 'rgba(220,180,90,.16)', light: 'rgba(236,212,150,', dark: 'rgba(28,18,8,', mountain: '#7a8a3c' }
  },
  urban: {
    id: 'urban',
    grass: [0.32, 0.36, 0.28],
    lush: [0.28, 0.34, 0.26],
    dry: [0.42, 0.40, 0.34],
    dirt: [0.34, 0.32, 0.28],
    packed: [0.36, 0.35, 0.32],
    rock: [0.40, 0.39, 0.38],
    forest: [0.15, 0.27, 0.15],
    skirt: 0x3a3c38,
    pad: 0x3e3c38,
    fog: 0x8a9aaa,
    horizon: 0xc8c4b8,
    mid: 0x8aa8c0,
    zenith: 0x3a5a78,
    skyGround: 0x6a7080,
    hemiSky: 0x9ab0c4,
    hemiGround: 0x3a3c34,
    sun: 0xf0e8d8,
    fill: 0x8a9aaa,
    rim: 0xa8c0d0,
    tex: [0.88, 0.90, 0.86],
    minimap: { base: '#3a3e38', dry: 'rgba(160,156,140,.14)', light: 'rgba(200,204,196,', dark: 'rgba(8,10,10,', mountain: '#3a5c3a' }
  },
  crater: {
    id: 'crater',
    grass: [0.52, 0.32, 0.20],
    lush: [0.42, 0.26, 0.16],
    dry: [0.66, 0.40, 0.22],
    dirt: [0.48, 0.30, 0.18],
    packed: [0.46, 0.32, 0.22],
    rock: [0.50, 0.38, 0.32],
    forest: [0.13, 0.25, 0.11],
    skirt: 0x5a3a28,
    pad: 0x5a4030,
    fog: 0xb88870,
    horizon: 0xf0c090,
    mid: 0xc89068,
    zenith: 0x4a6088,
    skyGround: 0xa07058,
    hemiSky: 0xd8b090,
    hemiGround: 0x5a3828,
    sun: 0xffd090,
    fill: 0xc09070,
    rim: 0xf0b080,
    tex: [1.00, 0.78, 0.62],
    minimap: { base: '#5a3a28', dry: 'rgba(220,140,70,.16)', light: 'rgba(236,180,120,', dark: 'rgba(24,10,6,', mountain: '#3c5c2c' }
  }
};

function displayTheme(themeId) {
  return MAP_DISPLAY_THEMES[themeId] || MAP_DISPLAY_THEMES.grassland;
}

// 服务端会随地图下发同名细节参数；这里保留主题缺省值，旧存档/旧服务端的
// full 帧也能得到完整地表。它们只改变网格高度和装饰物，不参与 2D 权威碰撞。
const TERRAIN_DETAIL_DEFAULTS = {
  grassland: { relief: 1.20, colorVariation: 1.18, grassDensity: 1.00, rockDensity: 0.78, spawnFlatRadius: 280, centerFlatRadius: 0 },
  arid: { relief: 1.32, colorVariation: 1.26, grassDensity: 0.34, rockDensity: 1.18, spawnFlatRadius: 280, centerFlatRadius: 0 },
  urban: { relief: 0.62, colorVariation: 0.82, grassDensity: 0.18, rockDensity: 0.62, spawnFlatRadius: 300, centerFlatRadius: 0 },
  crater: { relief: 1.42, colorVariation: 1.34, grassDensity: 0.16, rockDensity: 1.34, spawnFlatRadius: 290, centerFlatRadius: 0 }
};

function resolveTerrainDetail(map, terrain) {
  const themeId = (terrain && terrain.theme) || 'grassland';
  const result = Object.assign({},
    TERRAIN_DETAIL_DEFAULTS[themeId] || TERRAIN_DETAIL_DEFAULTS.grassland);
  // 兼容未重启的旧服务端：五车争疆可由唯一的 4000×4000 / 五出生点布局识别。
  const isCentralScramble = (map && map.id === 'central_scramble') ||
    (map && map.width === 4000 && map.height === 4000);
  if (isCentralScramble) {
    Object.assign(result, {
      relief: 1.58, colorVariation: 1.42, grassDensity: 1.35,
      rockDensity: 1.48, spawnFlatRadius: 320, centerFlatRadius: 620
    });
  }
  Object.assign(result, (terrain && terrain.detail) || {});
  result.relief = THREE.MathUtils.clamp(Number(result.relief) || 1, 0.35, 2.2);
  result.colorVariation = THREE.MathUtils.clamp(Number(result.colorVariation) || 1, 0.5, 1.8);
  result.grassDensity = THREE.MathUtils.clamp(Number(result.grassDensity) || 0, 0, 2);
  result.rockDensity = THREE.MathUtils.clamp(Number(result.rockDensity) || 0, 0, 2);
  result.spawnFlatRadius = THREE.MathUtils.clamp(Number(result.spawnFlatRadius) || 0, 0, 700);
  result.centerFlatRadius = THREE.MathUtils.clamp(Number(result.centerFlatRadius) || 0, 0, 1000);
  return result;
}

// 相机拉到这个距离以外才换用可辨识的兵种剪影。单位数量不再触发全场
// 硬切低模：InstancedMesh 的绘制调用本来就按兵种合批，数量阈值只会造成
// 模型突然一起变成盒子，却没有省下任何 draw call。
const UNIT_LOD_DISTANCE = 900;
// 渲染出来的通道比碰撞尺寸长这么多倍，用来跨过做了抖动加宽的林带
const BRIDGE_RENDER_SPAN = 2.0;

/**
 * 单位模型的视觉放大系数（纯表现，不影响碰撞/选取，那些仍用服务端 size）。
 *
 * 服务端的 size 是给 2D 俯视图定的碰撞半径；照搬到 3D 里，从 RTS 常用的
 * 视距看步兵只有几个像素，根本认不出兵种。这里按兵种放大到能辨识的比例。
 */
const UNIT_VISUAL_SCALE = {
  rifle: 2.15, rocket: 2.15, sniper: 2.15, tesla: 2.15, dog: 1.85,
  tank: 1.28, scout: 1.34, tank_destroyer: 1.28,
  artillery: 1.28, harvester: 1.16, mcv: 1.30, v3: 1.28,
  overlord: 1.30, prism: 1.28, bomb_truck: 1.32,
  mage: 2.15, frost: 2.15, imp: 2.05, oracle: 2.15, golem: 1.42, panther: 1.7, dragon: 1.34,
  warden: 1.55, colossus: 1.38, comet: 1.28, hexling: 2.05,
  mharvester: 1.16, mmcv: 1.30
};

/**
 * 俯视点选半径相对服务端 size 的表现层校正。长法杖、龙翼和低矮兽身会伸出
 * 玩法碰撞圆；这里仅让可见轮廓能被点中，不参与碰撞、寻路或武器判定。
 */
export const UNIT_VISUAL_PICK_SCALE = Object.freeze({
  mage: 3.10, frost: 3.10, imp: 1.70, oracle: 3.25,
  golem: 1.05, panther: 1.90, dragon: 1.90,
  warden: 1.75, colossus: 1.45, comet: 1.20,
  mharvester: 1.00, mmcv: 1.20, hexling: 1.10
});

/* 共享的哈希值噪声：天空的云、水面的泡沫、地形的细节法线都用同一套，
 * 免得每个着色器各带一份不同实现。 */
const NOISE_GLSL = `
float hash12(vec2 p) {
  return fract(sin(dot(p, vec2(127.1, 311.7))) * 43758.5453);
}
float vnoise(vec2 p) {
  vec2 i = floor(p);
  vec2 f = fract(p);
  f = f * f * (3.0 - 2.0 * f);
  return mix(mix(hash12(i), hash12(i + vec2(1.0, 0.0)), f.x),
             mix(hash12(i + vec2(0.0, 1.0)), hash12(i + vec2(1.0, 1.0)), f.x), f.y);
}
`;

/* 天空球：明亮的热带白昼 —— 天顶蓝、地平线暖白、太阳盘 + FBM 流云。
 * 参考画面的整体基调是高饱和晴天，阴沉的夜战配色出不来那个味道。 */
const SKY_VERT = `
varying vec3 vDir;
void main() {
  vDir = normalize(position);
  gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
}
`;

const SKY_FRAG = `
uniform vec3 uHorizon;
uniform vec3 uMid;
uniform vec3 uZenith;
uniform vec3 uGround;
uniform vec3 uSunDir;
uniform vec3 uSunColor;
uniform float uTime;
varying vec3 vDir;
${NOISE_GLSL}
void main() {
  vec3 dir = normalize(vDir);
  float h = dir.y;
  vec3 color;
  if (h > 0.0) {
    // 两段式：地平线暖白 → 中层浅蓝 → 天顶饱和蓝
    color = mix(uHorizon, uMid, smoothstep(0.0, 0.22, h));
    color = mix(color, uZenith, smoothstep(0.18, 0.85, h));
  } else {
    color = mix(uHorizon, uGround, pow(clamp(-h, 0.0, 1.0), 0.45));
  }
  // 地平线附近加一道很淡的辉光带，远处不再是一刀切
  color += uHorizon * 0.25 * exp(-abs(h) * 12.0);

  // FBM 流云：把方向投影到虚拟云层平面上采样，随时间漂移。
  // 只在地平线以上，靠近地平线渐隐避免和辉光带打架。
  if (h > 0.015) {
    vec2 cuv = dir.xz / max(dir.y, 0.06) * 0.32 + uTime * vec2(0.010, 0.004);
    float cl = 0.0;
    float amp = 0.5;
    vec2 p = cuv * 3.0;
    for (int i = 0; i < 2; i++) {
      cl += amp * vnoise(p);
      p = p * 2.03 + 17.0;
      amp *= 0.5;
    }
    float clouds = smoothstep(0.52, 0.82, cl) * smoothstep(0.02, 0.16, h);
    // 云底略带暖灰，向阳一侧压白
    float lit = 0.5 + 0.5 * max(dot(dir, uSunDir), 0.0);
    vec3 cloudCol = mix(vec3(0.86, 0.88, 0.92), vec3(1.08, 1.05, 1.0), lit * 0.6);
    color = mix(color, cloudCol, clouds * 0.62);
    // 太阳：紧致的 HDR 亮盘（辉光管线会自动做出光晕）+ 宽柔光晕
    float sd = max(dot(dir, uSunDir), 0.0);
    color += uSunColor * (pow(sd, 900.0) * 5.0 + pow(sd, 40.0) * 0.30) * (1.0 - clouds * 0.85);
  }
  gl_FragColor = vec4(color, 1.0);
}
`;

export function createRenderer(canvas) {
  const renderer = new THREE.WebGLRenderer({
    canvas: canvas,
    antialias: false,
    powerPreference: 'high-performance'
  });
  renderer.outputColorSpace = THREE.SRGBColorSpace;
  renderer.shadowMap.enabled = true;
  // 软阴影：PCFSoft 的软边比硬 PCF 更接近 Apple 那种柔和的接触影
  renderer.shadowMap.type = THREE.PCFSoftShadowMap;
  renderer.setClearColor(0x9ec8d8);

  const textureLoader = new THREE.TextureLoader();
  const sharedTextureCache = new Map();
  function loadSharedTexture(path, mirrored, anisotropy) {
    let tex = sharedTextureCache.get(path);
    if (tex) return tex;
    tex = textureLoader.load(path);
    tex.wrapS = tex.wrapT = mirrored ? THREE.MirroredRepeatWrapping : THREE.ClampToEdgeWrapping;
    tex.colorSpace = THREE.SRGBColorSpace;
    tex.minFilter = THREE.LinearMipmapLinearFilter;
    tex.magFilter = THREE.LinearFilter;
    tex.generateMipmaps = true;
    tex.anisotropy = Math.min(anisotropy || 4, renderer.capabilities.getMaxAnisotropy());
    sharedTextureCache.set(path, tex);
    return tex;
  }

  const postfx = createPostFX(renderer);

  const scene = new THREE.Scene();
  // 亮色大气雾：远景融进天光而不是沉进黑暗，整张地图才有白昼感
  scene.fog = new THREE.Fog(0x9ec8d8, 2400, 5200);

  const camera = new THREE.PerspectiveCamera(46, 1, 12, 12000);

  // 太阳方位是常量（applyCamera 里位置总是焦点 + (700,1150,-500)），
  // 天空的太阳盘、水面的高光、单位的镜面反射共用这一个方向。
  const SUN_DIR = new THREE.Vector3(700, 1150, -500).normalize();
  const SUN_TINT = new THREE.Color(1.0, 0.92, 0.78);

  // 天空球跟着相机走，永远画在最里层
  const skyMaterial = new THREE.ShaderMaterial({
    uniforms: {
      uHorizon: { value: new THREE.Color(0xf2e4c4) },
      uMid: { value: new THREE.Color(0x9fd4ee) },
      uZenith: { value: new THREE.Color(0x3f8fd6) },
      uGround: { value: new THREE.Color(0x8fb2c0) },
      uSunDir: { value: SUN_DIR },
      uSunColor: { value: SUN_TINT },
      uTime: { value: 0 }
    },
    vertexShader: SKY_VERT,
    fragmentShader: SKY_FRAG,
    side: THREE.BackSide,
    depthWrite: false,
    fog: false
  });
  const sky = new THREE.Mesh(new THREE.SphereGeometry(1, 12, 8), skyMaterial);
  sky.renderOrder = -100;
  sky.frustumCulled = false;
  scene.add(sky);

  // 自然日光：暖色主光塑造体积，冷天光只负责抬暗部，轮廓光保持克制。
  // 写实粗糙材质不能被过强补光洗成塑料，所以整体强度比旧版更收敛。
  const hemi = new THREE.HemisphereLight(0xaed9ff, 0x55603a, 0.62);
  scene.add(hemi);

  const sun = new THREE.DirectionalLight(0xffedc2, 2.0);
  sun.castShadow = true;
  // 阴影默认关闭、开了就是要画质，所以给到 1024，软边的细节才出得来
  sun.shadow.mapSize.set(1024, 1024);
  sun.shadow.camera.near = 50;
  sun.shadow.camera.far = 3200;
  sun.shadow.bias = -0.0012;
  sun.shadow.normalBias = 1.2;
  scene.add(sun);
  scene.add(sun.target);

  const fill = new THREE.DirectionalLight(0x9ab4c4, 0.22);
  scene.add(fill);
  const rim = new THREE.DirectionalLight(0xa8e2f2, 0.26);
  scene.add(rim);

  const worldRoot = new THREE.Group();
  scene.add(worldRoot);

  const state = {
    width: 1, height: 1, dpr: 1,
    map: null, terrain: null,
    camX: 0, camY: 0, zoom: 0.78, yaw: 0, pitch: 0.94,
    shadows: 'structures', lod: true, fogScale: 6, particleBudget: 600,
    bloom: true,
    showProjectiles: true,
    buildTerrainMs: 0, groundDetailParts: 0,
    snapshotUnits: 0, renderedUnits: 0, renderedStructures: 0,
    sight: null, terrainDetail: null,
    palette: new Map(),
    friendly: function () { return false; },
    viewerId: null
  };

  /* -------------------- 地形 -------------------- */

  let groundTexture = null;
  let terrainGroup = null;
  let waterMesh = null;
  // 已经建好的静态世界的身份。full 帧不等于「静态数据变了」——重连、恢复
  // 会话、以及每条 REST 响应都会带 full 帧，其中绝大多数是同一张图。
  // 只有这个键变了才值得推倒重建，否则直接复用显存里现成的地形。
  let builtWorldKey = '';
  // 地形建好后直接采样网格高度。过去每个可见单位每帧都重新遍历河流、山脉
  // 并执行多组三角函数，军团规模上来后 CPU 时间会线性爆炸。
  let heightField = null;

  function riverDepthAt(x, y) {
    // 返回 0..1：越靠近沟壑中心越深。用于压低地形顶点，形成真实的深沟。
    //
    // 衰减用 smoothstep 而不是线性：线性剖面在沟沿处一阶导数突变，网格再密
    // 也会看到一圈折角；smoothstep 两端导数为零，沟沿自然。
    const rivers = (state.terrain && state.terrain.rivers) || [];
    let deepest = 0;
    for (let i = 0; i < rivers.length; i++) {
      const r = rivers[i];
      const half = r.width * 0.5;
      const dx = r.x2 - r.x1;
      const dy = r.y2 - r.y1;
      const lenSq = dx * dx + dy * dy;
      let t = lenSq < 0.001 ? 0 : ((x - r.x1) * dx + (y - r.y1) * dy) / lenSq;
      t = Math.max(0, Math.min(1, t));
      const cx = r.x1 + t * dx;
      const cy = r.y1 + t * dy;
      const dist = Math.hypot(x - cx, y - cy);
      // 岸线抖动：完全笔直的沟沿一眼假。沿沟长方向取一段噪声调制过渡带
      // 宽度，让沟沿自然弯曲。抖动只向外扩不向内收 —— 视觉沟壑是碰撞区域
      // 的超集，玩家看到深沟的地方一定过不去，不会出现「看着是地却走不了」。
      const wob = 1.0
        + 0.17 * Math.sin(t * 13.7 + r.x1 * 0.004)
        + 0.11 * Math.sin(t * 27.3 - r.y1 * 0.005)
        + 0.07 * Math.sin((x + y) * 0.0042);
      const bank = half + 130 * Math.max(0.6, wob);
      if (dist < bank) {
        const k = 1 - dist / bank;
        let depth = k * k * (3 - 2 * k);            // smoothstep
        // 河床沿程深浅变化，不是一条等深水槽
        depth *= 0.82 + 0.18 * Math.sin(t * 5.1 + r.x1 * 0.002);
        if (depth > deepest) deepest = depth;
      }
    }
    return deepest;
  }

  /**
   * 把「顶点色 > 1 即自发光」的规则注入到受光材质里。
   *
   * 发光件本来就是团队色，只是不受光。原先它们单独一个网格，于是每个单位
   * 和每座建筑都要多一次绘制调用（600 单位 + 80 建筑时是一百多次）。合并进
   * 主网格后，靠顶点色的量级区分：≤1 走正常光照，>1 直接当自发光输出。
   */
  // 视空间的太阳方向：所有注入材质共享同一个 uniform 对象，逐帧只更新一次
  const sunDirViewUniform = { value: new THREE.Vector3(0.4, 0.8, 0.4) };
  const armyTimeUniform = { value: 0 };
  /** 左半是旧化军用钢板，右半是风化玄武岩；所有军械共用这一张 1024×512 图。 */
  function makeArmySurfaceTexture() {
    return loadSharedTexture('/assets/textures/army-real-atlas.webp', false, 4);
  }

  function applyEmissiveByVertexColor(material, surfaceKind) {
    const surfaceMode = surfaceKind === 'stone' ? 1 :
      (surfaceKind === 'cloth' ? 2 : (surfaceKind === 'hide' ? 3 : 0));
    material.onBeforeCompile = function (shader) {
      shader.uniforms.uSunDirView = sunDirViewUniform;
      shader.uniforms.uArmyTime = armyTimeUniform;
      shader.uniforms.uArmySurface = { value: makeArmySurfaceTexture() };
      shader.uniforms.uArmySurfaceMode = { value: surfaceMode };
      // three.js 的 <color_vertex> 已经把 instanceColor 乘进 vColor，
      // 所以另存一份未乘的原始顶点色，供固有色零件使用。
      shader.vertexShader = 'attribute float aTeam;\nvarying float vTeamMix;\n' +
        'varying vec3 vOwnColor;\nvarying vec3 vArmyWorld;\n' + shader.vertexShader
          .replace(
            '#include <color_vertex>',
            '#include <color_vertex>\n  vTeamMix = aTeam;\n  vOwnColor = color;')
          .replace(
            '#include <begin_vertex>',
            '#include <begin_vertex>\n' +
            '  {\n' +
            '    vec4 armyWorld = vec4(transformed, 1.0);\n' +
            '#ifdef USE_INSTANCING\n' +
            '    armyWorld = instanceMatrix * armyWorld;\n' +
            '#endif\n' +
            '    vArmyWorld = (modelMatrix * armyWorld).xyz;\n' +
            '  }');
      shader.fragmentShader = 'varying float vTeamMix;\nvarying vec3 vOwnColor;\n' +
        'varying vec3 vArmyWorld;\nuniform vec3 uSunDirView;\nuniform float uArmyTime;\n' +
        'uniform sampler2D uArmySurface;\nuniform float uArmySurfaceMode;\n' +
        shader.fragmentShader
          .replace('#include <color_fragment>',
            '#include <color_fragment>\n' +
            // vTeamMix=0 走固有色，=1 走「团队色 × 明暗系数」
            '  diffuseColor.rgb = mix(vOwnColor, diffuseColor.rgb, vTeamMix);\n' +
            '  vec3 gBase = diffuseColor.rgb;\n' +
            '  float gEmissive = clamp(max(max(gBase.r, gBase.g), gBase.b) - 1.0, 0.0, 1.0);\n' +
            // 纯 RGB 队色会像塑料玩具；非发光涂装保留色相，但压饱和、压亮度，
            // 看起来更像喷在钢板/布料上的哑光识别色。
            '  if (gEmissive < 0.04 && vTeamMix > 0.01) {\n' +
            '    float gPaintLum = dot(diffuseColor.rgb, vec3(0.299, 0.587, 0.114));\n' +
            '    vec3 gFieldPaint = mix(vec3(gPaintLum), diffuseColor.rgb, 0.64) * 0.78;\n' +
            '    diffuseColor.rgb = mix(diffuseColor.rgb, gFieldPaint, vTeamMix);\n' +
            '    gBase = diffuseColor.rgb;\n' +
            '  }\n' +
            '  float gSurfaceLum = 0.5;\n' +
            '  float gAtlasSide = step(0.5, uArmySurfaceMode);\n' +
            '  float gRoughness = mix(0.56, 0.84, gAtlasSide);\n' +
            '  float gBumpScale = mix(0.30, 0.72, gAtlasSide);\n' +
            '  float gSurfaceBlend = 0.34;\n' +
            // 布料和皮革仍复用右半张风化纹理，但把凹凸/色差压低；法袍不再像石柱，
            // 兽皮也不会出现钢板高光。只增加两个共享材质变体，不拆单位合批。
            '  if (uArmySurfaceMode > 1.5 && uArmySurfaceMode < 2.5) {\n' +
            '    gRoughness = 0.92; gBumpScale = 0.20; gSurfaceBlend = 0.16;\n' +
            '  } else if (uArmySurfaceMode > 2.5) {\n' +
            '    gRoughness = 0.74; gBumpScale = 0.34; gSurfaceBlend = 0.22;\n' +
            '  }\n' +
            // 世界空间镜像投影：左半旧钢、右半玄武岩。一次采样同时提供颜色、
            // 粗糙度依据和凹凸高度，仍然不拆单位/建筑的合批。
            '  if (gEmissive < 0.04) {\n' +
            '    vec2 gSurfaceUv = vec2(vArmyWorld.x + vArmyWorld.y * 0.37, vArmyWorld.z + vArmyWorld.y * 0.61) * 0.032;\n' +
            '    vec2 gMirror = abs(fract(gSurfaceUv * 0.5) * 2.0 - 1.0);\n' +
            '    vec2 gAtlasUv = vec2(mix(0.01, 0.51, gAtlasSide) + gMirror.x * 0.48, 0.01 + gMirror.y * 0.98);\n' +
            '    vec3 gSurface = texture2D(uArmySurface, gAtlasUv).rgb;\n' +
            '    gSurfaceLum = dot(gSurface, vec3(0.299, 0.587, 0.114));\n' +
            '    vec3 gNeutral = gSurface / max(gSurfaceLum, 0.10);\n' +
            '    float gRelief = mix(0.68, 1.30, smoothstep(0.08, 0.78, gSurfaceLum));\n' +
            '    diffuseColor.rgb *= mix(vec3(1.0), gNeutral, gSurfaceBlend) * gRelief;\n' +
            '    float gGrime = smoothstep(0.36, 0.10, gSurfaceLum);\n' +
            '    diffuseColor.rgb = mix(diffuseColor.rgb, diffuseColor.rgb * vec3(0.58, 0.55, 0.50), gGrime * 0.36);\n' +
            '    gRoughness = clamp(gRoughness + (0.45 - gSurfaceLum) * 0.18, 0.38, 0.94);\n' +
            '  }')
          .replace('#include <normal_fragment_begin>',
            '#include <normal_fragment_begin>\n' +
            // 由照片亮度导数产生微凹凸，不新增法线贴图采样；粗糙石面和旧钢的
            // 光不再贴着几何面整块滑动，能压掉低模最明显的塑料感。
            '  if (gEmissive < 0.04) {\n' +
            '    vec3 gSigmaX = dFdx(vViewPosition);\n' +
            '    vec3 gSigmaY = dFdy(vViewPosition);\n' +
            '    vec3 gR1 = cross(gSigmaY, normal);\n' +
            '    vec3 gR2 = cross(normal, gSigmaX);\n' +
            '    float gDet = dot(gSigmaX, gR1);\n' +
            '    vec3 gGrad = sign(gDet) * (dFdx(gSurfaceLum) * gR1 + dFdy(gSurfaceLum) * gR2);\n' +
            '    normal = normalize(abs(gDet) * normal - gBumpScale * gGrad);\n' +
            '  }\n' +
            '  vec3 gUpView = normalize((viewMatrix * vec4(0.0, 1.0, 0.0, 0.0)).xyz);\n' +
            '  diffuseColor.rgb *= mix(0.88, 1.045, smoothstep(-0.45, 1.0, dot(normal, gUpView)));')
          .replace('#include <dithering_fragment>',
            '#include <dithering_fragment>\n' +
            '  {\n' +
            '    vec3 gN = normalize(normal);\n' +
            '    vec3 gV = normalize(vViewPosition);\n' +
            '    float gRim = pow(1.0 - clamp(dot(gN, gV), 0.0, 1.0), 3.0);\n' +
            '    vec3 gH = normalize(gV + uSunDirView);\n' +
            '    float gGloss = 1.0 - gRoughness;\n' +
            '    float gSpec = pow(max(dot(gN, gH), 0.0), mix(12.0, 56.0, gGloss));\n' +
            '    gl_FragColor.rgb += (vec3(0.34, 0.42, 0.46) * gRim * 0.10\n' +
            '      + vec3(1.0, 0.93, 0.78) * gSpec * mix(0.10, 0.52, gGloss)) * (1.0 - gEmissive);\n' +
            '    float gPulse = 0.86 + 0.14 * sin(uArmyTime * 2.1 + vArmyWorld.x * 0.03);\n' +
            '    gl_FragColor.rgb = mix(gl_FragColor.rgb, gBase * gPulse, gEmissive);\n' +
            '  }');
    };
    material.customProgramCacheKey = function () { return 'teamOrOwn7-real-' + surfaceMode; };
    return material;
  }

  /**
   * 给地形类材质注入迷雾遮罩。
   *
   * 原来迷雾是一张贴在 y=26 的平面，只能盖住比它矮的东西；山体岩块高达
   * 一百多个单位，会整个戳出迷雾外，看起来像黑暗里浮着几块石头。改成在
   * 每个地形材质里按世界坐标采样迷雾贴图，多高都盖得住。
   *
   * UV 推导：迷雾平面用的是 rotateX(-90°) 的 PlaneGeometry，加上 CanvasTexture
   * 默认 flipY，最终 v = 1 - worldZ / mapHeight 才对得上画布行号。
   */
  // 云影时间：所有带迷雾遮罩的材质共享，逐帧推进一次
  const cloudTimeUniform = { value: 0 };

  function applyFogMask(material) {
    material.onBeforeCompile = function (shader) {
      shader.uniforms.uFogMask = { value: fogTexture };
      shader.uniforms.uMapSize = { value: fogMapSize };
      shader.uniforms.uCloudTime = cloudTimeUniform;
      fogMaskedShaders.push(shader);
      shader.vertexShader = 'varying vec3 vFogWorld;\n' + shader.vertexShader.replace(
        '#include <begin_vertex>',
        '#include <begin_vertex>\n  vFogWorld = (modelMatrix * vec4(transformed, 1.0)).xyz;');
      shader.fragmentShader =
        'uniform sampler2D uFogMask;\nuniform vec2 uMapSize;\nuniform float uCloudTime;\n' +
        'varying vec3 vFogWorld;\n' +
        'float fmHash(vec2 p) { return fract(sin(dot(p, vec2(127.1, 311.7))) * 43758.5453); }\n' +
        'float fmNoise(vec2 p) {\n' +
        '  vec2 i = floor(p); vec2 f = fract(p); f = f * f * (3.0 - 2.0 * f);\n' +
        '  return mix(mix(fmHash(i), fmHash(i + vec2(1.0, 0.0)), f.x),\n' +
        '             mix(fmHash(i + vec2(0.0, 1.0)), fmHash(i + vec2(1.0, 1.0)), f.x), f.y);\n' +
        '}\n' +
        shader.fragmentShader.replace(
          '#include <dithering_fragment>',
          '#include <dithering_fragment>\n' +
          // 移动云影：和天空 FBM 用同一漂移方向，顶视角虽然看不到云，
          // 但地面上缓慢滑过的暗斑会让人「知道」天上有云。
          '  float fmCloud = fmNoise(vFogWorld.xz * 0.0016 + uCloudTime * vec2(0.010, 0.004));\n' +
          '  fmCloud += 0.5 * fmNoise(vFogWorld.xz * 0.0037 + uCloudTime * vec2(0.013, 0.006));\n' +
          '  gl_FragColor.rgb *= 1.0 - 0.22 * smoothstep(0.72, 1.15, fmCloud);\n' +
          '  vec2 fogUv = vec2(vFogWorld.x / uMapSize.x, 1.0 - vFogWorld.z / uMapSize.y);\n' +
          '  float shroud = texture2D(uFogMask, clamp(fogUv, 0.0, 1.0)).a;\n' +
          '  gl_FragColor.rgb = mix(gl_FragColor.rgb, vec3(0.010, 0.024, 0.031), shroud);');
    };
    // 同一个着色器变体，缓存键固定即可，避免每个材质都重新编译
    material.customProgramCacheKey = function () { return 'fogmask2'; };
    return material;
  }

  // 地面片元着色用的主题色。所有地面材质共享，换图时只改这三个 Color。
  const terrainDirtTint = { value: new THREE.Color(0.40, 0.32, 0.20) };
  const terrainDryTint = { value: new THREE.Color(0.50, 0.44, 0.26) };
  const terrainGrassTint = { value: new THREE.Color(0.34, 0.44, 0.24) };

  /**
   * 给地面材质再叠一层逐像素细节，与迷雾注入串联使用。
   *
   * 顶点密度封顶 5 万面片，大地图上一格 40+ 世界单位，纯顶点色的地面
   * 在低角度阳光下是一整片均匀亮度 —— 平得像桌布。这里做三件事：
   *   1) 程序化细节贴图只提供微粒明暗，色相仍交给顶点色；
   *   2) 世界空间 FBM 在片元里混出土斑 / 枯草，近景才有「草皮」而不是色块；
   *   3) 带解析导数的值噪声扰动法线，让阳光把地面碎成自然明暗。
   */
  function applyTerrainDetail(material) {
    const prevCompile = material.onBeforeCompile;
    material.onBeforeCompile = function (shader) {
      if (prevCompile) prevCompile(shader);
      shader.uniforms.uDirtTint = terrainDirtTint;
      shader.uniforms.uDryTint = terrainDryTint;
      shader.uniforms.uGrassTint = terrainGrassTint;
      shader.fragmentShader =
        'uniform vec3 uDirtTint;\nuniform vec3 uDryTint;\nuniform vec3 uGrassTint;\n' +
        shader.fragmentShader
        .replace('#include <map_fragment>',
          '  vec4 tdTex = texture2D(map, vMapUv);\n' +
          '  float tdLum = dot(tdTex.rgb, vec3(0.30, 0.50, 0.20));\n' +
          '  vec3 tdNeutral = tdTex.rgb / max(tdLum, 0.12);\n' +
          '  float tdRelief = mix(0.76, 1.23, smoothstep(0.12, 0.78, tdLum));\n' +
          '  diffuseColor.rgb *= mix(vec3(1.0), tdNeutral, 0.36) * tdRelief;\n' +
          // 片元里再混一层土斑/枯草：顶点色负责大色块，这里负责近景草皮。
          // 必须写在 map_fragment，不能再碰 dithering_fragment —— 迷雾注入已经占用它。
          '  {\n' +
          '    vec2 tdW = vFogWorld.xz;\n' +
          '    float tdPatch = fmNoise(tdW * 0.0048);\n' +
          '    tdPatch += 0.45 * fmNoise(tdW * 0.011 + vec2(17.0, 9.0));\n' +
          // 贴图已经携带多方向的草痕/砂砾，复用本次采样的亮度，不再在片元里
          // 生成整幅平行正弦条纹，也省掉第三次值噪声。
          '    float tdGrain = smoothstep(0.42, 0.72, tdLum);\n' +
          '    diffuseColor.rgb = mix(diffuseColor.rgb, uDryTint, smoothstep(0.48, 0.84, tdPatch) * 0.30);\n' +
          '    diffuseColor.rgb = mix(diffuseColor.rgb, uDirtTint, (1.0 - tdGrain) * 0.10);\n' +
          '    diffuseColor.rgb = mix(diffuseColor.rgb, uGrassTint, 0.035);\n' +
          '  }')
        .replace('#include <normal_fragment_begin>',
          '#include <normal_fragment_begin>\n' +
          '  {\n' +
          '    vec3 tdSigmaX = dFdx(vViewPosition);\n' +
          '    vec3 tdSigmaY = dFdy(vViewPosition);\n' +
          '    vec3 tdR1 = cross(tdSigmaY, normal);\n' +
          '    vec3 tdR2 = cross(normal, tdSigmaX);\n' +
          '    float tdDet = dot(tdSigmaX, tdR1);\n' +
          '    vec3 tdGrad = sign(tdDet) * (dFdx(tdLum) * tdR1 + dFdy(tdLum) * tdR2);\n' +
          '    float tdFade = 1.0 - smoothstep(700.0, 1800.0, length(vViewPosition));\n' +
          '    normal = normalize(abs(tdDet) * normal - tdGrad * (0.55 * tdFade));\n' +
          '  }');
    };
    const prevKey = material.customProgramCacheKey;
    material.customProgramCacheKey = function () {
      return (prevKey ? prevKey.call(material) : '') + '+terraindetail4-real';
    };
    return material;
  }

  /**
   * 树冠继续是一整个合并网格；UV 来自每层低面数树冠，照片叶簇只作用于绿色
   * 部分，细树干仍保留棕色。亮度导数提供近景叶层凹凸，不再增加第二张贴图。
   */
  function applyForestRealism(material) {
    const prevCompile = material.onBeforeCompile;
    material.onBeforeCompile = function (shader) {
      if (prevCompile) prevCompile(shader);
      shader.fragmentShader = shader.fragmentShader
        .replace('#include <map_fragment>',
          '  vec4 frTex = texture2D(map, vMapUv);\n' +
          '  float frLum = dot(frTex.rgb, vec3(0.299, 0.587, 0.114));')
        .replace('#include <color_fragment>',
          '#include <color_fragment>\n' +
          '  float frFoliage = smoothstep(0.015, 0.12, diffuseColor.g - diffuseColor.r);\n' +
          '  vec3 frNeutral = frTex.rgb / max(frLum, 0.08);\n' +
          '  float frRelief = mix(0.70, 1.25, smoothstep(0.05, 0.58, frLum));\n' +
          '  diffuseColor.rgb *= mix(vec3(1.0), frNeutral * frRelief, frFoliage * 0.82);')
        .replace('#include <normal_fragment_begin>',
          '#include <normal_fragment_begin>\n' +
          '  if (frFoliage > 0.01) {\n' +
          '    vec3 frSigmaX = dFdx(vViewPosition);\n' +
          '    vec3 frSigmaY = dFdy(vViewPosition);\n' +
          '    vec3 frR1 = cross(frSigmaY, normal);\n' +
          '    vec3 frR2 = cross(normal, frSigmaX);\n' +
          '    float frDet = dot(frSigmaX, frR1);\n' +
          '    vec3 frGrad = sign(frDet) * (dFdx(frLum) * frR1 + dFdy(frLum) * frR2);\n' +
          '    normal = normalize(abs(frDet) * normal - frGrad * (0.46 * frFoliage));\n' +
          '  }');
    };
    const prevKey = material.customProgramCacheKey;
    material.customProgramCacheKey = function () {
      return (prevKey ? prevKey.call(material) : '') + '+forest-real1';
    };
    return material;
  }

  /**
   * 山体隆起。
   *
   * 单纯的 smoothstep 穹丘看起来就是个土包 —— 真实山体有放射状的山脊、
   * 深切的沟谷和起伏的岩面。这里在穹丘上乘一层「随绕山角度变化」的脊线
   * 噪声，再叠一层高频岩面细节；两者都随 k 衰减，山脚仍然平滑收敛到 0，
   * 不会破坏服务端按半径判定的碰撞边界。
   */
  function mountainHeightAt(x, y) {
    const mountains = (state.terrain && state.terrain.mountains) || [];
    let highest = 0;
    for (let i = 0; i < mountains.length; i++) {
      const m = mountains[i];
      const dx = x - m.x;
      const dy = y - m.y;
      const d = Math.hypot(dx, dy);
      if (d >= m.r) continue;
      const k = 1 - d / m.r;
      const s = k * k * (3 - 2 * k);
      // 每座山用自己的相位，形状各不相同
      const pa = m.x * 0.0031;
      const pb = m.y * 0.0027;
      const ang = Math.atan2(dy, dx);
      const ridge = 0.70 + 0.30 * (0.5 + 0.5 *
        Math.sin(ang * 4 + pa) * Math.sin(ang * 7 - pb));
      let h = m.r * 0.92 * s * ridge;
      // 岩面细节，同样随 k 衰减
      h += (Math.sin(x * 0.013 + pa) * Math.cos(y * 0.0115 - pb) * 9
        + Math.sin(x * 0.031 - y * 0.027) * 3.5) * s;
      if (h > highest) highest = h;
    }
    return Math.max(0, highest);
  }

  /**
   * 林间小路混合系数。返回 0..1：0 = 树林；1 = 小路核心区（通道碰撞盒内）；
   * 0..1 之间 = 路沿过渡带（渲染加长的那一截，从土路平滑落回林床）。
   * 树已经避开这块区域，这里就是森林里唯一的豁口。
   */
  function pointSegmentDistanceSq(px, py, x1, y1, x2, y2) {
    const dx = x2 - x1;
    const dy = y2 - y1;
    const lengthSq = dx * dx + dy * dy;
    let t = lengthSq > 0.001
      ? ((px - x1) * dx + (py - y1) * dy) / lengthSq
      : 0;
    t = Math.max(0, Math.min(1, t));
    const ox = px - (x1 + dx * t);
    const oy = py - (y1 + dy * t);
    return ox * ox + oy * oy;
  }

  function bridgeTrailAt(x, y) {
    const bridges = (state.terrain && state.terrain.bridges) || [];
    for (let i = 0; i < bridges.length; i++) {
      const b = bridges[i];
      if (Number.isFinite(b.x1) && Number.isFinite(b.y1) &&
          Number.isFinite(b.x2) && Number.isFinite(b.y2)) {
        const core = b.width * 0.5;
        const feather = 55;
        const distance = Math.sqrt(pointSegmentDistanceSq(
          x, y, b.x1, b.y1, b.x2, b.y2));
        if (distance <= core) return 1;
        if (distance < core + feather) {
          return 1 - (distance - core) / feather;
        }
        continue;
      }
      const along = b.w >= b.h;
      const halfW = b.w * 0.5;
      const halfH = b.h * 0.5;
      const renderHalfW = along ? halfW * BRIDGE_RENDER_SPAN : halfW;
      const renderHalfH = along ? halfH : halfH * BRIDGE_RENDER_SPAN;
      const dx = Math.abs(x - b.x);
      const dy = Math.abs(y - b.y);
      if (dx > renderHalfW || dy > renderHalfH) continue;
      let blend = 1;
      if (dx > halfW) {
        blend = Math.min(blend, 1 - (dx - halfW) / (renderHalfW - halfW));
      }
      if (dy > halfH) {
        blend = Math.min(blend, 1 - (dy - halfH) / (renderHalfH - halfH));
      }
      if (blend > 0) return blend;
    }
    return 0;
  }

  /**
   * 地表高度。地形网格、道路贴花、单位与建筑的落点都用这一个函数，
   * 否则各算各的就会出现「单位悬空」「路飘在坡上」这类错位。
   */
  const _ghCache = new Map();
  function terrainFlatnessAt(x, y) {
    const detail = state.terrainDetail;
    if (!detail || !state.map) return 0;
    let best = 0;
    const circle = function (cx, cy, radius, feather) {
      if (radius <= 0) return 0;
      const distance = Math.hypot(x - cx, y - cy);
      if (distance <= radius) return 1;
      if (distance >= radius + feather) return 0;
      const t = 1 - (distance - radius) / feather;
      return t * t * (3 - 2 * t);
    };
    if (detail.centerFlatRadius > 0) {
      best = circle(state.map.width * 0.5, state.map.height * 0.5,
        detail.centerFlatRadius, 260);
    }
    const spawns = state.spawnPoints || [];
    for (let i = 0; i < spawns.length && best < 1; i++) {
      best = Math.max(best, circle(spawns[i][0], spawns[i][1],
        detail.spawnFlatRadius, 180));
    }
    return best;
  }

  function rollingHeight(x, y) {
    // 纯装饰起伏：服务端寻路仍是 2D 平面。长波草坡负责打破桌面感，短波
    // 只刻画土壤；出生/展开区通过平滑权重压回水平，建筑不会架在坡肩上。
    const broad = Math.sin(x * 0.00043 + y * 0.00027) * 7.5
      + Math.cos(x * 0.00061 - y * 0.00039) * 5.5;
    const ground = broad
      + Math.sin(x * 0.0016) * Math.cos(y * 0.0021) * 10
      + Math.sin(x * 0.0007 + y * 0.0011) * 7
      + Math.sin(x * 0.0068 + y * 0.0043) * 2.6
      + Math.cos(x * 0.0121 - y * 0.0097) * 1.5
      + Math.sin(x * 0.028 + y * 0.019) * 0.8;
    const relief = state.terrainDetail ? state.terrainDetail.relief : 1;
    return ground * relief * (1 - terrainFlatnessAt(x, y));
  }

  function baseGroundHeight(x, y) {
    if (heightField) {
      const hf = heightField;
      const gx = THREE.MathUtils.clamp(x / hf.width * hf.segX, 0, hf.segX);
      const gy = THREE.MathUtils.clamp(y / hf.height * hf.segY, 0, hf.segY);
      const ix = Math.min(hf.segX - 1, Math.floor(gx));
      const iy = Math.min(hf.segY - 1, Math.floor(gy));
      const tx = gx - ix;
      const ty = gy - iy;
      const a = iy * hf.cols + ix;
      const h0 = hf.values[a] * (1 - tx) + hf.values[a + 1] * tx;
      const h1 = hf.values[a + hf.cols] * (1 - tx) + hf.values[a + hf.cols + 1] * tx;
      return h0 * (1 - ty) + h1 * ty;
    }
    const kx = (x * 2 + 0.5) | 0;
    const ky = (y * 2 + 0.5) | 0;
    const key = (kx << 16) | (ky & 0xffff);
    const cached = _ghCache.get(key);
    if (cached !== undefined) return cached;
    // 河道不挖深槽：渲染成平地树林（riverDepthAt 只用于着色与种树），
    // 桥从林间跨过。视觉上比下沉沟壑清楚，也不用担心桥头插进土里。
    const roll = rollingHeight(x, y);
    const result = roll + mountainHeightAt(x, y);
    _ghCache.set(key, result);
    return result;
  }

  function groundHeight(x, y) {
    return baseGroundHeight(x, y);
  }

  function spawnWearAt(x, y) {
    const spawns = state.spawnPoints || [];
    let best = 0;
    for (let i = 0; i < spawns.length; i++) {
      const d = Math.hypot(x - spawns[i][0], y - spawns[i][1]);
      if (d < 320) {
        const k = 1 - d / 320;
        if (k * k > best) best = k * k;
      }
    }
    return best;
  }

  /** 低频噪声：给地表顶点色做草木/干土斑块，同一张图每次一致。 */
  function clumpNoise(x, y) {
    return (Math.sin(x * 0.00085 + y * 0.00042) * 0.5
      + Math.sin(x * 0.00031 - y * 0.00097) * 0.35
      + Math.sin((x + y) * 0.00058) * 0.25) * 0.5 + 0.5;
  }

  const proceduralGroundCache = new Map();

  /**
   * 512px 实拍式压实土壤（WebP 约 90KB）。主题色仍由地形顶点决定，贴图只
   * 提供真实砂砾、纤维和小石子；镜像平铺避免素材边缘出现接缝。
   */
  function makeProceduralGroundTexture(themeId) {
    const cached = proceduralGroundCache.get(themeId);
    if (cached) {
      cached.userData.themeId = themeId;
      return cached;
    }
    const tex = loadSharedTexture('/assets/textures/ground-real.webp', true, 8);
    tex.userData.themeId = themeId;
    proceduralGroundCache.set(themeId, tex);
    return tex;
  }

  let buildingPadMat = null;
  const buildingPadGeo = new THREE.PlaneGeometry(2, 2).rotateX(-Math.PI / 2);
  let buildingPadTex = null;

  function makeBuildingPadTexture() {
    if (buildingPadTex) return buildingPadTex;
    const size = 128;
    const cv = document.createElement('canvas');
    cv.width = cv.height = size;
    const ctx = cv.getContext('2d');
    const img = ctx.createImageData(size, size);
    const d = img.data;
    for (let y = 0; y < size; y++) {
      for (let x = 0; x < size; x++) {
        const dx = (x + 0.5) / size * 2 - 1;
        const dy = (y + 0.5) / size * 2 - 1;
        // 圆角方垫：贴住方形钢坎/石台，不再是一块金属圆盘。
        const ax = Math.abs(dx), ay = Math.abs(dy);
        const rad = 0.22;
        const ox = Math.max(ax - (1 - rad), 0);
        const oy = Math.max(ay - (1 - rad), 0);
        const inside = Math.max(ax, ay) < (1 - rad);
        const edge = inside ? Math.max(ax, ay) * 0.55 : 0.55 + Math.hypot(ox, oy) / rad;
        const wobble = 0.05 * Math.sin(dx * 9.0 + dy * 7.0) * Math.cos(dy * 5.0);
        let a = 1 - Math.max(0, (edge + wobble - 0.52) / 0.48);
        if (a < 0) a = 0;
        a = a * a * (3 - 2 * a);
        const grit = (Math.sin(x * 0.41 + y * 0.17) * Math.cos(y * 0.33) + 1) * 0.5;
        const lum = 0.58 + grit * 0.32;
        const i = (y * size + x) * 4;
        d[i] = lum * 255;
        d[i + 1] = lum * 220;
        d[i + 2] = lum * 176;
        d[i + 3] = a * 188;
      }
    }
    ctx.putImageData(img, 0, 0);
    buildingPadTex = new THREE.CanvasTexture(cv);
    buildingPadTex.colorSpace = THREE.SRGBColorSpace;
    return buildingPadTex;
  }

  function applyWorldTheme(theme) {
    scene.fog.color.setHex(theme.fog);
    renderer.setClearColor(theme.fog);
    skyMaterial.uniforms.uHorizon.value.setHex(theme.horizon);
    skyMaterial.uniforms.uMid.value.setHex(theme.mid);
    skyMaterial.uniforms.uZenith.value.setHex(theme.zenith);
    skyMaterial.uniforms.uGround.value.setHex(theme.skyGround);
    hemi.color.setHex(theme.hemiSky);
    hemi.groundColor.setHex(theme.hemiGround);
    sun.color.setHex(theme.sun);
    fill.color.setHex(theme.fill);
    rim.color.setHex(theme.rim);
    terrainDirtTint.value.set(theme.dirt[0], theme.dirt[1], theme.dirt[2]);
    terrainDryTint.value.set(theme.dry[0], theme.dry[1], theme.dry[2]);
    terrainGrassTint.value.set(theme.grass[0], theme.grass[1], theme.grass[2]);
    if (buildingPadMat) buildingPadMat.color.setHex(theme.pad);
  }

  function buildTerrain() {
    const buildStarted = performance.now();
    heightField = null;
    _ghCache.clear();
    if (terrainGroup) {
      worldRoot.remove(terrainGroup);
      terrainGroup.traverse(function (o) {
        if (o.geometry) o.geometry.dispose();
      });
    }
    terrainGroup = new THREE.Group();
    worldRoot.add(terrainGroup);

    // 先建迷雾贴图：下面所有地形材质都要在编译时拿到它
    buildFogPlane();

    const mw = state.map.width;
    const mh = state.map.height;
    const theme = displayTheme(state.terrain && state.terrain.theme);
    const detail = state.terrainDetail || resolveTerrainDetail(state.map, state.terrain);
    state.groundDetailParts = 0;
    applyWorldTheme(theme);
    if (!groundTexture || groundTexture.userData.themeId !== theme.id) {
      groundTexture = makeProceduralGroundTexture(theme.id);
    }
    groundTexture.repeat.set(mw / 420, mh / 420);
    // 网格密度按面积自适应：最细 26 世界单位一格（60 太粗，一条 120 宽的河
    // 只跨两格，河床边缘全是折线），但总面片数封顶约 5 万，免得大地图上顶点
    // 数失控。这是一次性构建的静态几何，一个 draw call。
    const targetQuads = 20000;
    const cell = Math.max(40, Math.sqrt(mw * mh / targetQuads));
    const segX = Math.max(48, Math.round(mw / cell * GROUND_SEG));
    const segY = Math.max(48, Math.round(mh / cell * GROUND_SEG));

    const geo = new THREE.PlaneGeometry(mw, mh, segX, segY);
    geo.rotateX(-Math.PI / 2);
    const pos = geo.attributes.position;
    const colors = new Float32Array(pos.count * 3);
    const heights = new Float32Array(pos.count);
    for (let i = 0; i < pos.count; i++) {
      const wx = pos.getX(i) + mw / 2;
      const wz = pos.getZ(i) + mh / 2;
      const depth = riverDepthAt(wx, wz);
      const rock = mountainHeightAt(wx, wz);
      const height = rollingHeight(wx, wz) + rock;
      heights[i] = height;
      pos.setY(i, height);

      // 地表分层：主题底色 + 草木斑 + 出生点踩实土 + 山岩。
      // 色值压在 0.7 以下，避免 Lambert×强阳光把草地晒成荧光网球场。
      // 道路只留玩法加成，不再把路肩脏土画进顶点色。
      const stone = Math.min(1, rock / 70);
      const ravine = Math.min(1, depth * 1.4);
      const bank = Math.max(0, 1 - Math.abs(depth - 0.10) / 0.14) * (depth > 0.005 ? 1 : 0);
      const rawLush = clumpNoise(wx, wz);
      const lush = THREE.MathUtils.clamp(
        0.5 + (rawLush - 0.5) * detail.colorVariation, 0, 1);
      const stripe = 0.5 + 0.5 * Math.sin(wx * 0.0022 + lush * 2.4);
      const wear = spawnWearAt(wx, wz);
      const topo = 1 + Math.max(-1, Math.min(1, height / 24)) * 0.10;

      let r = theme.grass[0] + (theme.lush[0] - theme.grass[0]) * lush;
      let g = theme.grass[1] + (theme.lush[1] - theme.grass[1]) * lush;
      let b = theme.grass[2] + (theme.lush[2] - theme.grass[2]) * lush;
      const dry = Math.max(0, 0.46 - lush) * 1.7;
      r += (theme.dry[0] - r) * dry;
      g += (theme.dry[1] - g) * dry;
      b += (theme.dry[2] - b) * dry;
      r += (theme.lush[0] - r) * stripe * 0.16;
      g += (theme.lush[1] - g) * stripe * 0.16;
      b += (theme.lush[2] - b) * stripe * 0.16;
      r = r * (1 - bank) + theme.dirt[0] * 1.15 * bank;
      g = g * (1 - bank) + theme.dirt[1] * 1.05 * bank;
      b = b * (1 - bank) + theme.dirt[2] * bank;
      const packed = wear * 0.85;
      r = r * (1 - packed) + theme.packed[0] * packed;
      g = g * (1 - packed) + theme.packed[1] * packed;
      b = b * (1 - packed) + theme.packed[2] * packed;
      // 大山整片森林，小尺寸的巨石丘保留岩石本色——森林里嵌着石头，
      // 森林巨石区压缩可发展空间的同时还有地形读感。
      const forestMix = Math.min(1, rock / 150);
      r = r * (1 - stone * 0.72)
        + (theme.forest[0] * forestMix + theme.rock[0] * (1 - forestMix)) * stone;
      g = g * (1 - stone * 0.72)
        + (theme.forest[1] * forestMix + theme.rock[1] * (1 - forestMix)) * stone;
      b = b * (1 - stone * 0.72)
        + (theme.forest[2] * forestMix + theme.rock[2] * (1 - forestMix)) * stone;
      // 林间小路：通道碰撞盒（含渲染过渡带）露出土路，树已避开这片区域
      const trail = bridgeTrailAt(wx, wz);
      if (trail > 0) {
        r = r * (1 - trail) + theme.dirt[0] * trail;
        g = g * (1 - trail) + theme.dirt[1] * trail;
        b = b * (1 - trail) + theme.dirt[2] * trail;
      }
      // 河道：深绿林床（树荫 + 腐殖土），上面再立树模型
      r = r * (1 - ravine) + 0.13 * ravine;
      g = g * (1 - ravine) + 0.24 * ravine;
      b = b * (1 - ravine) + 0.12 * ravine;
      r *= topo; g *= topo; b *= topo;
      colors[i * 3] = r;
      colors[i * 3 + 1] = g;
      colors[i * 3 + 2] = b;
    }
    geo.setAttribute('color', new THREE.BufferAttribute(colors, 3));
    geo.computeVertexNormals();

    const material = applyTerrainDetail(applyFogMask(new THREE.MeshLambertMaterial({
      map: groundTexture, vertexColors: true
    })));
    const ground = new THREE.Mesh(geo, material);
    ground.position.set(mw / 2, 0, mh / 2);
    ground.receiveShadow = true;
    ground.name = 'ground';
    terrainGroup.add(ground);

    // PlaneGeometry 的顶点按 z 行、x 列排列。后续单位/建筑只做四次数组读取与
    // 双线性插值，且落点和实际渲染出来的网格完全一致。
    heightField = {
      values: heights, cols: segX + 1, segX: segX, segY: segY,
      width: mw, height: mh
    };
    _ghCache.clear();

    // 河道与山丘都不画水面/岩石：渲染成树林（riverDepthAt / mountainHeightAt
    // 决定林带位置），桥从林间跨过。没有水，也没有岩石 —— 走到林边看到的
    // 是真的过不去的密林，一眼就能看出桥是唯一的通路。
    waterMesh = null;

    // 树林：沿河道与山丘撒树，桥盒（含渲染加长段）两侧留出桥头空地。
    // 所有树干 + 树冠合并进一个网格，一次绘制调用。
    const bridges = (state.terrain && state.terrain.bridges) || [];
    const rivers = (state.terrain && state.terrain.rivers) || [];
    const mountains = (state.terrain && state.terrain.mountains) || [];
    if (rivers.length || mountains.length) {
      const forestParts = [];
      const treeSlab = function (w, h, d, x, y, z, rgb) {
        forestParts.push({
          geo: new THREE.BoxGeometry(w, h, d),
          matrix: new THREE.Matrix4().setPosition(x, y, z),
          rgb: rgb
        });
      };
      // 确定性哈希：同一张图每次打开树的位置不变
      const treeRand = function (n) {
        const s = Math.sin(n * 12.9898 + 78.233) * 43758.5453;
        return s - Math.floor(s);
      };
      // 树冠色板：每张图从主题森林色派生三种色调，山与河道各自取用，
      // 同图里不同位置也会出现深浅变化 ——「各种森林」而不是一种绿。
      const baseForest = theme.forest;
      const FOLIAGE_A = baseForest;
      const FOLIAGE_B = [
        Math.min(1, baseForest[0] * 1.35), Math.min(1, baseForest[1] * 1.3),
        Math.min(1, baseForest[2] * 1.35)
      ];
      const FOLIAGE_DARK = [
        baseForest[0] * 0.72, baseForest[1] * 0.82, baseForest[2] * 0.72
      ];
      const placeTree = function (tx, ty, seed) {
        if (riverDepthAt(tx, ty) > 0.05 || mountainHeightAt(tx, ty) > 0.05) {
          // 树底落在实际地面上（含山丘），避免树干悬空或埋进坡里
          const gy = rollingHeight(tx, ty) + mountainHeightAt(tx, ty);
          const big = treeRand(seed * 3.1 + 97) > 0.38;
          // 最高的魔法主堡约 144 高；森林树顶提高到约 147–178，
          // 保证每棵成树都越过建筑天际线，并在远处形成连续林冠。
          const trunkH = 68 + treeRand(seed + 53) * 22;
          const trunkW = big ? 3.8 : 3.1;
          const crownR = big ? 22 : 17;
          const crownH = big ? 64 : 58;
          const trunkShade = 0.84 + treeRand(seed * 2.7 + 9) * 0.24;
          const trunk = [0.30 * trunkShade, 0.20 * trunkShade, 0.10 * trunkShade];
          treeSlab(trunkW, trunkH, trunkW, tx, gy + trunkH * 0.5, ty, trunk);
          const foliage = treeRand(seed * 5.7 + 41);
          const rgb = foliage > 0.72 ? FOLIAGE_DARK
            : (foliage > 0.3 ? FOLIAGE_A : FOLIAGE_B);
          // 同一棵树的三层树冠分别压暗、保持、提亮，仍合并为原先的一个网格，
          // 但远看能读出厚实林墙，近看也不会是一整块纯色方柱。
          const shadeFoliage = function (amount) {
            return [
              Math.min(1, rgb[0] * amount),
              Math.min(1, rgb[1] * amount),
              Math.min(1, rgb[2] * amount)
            ];
          };
          const crownLow = shadeFoliage(0.76);
          const crownMid = shadeFoliage(0.96);
          const crownTop = shadeFoliage(1.16);
          // 三层收尖树冠：底层互相搭接形成林墙，上层保持单棵树的高耸轮廓。
          treeSlab(crownR * 2.1, crownH * 0.72, crownR * 2.1,
                   tx, gy + trunkH + crownH * 0.28, ty, crownLow);
          treeSlab(crownR * 1.5, crownH * 0.68, crownR * 1.5,
                   tx, gy + trunkH + crownH * 0.72, ty, crownMid);
          treeSlab(crownR * 0.86, crownH * 0.5, crownR * 0.86,
                   tx, gy + trunkH + crownH * 1.12, ty, crownTop);
        }
      };
      const nearBridge = function (tx, ty) {
        for (let bi = 0; bi < bridges.length; bi++) {
          const b = bridges[bi];
          if (Number.isFinite(b.x1) && Number.isFinite(b.y1) &&
              Number.isFinite(b.x2) && Number.isFinite(b.y2)) {
            const clearance = b.width * 0.5 + 65;
            if (pointSegmentDistanceSq(
                tx, ty, b.x1, b.y1, b.x2, b.y2) < clearance * clearance) {
              return true;
            }
            continue;
          }
          const along = b.w >= b.h;
          const hw = (along ? b.w * BRIDGE_RENDER_SPAN : b.w) * 0.5 + 55;
          const hh = (along ? b.h : b.h * BRIDGE_RENDER_SPAN) * 0.5 + 55;
          if (Math.abs(tx - b.x) < hw && Math.abs(ty - b.y) < hh) {
            return true;
          }
        }
        return false;
      };
      // 河道林带：树量同时随长度和宽度增加；加厚后的五条分界带会形成
      // 多排密林，而不是只把一排树横向拉散。
      for (let r = 0; r < rivers.length; r++) {
        const rv = rivers[r];
        const rdx = rv.x2 - rv.x1;
        const rdy = rv.y2 - rv.y1;
        const len = Math.hypot(rdx, rdy);
        const half = rv.width * 0.5;
        const density = Math.max(1, rv.width / 120);
        const count = Math.min(1500, Math.max(12, Math.floor(len / 17 * density)));
        const ux = len > 0.001 ? rdx / len : 1;
        const uy = len > 0.001 ? rdy / len : 0;
        const nx = -uy;
        const ny = ux;
        for (let k = 0; k < count; k++) {
          const t = (k + 0.5) / count;
          const cx = rv.x1 + rdx * t;
          const cy = rv.y1 + rdy * t;
          const lateral = (treeRand(k + r * 131) * 2 - 1) * half * 0.94;
          const alongJitter = (treeRand(k * 7.3 + r * 19) - 0.5) *
            Math.max(16, len / count * 1.8);
          const tx = cx + nx * lateral + ux * alongJitter;
          const ty = cy + ny * lateral + uy * alongJitter;
          if (riverDepthAt(tx, ty) < 0.12) continue;
          if (nearBridge(tx, ty)) continue;
          placeTree(tx, ty, k + r * 211);
        }
      }
      // 山丘森林：每座山按半径撒树，山顶到山脚密度递减，
      // 大树/小树/三种绿色混出「各种森林」
      for (let mi = 0; mi < mountains.length; mi++) {
        const m = mountains[mi];
        const mcount = Math.max(10, Math.round(m.r / 14));
        for (let k = 0; k < mcount; k++) {
          const ang = treeRand(k * 3.7 + mi * 29) * Math.PI * 2;
          const rad = m.r * (0.12 + treeRand(k * 1.9 + mi * 13) * 0.85);
          const tx = m.x + Math.cos(ang) * rad;
          const ty = m.y + Math.sin(ang) * rad;
          if (nearBridge(tx, ty)) continue;
          if (riverDepthAt(tx, ty) > 0.05) continue;
          placeTree(tx, ty, k + mi * 977 + 5000);
        }
      }
      if (forestParts.length) {
        const forestMesh = new THREE.Mesh(
          mergeParts(forestParts),
          applyForestRealism(applyFogMask(new THREE.MeshLambertMaterial({
            vertexColors: true,
            map: loadSharedTexture('/assets/textures/foliage-real.webp', true, 4)
          }))));
        forestMesh.castShadow = state.shadows !== 'off';
        forestMesh.receiveShadow = true;
        forestMesh.frustumCulled = false;
        terrainGroup.add(forestMesh);
      }
    }

    // 林间小路：没有桥面模型 —— 通道碰撞盒在网格顶点色里画成土路
    // （bridgeTrailAt），树已避开这片区域，森林在这里断开成一条豁口。
    // 单位直接走在平地上，服务端寻路不变。

    // 地图边界：一圈向外倾斜下沉的裙边，颜色贴近雾色，让边缘融进远景而
    // 不是留下一道生硬的黑边
    const edgeMat = applyFogMask(new THREE.MeshLambertMaterial({
      color: theme.skirt, fog: true, side: THREE.DoubleSide
    }));
    const skirt = 900;
    [[mw / 2, mh, mw + skirt * 2, skirt, 0],
     [mw / 2, 0, mw + skirt * 2, skirt, Math.PI],
     [0, mh / 2, mh + skirt * 2, skirt, Math.PI / 2],
     [mw, mh / 2, mh + skirt * 2, skirt, -Math.PI / 2]].forEach(function (e) {
      const geo = new THREE.PlaneGeometry(e[2], e[3], 1, 1);
      geo.rotateX(-Math.PI / 2);
      const pos = geo.attributes.position;
      for (let i = 0; i < pos.count; i++) {
        // 远离地图的一侧往下沉，形成缓坡
        if (pos.getZ(i) > 0) pos.setY(i, -190);
      }
      geo.computeVertexNormals();
      const apron = new THREE.Mesh(geo, edgeMat);
      apron.position.set(e[0], -2, e[1]);
      apron.rotation.y = e[4];
      terrainGroup.add(apron);
    });

    buildRocks();
    buildGroundDetail();
    buildOreField();
    state.buildTerrainMs = Math.round(performance.now() - buildStarted);
  }

  /**
   * 山体上的岩块：给隆起的地形一个硬朗的轮廓，而不只是一个土包。
   *
   * 每座山的所有岩块合并成一个网格。原来是一块石头一个 Mesh，12 座山就有
   * 250 多个对象要逐个做视锥剔除和绘制；合并后 12 次绘制调用搞定，剔除
   * 粒度仍然是「一座山」，足够用。
   */
  function buildRocks() {
    const mountains = (state.terrain && state.terrain.mountains) || [];
    if (!mountains.length) return;
    const rockGeo = new THREE.DodecahedronGeometry(1, 0);
    const material = applyFogMask(new THREE.MeshLambertMaterial({
      vertexColors: true, flatShading: true
    }));
    // 按高度分层取色：山脚是带土的褐岩，中段灰岩，接近峰顶压向雪白。
    // 一整座山都用同一个灰会很塑料。
    const LOW = [[0.34, 0.28, 0.22], [0.29, 0.25, 0.20], [0.38, 0.32, 0.25]];
    const MID = [[0.42, 0.41, 0.39], [0.31, 0.30, 0.29], [0.50, 0.48, 0.45]];
    const HIGH = [[0.74, 0.76, 0.79], [0.62, 0.64, 0.68], [0.86, 0.88, 0.91]];
    const bandFor = function (frac, pick) {
      if (frac > 0.66) return HIGH[pick];
      if (frac > 0.30) return MID[pick];
      return LOW[pick];
    };

    mountains.forEach(function (m, mi) {
      // 固定伪随机：同一张地图每次布局一致
      let seed = (Math.round(m.x) * 73856093 ^ Math.round(m.y) * 19349663 ^ mi) >>> 0;
      const rand = function () {
        seed = (seed * 1103515245 + 12345) & 0x7fffffff;
        return seed / 0x7fffffff;
      };
      const parts = [];
      const push = function (px, py, sx, sy, sz, rotY, tilt, rgb) {
        const mat = new THREE.Matrix4().makeRotationY(rotY);
        mat.multiply(new THREE.Matrix4().makeRotationX(tilt));
        mat.scale(new THREE.Vector3(sx, sy, sz));
        mat.setPosition(px, groundHeight(px, py) + sy * 0.35, py);
        parts.push({ geo: rockGeo, matrix: mat, rgb: rgb });
      };

      const count = Math.max(9, Math.round(m.r / 15));
      for (let i = 0; i < count; i++) {
        const a = rand() * TAU;
        const rr = Math.pow(rand(), 0.6) * m.r * 0.82;
        const px = m.x + Math.cos(a) * rr;
        const py = m.y + Math.sin(a) * rr;
        const size = m.r * (0.05 + rand() * 0.09) * (1 - rr / m.r * 0.35);
        // 用相对高度决定色带，山体的垂直分层才出得来
        const frac = 1 - rr / m.r;
        push(px, py, size, size * (0.7 + rand() * 0.9), size * (0.8 + rand() * 0.5),
          rand() * TAU, (rand() - 0.5) * 0.5, bandFor(frac, Math.floor(rand() * 3)));
      }
      // 峰顶岩：原来取半径的 0.34，在 r=300 的山上就是一块 100 单位的漂砾，
      // 比坦克还大，反而不像山。压到 0.13 并靠数量堆出体量。
      const ph = m.r * 0.13;
      push(m.x, m.y, ph, ph * 1.25, ph * 0.9, rand() * TAU, 0, HIGH[2]);

      // 山脚碎石带：让山「长」在地上，而不是扣上去的一顶帽子
      const scree = Math.round(m.r / 24);
      for (let i = 0; i < scree; i++) {
        const a = rand() * TAU;
        const rr = m.r * (0.86 + rand() * 0.26);
        const px = m.x + Math.cos(a) * rr;
        const py = m.y + Math.sin(a) * rr;
        const size = m.r * (0.015 + rand() * 0.035);
        push(px, py, size, size * (0.5 + rand() * 0.6), size * (0.9 + rand() * 0.5),
          rand() * TAU, (rand() - 0.5) * 0.8, LOW[Math.floor(rand() * 3)]);
      }

      const mesh = new THREE.Mesh(mergeParts(parts), material);
      mesh.castShadow = state.shadows !== 'off';
      mesh.receiveShadow = true;
      terrainGroup.add(mesh);
    });
  }

  /**
   * 可通行地面的自然细节：低矮草簇与小块散石共享一个合并网格。
   *
   * 这些物体不写进服务端 Terrain，所以绝不会挡路、占建造格或改变射线；
   * 出生区、矿区、道路、林道和碰撞山体周围主动留白，视觉也不会误导玩家。
   * 数量按地图面积增长但设有硬上限，整张地图只增加一个 draw call。
   */
  function buildGroundDetail() {
    const detail = state.terrainDetail;
    if (!detail || !state.map) return;
    const mw = state.map.width;
    const mh = state.map.height;
    const area = mw * mh;
    const theme = displayTheme(state.terrain && state.terrain.theme);
    const roads = (state.terrain && state.terrain.roads) || [];
    const resources = state.resources || [];
    const spawns = state.spawnPoints || [];

    let seed = ((Number(state.map.seed) || 1) ^ Math.round(mw * 31) ^
      Math.round(mh * 131)) >>> 0;
    const rand = function () {
      seed = (seed + 0x6d2b79f5) >>> 0;
      let value = seed;
      value = Math.imul(value ^ (value >>> 15), value | 1);
      value ^= value + Math.imul(value ^ (value >>> 7), value | 61);
      return ((value ^ (value >>> 14)) >>> 0) / 4294967296;
    };

    const clearAt = function (x, y, clearance) {
      if (x < 90 || y < 90 || x > mw - 90 || y > mh - 90) return false;
      if (riverDepthAt(x, y) > 0.025 || mountainHeightAt(x, y) > 0.8 ||
          bridgeTrailAt(x, y) > 0.02) return false;
      if (detail.centerFlatRadius > 0 &&
          Math.hypot(x - mw * 0.5, y - mh * 0.5) <
            detail.centerFlatRadius + clearance) return false;
      for (let i = 0; i < spawns.length; i++) {
        if (Math.hypot(x - spawns[i][0], y - spawns[i][1]) <
            detail.spawnFlatRadius + clearance) return false;
      }
      for (let i = 0; i < resources.length; i++) {
        const resource = resources[i];
        if (Math.hypot(x - resource.x, y - resource.y) <
            (resource.radius || 70) + clearance + 35) return false;
      }
      for (let i = 0; i < roads.length; i++) {
        const road = roads[i];
        const safeWidth = (road.width || 100) * 0.5 + clearance + 18;
        if (pointSegmentDistanceSq(x, y, road.x1, road.y1, road.x2, road.y2) <
            safeWidth * safeWidth) return false;
      }
      return true;
    };

    // 三片交叉三角叶组成一簇草：比三棱锥更像叶片，每簇只有 3 个三角形。
    const grassPositions = [];
    const grassNormals = [];
    const grassUvs = [];
    for (let blade = 0; blade < 3; blade++) {
      const angle = blade * Math.PI / 3;
      const dx = Math.cos(angle) * 0.5;
      const dz = Math.sin(angle) * 0.5;
      const nx = -Math.sin(angle);
      const nz = Math.cos(angle);
      grassPositions.push(-dx, 0, -dz, dx, 0, dz, 0, 1, 0);
      grassNormals.push(nx, 0, nz, nx, 0, nz, nx, 0, nz);
      grassUvs.push(0, 0, 1, 0, 0.5, 1);
    }
    const grassGeo = new THREE.BufferGeometry();
    grassGeo.setAttribute('position', new THREE.Float32BufferAttribute(grassPositions, 3));
    grassGeo.setAttribute('normal', new THREE.Float32BufferAttribute(grassNormals, 3));
    grassGeo.setAttribute('uv', new THREE.Float32BufferAttribute(grassUvs, 2));
    let pebbleGeo = new THREE.DodecahedronGeometry(1, 0);
    if (pebbleGeo.index) {
      const indexed = pebbleGeo;
      pebbleGeo = indexed.toNonIndexed();
      indexed.dispose();
    }
    const parts = [];
    const addPart = function (geo, x, y, sx, sy, sz, rotation, tilt, rgb) {
      const matrix = new THREE.Matrix4().makeRotationY(rotation);
      if (tilt) matrix.multiply(new THREE.Matrix4().makeRotationX(tilt));
      matrix.scale(new THREE.Vector3(sx, sy, sz));
      matrix.setPosition(x, groundHeight(x, y) + sy * 0.48, y);
      parts.push({ geo: geo, matrix: matrix, rgb: rgb });
    };

    // 每个采样点长成 1–3 株小草，颜色在主题草色与深草色间变化。
    const grassTarget = Math.min(640,
      Math.round(area / 58000 * detail.grassDensity));
    let acceptedGrass = 0;
    for (let attempt = 0; attempt < grassTarget * 14 &&
         acceptedGrass < grassTarget; attempt++) {
      const cx = 100 + rand() * (mw - 200);
      const cy = 100 + rand() * (mh - 200);
      if (!clearAt(cx, cy, 16)) continue;
      acceptedGrass++;
      const tuftCount = 2 + Math.floor(rand() * 3);
      for (let blade = 0; blade < tuftCount; blade++) {
        const angle = rand() * TAU;
        const distance = rand() * 8;
        const x = cx + Math.cos(angle) * distance;
        const y = cy + Math.sin(angle) * distance;
        const height = 9 + rand() * 9;
        const width = 3.0 + rand() * 2.2;
        const mix = rand();
        const shade = 0.90 + rand() * 0.30;
        const rgb = [0, 1, 2].map(function (channel) {
          return Math.min(1, (theme.grass[channel] * (1 - mix) +
            theme.lush[channel] * mix) * shade);
        });
        addPart(grassGeo, x, y, width, height, width * (0.72 + rand() * 0.35),
          rand() * TAU, (rand() - 0.5) * 0.18, rgb);
      }
    }

    // 散石以小簇出现，尺寸远小于碰撞山岩，让玩家一眼能区分装饰与障碍。
    const rockTarget = Math.min(180,
      Math.round(area / 260000 * detail.rockDensity));
    let acceptedRocks = 0;
    for (let attempt = 0; attempt < rockTarget * 18 &&
         acceptedRocks < rockTarget; attempt++) {
      const cx = 110 + rand() * (mw - 220);
      const cy = 110 + rand() * (mh - 220);
      if (!clearAt(cx, cy, 34)) continue;
      acceptedRocks++;
      const clusterSize = 2 + Math.floor(rand() * 4);
      for (let rock = 0; rock < clusterSize; rock++) {
        const angle = rand() * TAU;
        const distance = 5 + rand() * 26;
        const x = cx + Math.cos(angle) * distance;
        const y = cy + Math.sin(angle) * distance;
        if (!clearAt(x, y, 10)) continue;
        const size = 3.5 + rand() * 7.0;
        const shade = 0.72 + rand() * 0.42;
        const rgb = theme.rock.map(function (channel) {
          return Math.min(1, channel * shade);
        });
        addPart(pebbleGeo, x, y, size * (0.85 + rand() * 0.45),
          size * (0.50 + rand() * 0.42), size * (0.80 + rand() * 0.45),
          rand() * TAU, (rand() - 0.5) * 0.55, rgb);
      }
    }

    state.groundDetailParts = parts.length;
    if (parts.length) {
      const merged = mergeParts(parts);
      const mesh = new THREE.Mesh(merged, applyFogMask(new THREE.MeshLambertMaterial({
        vertexColors: true, flatShading: true, side: THREE.DoubleSide
      })));
      mesh.name = 'ground-detail';
      mesh.castShadow = false;
      mesh.receiveShadow = true;
      mesh.frustumCulled = false;
      terrainGroup.add(mesh);
    }
    grassGeo.dispose();
    pebbleGeo.dispose();
  }

  /* -------------------- 矿脉 -------------------- */

  let oreGroup = null;
  const oreMeshes = new Map();
  /** 石英、母岩与天然金脉的实拍式材质；矿簇网格数量保持不变。 */
  function makeOreVeinTexture() {
    return loadSharedTexture('/assets/textures/ore-real.webp', true, 4);
  }

  function buildOreField() {
    if (oreGroup) worldRoot.remove(oreGroup);
    oreGroup = new THREE.Group();
    worldRoot.add(oreGroup);
    oreMeshes.clear();
    if (!state.resources) return;

    // 真实石英/母岩材质只保留轻微内发光，矿区识别仍由地面辉光环承担。
    const crystalMat = new THREE.MeshStandardMaterial({
      color: 0xd8cdb8, emissive: 0x8a5a18, emissiveIntensity: 0.62,
      roughness: 0.48, metalness: 0.18, vertexColors: false,
      map: makeOreVeinTexture()
    });
    const crystalGeo = new THREE.ConeGeometry(1, 1, 5);
    // 地面辉光环：让矿脉在绿色草皮上有一个「发光底座」，拉远也不会消失。
    // 每处矿用自己的轻量材质实例，以便开采跨档时独立换色和缩小。
    const discGeo = new THREE.CircleGeometry(1, 18).rotateX(-Math.PI / 2);
    const guardRingGeo = new THREE.RingGeometry(0.82, 1.0, 32).rotateX(-Math.PI / 2);
    const guardRingMat = new THREE.MeshBasicMaterial({
      color: 0xff3f2f, transparent: true, opacity: 0.82,
      depthWrite: false, fog: false, side: THREE.DoubleSide
    });
    state.resources.forEach(function (res) {
      const cluster = new THREE.Group();
      cluster.position.set(res.x, groundHeight(res.x, res.y), res.y);
      cluster.userData.resourceId = res.id;
      const initialTier = oreReserveTier(res.amount);
      const maxTier = oreReserveTier(Math.max(res.amount || 0, res.maxAmount || 0));

      // 储量越高，辉光占地越大、颜色越亮；这和小地图图例使用同一档位。
      const disc = new THREE.Mesh(discGeo, new THREE.MeshBasicMaterial({
        color: initialTier.color, transparent: true, opacity: 0.30,
        depthWrite: false, fog: false, side: THREE.DoubleSide
      }));
      const initialDiscRadius = res.radius * (0.62 + initialTier.level * 0.13);
      disc.scale.set(initialDiscRadius, 1, initialDiscRadius);
      disc.position.y = 2.6;
      disc.renderOrder = 2;
      cluster.userData.disc = disc;
      cluster.add(disc);

      if (res.public) {
        const guardRing = new THREE.Mesh(guardRingGeo, guardRingMat);
        guardRing.scale.set(res.radius * 1.24, 1, res.radius * 1.24);
        guardRing.position.y = 3.0;
        guardRing.renderOrder = 3;
        guardRing.visible = !!res.guarded;
        cluster.userData.guardRing = guardRing;
        cluster.add(guardRing);
      }

      let seed = 0;
      for (let i = 0; i < res.id.length; i++) seed = (seed * 31 + res.id.charCodeAt(i)) >>> 0;
      const rand = function () {
        seed = (seed * 1103515245 + 12345) & 0x7fffffff;
        return seed / 0x7fffffff;
      };
      // 一处矿脉始终只有一个 InstancedMesh draw call。巨矿虽然有更多晶柱，
      // 也不会像旧版“每根晶柱一个 Mesh”那样按储量增加绘制调用。
      const count = maxTier.crystalCount;
      const crystals = new THREE.InstancedMesh(crystalGeo, crystalMat, count);
      const oreMatrix = new THREE.Matrix4();
      const orePosition = new THREE.Vector3();
      const oreRotation = new THREE.Quaternion();
      const oreScale = new THREE.Vector3();
      const oreEuler = new THREE.Euler();
      for (let i = 0; i < count; i++) {
        const a = rand() * TAU;
        // 先写入的晶柱更靠近中心；开采后降低 instance count 时，留下的矿簇
        // 会自然向中心收紧，而不是随机缺一块、视觉上仍占满原来面积。
        const spread = 0.38 + 0.62 * ((i + 1) / count);
        const rr = Math.sqrt(rand()) * res.radius * maxTier.footprint * spread;
        const h = (11 + rand() * 22) * maxTier.height;
        const w = (3.6 + rand() * 3.6) * (0.92 + maxTier.level * 0.035);
        orePosition.set(Math.cos(a) * rr, h / 2 + 2, Math.sin(a) * rr);
        oreEuler.set((rand() - 0.5) * 0.16, rand() * TAU, (rand() - 0.5) * 0.16);
        oreRotation.setFromEuler(oreEuler);
        oreScale.set(w, h, w);
        oreMatrix.compose(orePosition, oreRotation, oreScale);
        crystals.setMatrixAt(i, oreMatrix);
      }
      crystals.count = Math.min(count, initialTier.crystalCount);
      crystals.instanceMatrix.needsUpdate = true;
      crystals.castShadow = false;
      crystals.receiveShadow = true;
      crystals.frustumCulled = false;
      cluster.userData.crystalMesh = crystals;
      cluster.userData.crystalCapacity = count;
      cluster.userData.maxTier = maxTier;
      cluster.add(crystals);
      oreGroup.add(cluster);
      oreMeshes.set(res.id, cluster);
    });
  }

  function updateOre(ore, time) {
    if (!ore) return;
    for (let i = 0; i < ore.length; i++) {
      const cluster = oreMeshes.get(ore[i][0]);
      if (!cluster) continue;
      const res = state.resourceById && state.resourceById.get(ore[i][0]);
      const amount = Math.max(0, Number(ore[i][1]) || 0);
      if (res) {
        res.amount = amount;
        res.guarded = !!ore[i][2];
      }
      const tier = oreReserveTier(amount);
      const live = amount > 0.05;
      cluster.visible = live;
      const poorFraction = tier.id === 'poor' ? Math.max(0.10, amount / 8000) : 1;
      const crystals = cluster.userData.crystalMesh;
      if (crystals) {
        const wanted = tier.id === 'poor' ?
          Math.max(1, Math.ceil(tier.crystalCount * poorFraction)) : tier.crystalCount;
        crystals.count = live ? Math.min(cluster.userData.crystalCapacity, wanted) : 0;
        const maxTier = cluster.userData.maxTier || tier;
        crystals.scale.set(
          tier.footprint / maxTier.footprint,
          tier.height / maxTier.height,
          tier.footprint / maxTier.footprint
        );
      }
      const disc = cluster.userData.disc;
      if (disc) {
        const poorScale = tier.id === 'poor' ? 0.64 + poorFraction * 0.36 : 1;
        const discRadius = (res ? res.radius : 48) *
          (0.62 + tier.level * 0.13) * poorScale;
        disc.scale.set(discRadius, 1, discRadius);
        disc.material.color.set(tier.color);
        const pulse = 0.84 + 0.16 * Math.sin((time * 0.003 + ore[i][0].charCodeAt(0)) * 1.7);
        disc.material.opacity = live ? (0.20 + tier.level * 0.035) * pulse *
          (tier.id === 'poor' ? 0.45 + poorFraction * 0.55 : 1) : 0;
      }
      if (cluster.userData.guardRing) {
        cluster.userData.guardRing.visible = !!ore[i][2] && live;
        cluster.userData.guardRing.material.opacity =
          0.62 + 0.22 * Math.sin(time * 0.006 + i);
      }
    }
  }

  /* -------------------- 补给箱 -------------------- */

  let crateMesh = null;

  function ensureCrateMesh(needed) {
    if (crateMesh && crateMesh.instanceMatrix.count >= needed) return crateMesh;
    if (crateMesh) { worldRoot.remove(crateMesh); crateMesh.dispose(); }
    const geo = new THREE.BoxGeometry(1, 1, 1);
    const mat = new THREE.MeshBasicMaterial({
      vertexColors: true, transparent: true, opacity: 0.9,
      depthWrite: false, fog: false
    });
    crateMesh = new THREE.InstancedMesh(geo, mat, Math.max(8, Math.ceil(needed * 1.5)));
    crateMesh.instanceMatrix.setUsage(THREE.DynamicDrawUsage);
    crateMesh.frustumCulled = false;
    crateMesh.renderOrder = 6;
    crateMesh.count = 0;
    worldRoot.add(crateMesh);
    return crateMesh;
  }

  function updateCrates(game, time) {
    const crates = game.crates || [];
    if (!crates.length) {
      if (crateMesh && crateMesh.count) crateMesh.count = 0;
      return;
    }
    const m = ensureCrateMesh(crates.length);
    const spin = time * 0.0018;
    let count = 0;
    for (let i = 0; i < crates.length; i++) {
      const c = crates[i];
      if (!inViewportBounds(c.x, c.y)) continue;
      const gy = groundHeight(c.x, c.y);
      quat.setFromAxisAngle(upAxis, spin + i);
      vecAux.set(c.x, gy + 26 + Math.sin(time * 0.004 + i) * 6, c.y);
      vecScale.set(22, 22, 22);
      m.setMatrixAt(count, matrix.compose(vecAux, quat, vecScale));
      tmpColor.set(c.kind === 'cash' ? '#ffd700' : c.kind === 'heal' ? '#7dff5f' : '#ff3b3b');
      m.setColorAt(count, tmpColor);
      count++;
    }
    m.count = count;
    m.instanceMatrix.needsUpdate = true;
    if (m.instanceColor) m.instanceColor.needsUpdate = true;
  }

  /* -------------------- 轨道打击落点标圈 -------------------- */
  const STRIKE_RADIUS_FALLBACK = 180; // 旧快照缺 radius 时退回玩家超武半径
  let strikeMesh = null;

  function ensureStrikeMesh(capacity) {
    capacity = Math.max(8, capacity);
    if (strikeMesh && strikeMesh.userData.cap >= capacity) return strikeMesh;
    if (strikeMesh) { worldRoot.remove(strikeMesh); strikeMesh.geometry.dispose(); strikeMesh.material.dispose(); }
    const geo = new THREE.RingGeometry(0.86, 1.0, 48).rotateX(-Math.PI / 2);
    geo.setAttribute('aAlpha', new THREE.InstancedBufferAttribute(new Float32Array(capacity), 1));
    geo.setAttribute('instanceColorAttr',
      new THREE.InstancedBufferAttribute(new Float32Array(capacity * 3), 3));
    const mat = new THREE.ShaderMaterial({
      transparent: true, depthWrite: false, fog: false, side: THREE.DoubleSide,
      blending: THREE.AdditiveBlending, uniforms: {},
      vertexShader: [
        'attribute float aAlpha;', 'attribute vec3 instanceColorAttr;',
        'varying float vAlpha;', 'varying vec3 vColor;',
        'void main(){ vAlpha=aAlpha; vColor=instanceColorAttr;',
        ' gl_Position=projectionMatrix*modelViewMatrix*instanceMatrix*vec4(position,1.0); }'
      ].join('\n'),
      fragmentShader: [
        'varying float vAlpha;', 'varying vec3 vColor;',
        'void main(){ if(vAlpha<=0.004) discard; gl_FragColor=vec4(vColor,vAlpha); }'
      ].join('\n')
    });
    const mesh = new THREE.InstancedMesh(geo, mat, capacity);
    mesh.instanceMatrix.setUsage(THREE.DynamicDrawUsage);
    mesh.frustumCulled = false;
    mesh.renderOrder = 5;
    mesh.count = 0;
    mesh.userData.cap = capacity;
    worldRoot.add(mesh);
    strikeMesh = mesh;
    return mesh;
  }

  function updateStrikes(game, time) {
    const strikes = (game && game.strikes) || [];
    if (!strikes.length) {
      if (strikeMesh && strikeMesh.count) strikeMesh.count = 0;
      return;
    }
    const m = ensureStrikeMesh(strikes.length * 2 + 4);
    const alphas = m.geometry.attributes.aAlpha;
    const colors = m.geometry.attributes.instanceColorAttr;
    let idx = 0;
    for (let i = 0; i < strikes.length; i++) {
      const s = strikes[i];
      const warning = s.warnUntil > 0;
      const gy = groundHeight(s.x, s.y) + 5;
      const rot = time * 0.0009 * (warning ? 1 : 2.4);
      let r, g, b, aOut, aIn;
      if (warning) {
        const pulse = 0.5 + 0.5 * Math.sin(time * 0.012 + i);
        r = 1.0; g = 0.78; b = 0.25;
        aOut = 0.35 + 0.4 * pulse;
        aIn = 0.5 + 0.4 * pulse;
      } else {
        const flick = 0.6 + 0.4 * Math.sin(time * 0.03 + i * 1.7);
        r = 1.0; g = 0.2; b = 0.16;
        aOut = 0.5 * flick + 0.25;
        aIn = 0.8 * flick + 0.2;
      }
      // 外圈：危险区。半径跟这发走，轨道天降是 5 倍圈。
      const ringR = (s.radius > 0) ? s.radius : STRIKE_RADIUS_FALLBACK;
      quat.setFromAxisAngle(upAxis, rot);
      matrix.compose(vecAux.set(s.x, gy, s.y), quat, vecScale.set(ringR, 1, ringR));
      m.setMatrixAt(idx, matrix);
      alphas.array[idx] = aOut;
      colors.array[idx * 3] = r; colors.array[idx * 3 + 1] = g; colors.array[idx * 3 + 2] = b;
      idx++;
      // 中心标点：小亮环
      quat.setFromAxisAngle(upAxis, -rot * 1.5);
      matrix.compose(vecAux.set(s.x, gy + 0.5, s.y), quat, vecScale.set(18, 1, 18));
      m.setMatrixAt(idx, matrix);
      alphas.array[idx] = aIn;
      colors.array[idx * 3] = r; colors.array[idx * 3 + 1] = g; colors.array[idx * 3 + 2] = b;
      idx++;
    }
    m.count = idx;
    m.instanceMatrix.needsUpdate = true;
    alphas.needsUpdate = true;
    colors.needsUpdate = true;
  }

  /* -------------------- 集结点旗标 -------------------- */

  let rallyMesh = null;
  let lastRallyGame = null;
  const rallyGeo = (function () {
    const pole = new THREE.CylinderGeometry(0.8, 1.2, 26, 6);
    const panel = new THREE.BoxGeometry(0.35, 10, 6.5);
    return mergeParts([
      { geo: pole, matrix: new THREE.Matrix4().makeTranslation(0, 13, 0) },
      { geo: panel, matrix: new THREE.Matrix4().makeTranslation(5.5, 23.5, 0) }
    ]);
  })();

  function ensureRallyMesh(capacity) {
    capacity = Math.max(8, capacity);
    if (rallyMesh && rallyMesh.userData.cap >= capacity) return rallyMesh;
    if (rallyMesh) { worldRoot.remove(rallyMesh); rallyMesh.dispose(); }
    const mat = new THREE.MeshBasicMaterial({
      color: 0xffffff, fog: false, transparent: true, opacity: 0.9, depthWrite: false
    });
    rallyMesh = new THREE.InstancedMesh(rallyGeo, mat, capacity);
    rallyMesh.instanceMatrix.setUsage(THREE.DynamicDrawUsage);
    rallyMesh.frustumCulled = false;
    rallyMesh.renderOrder = 7;
    rallyMesh.count = 0;
    rallyMesh.userData.cap = capacity;
    worldRoot.add(rallyMesh);
    return rallyMesh;
  }

  function updateRallyFlags(game) {
    if (game === lastRallyGame) return;
    lastRallyGame = game;
    const structures = game && game.structures || [];
    let count = 0;
    for (let i = 0; i < structures.length; i++) {
      if (structures[i].rally) count++;
    }
    if (!count) {
      if (rallyMesh && rallyMesh.count) rallyMesh.count = 0;
      return;
    }
    const m = ensureRallyMesh(count + 2);
    let idx = 0;
    for (let i = 0; i < structures.length; i++) {
      const s = structures[i];
      if (!s.rally) continue;
      const gy = groundHeight(s.rally[0], s.rally[1]) + 2;
      matrix.compose(
        vecAux.set(s.rally[0], gy, s.rally[1]),
        quatIdentity,
        vecScale.set(1, 1, 1));
      m.setMatrixAt(idx, matrix);
      const col = (state.palette && state.palette.get(s.owner)) || '#42d9ff';
      tmpColor.set(col);
      m.setColorAt(idx, tmpColor);
      idx++;
    }
    m.count = idx;
    m.instanceMatrix.needsUpdate = true;
    if (m.instanceColor) m.instanceColor.needsUpdate = true;
  }

  /* -------------------- 永久探索黑幕 -------------------- */

  let fogCanvas = null;
  let fogCtx = null;
  let exploredCanvas = null;
  let exploredCtx = null;
  let fogGradientCanvas = null;
  let fogTexture = null;
  let fogPlane = null;
  const fogMapSize = new THREE.Vector2(1, 1);
  const fogMaskedShaders = [];
  const waterShaders = [];

  // 探索覆盖度粗网格。探索黑幕是永久的（探开就不再变黑），所以一个视野圆
  // 只要整个落在「已经完全探开」的区域里，再画一遍连一个像素都不会变。
  // 大部分时间部队都在自家已探开的地盘上机动，靠这张网格就能整帧跳过
  // 全画布填充、全画布合成和整张贴图上传。
  const FOG_CELL = 8;          // 覆盖网格格子边长（迷雾画布像素）
  const FOG_CORE = 0.82;       // 渐变里 alpha 已达 1 的实心区占半径的比例
  let fogCover = null;         // Uint8Array，1 = 该格已完全探开
  let fogCoverW = 0;
  let fogCoverH = 0;
  let fogApplied = null;       // 已画过的视野圆（量化后），去重用
  let fogFullRepaint = true;   // 画布刚重建，需要整张合成一次
  // 探索黑幕是永久揭开的静态信息，不参与战斗判定（敌方单位可见性由服务端
  // 视野决定，走的是另一条路）。所以没必要每个快照都重新合成并整张重传：
  // 攒够间隔再一次性处理累积的脏矩形，晚 100 多毫秒揭开黑幕看不出来。
  const FOG_UPLOAD_INTERVAL = 200;
  let fogLastUpload = 0;
  let fogPx0 = Infinity, fogPy0 = Infinity, fogPx1 = -Infinity, fogPy1 = -Infinity;

  function buildFogPlane() {
    const fw = Math.max(2, Math.ceil(state.map.width / state.fogScale));
    const fh = Math.max(2, Math.ceil(state.map.height / state.fogScale));
    fogMapSize.set(state.map.width, state.map.height);
    const previousExplored = exploredCanvas;

    fogCanvas = document.createElement('canvas');
    fogCanvas.width = fw; fogCanvas.height = fh;
    fogCtx = fogCanvas.getContext('2d');

    exploredCanvas = document.createElement('canvas');
    exploredCanvas.width = fw; exploredCanvas.height = fh;
    exploredCtx = exploredCanvas.getContext('2d');
    exploredCtx.clearRect(0, 0, fw, fh);

    // 覆盖网格跟着画布尺寸重建。这里一律从「什么都没探开」重新算起：
    // 保守方向是多画几次，绝不会漏掉真正该探开的地方。
    fogCoverW = Math.ceil(fw / FOG_CELL);
    fogCoverH = Math.ceil(fh / FOG_CELL);
    fogCover = new Uint8Array(fogCoverW * fogCoverH);
    fogApplied = new Set();
    fogFullRepaint = true;
    fogLastUpload = 0;
    fogPx0 = Infinity; fogPy0 = Infinity; fogPx1 = -Infinity; fogPy1 = -Infinity;
    // 调整黑幕精度时保留已经探开的区域，不能因为改了一项画质设置重新变黑。
    if (previousExplored) {
      exploredCtx.drawImage(previousExplored, 0, 0, fw, fh);
    }

    fogGradientCanvas = document.createElement('canvas');
    fogGradientCanvas.width = 128;
    fogGradientCanvas.height = 128;
    const gc = fogGradientCanvas.getContext('2d');
    const grad = gc.createRadialGradient(64, 64, 64 * 0.55, 64, 64, 64);
    grad.addColorStop(0, 'rgba(255,255,255,1)');
    grad.addColorStop(0.82, 'rgba(255,255,255,1)');
    grad.addColorStop(1, 'rgba(255,255,255,0)');
    gc.fillStyle = grad;
    gc.fillRect(0, 0, 128, 128);

    if (fogTexture) fogTexture.dispose();
    fogTexture = new THREE.CanvasTexture(fogCanvas);
    for (let i = 0; i < waterShaders.length; i++) {
      waterShaders[i].uniforms.uFogMask.value = fogTexture;
    }
    // 已经编译过的材质要换上新贴图，否则改黑幕精度后地形会停在旧遮罩上
    for (let i = 0; i < fogMaskedShaders.length; i++) {
      fogMaskedShaders[i].uniforms.uFogMask.value = fogTexture;
    }
    fogTexture.minFilter = THREE.LinearFilter;
    fogTexture.magFilter = THREE.LinearFilter;
    fogTexture.generateMipmaps = false;

    // 不再画迷雾平面：遮罩已经注入到各地形材质里，再叠一层会二次压暗，
    // 而且平面永远盖不住比它高的山体。
    if (fogPlane) {
      worldRoot.remove(fogPlane);
      fogPlane.geometry.dispose();
      fogPlane.material.dispose();
      fogPlane = null;
    }
  }

  // 探索源（客户端自行推导，服务端只发一次视距表）
  const visionSources = [];

  function collectVision(game) {
    visionSources.length = 0;
    if (!state.sight) return;
    const us = state.sight.units;
    const ss = state.sight.structures;
    for (let i = 0; i < game.units.length; i++) {
      const u = game.units[i];
      if (state.friendly(u.owner)) {
        visionSources.push(u.x, u.y, us[u.kind] || 350);
      }
    }
    for (let i = 0; i < game.structures.length; i++) {
      const s = game.structures[i];
      if (state.friendly(s.owner)) {
        visionSources.push(s.x, s.y, (ss[s.kind] || 350) * (s.active ? 1 : 0.45));
      }
    }
  }

  /**
   * 这个视野圆还可能探开新东西吗？
   *
   * 两道筛子：位置与半径量化后完全相同的圆已经画过（原地不动的建筑、驻守的
   * 部队每帧都会送来同一个圆）；或者它覆盖到的每一格都已经完全探开。
   * 两者都是「再画一遍也不会改变任何像素」，可以安全跳过。
   *
   * 判第二道筛子时只能看真正与圆相交的格子。用包围盒会永远判成「有新东西」
   * ——盒子四角落在圆外，那里几乎不可能被标记成已探开，筛子等于没装。
   */
  function fogCircleAdds(cx, cy, r) {
    const key = (cx | 0) + '|' + (cy | 0) + '|' + (r | 0);
    if (fogApplied.has(key)) return false;
    // 集合无限膨胀没有意义；到上限就清空，代价只是每个圆各多画一次。
    if (fogApplied.size > 20000) fogApplied.clear();
    fogApplied.add(key);
    if (!fogCover) return true;
    const rSq = r * r;
    const gx0 = Math.max(0, Math.floor((cx - r) / FOG_CELL));
    const gy0 = Math.max(0, Math.floor((cy - r) / FOG_CELL));
    const gx1 = Math.min(fogCoverW - 1, Math.floor((cx + r) / FOG_CELL));
    const gy1 = Math.min(fogCoverH - 1, Math.floor((cy + r) / FOG_CELL));
    for (let gy = gy0; gy <= gy1; gy++) {
      const row = gy * fogCoverW;
      const ty = gy * FOG_CELL;
      const ny = cy < ty ? ty : (cy > ty + FOG_CELL ? ty + FOG_CELL : cy);
      const nySq = (ny - cy) * (ny - cy);
      if (nySq > rSq) continue;
      for (let gx = gx0; gx <= gx1; gx++) {
        const lx = gx * FOG_CELL;
        const nx = cx < lx ? lx : (cx > lx + FOG_CELL ? lx + FOG_CELL : cx);
        if ((nx - cx) * (nx - cx) + nySq > rSq) continue;
        if (!fogCover[row + gx]) return true;
      }
    }
    return false;
  }

  /**
   * 把这个视野圆实心区完全盖住的格子标记成已探开。
   *
   * 只认 0.82r 以内 —— 渐变在那之外开始衰减，alpha 到不了 1。而且要求整格
   * （四个角）都在实心区里才标记：宁可漏标多画一次，也不能错标，错标会让
   * 真正该探开的地方永远留一圈没擦干净的黑边。
   */
  function fogMarkCovered(cx, cy, r) {
    if (!fogCover) return;
    const core = r * FOG_CORE;
    const coreSq = core * core;
    const gx0 = Math.max(0, Math.floor((cx - core) / FOG_CELL));
    const gy0 = Math.max(0, Math.floor((cy - core) / FOG_CELL));
    const gx1 = Math.min(fogCoverW - 1, Math.floor((cx + core) / FOG_CELL));
    const gy1 = Math.min(fogCoverH - 1, Math.floor((cy + core) / FOG_CELL));
    for (let gy = gy0; gy <= gy1; gy++) {
      const row = gy * fogCoverW;
      const ty = gy * FOG_CELL;
      const fy = Math.max(Math.abs(ty - cy), Math.abs(ty + FOG_CELL - cy));
      const fySq = fy * fy;
      if (fySq > coreSq) continue;
      for (let gx = gx0; gx <= gx1; gx++) {
        if (fogCover[row + gx]) continue;
        const lx = gx * FOG_CELL;
        const fx = Math.max(Math.abs(lx - cx), Math.abs(lx + FOG_CELL - cx));
        if (fx * fx + fySq <= coreSq) fogCover[row + gx] = 1;
      }
    }
  }

  function updateFog() {
    if (!fogCtx) return;
    const fw = fogCanvas.width;
    const fh = fogCanvas.height;
    const inv = 1 / state.fogScale;

    // 红警 2 式黑幕：把每次走到的视野永久画进 exploredCanvas，之后不会
    // 因单位离开而重新压暗。边缘使用软渐变，探图边界不会像圆规画出来。
    // 只画真正可能探开新地方的圆，并把它们的包围盒并进累积脏矩形。
    // 画进 exploredCanvas 这一步每帧都做：它很便宜，而且要保证不丢探索。
    exploredCtx.globalCompositeOperation = 'source-over';
    for (let i = 0; i < visionSources.length; i += 3) {
      const cx = visionSources[i] * inv;
      const cy = visionSources[i + 1] * inv;
      const r = visionSources[i + 2] * inv;
      if (!fogCircleAdds(cx, cy, r)) continue;
      const d = r * 2;
      exploredCtx.drawImage(fogGradientCanvas, cx - r, cy - r, d, d);
      fogMarkCovered(cx, cy, r);
      if (cx - r < fogPx0) fogPx0 = cx - r;
      if (cy - r < fogPy0) fogPy0 = cy - r;
      if (cx + r > fogPx1) fogPx1 = cx + r;
      if (cy + r > fogPy1) fogPy1 = cy + r;
    }

    // 探索黑幕一个像素都没变：不必重新合成，更不必把整张贴图重传一遍。
    // 部队在已探开的地盘上机动时，绝大多数帧都会走到这里。
    if (!fogFullRepaint && fogPx1 < fogPx0) return;
    const nowMs = performance.now();
    // 还没到合成间隔：脏矩形留着，下一个快照再一起处理。
    if (!fogFullRepaint && nowMs - fogLastUpload < FOG_UPLOAD_INTERVAL) return;
    fogLastUpload = nowMs;

    let x0 = 0, y0 = 0, x1 = fw, y1 = fh;
    if (fogFullRepaint) {
      fogFullRepaint = false;
    } else {
      x0 = Math.max(0, Math.floor(fogPx0));
      y0 = Math.max(0, Math.floor(fogPy0));
      x1 = Math.min(fw, Math.ceil(fogPx1));
      y1 = Math.min(fh, Math.ceil(fogPy1));
    }
    fogPx0 = Infinity; fogPy0 = Infinity; fogPx1 = -Infinity; fogPy1 = -Infinity;
    if (x1 <= x0 || y1 <= y0) return;
    const w = x1 - x0;
    const h = y1 - y0;

    // 只剩“未探索 / 已探索”两种状态：已探索区域完全清除黑幕，不再有
    // 当前视野之外的二次灰雾。敌方移动单位仍按服务端实时视野规则隐藏。
    // 先 clear 再 fill：脏矩形是反复重画的，直接 source-over 叠会让这一块
    // 越描越黑，和画布其余部分割裂出可见的接缝。
    fogCtx.globalCompositeOperation = 'source-over';
    fogCtx.clearRect(x0, y0, w, h);
    fogCtx.fillStyle = 'rgba(3, 7, 9, 0.94)';
    fogCtx.fillRect(x0, y0, w, h);
    fogCtx.globalCompositeOperation = 'destination-out';
    fogCtx.drawImage(exploredCanvas, x0, y0, w, h, x0, y0, w, h);
    fogCtx.globalCompositeOperation = 'source-over';
    fogTexture.needsUpdate = true;
  }

  function isVisible(x, y) {
    for (let i = 0; i < visionSources.length; i += 3) {
      const dx = visionSources[i] - x;
      const dy = visionSources[i + 1] - y;
      const r = visionSources[i + 2];
      if (dx * dx + dy * dy <= r * r) return true;
    }
    return false;
  }

  /* -------------------- 单位（实例化） -------------------- */

  // 车体走受光材质；发光件走不受光材质，顶点系数 > 1，因此会被后处理的
  // 亮度提取捕捉到，形成灯带与传感器的光晕。
  const unitMetalMaterial = applyEmissiveByVertexColor(
    new THREE.MeshLambertMaterial({ vertexColors: true }), 'metal');
  const unitStoneMaterial = applyEmissiveByVertexColor(
    new THREE.MeshLambertMaterial({ vertexColors: true }), 'stone');
  const unitClothMaterial = applyEmissiveByVertexColor(
    new THREE.MeshLambertMaterial({ vertexColors: true }), 'cloth');
  const unitHideMaterial = applyEmissiveByVertexColor(
    new THREE.MeshLambertMaterial({ vertexColors: true }), 'hide');
  const unitPools = new Map();     // kind -> { mesh, glow, simple, capacity }
  const shadowGeo = new THREE.CircleGeometry(1, 12).rotateX(-Math.PI / 2);

  function makeUnitShadowTexture() {
    const canvas = document.createElement('canvas');
    canvas.width = canvas.height = 64;
    const ctx = canvas.getContext('2d');
    const gradient = ctx.createRadialGradient(32, 32, 2, 32, 32, 31);
    gradient.addColorStop(0.0, 'rgba(0,0,0,0.82)');
    gradient.addColorStop(0.42, 'rgba(0,0,0,0.46)');
    gradient.addColorStop(0.78, 'rgba(0,0,0,0.13)');
    gradient.addColorStop(1.0, 'rgba(0,0,0,0)');
    ctx.fillStyle = gradient;
    ctx.fillRect(0, 0, 64, 64);
    const texture = new THREE.CanvasTexture(canvas);
    texture.generateMipmaps = true;
    texture.minFilter = THREE.LinearMipmapLinearFilter;
    return texture;
  }
  const shadowMaterial = new THREE.MeshBasicMaterial({
    color: 0xffffff, map: makeUnitShadowTexture(), transparent: true,
    opacity: 0.72, depthWrite: false, fog: false
  });
  let shadowMesh = null;

  // 几何体按兵种缓存，所有实例共用
  const UNIT_GEOMETRY_CACHE = new Map();

  /**
   * 远景模型仍保留每个兵种最醒目的轮廓：步兵武器、坦克炮管、矿斗、
   * 攻城炮长身管和 V3 导弹。它们只有 3~5 个零件，三角数很低，但不会再
   * 出现所有兵种都是同一只小盒子的情况。
   */
  function simpleUnitParts(kind) {
    // 远处只有几像素大，保留 12 面方盒即可；近景才使用倒角轮廓。
    const box = plainBox;
    const taperedBox = plainTaperedBox;
    const infantry = [
      taperedBox(7.2, 5.2, 5.6, 4.2, 8.4, 0.2, 8.0, 0, MAT.olive),
      box(4.2, 2.2, 8.6, -0.2, 11.2, 0, 0.95),
      sph(2.6, 6, 0.4, 13.6, 0, MAT.sandArmor),
      box(2.2, 2.2, 4.6, 1.0, 9.6, 4.2, MAT.olive),
      box(2.2, 2.2, 4.6, 1.0, 9.6, -4.2, MAT.olive)
    ];
    if (kind === 'rifle') {
      return infantry.concat([box(12, 1.5, 1.5, 5.2, 8.4, -3.0, MAT.gunmetal)]);
    }
    if (kind === 'rocket') {
      return infantry.concat([cyl(2.2, 2.2, 14, 6, 4, 10, 1.5, MAT.olive, ROT_Z90)]);
    }
    if (kind === 'sniper') {
      return infantry.concat([box(17, 1.1, 1.1, 7, 10, 1.6, MAT.gunmetal)]);
    }

    const hull = function (length, width, height) {
      return [
        taperedBox(length, width, length * 0.86, width * 0.78,
          height, 0, height * 0.5 + 3, 0, 0.86),
        box(length, 4.2, width + 2, 0, 3, 0, MAT.track)
      ];
    };
    if (kind === 'tank') {
      return hull(32, 20, 8).concat([
        taperedBox(16, 14, 11, 9, 7, -1, 15, 0, 1.0),
        cyl(1.7, 1.7, 23, 6, 14, 15, 0, MAT.gunmetal, ROT_Z90)
      ]);
    }
    if (kind === 'scout') {
      return hull(27, 14, 6).concat([
        taperedBox(10, 9, 7, 7, 5, -1, 13, 0, 1.05),
        cyl(3, 3, 0.8, 8, -6, 17, 0, GLOW_HOT)
      ]);
    }
    if (kind === 'harvester') {
      return hull(35, 24, 9).concat([
        taperedBox(20, 23, 16, 19, 15, -8, 19, 0, MAT.rust),
        sph(6, 6, -7, 29, 0, MAT.oreGlow),
        taperedBox(13, 17, 10, 13, 9, 10, 18, 0, 0.82),
        cyl(6.5, 6.5, 25, 8, 21, 8.5, 0, MAT.warnYellow, ROT_X90)
      ]);
    }
    if (kind === 'artillery') {
      return hull(34, 22, 8).concat([
        taperedBox(15, 16, 11, 12, 6, -6, 15, 0, 0.95),
        cyl(2.3, 2.6, 34, 6, 14, 22, 0, MAT.gunmetal,
          new THREE.Matrix4().makeRotationZ(Math.PI / 2 - 0.34))
      ]);
    }
    if (kind === 'tank_destroyer') {
      return hull(33, 19, 7).concat([
        taperedBox(22, 15, 14, 10, 7, -2, 13, 0, 1.0),
        cyl(1.4, 1.6, 31, 6, 18, 14, 0, MAT.gunmetal, ROT_Z90)
      ]);
    }
    if (kind === 'v3') {
      return hull(36, 25, 8).concat([
        box(18, 4, 20, 0, 11, 0, 0.9),
        cyl(3.2, 3.6, 34, 7, 1, 30, 0, MAT.gunmetal),
        cyl(3.2, 0.8, 8, 7, 1, 51, 0, MAT.warnYellow)
      ]);
    }
    if (kind === 'mcv') {
      return hull(48, 30, 14).concat([
        taperedBox(30, 27, 24, 22, 16, -5, 25, 0, 1.0),
        box(14, 13, 18, -7, 39, 0, MAT.steel),
        taperedBox(15, 20, 11, 16, 11, 16, 25, 0, 0.9),
        box(32, 10, 3.2, -4, 25, 17.5, 0.92),
        box(32, 10, 3.2, -4, 25, -17.5, 0.92),
        box(3, 20, 3, -14, 50, 0, GLOW_HOT)
      ]);
    }
    if (kind === 'overlord') {
      return hull(40, 24, 10).concat([
        taperedBox(22, 19, 18, 15, 8, 2, 16, 0, 1.0),
        cyl(1.6, 1.9, 24, 8, 14, 16, 3.6, MAT.gunmetal, ROT_Z90),
        cyl(1.6, 1.9, 24, 8, 14, 16, -3.6, MAT.gunmetal, ROT_Z90)
      ]);
    }
    if (kind === 'prism') {
      return hull(32, 18, 8).concat([
        taperedBox(16, 14, 13, 11, 7, -1, 15, 0, 1.0),
        box(2.2, 14, 2.2, 4, 22, 0, MAT.gunmetal),
        sph(2.2, 6, 4, 32, 0, MAT.prismGlow)
      ]);
    }
    if (kind === 'bomb_truck') {
      return [
        taperedBox(30, 16, 24, 14, 7.2, -1, 8.2, 0, 0.92),
        taperedBox(12, 14, 10, 12, 8.0, 10, 13.0, 0, 0.78),
        cyl(3.6, 3.6, 7.2, 8, -4, 16.2, 3.2, MAT.rust),
        cyl(3.6, 3.6, 7.2, 8, -4, 16.2, -3.2, MAT.rust),
        sph(1.2, 6, -4, 20.4, 0, GLOW_HOT)
      ];
    }
    if (kind === 'tesla') {
      return infantry.concat([
        box(4.4, 2.6, 10.6, -0.2, 11.2, 0, 0.5),
        sph(1.5, 5, -4.4, 18, 2.2, MAT.teslaArc),
        sph(1.5, 5, -4.4, 18, -2.2, MAT.teslaArc),
        box(9.0, 1.6, 1.6, 4.6, 8.4, 1.9, MAT.gunmetal)
      ]);
    }
    if (kind === 'dog') {
      // 远景 LOD：低矮长身 + 头块 + 四条腿，认得出是四足兽即可
      const quad = [
        box(16, 6, 6, 0, 6, 0, MAT.furTan),
        box(6, 5, 5, 9, 8, 0, MAT.furTan)
      ];
      [5, -5].forEach(function (px) {
        [2, -2].forEach(function (pz) {
          quad.push(box(1.6, 5, 1.6, px, 2.5, pz, MAT.furDark));
        });
      });
      return quad;
    }
    /* ---- 秘法会 LOD ---- */
    if (kind === 'mage' || kind === 'frost') {
      const orb = kind === 'frost' ? MAT.frostGlow : MAT.runeCyan;
      const robe = kind === 'frost' ? MAT.frostRobe : MAT.robe;
      const shaft = kind === 'frost' ? MAT.iceShard : MAT.goldTrim;
      const parts = [
        taperedBox(kind === 'frost' ? 10.2 : 8.8, kind === 'frost' ? 10.2 : 8.8, 3.6, 3.6, 12.4, 0, 6.8, 0, robe),
        box(6.0, 1.6, 7, -0.4, 13.2, 0, 0.9),                 // 玩家色肩饰
        box(5.8, 0.65, 6.0, -2.0, 10.8, 0, 0.84),            // 玩家色披挂
        box(2.0, 2.0, 4.4, 1.0, 11.4, 4.0, robe),
        cyl(0.38, 0.38, 13, 6, 4.6, 9.0, 2.6, shaft, ROT_Z90),
        sph(1.8, 6, 11.5, 9.0, 2.6, orb)
      ];
      if (kind === 'frost') {
        parts.push(cyl(7.2, 7.4, 0.42, 12, 0, 16.4, 0, MAT.frostRobe));
      } else {
        parts.push(taperedBox(3.2, 3.2, 0.55, 0.55, 4.2, 0, 18.2, 0, MAT.robe));
        parts.push(box(5.0, 0.38, 5.0, 0, 16.6, 0, MAT.goldTrim));
      }
      return parts;
    }
    if (kind === 'imp') {
      return [
        taperedBox(8.4, 6.2, 5.2, 4.4, 3.4, 0.6, 3.4, 0, MAT.miteCrystal),
        box(6.4, 0.70, 4.8, -0.4, 5.4, 0, 0.92),             // 玩家色背甲
        pyr(0.7, 2.4, 4, 1.0, 6.4, 0, MAT.miteCrystal),
        box(1.1, 2.4, 1.1, 3.0, 1.3, 2.2, MAT.crystal),
        box(1.1, 2.4, 1.1, 3.0, 1.3, -2.2, MAT.crystal),
        sph(1.0, 6, 1.4, 4.2, 0, MAT.runeCyan)
      ];
    }
    if (kind === 'oracle') {
      return [
        taperedBox(5.6, 5.6, 2.2, 2.2, 15.0, 0, 8.2, 0, MAT.deepViolet),
        box(5.2, 0.65, 5.8, -1.8, 13.8, 0, 0.88),            // 玩家色披肩
        box(5.2, 1.1, 2.2, 1.2, 18.0, 0, MAT.prismGlow),
        cyl(0.24, 0.28, 15.5, 6, 4.6, 11.0, 2.2, MAT.goldTrim, ROT_Z90),
        sph(1.2, 6, 12.8, 11.0, 2.2, MAT.prismGlow)
      ];
    }
    if (kind === 'golem') {
      return scalePartList([
        taperedBox(12, 10, 9, 7.4, 12, 0, 10.4, 0, MAT.magicStone),
        box(9.0, 0.90, 6.6, -1.0, 15.8, 0, 0.88),            // 玩家色胸背甲
        box(5, 10, 5, 1, 9.4, 7, MAT.magicStone),
        box(5, 10, 5, 1, 9.4, -7, MAT.magicStone),
        sph(1.7, 6, 4.8, 11.2, 0, MAT.runeCyan)
      ], 1.35, 1.10, 1.35);
    }
    if (kind === 'panther') {
      const quad = [
        box(18, 4.2, 4.6, 0.2, 5.4, 0, MAT.magicHide),
        box(5, 3.4, 4, 10.2, 7.2, 0, MAT.magicHide),
        taperedBox(10.0, 6.8, 8.2, 5.6, 1.2, -1.0, 8.8, 0, 0.94) // 玩家色鞍甲
      ];
      [5.8, -6.0].forEach(function (px) {
        [1.7, -1.7].forEach(function (pz) {
          quad.push(box(1.35, 4.6, 1.35, px, 2.3, pz, MAT.magicHide));
        });
      });
      return scalePartList(quad, 0.88, 1.0, 1.0);
    }
    if (kind === 'dragon') {
      const dragon = [
        taperedBox(28, 11, 20, 8, 7.2, -2, 8.2, 0, MAT.scaleHide),
        box(14.0, 0.75, 6.2, -2.0, 12.3, 0, 0.90),
        taperedBox(7, 4, 5, 3, 4, 12.2, 12.0, 0, MAT.scaleHide),
        taperedBox(6.2, 4.2, 4.8, 3.0, 3.4, 20.4, 14.6, 0, MAT.scaleHide),
        taperedBox(10, 2.2, 5, 1.1, 2.0, -18.4, 7.5, 0, MAT.scaleHide),
        sph(1.6, 6, 26.6, 14.2, 0, MAT.fireGlow)
      ];
      const wings = [
        boxOrient(22, 0.28, 15.4, -2.8, 13.4, 16.0, MAT.wingMembrane, 0.18, 0.48, 0.08),
        boxOrient(22, 0.28, 15.4, -2.8, 13.4, -16.0, MAT.wingMembrane, -0.18, -0.48, 0.08)
      ];
      [1, -1].forEach(function (side) {
        wings.push(boxOrient(14, 0.34, 3.4, -2.0, 13.9, side * 17.0, 0.86,
          side * 0.18, side * 0.48, 0.08));
      });
      dragon.push.apply(dragon, scalePartList(wings, 1.0, 1.0, 0.82));
      return dragon;
    }
    if (kind === 'warden') {
      return scalePartList([
        taperedBox(13.2, 10.2, 9.6, 7.4, 12.4, 0, 11.4, 0, MAT.plateViolet),
        box(10.4, 0.95, 6.8, -0.4, 17.8, 0, 0.92),           // 玩家色胸背甲
        box(5.6, 3.2, 13.2, 0.8, 16.1, 0, MAT.slate),        // 宽肩剪影
        taperedBox(2.1, 13.8, 1.2, 10.2, 15.8, 2.4, 11.1, 10.2, MAT.goldTrim),
        box(0.8, 10.4, 1.2, 3.2, 11.4, 10.2, 0.84),          // 塔盾面
        cyl(0.48, 0.58, 17.5, 6, 6.8, 11.0, -5.1, MAT.goldTrim, ROT_Z90),
        box(5.4, 5.0, 4.4, 17.1, 11.0, -5.1, MAT.crystal),   // 晶锤头
        pyr(0.75, 3.4, 4, 2.7, 24.8, 0, MAT.crystal),
        sph(1.35, 6, 4.8, 13.0, 0, MAT.runeCyan)
      ], 1.18, 1.14, 1.18);
    }
    if (kind === 'colossus') {
      return [
        taperedBox(26, 14.4, 20, 11.6, 8.6, 0.2, 10.4, 0, MAT.magicStone),
        taperedBox(15.2, 9.8, 12.4, 7.6, 1.1, -1.2, 15.2, 0, 0.88),
        box(4.6, 8.6, 4.6, 8.8, 4.5, 6.0, MAT.magicStone),
        box(4.6, 8.6, 4.6, 8.8, 4.5, -6.0, MAT.magicStone),
        box(5.0, 9.0, 5.0, -8.4, 4.7, 6.4, MAT.magicStone),
        box(5.0, 9.0, 5.0, -8.4, 4.7, -6.4, MAT.magicStone),
        cyl(1.95, 2.45, 22, 7, 10.6, 22.8, 0, MAT.miteCrystal,
          new THREE.Matrix4().makeRotationZ(Math.PI / 2 - 0.38)),
        sph(2.0, 6, -1.2, 14.2, 0, MAT.runeCyan)
      ];
    }
    if (kind === 'comet') {
      return [
        taperedBox(36, 24, 30, 20, 7.6, 0, 7.2, 0, MAT.goldStoneDark),
        taperedBox(27, 16, 23, 13, 1.0, -1.0, 12.3, 0, 0.88), // 玩家色发射平台顶板
        box(5.2, 7.6, 5.2, 10.6, 4.8, 7.4, MAT.goldStone),
        box(5.2, 7.6, 5.2, 10.6, 4.8, -7.4, MAT.goldStone),
        cyl(2.15, 2.85, 22, 7, 0.8, 28.4, 0, MAT.miteCrystal),
        sph(2.4, 7, 0.8, 40.0, 0, MAT.runeCyan)
      ];
    }
    if (kind === 'mharvester') {
      return scalePartList([
        taperedBox(16, 14, 18, 16, 4, 0, 6, 0, MAT.goldStoneDark),
        taperedBox(15, 12, 13, 10, 1.0, 0, 8.5, 0, 0.90),    // 玩家色浮台上盖
        taperedBox(7, 7, 2.5, 2.5, 12, -2, 14, 0, MAT.miteCrystal),
        sph(2, 6, 0, 8.5, 0, MAT.runeCyan)
      ], 1.65, 1.25, 1.65);
    }
    if (kind === 'mmcv') {
      return scalePartList([
        taperedBox(22, 16, 24, 18, 5, 0, 6, 0, MAT.goldStone),
        taperedBox(19, 13, 16, 10, 1.2, 0, 9.0, 0, 0.92),    // 玩家色平台上盖
        cyl(9, 9, 2, 10, 0, 16, 0, MAT.goldTrim, ROT_Z90)
      ], 1.65, 1.42, 1.65);
    }
    if (kind === 'hexling') {
      return scalePartList([
        sph(3.6, 8, 0, 7.2, 0, MAT.crystal),
        torus(4.2, 0.45, 6, 12, 0, 7.2, 0, 0.94, ROT_X90),   // 玩家色识别环
        sph(2.2, 7, 0, 7.2, 0, MAT.fireGlow),
        cyl(3.6, 3.6, 0.22, 10, 0, 6.4, 0, MAT.fireGlow)
      ], 1.20, 1.20, 1.20);
    }
    return infantry;
  }

  function unitGeometry(kind) {
    let entry = UNIT_GEOMETRY_CACHE.get(kind);
    if (entry) return entry;
    const builder = UNIT_BUILDERS[kind] || UNIT_BUILDERS.rifle;
    const parts = builder();
    entry = {
      // 车体与发光件合并成一个几何体：发光件的顶点系数 > 1，着色器据此
      // 跳过光照，效果一样但少一半绘制调用
      body: mergeParts(parts.body.concat(parts.glow || [])),
      simple: mergeParts(simpleUnitParts(kind))
    };
    UNIT_GEOMETRY_CACHE.set(kind, entry);
    return entry;
  }

  function ensurePool(kind, needed) {
    let pool = unitPools.get(kind);
    if (!pool) pool = { capacity: 0, mesh: null, simple: null };
    if (pool.capacity >= needed) return pool;

    const capacity = Math.max(16, Math.ceil(needed * 1.5));
    const geo = unitGeometry(kind);
    const build = function (key, geometry, material, casts) {
      if (pool[key]) {
        worldRoot.remove(pool[key]);
        pool[key].dispose();
        pool[key] = null;
      }
      if (!geometry) return;
      const mesh = new THREE.InstancedMesh(geometry, material, capacity);
      mesh.instanceMatrix.setUsage(THREE.DynamicDrawUsage);
      mesh.castShadow = casts && state.shadows === 'all';
      mesh.receiveShadow = false;
      mesh.frustumCulled = false;
      mesh.count = 0;
      // 大部分 RTS 单位多数时间静止。缓存每个实例槽位的变换与颜色，只有
      // 真正移动、换槽或换队伍色时才重写 GPU buffer，避免静止大军也在
      // 60FPS 下反复 compose 数百个完全相同的矩阵。
      mesh.userData.instanceIds = new Array(capacity);
      mesh.userData.instanceX = new Float32Array(capacity);
      mesh.userData.instanceY = new Float32Array(capacity);
      mesh.userData.instanceDir = new Float32Array(capacity);
      mesh.userData.instanceX.fill(NaN);
      mesh.userData.instanceY.fill(NaN);
      mesh.userData.instanceDir.fill(NaN);
      mesh.userData.instanceColors = new Array(capacity);
      worldRoot.add(mesh);
      pool[key] = mesh;
    };
    const unitMaterial = CLOTH_UNIT_KINDS[kind] ? unitClothMaterial :
      (HIDE_UNIT_KINDS[kind] ? unitHideMaterial :
        (MAGIC_UNIT_KINDS[kind] ? unitStoneMaterial : unitMetalMaterial));
    build('mesh', geo.body, unitMaterial, true);
    build('simple', geo.simple, unitMaterial, false);
    pool.capacity = capacity;
    unitPools.set(kind, pool);
    return pool;
  }

  function ensureShadowMesh(needed) {
    if (shadowMesh && shadowMesh.instanceMatrix.count >= needed) return shadowMesh;
    if (shadowMesh) {
      worldRoot.remove(shadowMesh);
      shadowMesh.dispose();
    }
    shadowMesh = new THREE.InstancedMesh(shadowGeo, shadowMaterial,
      Math.max(64, Math.ceil(needed * 1.5)));
    shadowMesh.instanceMatrix.setUsage(THREE.DynamicDrawUsage);
    shadowMesh.frustumCulled = false;
    shadowMesh.renderOrder = 2;
    shadowMesh.count = 0;
    worldRoot.add(shadowMesh);
    return shadowMesh;
  }

  /* -------------------- 血条层（GPU instanced，替代 Canvas 2D hudBar） -------------------- */

  let barBgMesh = null;
  let barFillMesh = null;
  let barSecMesh = null;
  // 这些资源过去在 ensureBarMeshes() 的热路径里每帧 new 一套，即使容量足够
  // 直接返回也已经造成三份材质泄漏。改成全局复用后，长时间游戏不再持续积累
  // GPU 程序/JS 垃圾。
  const barGeo = new THREE.PlaneGeometry(1, 1).rotateX(-Math.PI / 2);
  const barBgMaterial = new THREE.MeshBasicMaterial({
    // 底板压得更轻更扁：不再是单位头顶一块厚重的黑牌，只留一层让彩条
    // 在亮地面上读得出的淡底（地面变干净变亮后这层仍要保住对比度）
    color: 0x10130e, transparent: true, opacity: 0.6,
    depthTest: false, depthWrite: false, fog: false, side: THREE.DoubleSide
  });
  const barFillMaterial = new THREE.MeshBasicMaterial({
    transparent: true, opacity: 0.95,
    depthTest: false, depthWrite: false, fog: false, side: THREE.DoubleSide
  });
  const barSecMaterial = new THREE.MeshBasicMaterial({
    transparent: true, opacity: 0.88,
    depthTest: false, depthWrite: false, fog: false, side: THREE.DoubleSide
  });
  const barQuat = new THREE.Quaternion();
  const barPos = new THREE.Vector3();
  const barScale = new THREE.Vector3();
  const barGreen = new THREE.Color('#7dd85f');
  const barRed = new THREE.Color('#e04a3a');

  function ensureBarMeshes(needed) {
    const cap = Math.max(128, Math.ceil(needed * 1.6));
    const make = function (existing, material, order) {
      if (existing && existing.instanceMatrix.count >= cap) return existing;
      if (existing) { worldRoot.remove(existing); existing.dispose(); }
      const m = new THREE.InstancedMesh(barGeo, material, cap);
      m.instanceMatrix.setUsage(THREE.DynamicDrawUsage);
      m.frustumCulled = false;
      m.renderOrder = order;
      m.count = 0;
      worldRoot.add(m);
      return m;
    };
    barBgMesh = make(barBgMesh, barBgMaterial, 7);
    barFillMesh = make(barFillMesh, barFillMaterial, 8);
    barSecMesh = make(barSecMesh, barSecMaterial, 9);
  }

  function updateBars(game, selectedUnits, selectedStructureId, farOut) {
    const total = visual.size + game.structures.length;
    ensureBarMeshes(total);

    let bg = 0, fg = 0, sc = 0;
    visual.forEach(function (vis, _id) {
      if (!vis.inRenderRange) return;
      const u = vis.unit;
      const sel = selectedUnits.has(u.id);
      const ratio = Math.max(0, Math.min(1, u.hp / u.maxHp));
      const damaged = ratio < 0.999;
      const hasCargo = u.kind === 'harvester' && u.capacity && u.cargo > 0.005;
      // 满血、未选中的单位不需要常驻血条。大规模交战时这通常能让需要
      // 合成和上传的实例从数百个降到几十个；采矿车仍保留有货时的货仓条。
      if (!damaged && !sel && !hasCargo) return;
      if (farOut && !damaged && !sel) return;

      const barW = (u.size > 16 ? 26 : 18) + (sel ? 4 : 0);
      const barH = sel ? 4 : 3;
      const gy = vis.groundY == null ? groundHeight(vis.x, vis.y) : vis.groundY;
      const barY = gy + u.size * 1.9 + 12;

      barScale.set(barW + 1.5, 1, barH + 1);
      barBgMesh.setMatrixAt(bg, matrix.compose(barPos.set(vis.x, barY, vis.y), barQuat, barScale));
      bg++;

      const fillW = Math.max(0.5, barW * ratio);
      const shiftX = -(barW + 1.5 - fillW) / 2;
      barScale.set(fillW, 1, barH);
      barFillMesh.setMatrixAt(fg, matrix.compose(barPos.set(vis.x + shiftX, barY + 0.6, vis.y), barQuat, barScale));
      barFillMesh.setColorAt(fg, tmpColor.copy(barRed).lerp(barGreen, ratio));
      fg++;

      if (u.kind === 'harvester' && u.capacity) {
        const cr = Math.min(1, u.cargo / u.capacity);
        if (cr > 0.005) {
          const cFillW = Math.max(0.5, barW * cr);
          const cShiftX = -(barW + 1.5 - cFillW) / 2;
          barScale.set(cFillW, 1, sel ? 2 : 1.5);
          barSecMesh.setMatrixAt(sc, matrix.compose(
            barPos.set(vis.x + cShiftX, barY + (sel ? 6 : 5), vis.y), barQuat, barScale));
          barSecMesh.setColorAt(sc, tmpColor.set('#f6c84a'));
          sc++;
        }
      }
    });

    for (let i = 0; i < game.structures.length; i++) {
      const s = game.structures[i];
      const structureNode = structureNodes.get(s.id);
      if (structureNode && !structureNode.group.visible) continue;
      const sel = selectedStructureId === s.id;
      const damaged = s.hp < s.maxHp * 0.999;
      const producing = !!(s.queue && s.queue.length && s.owner === state.viewerId);
      if (s.active && !damaged && !sel && !producing) continue;
      const gy = structureNode && structureNode.groundY != null
        ? structureNode.groundY : groundHeight(s.x, s.y);
      const barY = gy + s.size * 2.1;

      if (!s.active && s.buildTotal) {
        const progress = 1 - (s.buildRemaining / s.buildTotal);
        const barW = 42;
        const barH = 3.5;
        barScale.set(barW + 1, 1, barH + 1);
        barBgMesh.setMatrixAt(bg, matrix.compose(barPos.set(s.x, barY, s.y), barQuat, barScale));
        bg++;
        const pFillW = Math.max(0.5, barW * progress);
        const pShiftX = -(barW + 1 - pFillW) / 2;
        barScale.set(pFillW, 1, barH);
        barFillMesh.setMatrixAt(fg, matrix.compose(barPos.set(s.x + pShiftX, barY + 0.6, s.y), barQuat, barScale));
        barFillMesh.setColorAt(fg, tmpColor.set('#42d9ff'));
        fg++;
      } else {
        const ratio = Math.max(0, Math.min(1, s.hp / s.maxHp));
        const barW = sel ? 46 : 40;
        const barH = sel ? 5 : 4;
        barScale.set(barW + 1.5, 1, barH + 1);
        barBgMesh.setMatrixAt(bg, matrix.compose(barPos.set(s.x, barY, s.y), barQuat, barScale));
        bg++;
        const hFillW = Math.max(0.5, barW * ratio);
        const hShiftX = -(barW + 1.5 - hFillW) / 2;
        barScale.set(hFillW, 1, barH);
        barFillMesh.setMatrixAt(fg, matrix.compose(barPos.set(s.x + hShiftX, barY + 0.6, s.y), barQuat, barScale));
        barFillMesh.setColorAt(fg, tmpColor.copy(barRed).lerp(barGreen, ratio));
        fg++;

        if (producing) {
          const done = 1 - (s.queue[0].remaining / s.queue[0].total);
          const qFillW = Math.max(0.5, barW * done);
          const qShiftX = -(barW + 1.5 - qFillW) / 2;
          barScale.set(qFillW, 1, 2.5);
          barSecMesh.setMatrixAt(sc, matrix.compose(
            barPos.set(s.x + qShiftX, barY + 7, s.y), barQuat, barScale));
          barSecMesh.setColorAt(sc, tmpColor.set('#f6c84a'));
          sc++;
        }
      }
    }

    barBgMesh.count = bg;
    if (bg) barBgMesh.instanceMatrix.needsUpdate = true;
    barFillMesh.count = fg;
    if (fg) {
      barFillMesh.instanceMatrix.needsUpdate = true;
      if (barFillMesh.instanceColor) barFillMesh.instanceColor.needsUpdate = true;
    }
    barSecMesh.count = sc;
    if (sc) {
      barSecMesh.instanceMatrix.needsUpdate = true;
      if (barSecMesh.instanceColor) barSecMesh.instanceColor.needsUpdate = true;
    }
  }

  /* -------------------- 建筑 -------------------- */

  const structureNodes = new Map();  // id -> {group, teamMat, kind}

  function ensureStructure(structure) {
    let node = structureNodes.get(structure.id);
    if (node && node.kind === structure.kind) return node;
    if (node) disposeStructure(structure.id);
    // vertexColors 让合并后的几何体仍能按零件明暗分层
    // 单一材质：零件的固有色/团队色由顶点属性区分
    const teamMat = applyEmissiveByVertexColor(
      new THREE.MeshLambertMaterial({ color: 0xffffff, vertexColors: true }),
      MAGIC_STRUCTURE_KINDS[structure.kind] ? 'stone' : 'metal');
    const group = structureGroup(structure.kind, structure.size, teamMat);
    if (!buildingPadMat) {
      buildingPadMat = applyFogMask(new THREE.MeshLambertMaterial({
        color: displayTheme(state.terrain && state.terrain.theme).pad,
        map: makeBuildingPadTexture(),
        transparent: true, opacity: 0.82, depthWrite: false
      }));
    }
    const pad = new THREE.Mesh(buildingPadGeo, buildingPadMat);
    // 尘土围裙略大于新地基，让建筑坐进 #7 的踩实土而不是压住一整块灰板。
    pad.scale.set(structure.size * 0.86, 1, structure.size * 0.86);
    pad.position.y = 0.42;
    pad.receiveShadow = true;
    pad.renderOrder = 1;
    group.add(pad);
    group.position.set(structure.x, 0, structure.y);
    worldRoot.add(group);
    node = {
      group: group, teamMat: teamMat,
      kind: structure.kind,
      head: group.getObjectByName('turretHead'),
      spinner: group.getObjectByName('spinner')
    };
    structureNodes.set(structure.id, node);
    return node;
  }

  function disposeStructure(id) {
    const node = structureNodes.get(id);
    if (!node) return;
    worldRoot.remove(node.group);
    // 几何体来自 STRUCTURE_GEOMETRY_CACHE，由所有同类建筑共享，不能释放
    node.teamMat.dispose();
    structureNodes.delete(id);
  }

  /* -------------------- 弹道与特效 -------------------- */

  function paintGeoWhite(geo) {
    const n = geo.attributes.position.count;
    const col = new Float32Array(n * 3);
    col.fill(1);
    geo.setAttribute('color', new THREE.BufferAttribute(col, 3));
    return geo;
  }
  const tracerGeo = paintGeoWhite(new THREE.CylinderGeometry(0.9, 0.9, 1, 6).rotateZ(Math.PI / 2));
  const tracerOrbGeo = paintGeoWhite(new THREE.SphereGeometry(1, 8, 6));
  const tracerShardGeo = paintGeoWhite(new THREE.CylinderGeometry(0.04, 1.05, 1, 4).rotateZ(Math.PI / 2));
  const tracerMaterial = new THREE.MeshBasicMaterial({ vertexColors: true, fog: false, toneMapped: false });
  let tracerMesh = null;
  let tracerOrbMesh = null;
  let tracerShardMesh = null;

  const PROJECTILE_STYLE = {
    bullet: { len: 16, thick: 0.8, color: 0xfff0b0, arc: 0, look: 'streak' },
    rocket: { len: 22, thick: 1.7, color: 0xff9a4a, arc: 34, look: 'streak' },
    shell: { len: 18, thick: 1.5, color: 0xffd07a, arc: 22, look: 'streak' },
    sniper: { len: 34, thick: 0.6, color: 0xbfe9ff, arc: 0, look: 'streak' },
    siege: { len: 24, thick: 2.4, color: 0xffb347, arc: 120, look: 'streak' },
    ap: { len: 26, thick: 1.0, color: 0xd8f0ff, arc: 6, look: 'streak' },
    missile: { len: 32, thick: 2.8, color: 0xff6633, arc: 140, look: 'streak' },
    // 磁暴电弧：短促、近乎笔直的蓝白电光，叠两段错位闪电
    tesla: { len: 13, thick: 1.15, color: 0x9ad0ff, arc: 0, look: 'arc' },
    // 光棱聚焦光束：细长、笔直、亮青色，指哪打哪
    laser: { len: 46, thick: 0.52, color: 0xb8f8ff, arc: 0, look: 'beam' },
    // ---- 魔法弹道 ----
    // 奥术弹：紫色流光 + 亮核，微微上飘
    arcane: { len: 28, thick: 1.05, color: 0xd6a6ff, arc: 8, look: 'bolt' },
    // 冰霜：冰蓝棱晶，拖着寒气
    frost: { len: 18, thick: 1.15, color: 0xc4f4ff, arc: 12, look: 'shard' },
    // 巨石：傀儡投掷，高弧线
    boulder: { len: 20, thick: 2.6, color: 0xb09a7a, arc: 70, look: 'streak' },
    // 火球：巨龙喷吐，橙色高弧 + 光核
    fireball: { len: 15, thick: 3.1, color: 0xff7a28, arc: 52, look: 'fireball' },
    // 晶刃：卫士短促紫晶弹
    crystal: { len: 20, thick: 1.15, color: 0xe0c4ff, arc: 10, look: 'crystal' },
    // 虹视：细长棱晶束，几乎无弧
    iris: { len: 38, thick: 0.62, color: 0xffc8f0, arc: 0, look: 'beam' },
    // 晶陨：裂地高弧攻城弹
    meteor: { len: 24, thick: 3.1, color: 0xc9a0ff, arc: 118, look: 'meteor' },
    // 坠星：东风同档慢弹高弧，晶彗核 + 长尾，能被看见躲
    comet: { len: 34, thick: 3.4, color: 0xe8d0ff, arc: 140, look: 'comet' }
  };

  function ensureStyledMesh(existing, geo, needed) {
    if (existing && existing.instanceMatrix.count >= needed) return existing;
    if (existing) {
      worldRoot.remove(existing);
      existing.dispose();
    }
    const mesh = new THREE.InstancedMesh(geo, tracerMaterial,
      Math.max(64, Math.ceil(needed * 1.6)));
    mesh.instanceMatrix.setUsage(THREE.DynamicDrawUsage);
    mesh.frustumCulled = false;
    mesh.count = 0;
    worldRoot.add(mesh);
    return mesh;
  }

  function ensureTracerMesh(needed) {
    tracerMesh = ensureStyledMesh(tracerMesh, tracerGeo, needed);
    return tracerMesh;
  }

  function ensureTracerOrbMesh(needed) {
    tracerOrbMesh = ensureStyledMesh(tracerOrbMesh, tracerOrbGeo, needed);
    return tracerOrbMesh;
  }

  function ensureTracerShardMesh(needed) {
    tracerShardMesh = ensureStyledMesh(tracerShardMesh, tracerShardGeo, needed);
    return tracerShardMesh;
  }

  // 上一帧还在飞的弹道，用来给本帧服务端 impact 对上冰霜/火球等视觉种类。
  let projectileHintPrev = [];

  /* -------------------- 粒子 -------------------- *
   *
   * 分两层：加色层画火光/火花/能量，普通混合层画烟尘。烟必须走普通混合 ——
   * 加色模式下深色等于不可见，烟会整个消失。
   */

  const EFFECT_MAX = 400;

  function createParticleLayer(blending, hot) {
    const geo = new THREE.BufferGeometry();
    geo.setAttribute('position', new THREE.BufferAttribute(new Float32Array(EFFECT_MAX * 3), 3));
    geo.setAttribute('color', new THREE.BufferAttribute(new Float32Array(EFFECT_MAX * 3), 3));
    geo.setAttribute('size', new THREE.BufferAttribute(new Float32Array(EFFECT_MAX), 1));
    geo.setAttribute('alpha', new THREE.BufferAttribute(new Float32Array(EFFECT_MAX), 1));
    geo.setAttribute('seed', new THREE.BufferAttribute(new Float32Array(EFFECT_MAX), 1));
    const material = new THREE.ShaderMaterial({
      transparent: true,
      depthWrite: false,
      blending: blending,
      vertexColors: true,
      uniforms: { uScale: { value: 1 }, uHot: { value: hot ? 1 : 0 } },
      vertexShader: [
        'attribute float size;',
        'attribute float alpha;',
        'attribute float seed;',
        'varying vec3 vColor;',
        'varying float vAlpha;',
        'varying float vSeed;',
        'uniform float uScale;',
        'void main() {',
        '  vColor = color;',
        '  vAlpha = alpha;',
        '  vSeed = seed;',
        '  vec4 mv = modelViewMatrix * vec4(position, 1.0);',
        '  gl_PointSize = size * uScale / max(1.0, -mv.z) * 300.0;',
        '  gl_Position = projectionMatrix * mv;',
        '}'
      ].join('\n'),
      fragmentShader: [
        'varying vec3 vColor;',
        'varying float vAlpha;',
        'varying float vSeed;',
        'uniform float uHot;',
        NOISE_GLSL,
        'void main() {',
        '  vec2 pc = gl_PointCoord - vec2(0.5);',
        '  float r = length(pc) * 2.0;',
        // 噪声撕裂边缘：光滑圆点像肥皂泡，被噪声咬出缺口才像火团/烟团。
        // 噪声随粒子年龄（1-vAlpha）滚动，火焰边缘会持续翻卷。
        '  float n = vnoise(pc * 5.0 + vec2(vSeed, vSeed * 1.7) + (1.0 - vAlpha) * 3.0);',
        '  float edge = 1.0 - smoothstep(0.30, 1.0, r + (n - 0.5) * 0.7);',
        '  float a = edge * vAlpha;',
        '  if (a <= 0.01) discard;',
        // 火焰层带 HDR 核心：中心 >1 的亮度交给辉光变成光斑
        '  float core = exp(-r * r * 6.0);',
        '  vec3 col = vColor * (1.0 + uHot * core * 1.6);',
        '  gl_FragColor = vec4(col, a);',
        '}'
      ].join('\n')
    });
    const points = new THREE.Points(geo, material);
    points.frustumCulled = false;
    points.renderOrder = blending === THREE.AdditiveBlending ? 16 : 15;
    scene.add(points);
    return { geo: geo, points: points, list: [] };
  }

  const fireLayer = createParticleLayer(THREE.AdditiveBlending, 1);
  const smokeLayer = createParticleLayer(THREE.NormalBlending, 0);

  function emit(layer, options) {
    if (layer.list.length >= state.particleBudget) return;
    if (options.seed == null) options.seed = Math.random() * 100;
    layer.list.push(options);
  }

  function burst(layer, count, make) {
    for (let i = 0; i < count; i++) {
      if (layer.list.length >= state.particleBudget) return;
      const p = make(i);
      if (p.seed == null) p.seed = Math.random() * 100;
      layer.list.push(p);
    }
  }

  function updateParticleLayer(layer, dt, drag, gravity) {
    const list = layer.list;
    const pos = layer.geo.attributes.position;
    const col = layer.geo.attributes.color;
    const size = layer.geo.attributes.size;
    const alpha = layer.geo.attributes.alpha;
    const seed = layer.geo.attributes.seed;
    let live = 0;
    for (let i = 0; i < list.length; i++) {
      const p = list[i];
      p.life -= dt;
      if (p.life <= 0) continue;
      p.vy -= gravity * dt * (p.buoyancy || 1);
      const damp = Math.pow(drag, dt * 60);
      p.vx *= damp;
      p.vz *= damp;
      p.x += p.vx * dt;
      p.y += p.vy * dt;
      p.z += p.vz * dt;
      if (p.y < 1.5) { p.y = 1.5; p.vy *= -0.25; p.vx *= 0.55; p.vz *= 0.55; }
      const t = p.life / p.maxLife;
      pos.array[live * 3] = p.x;
      pos.array[live * 3 + 1] = p.y;
      pos.array[live * 3 + 2] = p.z;
      col.array[live * 3] = p.r;
      col.array[live * 3 + 1] = p.g;
      col.array[live * 3 + 2] = p.b;
      size.array[live] = p.size * (p.grow ? (2 - t) : (0.4 + t * 0.6));
      alpha.array[live] = p.fade === 'in' ? Math.min(1, (1 - t) * 4) * t : t;
      seed.array[live] = p.seed || 0;
      list[live] = p;
      live++;
    }
    list.length = live;
    layer.geo.setDrawRange(0, live);
    pos.needsUpdate = true;
    col.needsUpdate = true;
    size.needsUpdate = true;
    alpha.needsUpdate = true;
    seed.needsUpdate = true;
  }

  /* -------------------- 地面贴花（冲击波 / 焦痕） -------------------- *
   *
   * 每个实例要有独立的透明度，普通材质做不到，所以用 InstancedBufferAttribute
   * 自带一条 alpha 通道，配一个最小的着色器。
   */

  function createDecalLayer(geometry, capacity, blending) {
    const alphas = new THREE.InstancedBufferAttribute(new Float32Array(capacity), 1);
    geometry = geometry.clone();
    geometry.setAttribute('aAlpha', alphas);
    const material = new THREE.ShaderMaterial({
      transparent: true,
      depthWrite: false,
      blending: blending,
      side: THREE.DoubleSide,
      uniforms: {},
      vertexShader: [
        'attribute float aAlpha;',
        'attribute vec3 instanceColorAttr;',
        'varying float vAlpha;',
        'varying vec3 vColor;',
        'void main() {',
        '  vAlpha = aAlpha;',
        '  vColor = instanceColorAttr;',
        '  gl_Position = projectionMatrix * modelViewMatrix * instanceMatrix * vec4(position, 1.0);',
        '}'
      ].join('\n'),
      fragmentShader: [
        'varying float vAlpha;',
        'varying vec3 vColor;',
        'void main() {',
        '  if (vAlpha <= 0.004) discard;',
        '  gl_FragColor = vec4(vColor, vAlpha);',
        '}'
      ].join('\n')
    });
    geometry.setAttribute('instanceColorAttr',
      new THREE.InstancedBufferAttribute(new Float32Array(capacity * 3), 3));
    const mesh = new THREE.InstancedMesh(geometry, material, capacity);
    mesh.instanceMatrix.setUsage(THREE.DynamicDrawUsage);
    mesh.frustumCulled = false;
    mesh.count = 0;
    mesh.renderOrder = 4;
    worldRoot.add(mesh);
    return {
      mesh: mesh,
      capacity: capacity,
      list: [],
      spawn: function (item) {
        if (this.list.length >= capacity) this.list.shift();
        this.list.push(item);
      }
    };
  }

  const shockLayer = createDecalLayer(
    new THREE.RingGeometry(0.72, 1.0, 32).rotateX(-Math.PI / 2), 48,
    THREE.AdditiveBlending);
  const scorchLayer = createDecalLayer(
    new THREE.CircleGeometry(1, 18).rotateX(-Math.PI / 2), 64,
    THREE.NormalBlending);

  function updateDecalLayer(layer, dt, groundY) {
    const list = layer.list;
    const alphas = layer.mesh.geometry.attributes.aAlpha;
    const colors = layer.mesh.geometry.attributes.instanceColorAttr;
    let live = 0;
    for (let i = 0; i < list.length; i++) {
      const d = list[i];
      d.life -= dt;
      if (d.life <= 0) continue;
      const t = d.life / d.maxLife;
      const radius = d.radius + (d.growth || 0) * (1 - t);
      matrix.compose(
        vecAux.set(d.x, groundHeight(d.x, d.y) + groundY, d.y),
        quatIdentity,
        vecScale.set(radius, 1, radius));
      layer.mesh.setMatrixAt(live, matrix);
      alphas.array[live] = d.alpha * (d.hold ? Math.min(1, t / 0.35) : t);
      colors.array[live * 3] = d.r;
      colors.array[live * 3 + 1] = d.g;
      colors.array[live * 3 + 2] = d.b;
      list[live] = d;
      live++;
    }
    list.length = live;
    layer.mesh.count = live;
    layer.mesh.instanceMatrix.needsUpdate = true;
    alphas.needsUpdate = true;
    colors.needsUpdate = true;
  }

  /* -------------------- 特效编排 -------------------- */

  /**
   * 爆炸闪光：一个小小的点光源池。带逐片元光照的 Lambert 材质下，
   * 附近的单位和地面真的会被爆炸「照亮」一瞬间 —— 这是所有爆炸分层里
   * 最有说服力的一层。池子只有 4 盏，大战场上按「最接近熄灭」抢占。
   */
  const flashPool = [];
  for (let fi = 0; fi < 2; fi++) {
    const l = new THREE.PointLight(0xffa445, 0, 340, 1.8);
    l.castShadow = false;
    l.visible = false;
    scene.add(l);
    flashPool.push({ light: l, life: 0, maxLife: 0.3 });
  }

  function flashAt(x, y, colorHex) {
    let best = flashPool[0];
    for (let i = 1; i < flashPool.length; i++) {
      if (flashPool[i].life < best.life) best = flashPool[i];
    }
    best.life = best.maxLife;
    best.light.color.setHex(colorHex || 0xffa445);
    best.light.position.set(x, groundHeight(x, y) + 34, y);
    best.light.visible = true;
  }

  function updateFlashes(dt) {
    for (let i = 0; i < flashPool.length; i++) {
      const f = flashPool[i];
      if (f.life <= 0) continue;
      f.life -= dt;
      const t = Math.max(0, f.life / f.maxLife);
      f.light.intensity = 5200 * t * t;
      if (f.life <= 0) f.light.visible = false;
    }
  }

  function spawnEffect(type, x, y, kind) {
    const rand = Math.random;
    if (type === 'explosion') {
      // 火球：颜色写成 >1 的线性值，核心经辉光放大成光斑
      burst(fireLayer, 8, function () {
        const a = rand() * TAU;
        const sp = 60 + rand() * 110;
        return {
          x: x, y: 8 + rand() * 10, z: y,
          vx: Math.cos(a) * sp, vy: 40 + rand() * 90, vz: Math.sin(a) * sp,
          life: 0.5 + rand() * 0.35, maxLife: 0.85,
          size: 16 + rand() * 14, grow: true,
          r: 2.2, g: 0.9 + rand() * 0.5, b: 0.22
        };
      });
      // 溅射火花
      burst(fireLayer, 6, function () {
        const a = rand() * TAU;
        const sp = 180 + rand() * 220;
        return {
          x: x, y: 6, z: y,
          vx: Math.cos(a) * sp, vy: 90 + rand() * 160, vz: Math.sin(a) * sp,
          life: 0.35 + rand() * 0.3, maxLife: 0.65,
          size: 4 + rand() * 3,
          r: 2.4, g: 1.9, b: 1.0
        };
      });
      flashAt(x, y);
      // 上升烟柱
      burst(smokeLayer, 6, function () {
        const a = rand() * TAU;
        const sp = 25 + rand() * 55;
        const grey = 0.16 + rand() * 0.12;
        return {
          x: x, y: 10 + rand() * 14, z: y,
          vx: Math.cos(a) * sp, vy: 40 + rand() * 40, vz: Math.sin(a) * sp,
          life: 1.1 + rand() * 0.9, maxLife: 2.0,
          size: 22 + rand() * 20, grow: true, buoyancy: -0.12,
          r: grey, g: grey * 0.95, b: grey * 0.9
        };
      });
      shockLayer.spawn({
        x: x, y: y, radius: 12, growth: 105, alpha: 0.75,
        life: 0.42, maxLife: 0.42, r: 1.0, g: 0.72, b: 0.36
      });
      scorchLayer.spawn({
        x: x, y: y, radius: 26 + rand() * 10, growth: 0, alpha: 0.5,
        life: 14, maxLife: 14, hold: true, r: 0.05, g: 0.04, b: 0.03
      });
    } else if (type === 'blast') {
      // 自爆单位的大爆炸：比普通阵亡火球更大，魔仆带紫核。
      const magic = kind === 'hexling';
      burst(fireLayer, 14, function () {
        const a = rand() * TAU;
        const sp = 80 + rand() * 150;
        return {
          x: x, y: 10 + rand() * 14, z: y,
          vx: Math.cos(a) * sp, vy: 50 + rand() * 110, vz: Math.sin(a) * sp,
          life: 0.6 + rand() * 0.4, maxLife: 1.0,
          size: 22 + rand() * 18, grow: true,
          r: magic ? 1.7 : 2.4, g: magic ? 0.55 : 1.0, b: magic ? 2.2 : 0.22
        };
      });
      burst(fireLayer, 10, function () {
        const a = rand() * TAU;
        const sp = 220 + rand() * 260;
        return {
          x: x, y: 8, z: y,
          vx: Math.cos(a) * sp, vy: 110 + rand() * 180, vz: Math.sin(a) * sp,
          life: 0.4 + rand() * 0.35, maxLife: 0.75,
          size: 5 + rand() * 4,
          r: magic ? 1.9 : 2.5, g: magic ? 0.8 : 1.95, b: magic ? 2.4 : 1.0
        };
      });
      flashAt(x, y, magic ? 0xc46bff : 0xffa445);
      burst(smokeLayer, 9, function () {
        const a = rand() * TAU;
        const sp = 30 + rand() * 70;
        const grey = 0.14 + rand() * 0.12;
        return {
          x: x, y: 12 + rand() * 16, z: y,
          vx: Math.cos(a) * sp, vy: 46 + rand() * 46, vz: Math.sin(a) * sp,
          life: 1.3 + rand() * 1.0, maxLife: 2.3,
          size: 28 + rand() * 24, grow: true, buoyancy: -0.12,
          r: magic ? grey * 0.7 : grey, g: grey * 0.9, b: magic ? grey * 1.2 : grey * 0.85
        };
      });
      shockLayer.spawn({
        x: x, y: y, radius: 18, growth: 150, alpha: 0.85,
        life: 0.5, maxLife: 0.5,
        r: magic ? 0.82 : 1.0, g: magic ? 0.42 : 0.72, b: magic ? 1.0 : 0.36
      });
      scorchLayer.spawn({
        x: x, y: y, radius: 40 + rand() * 12, growth: 0, alpha: 0.58,
        life: 16, maxLife: 16, hold: true, r: 0.05, g: 0.04, b: 0.03
      });
    } else if (type === 'impact') {
      if (kind === 'dog_arcane') {
        // 军犬咬法师：牙印金星 + 袍子紫屑。视觉彩蛋，不改扑咬数值。
        burst(fireLayer, 10, function () {
          const a = rand() * TAU;
          const sp = 50 + rand() * 90;
          return {
            x: x, y: 4 + rand() * 8, z: y,
            vx: Math.cos(a) * sp, vy: 70 + rand() * 90, vz: Math.sin(a) * sp,
            life: 0.32 + rand() * 0.22, maxLife: 0.55,
            size: 4 + rand() * 3,
            r: 2.1, g: 1.55, b: 0.45
          };
        });
        burst(fireLayer, 8, function () {
          const a = rand() * TAU;
          const sp = 40 + rand() * 70;
          return {
            x: x, y: 6, z: y,
            vx: Math.cos(a) * sp, vy: 30 + rand() * 50, vz: Math.sin(a) * sp,
            life: 0.28 + rand() * 0.18, maxLife: 0.48,
            size: 5 + rand() * 4,
            r: 1.45, g: 0.5, b: 2.05
          };
        });
        shockLayer.spawn({
          x: x, y: y, radius: 5, growth: 36, alpha: 0.55,
          life: 0.28, maxLife: 0.28, r: 1.15, g: 0.7, b: 1.35
        });
      } else if (kind === 'frost') {
        burst(fireLayer, 8, function () {
          const a = rand() * TAU;
          const sp = 70 + rand() * 120;
          return {
            x: x, y: 6, z: y,
            vx: Math.cos(a) * sp, vy: 40 + rand() * 80, vz: Math.sin(a) * sp,
            life: 0.28 + rand() * 0.22, maxLife: 0.5,
            size: 4 + rand() * 4,
            r: 0.75, g: 1.45, b: 2.1
          };
        });
        burst(smokeLayer, 3, function () {
          const a = rand() * TAU;
          return {
            x: x, y: 5, z: y,
            vx: Math.cos(a) * 18, vy: 16 + rand() * 14, vz: Math.sin(a) * 18,
            life: 0.7 + rand() * 0.4, maxLife: 1.1,
            size: 12 + rand() * 8, grow: true, buoyancy: -0.08,
            r: 0.62, g: 0.78, b: 0.88
          };
        });
        shockLayer.spawn({
          x: x, y: y, radius: 10, growth: 52, alpha: 0.62,
          life: 0.48, maxLife: 0.48, r: 0.55, g: 0.92, b: 1.2
        });
        // 减速场暗示：地面留一圈淡青霜斑，比焦痕更冷、更短
        scorchLayer.spawn({
          x: x, y: y, radius: 22, growth: 8, alpha: 0.38,
          life: 2.1, maxLife: 2.1, hold: true, r: 0.42, g: 0.68, b: 0.82
        });
        flashAt(x, y, 0x9fe8ff);
      } else if (kind === 'fireball') {
        burst(fireLayer, 8, function () {
          const a = rand() * TAU;
          const sp = 80 + rand() * 140;
          return {
            x: x, y: 8, z: y,
            vx: Math.cos(a) * sp, vy: 50 + rand() * 90, vz: Math.sin(a) * sp,
            life: 0.35 + rand() * 0.25, maxLife: 0.6,
            size: 10 + rand() * 8, grow: true,
            r: 2.3, g: 1.05, b: 0.28
          };
        });
        burst(fireLayer, 5, function () {
          const a = rand() * TAU;
          const sp = 160 + rand() * 180;
          return {
            x: x, y: 7, z: y,
            vx: Math.cos(a) * sp, vy: 80 + rand() * 120, vz: Math.sin(a) * sp,
            life: 0.22 + rand() * 0.18, maxLife: 0.4,
            size: 4 + rand() * 3,
            r: 2.4, g: 1.8, b: 0.7
          };
        });
        shockLayer.spawn({
          x: x, y: y, radius: 10, growth: 70, alpha: 0.7,
          life: 0.36, maxLife: 0.36, r: 1.2, g: 0.55, b: 0.18
        });
        scorchLayer.spawn({
          x: x, y: y, radius: 24 + rand() * 8, growth: 0, alpha: 0.46,
          life: 10, maxLife: 10, hold: true, r: 0.06, g: 0.03, b: 0.02
        });
        flashAt(x, y, 0xff7a2a);
      } else if (kind === 'meteor') {
        burst(fireLayer, 12, function () {
          const a = rand() * TAU;
          const sp = 90 + rand() * 170;
          return {
            x: x, y: 8, z: y,
            vx: Math.cos(a) * sp, vy: 50 + rand() * 90, vz: Math.sin(a) * sp,
            life: 0.34 + rand() * 0.24, maxLife: 0.58,
            size: 7 + rand() * 6, grow: true,
            r: 1.7, g: 0.62, b: 2.2
          };
        });
        burst(fireLayer, 8, function () {
          const a = rand() * TAU;
          const sp = 140 + rand() * 170;
          return {
            x: x, y: 3 + rand() * 4, z: y,
            vx: Math.cos(a) * sp, vy: 18 + rand() * 40, vz: Math.sin(a) * sp,
            life: 0.22 + rand() * 0.16, maxLife: 0.38,
            size: 3 + rand() * 3,
            r: 2.1, g: 1.4, b: 2.4
          };
        });
        shockLayer.spawn({
          x: x, y: y, radius: 12, growth: 88, alpha: 0.68,
          life: 0.4, maxLife: 0.4, r: 0.85, g: 0.45, b: 1.2
        });
        shockLayer.spawn({
          x: x, y: y, radius: 6, growth: 48, alpha: 0.4,
          life: 0.26, maxLife: 0.26, r: 1.15, g: 0.58, b: 1.45
        });
        scorchLayer.spawn({
          x: x, y: y, radius: 28 + rand() * 8, growth: 0, alpha: 0.44,
          life: 11, maxLife: 11, hold: true, r: 0.08, g: 0.04, b: 0.12
        });
        flashAt(x, y, 0xd6a6ff);
      } else if (kind === 'comet') {
        burst(fireLayer, 16, function () {
          const a = rand() * TAU;
          const sp = 110 + rand() * 200;
          return {
            x: x, y: 9, z: y,
            vx: Math.cos(a) * sp, vy: 40 + rand() * 100, vz: Math.sin(a) * sp,
            life: 0.4 + rand() * 0.28, maxLife: 0.68,
            size: 8 + rand() * 7, grow: true,
            r: 1.85, g: 0.7, b: 2.3
          };
        });
        burst(fireLayer, 10, function () {
          const a = rand() * TAU;
          const sp = 160 + rand() * 190;
          return {
            x: x, y: 3 + rand() * 5, z: y,
            vx: Math.cos(a) * sp, vy: 14 + rand() * 36, vz: Math.sin(a) * sp,
            life: 0.26 + rand() * 0.18, maxLife: 0.44,
            size: 4 + rand() * 4,
            r: 2.2, g: 1.5, b: 2.5
          };
        });
        shockLayer.spawn({
          x: x, y: y, radius: 16, growth: 110, alpha: 0.74,
          life: 0.46, maxLife: 0.46, r: 0.9, g: 0.48, b: 1.25
        });
        shockLayer.spawn({
          x: x, y: y, radius: 8, growth: 62, alpha: 0.46,
          life: 0.3, maxLife: 0.3, r: 1.2, g: 0.62, b: 1.5
        });
        scorchLayer.spawn({
          x: x, y: y, radius: 36 + rand() * 10, growth: 0, alpha: 0.48,
          life: 13, maxLife: 13, hold: true, r: 0.1, g: 0.04, b: 0.16
        });
        flashAt(x, y, 0xf2e6ff);
      } else if (kind === 'iris') {
        burst(fireLayer, 6, function () {
          const a = rand() * TAU;
          const sp = 90 + rand() * 140;
          return {
            x: x, y: 7, z: y,
            vx: Math.cos(a) * sp, vy: 30 + rand() * 60, vz: Math.sin(a) * sp,
            life: 0.18 + rand() * 0.16, maxLife: 0.34,
            size: 3 + rand() * 3,
            r: 1.9, g: 1.15, b: 2.05
          };
        });
        shockLayer.spawn({
          x: x, y: y, radius: 5, growth: 40, alpha: 0.5,
          life: 0.22, maxLife: 0.22, r: 1.2, g: 0.7, b: 1.15
        });
      } else if (kind === 'crystal') {
        burst(fireLayer, 7, function () {
          const a = rand() * TAU;
          const sp = 70 + rand() * 120;
          return {
            x: x, y: 6, z: y,
            vx: Math.cos(a) * sp, vy: 40 + rand() * 70, vz: Math.sin(a) * sp,
            life: 0.2 + rand() * 0.18, maxLife: 0.38,
            size: 4 + rand() * 3,
            r: 1.6, g: 0.7, b: 2.15
          };
        });
        shockLayer.spawn({
          x: x, y: y, radius: 6, growth: 36, alpha: 0.48,
          life: 0.24, maxLife: 0.24, r: 0.9, g: 0.5, b: 1.2
        });
      } else if (kind === 'arcane') {
        burst(fireLayer, 7, function () {
          const a = rand() * TAU;
          const sp = 80 + rand() * 130;
          return {
            x: x, y: 6, z: y,
            vx: Math.cos(a) * sp, vy: 50 + rand() * 90, vz: Math.sin(a) * sp,
            life: 0.22 + rand() * 0.2, maxLife: 0.42,
            size: 4 + rand() * 4,
            r: 1.55, g: 0.55, b: 2.15
          };
        });
        shockLayer.spawn({
          x: x, y: y, radius: 6, growth: 40, alpha: 0.5,
          life: 0.26, maxLife: 0.26, r: 0.85, g: 0.4, b: 1.15
        });
      } else if (kind === 'tesla') {
        burst(fireLayer, 7, function () {
          const a = rand() * TAU;
          const sp = 110 + rand() * 160;
          return {
            x: x, y: 8, z: y,
            vx: Math.cos(a) * sp, vy: 20 + rand() * 50, vz: Math.sin(a) * sp,
            life: 0.14 + rand() * 0.12, maxLife: 0.26,
            size: 3 + rand() * 3,
            r: 0.55, g: 1.35, b: 2.3
          };
        });
        shockLayer.spawn({
          x: x, y: y, radius: 5, growth: 28, alpha: 0.45,
          life: 0.16, maxLife: 0.16, r: 0.5, g: 0.85, b: 1.3
        });
      } else if (kind === 'laser') {
        burst(fireLayer, 5, function () {
          const a = rand() * TAU;
          return {
            x: x, y: 8, z: y,
            vx: Math.cos(a) * 40, vy: 10, vz: Math.sin(a) * 40,
            life: 0.12 + rand() * 0.08, maxLife: 0.2,
            size: 6 + rand() * 4,
            r: 0.85, g: 1.6, b: 1.8
          };
        });
        shockLayer.spawn({
          x: x, y: y, radius: 4, growth: 22, alpha: 0.4,
          life: 0.14, maxLife: 0.14, r: 0.7, g: 1.15, b: 1.25
        });
      } else {
        burst(fireLayer, 9, function () {
          const a = rand() * TAU;
          const sp = 90 + rand() * 150;
          return {
            x: x, y: 5, z: y,
            vx: Math.cos(a) * sp, vy: 60 + rand() * 110, vz: Math.sin(a) * sp,
            life: 0.2 + rand() * 0.22, maxLife: 0.42,
            size: 4 + rand() * 4,
            r: 1.0, g: 0.8, b: 0.4
          };
        });
        burst(smokeLayer, 4, function () {
          const a = rand() * TAU;
          const grey = 0.2 + rand() * 0.1;
          return {
            x: x, y: 6, z: y,
            vx: Math.cos(a) * 30, vy: 26 + rand() * 22, vz: Math.sin(a) * 30,
            life: 0.5 + rand() * 0.4, maxLife: 0.9,
            size: 11 + rand() * 8, grow: true, buoyancy: -0.1,
            r: grey, g: grey, b: grey * 0.94
          };
        });
        shockLayer.spawn({
          x: x, y: y, radius: 6, growth: 34, alpha: 0.4,
          life: 0.22, maxLife: 0.22, r: 1.0, g: 0.85, b: 0.5
        });
      }
    } else if (type === 'muzzle') {
      if (kind === 'meteor') {
        burst(fireLayer, 8, function () {
          const a = rand() * TAU;
          return {
            x: x + (rand() - 0.5) * 8, y: 16 + rand() * 8, z: y + (rand() - 0.5) * 8,
            vx: Math.cos(a) * 36, vy: 28 + rand() * 40, vz: Math.sin(a) * 36,
            life: 0.18 + rand() * 0.12, maxLife: 0.3,
            size: 7 + rand() * 5,
            r: 1.7, g: 0.62, b: 2.2
          };
        });
        burst(fireLayer, 6, function () {
          const a = rand() * TAU;
          return {
            x: x, y: 2 + rand() * 3, z: y,
            vx: Math.cos(a) * 52, vy: 8 + rand() * 16, vz: Math.sin(a) * 52,
            life: 0.22 + rand() * 0.12, maxLife: 0.34,
            size: 4 + rand() * 3,
            r: 1.45, g: 0.5, b: 2.05
          };
        });
        shockLayer.spawn({
          x: x, y: y, radius: 8, growth: 70, alpha: 0.55,
          life: 0.32, maxLife: 0.32, r: 0.85, g: 0.42, b: 1.15
        });
        scorchLayer.spawn({
          x: x, y: y, radius: 16, growth: 10, alpha: 0.28,
          life: 1.6, maxLife: 1.6, hold: true, r: 0.12, g: 0.05, b: 0.18
        });
        flashAt(x, y, 0xd6a6ff);
      } else if (kind === 'comet') {
        burst(fireLayer, 10, function () {
          const a = rand() * TAU;
          return {
            x: x + (rand() - 0.5) * 10, y: 22 + rand() * 10, z: y + (rand() - 0.5) * 10,
            vx: Math.cos(a) * 42, vy: 36 + rand() * 48, vz: Math.sin(a) * 42,
            life: 0.22 + rand() * 0.14, maxLife: 0.36,
            size: 8 + rand() * 6,
            r: 1.85, g: 0.7, b: 2.3
          };
        });
        burst(fireLayer, 7, function () {
          const a = rand() * TAU;
          return {
            x: x, y: 2 + rand() * 3, z: y,
            vx: Math.cos(a) * 64, vy: 10 + rand() * 18, vz: Math.sin(a) * 64,
            life: 0.26 + rand() * 0.14, maxLife: 0.4,
            size: 4 + rand() * 3,
            r: 1.55, g: 0.55, b: 2.1
          };
        });
        shockLayer.spawn({
          x: x, y: y, radius: 10, growth: 86, alpha: 0.6,
          life: 0.36, maxLife: 0.36, r: 0.9, g: 0.45, b: 1.2
        });
        scorchLayer.spawn({
          x: x, y: y, radius: 20, growth: 12, alpha: 0.3,
          life: 1.8, maxLife: 1.8, hold: true, r: 0.14, g: 0.05, b: 0.2
        });
        flashAt(x, y, 0xf2e6ff);
      } else {
        burst(fireLayer, 5, function () {
          const a = rand() * TAU;
          return {
            x: x, y: 11, z: y,
            vx: Math.cos(a) * 40, vy: 14, vz: Math.sin(a) * 40,
            life: 0.09 + rand() * 0.06, maxLife: 0.15,
            size: 9 + rand() * 6,
            r: 1.0, g: 0.94, b: 0.68
          };
        });
      }
    } else if (type === 'complete') {
      burst(fireLayer, 10, function (i) {
        const a = (i / 20) * TAU;
        return {
          x: x + Math.cos(a) * 26, y: 4, z: y + Math.sin(a) * 26,
          vx: Math.cos(a) * 14, vy: 95 + rand() * 70, vz: Math.sin(a) * 14,
          life: 0.7 + rand() * 0.5, maxLife: 1.2,
          size: 7 + rand() * 5, buoyancy: -0.5,
          r: 0.42, g: 1.0, b: 0.72
        };
      });
      shockLayer.spawn({
        x: x, y: y, radius: 16, growth: 78, alpha: 0.6,
        life: 0.75, maxLife: 0.75, r: 0.4, g: 1.0, b: 0.7
      });
    } else if (type === 'smoke') {
      // 残血建筑的持续冒烟
      const grey = 0.17 + Math.random() * 0.1;
      emit(smokeLayer, {
        x: x, y: 14, z: y,
        vx: (rand() - 0.5) * 18, vy: 34 + rand() * 26, vz: (rand() - 0.5) * 18,
        life: 1.4 + rand() * 1.0, maxLife: 2.4,
        size: 16 + rand() * 14, grow: true, buoyancy: -0.14,
        r: grey, g: grey * 0.96, b: grey * 0.92
      });
    } else if (type === 'sell') {
      burst(fireLayer, 12, function () {
        const a = rand() * TAU;
        return {
          x: x, y: 6, z: y,
          vx: Math.cos(a) * 70, vy: 60 + rand() * 60, vz: Math.sin(a) * 70,
          life: 0.4 + rand() * 0.3, maxLife: 0.7,
          size: 6 + rand() * 4,
          r: 1.0, g: 0.78, b: 0.28
        };
      });
    } else if (type === 'promote') {
      // 晋升礼花：金色星点腾空 + 地面扩散一道金环。金色写成 >1 的线性值，
      // 走自发光被辉光提出来；与爆炸的橙、完工的绿在色相上区分开。
      burst(fireLayer, 16, function (i) {
        const a = (i / 16) * TAU + rand() * 0.6;
        return {
          x: x + Math.cos(a) * 7, y: 5 + rand() * 8, z: y + Math.sin(a) * 7,
          vx: Math.cos(a) * (10 + rand() * 14),
          vy: 130 + rand() * 100,
          vz: Math.sin(a) * (10 + rand() * 14),
          life: 0.6 + rand() * 0.45, maxLife: 1.05,
          size: 5 + rand() * 4, buoyancy: -0.4,
          r: 2.3, g: 1.85, b: 0.5
        };
      });
      shockLayer.spawn({
        x: x, y: y, radius: 9, growth: 96, alpha: 0.85,
        life: 0.6, maxLife: 0.6, r: 1.0, g: 0.85, b: 0.3
      });
    } else if (type === 'hq_salute') {
      // 连点主堡：多冒几口烟，雷达/顶晶在结构循环里短暂加速。
      burst(smokeLayer, 6, function () {
        const a = rand() * TAU;
        const grey = 0.2 + rand() * 0.1;
        return {
          x: x + Math.cos(a) * 18, y: 16, z: y + Math.sin(a) * 18,
          vx: Math.cos(a) * 12, vy: 40 + rand() * 28, vz: Math.sin(a) * 12,
          life: 1.2 + rand() * 0.6, maxLife: 1.8,
          size: 14 + rand() * 10, grow: true, buoyancy: -0.12,
          r: grey, g: grey * 0.96, b: grey * 0.9
        };
      });
      shockLayer.spawn({
        x: x, y: y, radius: 12, growth: 70, alpha: 0.55,
        life: 0.55, maxLife: 0.55, r: 1.0, g: 0.82, b: 0.35
      });
    }
  }

  function updateEffects(dt) {
    updateParticleLayer(fireLayer, dt, 0.90, 190);
    updateParticleLayer(smokeLayer, dt, 0.955, 190);
    updateDecalLayer(shockLayer, dt, 3.5);
    updateDecalLayer(scorchLayer, dt, 2.2);
    updateFlashes(dt);
  }

  /* -------------------- 选中环 / 建造预览 -------------------- */

  /**
   * 选中标记：四段带缺口的弧 + 一圈淡内环，整体缓慢自转。
   * 比一个完整圆环更像瞄准框，也更容易在杂乱地形上分辨出来。
   */
  function selectionBracketGeometry() {
    const arcs = [];
    for (let i = 0; i < 4; i++) {
      const start = i * (Math.PI / 2) - 0.42;
      const outer = new THREE.RingGeometry(0.82, 1.0, 10, 1, start, 0.84);
      outer.rotateX(-Math.PI / 2);
      arcs.push({ geo: outer, shade: 1 });
      // 弧末端的小刻线
      const tick = new THREE.RingGeometry(0.66, 1.0, 2, 1, start, 0.06);
      tick.rotateX(-Math.PI / 2);
      arcs.push({ geo: tick, shade: 1 });
    }
    const inner = new THREE.RingGeometry(0.44, 0.48, 24);
    inner.rotateX(-Math.PI / 2);
    arcs.push({ geo: inner, shade: 0.5 });
    return mergeParts(arcs);
  }

  const ringGeo = selectionBracketGeometry();
  const ringMaterial = new THREE.MeshBasicMaterial({
    vertexColors: true, transparent: true, opacity: 0.95,
    depthWrite: false, fog: false, side: THREE.DoubleSide, toneMapped: false
  });
  let ringMesh = null;

  function ensureRingMesh(needed) {
    if (ringMesh && ringMesh.instanceMatrix.count >= needed) return ringMesh;
    if (ringMesh) {
      worldRoot.remove(ringMesh);
      ringMesh.dispose();
    }
    ringMesh = new THREE.InstancedMesh(ringGeo, ringMaterial,
      Math.max(32, Math.ceil(needed * 1.5)));
    ringMesh.instanceMatrix.setUsage(THREE.DynamicDrawUsage);
    ringMesh.frustumCulled = false;
    ringMesh.renderOrder = 3;
    ringMesh.count = 0;
    worldRoot.add(ringMesh);
    return ringMesh;
  }

  // 军衔环：连续细金圈，无括弧无刻线、静止不转 —— 和「旋转的选中括弧环」一眼
  // 区分开。让老兵以上(3/8/16 杀)的单位即便没被选中，也能在军团里被一眼认出。
  // 颜色沿用选中环的三档军衔配色，仅亮度略低，避免大片金环盖过「选中」语义。
  const rankRingGeo = new THREE.RingGeometry(0.84, 1.0, 28)
    .rotateX(-Math.PI / 2);
  const rankRingMaterial = new THREE.MeshBasicMaterial({
    transparent: true, opacity: 0.9, depthWrite: false,
    fog: false, side: THREE.DoubleSide, toneMapped: false
  });
  let rankRingMesh = null;
  const rankRingVisuals = [];

  function ensureRankRingMesh(needed) {
    if (rankRingMesh && rankRingMesh.instanceMatrix.count >= needed) {
      return rankRingMesh;
    }
    if (rankRingMesh) {
      worldRoot.remove(rankRingMesh);
      rankRingMesh.dispose();
    }
    rankRingMesh = new THREE.InstancedMesh(rankRingGeo, rankRingMaterial,
      Math.max(16, Math.ceil(needed * 1.5)));
    rankRingMesh.instanceMatrix.setUsage(THREE.DynamicDrawUsage);
    rankRingMesh.frustumCulled = false;
    rankRingMesh.renderOrder = 3;
    rankRingMesh.count = 0;
    worldRoot.add(rankRingMesh);
    return rankRingMesh;
  }

  let previewGroup = null;
  let previewKind = null;
  const previewTeamMat = new THREE.MeshLambertMaterial({
    color: 0x66ff99, transparent: true, opacity: 0.5, depthWrite: false, vertexColors: true
  });
  const rangeRing = new THREE.Mesh(
    new THREE.RingGeometry(0.97, 1.0, 64).rotateX(-Math.PI / 2),
    new THREE.MeshBasicMaterial({
      color: 0x5fe0a0, transparent: true, opacity: 0.35,
      depthWrite: false, fog: false, side: THREE.DoubleSide
    })
  );
  rangeRing.visible = false;
  rangeRing.renderOrder = 4;
  worldRoot.add(rangeRing);

  function updatePreview(preview) {
    if (!preview) {
      if (previewGroup) previewGroup.visible = false;
      rangeRing.visible = false;
      return;
    }
    if (previewKind !== preview.kind) {
      if (previewGroup) {
        worldRoot.remove(previewGroup);   // 几何体是共享的，不释放
      }
      previewGroup = structureGroup(preview.kind, preview.size, previewTeamMat);
      previewGroup.traverse(function (o) {
        o.castShadow = false;
        o.receiveShadow = false;
      });
      previewGroup.renderOrder = 6;
      worldRoot.add(previewGroup);
      previewKind = preview.kind;
    }
    previewGroup.visible = true;
    previewGroup.position.set(preview.x, groundHeight(preview.x, preview.y), preview.y);
    const tint = preview.valid ? 0x66ff99 : 0xff5a5a;
    previewTeamMat.color.setHex(tint);

    if (preview.anchorRadius) {
      rangeRing.visible = true;
      rangeRing.position.set(preview.anchorX,
        groundHeight(preview.anchorX, preview.anchorY) + 8, preview.anchorY);
      rangeRing.scale.set(preview.anchorRadius, 1, preview.anchorRadius);
    } else {
      rangeRing.visible = false;
    }
  }

  /* -------------------- 相机 -------------------- */

  const groundPlane = new THREE.Plane(new THREE.Vector3(0, 1, 0), 0);
  const raycaster = new THREE.Raycaster();
  const ndc = new THREE.Vector2();
  const hitPoint = new THREE.Vector3();
  const projected = new THREE.Vector3();
  let appliedCamX = NaN;
  let appliedCamY = NaN;
  let appliedZoom = NaN;
  let appliedYaw = NaN;
  let appliedPitch = NaN;
  let appliedViewWidth = -1;
  let appliedViewHeight = -1;

  function applyCamera() {
    if (appliedCamX === state.camX && appliedCamY === state.camY &&
        appliedZoom === state.zoom && appliedYaw === state.yaw &&
        appliedPitch === state.pitch && appliedViewWidth === state.width &&
        appliedViewHeight === state.height) {
      return false;
    }
    appliedCamX = state.camX;
    appliedCamY = state.camY;
    appliedZoom = state.zoom;
    appliedYaw = state.yaw;
    appliedPitch = state.pitch;
    appliedViewWidth = state.width;
    appliedViewHeight = state.height;
    // zoom 沿用 2D 版语义：越大越近。换算成相机到焦点的距离。
    // 620 而不是 900：同样的 zoom 值下镜头离地面更近，单位看得更清楚
    const dist = THREE.MathUtils.clamp(620 / Math.max(0.12, state.zoom), 190, 4200);
    const pitch = state.pitch;
    const yaw = state.yaw;
    const fx = state.camX;
    const fz = state.camY;
    camera.position.set(
      fx - Math.sin(yaw) * Math.cos(pitch) * dist,
      Math.sin(pitch) * dist,
      fz + Math.cos(yaw) * Math.cos(pitch) * dist
    );
    camera.lookAt(fx, 0, fz);
    camera.updateMatrixWorld();

    // 天空球跟着相机平移，尺寸略小于远裁剪面
    sky.position.copy(camera.position);
    sky.scale.setScalar(camera.far * 0.85);

    // 亮色大气雾：起点推远一些，近景通透；远景慢慢融进天光
    scene.fog.near = dist * 2.2 + 600;
    scene.fog.far = dist * 6.5 + 3200;

    // 阴影关闭时不更新一套完全不会参与渲染的投影矩阵。
    if (state.shadows !== 'off') {
      const span = Math.min(1500, dist * 0.9 + 300);
      sun.position.set(fx + 700, 1150, fz - 500);
      sun.target.position.set(fx, 0, fz);
      sun.target.updateMatrixWorld();
      const cam = sun.shadow.camera;
      cam.left = -span; cam.right = span;
      cam.top = span; cam.bottom = -span;
      cam.updateProjectionMatrix();
    }

    // 补光从主光对面打，轮廓光从相机背后偏上打，勾出边缘
    fill.position.set(fx - 900, 620, fz + 800);
    rim.position.set(
      fx - Math.sin(yaw) * 1400,
      900,
      fz + Math.cos(yaw) * 1400);
    return true;
  }

  function screenToWorld(sx, sy) {
    ndc.x = (sx / state.width) * 2 - 1;
    ndc.y = -(sy / state.height) * 2 + 1;
    raycaster.setFromCamera(ndc, camera);
    if (!raycaster.ray.intersectPlane(groundPlane, hitPoint)) {
      return { x: state.camX, y: state.camY };
    }
    return { x: hitPoint.x, y: hitPoint.z };
  }

  function worldToScreen(x, y, height) {
    projected.set(x, height || 0, y);
    projected.project(camera);
    return {
      x: (projected.x * 0.5 + 0.5) * state.width,
      y: (-projected.y * 0.5 + 0.5) * state.height,
      behind: projected.z > 1
    };
  }

  /* -------------------- 逐帧渲染 -------------------- */

  // 逐帧复用，避免每单位每帧都分配临时对象
  const matrix = new THREE.Matrix4();
  const quat = new THREE.Quaternion();
  const quatIdentity = new THREE.Quaternion();
  const vecPos = new THREE.Vector3();
  const vecScale = new THREE.Vector3(1, 1, 1);
  const vecAux = new THREE.Vector3();
  const tmpColor = new THREE.Color();
  const upAxis = new THREE.Vector3(0, 1, 0);

  // 单位插值：服务端 8Hz，渲染 60Hz，必须补间
  const visual = new Map();
  const snapshotVisuals = [];
  const byKindCache = new Map();
  let renderGeneration = 0;
  let lastFogGame = null;
  let lastEntityGame = null;
  let lastOreAt = -Infinity;
  let lastBarsAt = -Infinity;

  function colorOf(owner) {
    if (owner === 'neutral') return '#c79545';
    return state.palette.get(owner) || '#8fa2ad';
  }

  // 地面可见区域是一个随俯角旋转的梯形。以前用以镜头焦点为圆心的大圆
  // 做剔除，在宽屏和拉远时会把屏幕背后大量单位也提交给 GPU。四个屏幕角
  // 反投影后取保守 AABB，保留边缘余量，既不会切掉进入画面的单位，也不会
  // 为完全离屏的军团做插值、落地采样和实例矩阵上传。
  const viewportBounds = { minX: 0, minY: 0, maxX: 0, maxY: 0 };
  function updateViewportBounds(margin) {
    const a = screenToWorld(0, 0);
    const b = screenToWorld(state.width, 0);
    const c = screenToWorld(0, state.height);
    const d = screenToWorld(state.width, state.height);
    viewportBounds.minX = Math.max(-margin,
      Math.min(a.x, b.x, c.x, d.x) - margin);
    viewportBounds.maxX = Math.min(state.map.width + margin,
      Math.max(a.x, b.x, c.x, d.x) + margin);
    viewportBounds.minY = Math.max(-margin,
      Math.min(a.y, b.y, c.y, d.y) - margin);
    viewportBounds.maxY = Math.min(state.map.height + margin,
      Math.max(a.y, b.y, c.y, d.y) + margin);
  }

  function inViewportBounds(x, y) {
    return x >= viewportBounds.minX && x <= viewportBounds.maxX &&
      y >= viewportBounds.minY && y <= viewportBounds.maxY;
  }

  function guessImpactKind(x, y, hints) {
    let best = null;
    let bestD = 130 * 130;
    for (let i = 0; i < hints.length; i++) {
      const p = hints[i];
      const d1 = (p.tx - x) * (p.tx - x) + (p.ty - y) * (p.ty - y);
      const d2 = (p.x - x) * (p.x - x) + (p.y - y) * (p.y - y);
      const d = d1 < d2 ? d1 : d2;
      if (d < bestD) {
        bestD = d;
        best = p.kind;
      }
    }
    return best;
  }

  function guessMuzzleKind(x, y, hints) {
    let best = null;
    let bestD = 40 * 40;
    for (let i = 0; i < hints.length; i++) {
      const p = hints[i];
      const d = (p.x - x) * (p.x - x) + (p.y - y) * (p.y - y);
      if (d < bestD) {
        bestD = d;
        best = p.kind;
      }
    }
    return best;
  }

  function writeTracer(mesh, index, x, height, z, yaw, sx, sy, sz, colorHex) {
    quat.setFromAxisAngle(upAxis, -yaw);
    matrix.compose(vecPos.set(x, height, z), quat, vecScale.set(sx, sy, sz));
    mesh.setMatrixAt(index, matrix);
    tmpColor.setHex(colorHex);
    mesh.setColorAt(index, tmpColor);
  }

  function emitProjectileTrail(look, x, height, y) {
    if (fireLayer.list.length > state.particleBudget * 0.62) return;
    if (look === 'fireball') {
      emit(fireLayer, {
        x: x + (Math.random() - 0.5) * 5, y: height, z: y + (Math.random() - 0.5) * 5,
        vx: (Math.random() - 0.5) * 16, vy: 8 + Math.random() * 14, vz: (Math.random() - 0.5) * 16,
        life: 0.22, maxLife: 0.22, size: 6 + Math.random() * 5,
        r: 2.2, g: 0.95, b: 0.25
      });
    } else if (look === 'shard') {
      emit(fireLayer, {
        x: x, y: height, z: y,
        vx: (Math.random() - 0.5) * 9, vy: 4 + Math.random() * 9, vz: (Math.random() - 0.5) * 9,
        life: 0.28, maxLife: 0.28, size: 3.4 + Math.random() * 3,
        r: 0.7, g: 1.4, b: 1.9
      });
    } else if (look === 'crystal') {
      emit(fireLayer, {
        x: x, y: height, z: y,
        vx: (Math.random() - 0.5) * 8, vy: 5 + Math.random() * 8, vz: (Math.random() - 0.5) * 8,
        life: 0.24, maxLife: 0.24, size: 3.2 + Math.random() * 2.6,
        r: 1.55, g: 0.7, b: 2.15
      });
    } else if (look === 'meteor') {
      emit(fireLayer, {
        x: x + (Math.random() - 0.5) * 6, y: height, z: y + (Math.random() - 0.5) * 6,
        vx: (Math.random() - 0.5) * 12, vy: -8 + Math.random() * 6, vz: (Math.random() - 0.5) * 12,
        life: 0.3, maxLife: 0.3, size: 5.4 + Math.random() * 4.2,
        r: 1.75, g: 0.68, b: 2.25
      });
    } else if (look === 'comet') {
      emit(fireLayer, {
        x: x + (Math.random() - 0.5) * 8, y: height, z: y + (Math.random() - 0.5) * 8,
        vx: (Math.random() - 0.5) * 14, vy: -10 + Math.random() * 7, vz: (Math.random() - 0.5) * 14,
        life: 0.36, maxLife: 0.36, size: 6.4 + Math.random() * 5,
        r: 1.9, g: 0.75, b: 2.35
      });
    } else if (look === 'bolt') {
      emit(fireLayer, {
        x: x, y: height, z: y,
        vx: (Math.random() - 0.5) * 7, vy: 6, vz: (Math.random() - 0.5) * 7,
        life: 0.18, maxLife: 0.18, size: 3.1,
        r: 1.5, g: 0.55, b: 2.1
      });
    } else if (look === 'arc') {
      emit(fireLayer, {
        x: x, y: height, z: y,
        vx: (Math.random() - 0.5) * 28, vy: 4, vz: (Math.random() - 0.5) * 28,
        life: 0.1, maxLife: 0.1, size: 2.6,
        r: 0.55, g: 1.4, b: 2.3
      });
    }
  }

  function emitIdleAura(vis, dt, useSimple) {
    if (useSimple) return;
    const kind = vis.unit.kind;
    if (kind !== 'frost' && kind !== 'dragon' && kind !== 'mage'
        && kind !== 'warden' && kind !== 'colossus' && kind !== 'comet'
        && kind !== 'bomb_truck' && kind !== 'hexling'
        && kind !== 'imp' && kind !== 'oracle') return;
    if (fireLayer.list.length > state.particleBudget * 0.5) return;
    const rate = kind === 'dragon' ? 8 : kind === 'frost' ? 6
      : kind === 'bomb_truck' ? 7 : kind === 'hexling' ? 6
      : kind === 'colossus' ? 7 : kind === 'comet' ? 6 : kind === 'warden' ? 4
      : kind === 'oracle' ? 4 : kind === 'imp' ? 3 : 3.5;
    if (Math.random() > dt * rate) return;
    const gy = vis.groundY == null ? groundHeight(vis.x, vis.y) : vis.groundY;
    const scale = UNIT_VISUAL_SCALE[kind] || 1;
    if (kind === 'frost') {
      emit(fireLayer, {
        x: vis.x + (Math.random() - 0.5) * 12,
        y: gy + 3 + Math.random() * 14,
        z: vis.y + (Math.random() - 0.5) * 12,
        vx: (Math.random() - 0.5) * 7, vy: 8 + Math.random() * 10, vz: (Math.random() - 0.5) * 7,
        life: 0.5, maxLife: 0.5, size: 3.5 + Math.random() * 3,
        r: 0.65, g: 1.35, b: 1.85
      });
    } else if (kind === 'dragon') {
      const mx = vis.x + Math.cos(vis.dir) * 22 * scale * 0.55;
      const mz = vis.y + Math.sin(vis.dir) * 22 * scale * 0.55;
      emit(fireLayer, {
        x: mx, y: gy + 16 * scale * 0.55, z: mz,
        vx: Math.cos(vis.dir) * 16 + (Math.random() - 0.5) * 8,
        vy: 6 + Math.random() * 10,
        vz: Math.sin(vis.dir) * 16 + (Math.random() - 0.5) * 8,
        life: 0.28, maxLife: 0.28, size: 5 + Math.random() * 4,
        r: 2.2, g: 1.0, b: 0.28
      });
    } else if (kind === 'colossus') {
      if (Math.random() < 0.58) {
        emit(fireLayer, {
          x: vis.x + (Math.random() - 0.5) * 22,
          y: gy + 0.6 + Math.random() * 2.6,
          z: vis.y + (Math.random() - 0.5) * 22,
          vx: (Math.random() - 0.5) * 10, vy: 4 + Math.random() * 8, vz: (Math.random() - 0.5) * 10,
          life: 0.38, maxLife: 0.38, size: 3.2 + Math.random() * 2.8,
          r: 1.5, g: 0.55, b: 2.1
        });
      } else {
        const mx = vis.x + Math.cos(vis.dir) * 10 * scale;
        const mz = vis.y + Math.sin(vis.dir) * 10 * scale;
        emit(fireLayer, {
          x: mx + (Math.random() - 0.5) * 4,
          y: gy + 18 * scale * 0.55,
          z: mz + (Math.random() - 0.5) * 4,
          vx: (Math.random() - 0.5) * 4, vy: 8 + Math.random() * 8, vz: (Math.random() - 0.5) * 4,
          life: 0.42, maxLife: 0.42, size: 4.2 + Math.random() * 3,
          r: 1.7, g: 0.7, b: 2.2
        });
      }
    } else if (kind === 'comet') {
      const mx = vis.x + Math.cos(vis.dir) * 8 * scale;
      const mz = vis.y + Math.sin(vis.dir) * 8 * scale;
      emit(fireLayer, {
        x: mx + (Math.random() - 0.5) * 6,
        y: gy + 22 * scale * 0.55 + Math.random() * 8,
        z: mz + (Math.random() - 0.5) * 6,
        vx: (Math.random() - 0.5) * 5, vy: 10 + Math.random() * 8, vz: (Math.random() - 0.5) * 5,
        life: 0.4, maxLife: 0.4, size: 4.6 + Math.random() * 3.4,
        r: 1.85, g: 0.72, b: 2.3
      });
    } else if (kind === 'warden') {
      emit(fireLayer, {
        x: vis.x + (Math.random() - 0.5) * 8,
        y: gy + 10 + Math.random() * 8,
        z: vis.y + (Math.random() - 0.5) * 8,
        vx: 0, vy: 11, vz: 0,
        life: 0.36, maxLife: 0.36, size: 3.0,
        r: 1.4, g: 0.7, b: 2.05
      });
    } else if (kind === 'bomb_truck') {
      emit(fireLayer, {
        x: vis.x + (Math.random() - 0.5) * 6,
        y: gy + 16 + Math.random() * 6,
        z: vis.y + (Math.random() - 0.5) * 6,
        vx: (Math.random() - 0.5) * 4, vy: 16 + Math.random() * 10, vz: (Math.random() - 0.5) * 4,
        life: 0.28, maxLife: 0.28, size: 3.4,
        r: 2.3, g: 1.1, b: 0.28
      });
    } else if (kind === 'hexling') {
      emit(fireLayer, {
        x: vis.x + (Math.random() - 0.5) * 6,
        y: gy + 7 + Math.random() * 5,
        z: vis.y + (Math.random() - 0.5) * 6,
        vx: (Math.random() - 0.5) * 6, vy: 10 + Math.random() * 8, vz: (Math.random() - 0.5) * 6,
        life: 0.28, maxLife: 0.28, size: 3.6,
        r: 2.25, g: 0.7, b: 0.55
      });
    } else if (kind === 'imp') {
      emit(fireLayer, {
        x: vis.x + (Math.random() - 0.5) * 6,
        y: gy + 3 + Math.random() * 4,
        z: vis.y + (Math.random() - 0.5) * 6,
        vx: 0, vy: 8, vz: 0,
        life: 0.26, maxLife: 0.26, size: 2.2,
        r: 0.55, g: 1.55, b: 2.05
      });
    } else if (kind === 'oracle') {
      emit(fireLayer, {
        x: vis.x + (Math.random() - 0.5) * 4,
        y: gy + 14 + Math.random() * 6,
        z: vis.y + (Math.random() - 0.5) * 4,
        vx: 0, vy: 12, vz: 0,
        life: 0.34, maxLife: 0.34, size: 2.8,
        r: 1.85, g: 1.15, b: 2.0
      });
    } else {
      emit(fireLayer, {
        x: vis.x + (Math.random() - 0.5) * 7,
        y: gy + 12 + Math.random() * 6,
        z: vis.y + (Math.random() - 0.5) * 7,
        vx: 0, vy: 14, vz: 0,
        life: 0.35, maxLife: 0.35, size: 3.2,
        r: 1.45, g: 0.52, b: 2.05
      });
    }
  }

  function render(payload) {
    const game = payload.game;
    const dt = payload.dt;
    if (!game || !state.map) return;

    const cameraChanged = applyCamera();
    const camDist = camera.position.distanceTo(
      vecPos.set(state.camX, 0, state.camY));
    if (cameraChanged) updateViewportBounds(190);
    // 迷雾只依赖服务端快照中的位置。过去 60FPS 每帧都重画一张 Canvas、
    // 上传一次纹理；大军团时这是持续卡顿的主要来源之一。每个 8Hz 快照更新
    // 一次即可，单位本身仍然按 60FPS 插值。
    if (game !== lastFogGame) {
      collectVision(game);
      updateFog();
      lastFogGame = game;
    }

    /* --- 单位 --- */
    state.snapshotUnits = game.units.length;
    state.renderedUnits = 0;
    // Map 查找、实体创建和阵亡清理只在 8Hz 网络快照变化时做一次。上一版把
    // 它们放在 60Hz 热循环中，400 单位时每秒会产生两万多次无意义查找。
    if (game !== lastEntityGame) {
      renderGeneration++;
      snapshotVisuals.length = game.units.length;
      for (let i = 0; i < game.units.length; i++) {
        const u = game.units[i];
        let vis = visual.get(u.id);
        if (!vis) {
          vis = { x: u.x, y: u.y, dir: u.dir };
          visual.set(u.id, vis);
        }
        vis.unit = u;
        vis.seen = renderGeneration;
        snapshotVisuals[i] = vis;
      }
      visual.forEach(function (vis, id) {
        if (vis.seen !== renderGeneration) {
          if (isVisible(vis.x, vis.y)) spawnEffect('explosion', vis.x, vis.y);
          visual.delete(id);
        }
      });

      for (let i = 0; i < game.structures.length; i++) {
        const s = game.structures[i];
        const node = ensureStructure(s);
        node.seen = renderGeneration;
        node.structure = s;
      }
      structureNodes.forEach(function (node, id) {
        if (node.seen === renderGeneration) return;
        if (node.group.visible) {
          spawnEffect('explosion', node.group.position.x, node.group.position.z);
        }
        disposeStructure(id);
      });
      lastEntityGame = game;
    }

    byKindCache.forEach(function (list) { list.length = 0; });
    const byKind = byKindCache;
    let movingVisibleBar = false;
    for (let i = 0; i < snapshotVisuals.length; i++) {
      const vis = snapshotVisuals[i];
      const u = vis.unit;
      // 离屏单位直接吸附到最新快照；它们重新进入带余量的视口时再恢复 60Hz
      // 插值。这样镜头另一端的几百个单位只付一次边界比较的成本。
      if (!inViewportBounds(u.x, u.y) && !inViewportBounds(vis.x, vis.y)) {
        vis.x = u.x;
        vis.y = u.y;
        vis.dir = u.dir;
        vis.inRenderRange = false;
        continue;
      }
      // 位置线性追赶，朝向走最短弧
      const oldX = vis.x;
      const oldY = vis.y;
      const k = Math.min(1, dt * 13);
      vis.x += (u.x - vis.x) * k;
      vis.y += (u.y - vis.y) * k;
      let dd = u.dir - vis.dir;
      while (dd > Math.PI) dd -= TAU;
      while (dd < -Math.PI) dd += TAU;
      vis.dir += dd * Math.min(1, dt * 11);
      vis.inRenderRange = inViewportBounds(vis.x, vis.y);
      if (!vis.inRenderRange) continue;
      state.renderedUnits++;

      // 单位模型本身按渲染帧插值。只要一个实际显示血条的单位本帧发生了
      // 位移，血条也必须同帧更新，否则 60Hz 模型配 20Hz 血条会产生跳动、
      // 重影，看起来就像行进过程中不断闪烁。静止场景仍保留 20Hz 降频。
      if (!movingVisibleBar &&
          (Math.abs(vis.x - oldX) > 0.005 || Math.abs(vis.y - oldY) > 0.005)) {
        const selected = payload.selectedUnitIds.has(u.id);
        const damaged = u.maxHp > 0 && u.hp < u.maxHp * 0.999;
        const hasCargo = u.kind === 'harvester' && u.capacity && u.cargo > 0.005;
        const farOut = camDist > UNIT_LOD_DISTANCE * 1.4;
        movingVisibleBar = (damaged || selected || hasCargo) &&
          (!farOut || damaged || selected);
      }

      let bucket = byKind.get(u.kind);
      if (!bucket) { bucket = []; byKind.set(u.kind, bucket); }
      bucket.push(vis);
    }
    // 只按相机距离降模；单位数量增加不会让整场模型突然变成盒子。
    const useSimple = state.lod && camDist > UNIT_LOD_DISTANCE;

    let shadowCount = 0;
    const doShadows = state.shadows === 'all';
    const shadows = doShadows ? ensureShadowMesh(state.renderedUnits) : null;

    unitPools.forEach(function (pool) {
      if (pool.mesh) pool.mesh.count = 0;
      if (pool.simple) pool.simple.count = 0;
    });

    byKind.forEach(function (list, kind) {
      const pool = ensurePool(kind, list.length);
      const mesh = useSimple ? pool.simple : pool.mesh;
      const scale = UNIT_VISUAL_SCALE[kind] || 1;
      vecScale.set(scale, scale, scale);
      const ids = mesh.userData.instanceIds;
      const xs = mesh.userData.instanceX;
      const ys = mesh.userData.instanceY;
      const dirs = mesh.userData.instanceDir;
      const colors = mesh.userData.instanceColors;
      let matrixDirty = false;
      let colorDirty = false;
      for (let i = 0; i < list.length; i++) {
        const vis = list[i];
        let gy = vis.groundY;
        const transformDirty = ids[i] !== vis.unit.id ||
          Math.abs(xs[i] - vis.x) > 0.005 ||
          Math.abs(ys[i] - vis.y) > 0.005 ||
          Math.abs(dirs[i] - vis.dir) > 0.0001;
        if (transformDirty) {
          gy = groundHeight(vis.x, vis.y);
          vis.groundY = gy;
          quat.setFromAxisAngle(upAxis, -vis.dir);
          vecPos.set(vis.x, gy, vis.y);
          matrix.compose(vecPos, quat, vecScale);
          mesh.setMatrixAt(i, matrix);
          ids[i] = vis.unit.id;
          xs[i] = vis.x;
          ys[i] = vis.y;
          dirs[i] = vis.dir;
          matrixDirty = true;
        }
        const color = colorOf(vis.unit.owner);
        if (colors[i] !== color) {
          tmpColor.set(color);
          mesh.setColorAt(i, tmpColor);
          colors[i] = color;
          colorDirty = true;
        }

        if (doShadows) {
          const r = vis.unit.size * 1.15 * scale;
          matrix.compose(
            vecAux.set(vis.x, gy + 1.2, vis.y),
            quatIdentity,
            vecPos.set(r, 1, r));
          shadows.setMatrixAt(shadowCount++, matrix);
        }
      }
      mesh.count = list.length;
      if (matrixDirty) mesh.instanceMatrix.needsUpdate = true;
      if (colorDirty && mesh.instanceColor) mesh.instanceColor.needsUpdate = true;
      mesh.castShadow = doShadows && !useSimple;
    });

    if (shadows) {
      shadows.count = shadowCount;
      shadows.instanceMatrix.needsUpdate = true;
    }

    /* --- 建筑 --- */
    state.renderedStructures = 0;
    for (let i = 0; i < game.structures.length; i++) {
      const s = game.structures[i];
      const node = structureNodes.get(s.id);
      node.group.visible = inViewportBounds(s.x, s.y);
      if (!node.group.visible) continue;
      state.renderedStructures++;
      if (node.x !== s.x || node.y !== s.y) {
        node.x = s.x;
        node.y = s.y;
        node.groundY = groundHeight(s.x, s.y);
        node.group.position.set(s.x, node.groundY, s.y);
      }
      const teamColor = colorOf(s.owner);
      if (node.teamColor !== teamColor) {
        node.teamColor = teamColor;
        node.teamMat.color.set(teamColor);
      }
      // 建造中：从地里升起，并整体透出全息感
      if (!s.active && s.buildTotal) {
        const progress = 1 - (s.buildRemaining / s.buildTotal);
        if (node.buildProgress !== progress) {
          node.buildProgress = progress;
          node.group.scale.set(1, Math.max(0.08, progress), 1);
        }
        // 未完工时整体半透，像是在通电自检；透明度还带一点脉动
        const alpha = (0.45 + progress * 0.45) *
          (0.82 + 0.18 * Math.abs(Math.sin(payload.time * 0.006)));
        node.teamMat.opacity = alpha;
        node.teamMat.transparent = true;
      } else {
        if (node.buildProgress !== 1) {
          if (node.buildProgress != null && node.buildProgress < 0.999) {
            spawnEffect('complete', s.x, s.y);
          }
          node.buildProgress = 1;
          node.group.scale.set(1, 1, 1);
          node.teamMat.transparent = false;
          node.teamMat.opacity = 1;
        }
      }
      if (node.head && s.dir != null && node.dir !== s.dir) {
        node.dir = s.dir;
        node.head.rotation.y = -s.dir;
      }
      if (node.spinner) {
        let spinMul = 1;
        const salute = payload.hqSalute;
        if (salute && payload.time < salute.until
            && Math.hypot(s.x - salute.x, s.y - salute.y) < 10) {
          spinMul = 7;
        }
        node.spinner.rotation.y += dt * node.spinner.userData.speed * spinMul;
      }
      // 残血建筑冒烟
      const wounded = s.hp / s.maxHp;
      if (s.active && wounded < 0.55 && Math.random() < dt * (1.6 - wounded)) {
        spawnEffect('smoke', s.x + (Math.random() - 0.5) * s.size,
          s.y + (Math.random() - 0.5) * s.size);
      }
    }
    /* --- 矿脉 --- */
    if (payload.time - lastOreAt >= 50) {
      updateOre(game.ore, payload.time);
      lastOreAt = payload.time;
    }

    /* --- 补给箱 --- */
    updateCrates(game, payload.time);
    updateStrikes(game, payload.time);
    updateRallyFlags(game);

    /* --- 血条 --- */
    // 移动单位的血条逐帧跟随；没有可见血条在移动时才降到 20Hz，避免四人局
    // 为静止建筑和状态条重复上传完全相同的实例矩阵。
    if (movingVisibleBar || payload.time - lastBarsAt >= 50) {
      updateBars(game, payload.selectedUnitIds, payload.selectedStructureId,
        camDist > UNIT_LOD_DISTANCE * 1.4);
      lastBarsAt = payload.time;
    }

    /* --- 弹道 --- */
    const projectiles = game.projectiles || [];
    const projectileHints = [];
    let tracerCount = 0;
    let orbCount = 0;
    let shardCount = 0;
    if (state.showProjectiles && projectiles.length) {
      const tracers = ensureTracerMesh(projectiles.length * 4);
      const orbs = ensureTracerOrbMesh(projectiles.length);
      const shards = ensureTracerShardMesh(Math.max(8, projectiles.length));
      for (let i = 0; i < projectiles.length; i++) {
        const p = projectiles[i];
        // 近战（军犬扑咬 / 影豹爪击）不画弹道，命中反馈交给服务端的 impact 特效
        if (p.kind === 'bite' || p.kind === 'claw') continue;
        projectileHints.push({
          kind: p.kind, x: p.x, y: p.y, tx: p.targetX, ty: p.targetY
        });
        if (!inViewportBounds(p.x, p.y)) continue;
        const style = PROJECTILE_STYLE[p.kind] || PROJECTILE_STYLE.bullet;
        const t = p.t == null ? 0.5 : p.t;
        const height = 14 + style.arc * Math.sin(Math.PI * t);
        const dx = p.targetX - p.x;
        const dy = p.targetY - p.y;
        const yaw = Math.atan2(dy, dx);
        const look = style.look || 'streak';
        if (look === 'fireball') {
          writeTracer(orbs, orbCount++, p.x, height, p.y, yaw, 4.2, 4.2, 4.2, 0xffb060);
          writeTracer(tracers, tracerCount++, p.x, height, p.y, yaw,
            style.len, style.thick, style.thick, style.color);
          writeTracer(tracers, tracerCount++, p.x, height, p.y, yaw,
            style.len * 1.7, style.thick * 0.45, style.thick * 0.45, 0xffc878);
        } else if (look === 'shard') {
          writeTracer(shards, shardCount++, p.x, height, p.y, yaw, 9.5, 2.1, 2.1, 0xe8fbff);
          writeTracer(tracers, tracerCount++, p.x, height, p.y, yaw,
            style.len, style.thick * 0.7, style.thick * 0.7, style.color);
          writeTracer(shards, shardCount++, p.x, height + 1.4, p.y, yaw + 0.35, 6.2, 1.3, 1.3, 0x9fe8ff);
        } else if (look === 'crystal') {
          writeTracer(shards, shardCount++, p.x, height, p.y, yaw, 9.2, 2.0, 2.0, 0xf0d8ff);
          writeTracer(tracers, tracerCount++, p.x, height, p.y, yaw,
            style.len, style.thick * 0.7, style.thick * 0.7, style.color);
          writeTracer(shards, shardCount++, p.x, height + 1.2, p.y, yaw + 0.32, 6.0, 1.25, 1.25, 0xb46bff);
        } else if (look === 'meteor') {
          writeTracer(orbs, orbCount++, p.x, height, p.y, yaw, 4.2, 4.2, 4.2, 0xe8d0ff);
          writeTracer(tracers, tracerCount++, p.x, height, p.y, yaw,
            style.len, style.thick, style.thick, style.color);
          writeTracer(shards, shardCount++, p.x, height + 1.8, p.y, yaw, 9.2, 2.7, 2.7, 0xd6a6ff);
          writeTracer(shards, shardCount++, p.x, height - 1.2, p.y, yaw + 0.4, 6.4, 1.8, 1.8, 0xb46bff);
          writeTracer(tracers, tracerCount++, p.x, height, p.y, yaw,
            style.len * 1.55, style.thick * 0.42, style.thick * 0.42, 0xf2e6ff);
        } else if (look === 'comet') {
          writeTracer(orbs, orbCount++, p.x, height, p.y, yaw, 5.4, 5.4, 5.4, 0xf4e8ff);
          writeTracer(orbs, orbCount++, p.x, height, p.y, yaw, 3.1, 3.1, 3.1, 0xb46bff);
          writeTracer(tracers, tracerCount++, p.x, height, p.y, yaw,
            style.len, style.thick, style.thick, style.color);
          writeTracer(shards, shardCount++, p.x, height + 2.2, p.y, yaw, 11.4, 3.2, 3.2, 0xe8d0ff);
          writeTracer(shards, shardCount++, p.x, height - 1.6, p.y, yaw + 0.38, 8.2, 2.2, 2.2, 0x9a7fd0);
          writeTracer(tracers, tracerCount++, p.x, height, p.y, yaw,
            style.len * 1.85, style.thick * 0.48, style.thick * 0.48, 0xf2e6ff);
        } else if (look === 'bolt') {
          writeTracer(orbs, orbCount++, p.x, height, p.y, yaw, 2.15, 2.15, 2.15, 0xf0d0ff);
          writeTracer(tracers, tracerCount++, p.x, height, p.y, yaw,
            style.len, style.thick, style.thick, style.color);
          writeTracer(tracers, tracerCount++, p.x, height, p.y, yaw,
            style.len * 1.55, style.thick * 0.42, style.thick * 0.42, 0xe0b8ff);
        } else if (look === 'arc') {
          writeTracer(tracers, tracerCount++, p.x, height, p.y, yaw,
            style.len, style.thick, style.thick, style.color);
          writeTracer(tracers, tracerCount++, p.x + Math.sin(yaw) * 2.2, height + 1.6, p.y - Math.cos(yaw) * 2.2,
            yaw + 0.28, style.len * 0.62, style.thick * 0.55, style.thick * 0.55, 0xd8f0ff);
          writeTracer(tracers, tracerCount++, p.x - Math.sin(yaw) * 1.8, height - 1.2, p.y + Math.cos(yaw) * 1.8,
            yaw - 0.22, style.len * 0.5, style.thick * 0.45, style.thick * 0.45, 0x86b8ff);
        } else if (look === 'beam') {
          writeTracer(tracers, tracerCount++, p.x, height, p.y, yaw,
            style.len, style.thick, style.thick, style.color);
          writeTracer(tracers, tracerCount++, p.x, height, p.y, yaw,
            style.len * 0.72, style.thick * 2.1, style.thick * 2.1, 0xe8ffff);
        } else {
          writeTracer(tracers, tracerCount++, p.x, height, p.y, yaw,
            style.len, style.thick, style.thick, style.color);
        }
        if (look !== 'streak' && Math.random() < dt * 18) {
          emitProjectileTrail(look, p.x, height, p.y);
        }
      }
      tracers.count = tracerCount;
      tracers.instanceMatrix.needsUpdate = true;
      if (tracers.instanceColor) tracers.instanceColor.needsUpdate = true;
      orbs.count = orbCount;
      orbs.instanceMatrix.needsUpdate = true;
      if (orbs.instanceColor) orbs.instanceColor.needsUpdate = true;
      shards.count = shardCount;
      shards.instanceMatrix.needsUpdate = true;
      if (shards.instanceColor) shards.instanceColor.needsUpdate = true;
    } else {
      if (tracerMesh) tracerMesh.count = 0;
      if (tracerOrbMesh) tracerOrbMesh.count = 0;
      if (tracerShardMesh) tracerShardMesh.count = 0;
    }

    /* --- 特效 --- */
    // app.js 已经按 id 去重过，这里收到的都是本帧新出现的
    const fresh = payload.newEffects || [];
    for (let i = 0; i < fresh.length; i++) {
      const fx = fresh[i];
      const fxKind = fx.type === 'impact'
        ? guessImpactKind(fx.x, fx.y, projectileHintPrev)
        : (fx.kind || (fx.type === 'muzzle'
          ? guessMuzzleKind(fx.x, fx.y, projectileHints) : null));
      spawnEffect(fx.type, fx.x, fx.y, fxKind);
    }
    projectileHintPrev = projectileHints;
    if (!useSimple) {
      for (let i = 0; i < snapshotVisuals.length; i++) {
        const vis = snapshotVisuals[i];
        if (vis.inRenderRange) emitIdleAura(vis, dt, useSimple);
      }
    }
    updateEffects(dt);

    /* --- 选中环 --- */
    const selected = payload.selectedUnitIds;
    const rings = ensureRingMesh(selected.size + 2);
    let ringCount = 0;
    // 整体缓慢自转，静止时也能一眼看出「这个被选中了」
    const ringSpin = quat.setFromAxisAngle(upAxis, payload.time * 0.0006);
    selected.forEach(function (id) {
      const vis = visual.get(id);
      if (!vis || !vis.inRenderRange) return;
      const r = vis.unit.size * 1.55;
      matrix.compose(
        vecPos.set(vis.x, groundHeight(vis.x, vis.y) + 2.5, vis.y),
        ringSpin,
        vecScale.set(r, 1, r));
      rings.setMatrixAt(ringCount, matrix);
      const kills = vis.unit.kills || 0;
      if (kills >= 16) {
        tmpColor.set(1.0, 0.85, 0.0);
      } else if (kills >= 8) {
        tmpColor.set(1.0, 0.7, 0.0);
      } else if (kills >= 3) {
        tmpColor.set(1.0, 0.55, 0.0);
      } else {
        tmpColor.set(colorOf(vis.unit.owner));
      }
      rings.setColorAt(ringCount, tmpColor);
      ringCount++;
    });
    if (payload.selectedStructureId) {
      const node = structureNodes.get(payload.selectedStructureId);
      const s = node && node.structure;
      if (node && node.group.visible && s) {
        const r = s.size * 1.5;
        matrix.compose(
          vecPos.set(s.x, groundHeight(s.x, s.y) + 2.5, s.y),
          ringSpin,
          vecScale.set(r, 1, r));
        rings.setMatrixAt(ringCount, matrix);
        tmpColor.set(colorOf(s.owner));
        rings.setColorAt(ringCount, tmpColor);
        ringCount++;
      }
    }
    if (payload.selectedResourceId) {
      const res = state.resourceById && state.resourceById.get(payload.selectedResourceId);
      const cluster = oreMeshes.get(payload.selectedResourceId);
      if (res && res.amount > 0 && cluster && cluster.visible && isVisible(res.x, res.y)) {
        const tier = oreReserveTier(res.amount);
        const r = res.radius * (0.78 + tier.level * 0.14);
        matrix.compose(
          vecPos.set(res.x, groundHeight(res.x, res.y) + 3.2, res.y),
          ringSpin,
          vecScale.set(r, 1, r));
        rings.setMatrixAt(ringCount, matrix);
        tmpColor.set(tier.color);
        rings.setColorAt(ringCount, tmpColor);
        ringCount++;
      }
    }
    rings.count = ringCount;
    if (ringCount) {
      rings.instanceMatrix.needsUpdate = true;
      if (rings.instanceColor) rings.instanceColor.needsUpdate = true;
    }

    // 军衔环：未选中的老兵/精英/王牌脚下常驻一枚金环。selected 里的是旋转
    // 选中环（已按军衔配色），这里只补没选中的，避免同单位两环叠着闪。
    rankRingVisuals.length = 0;
    for (let i = 0; i < snapshotVisuals.length; i++) {
      const vis = snapshotVisuals[i];
      if (!vis.inRenderRange) continue;
      const kills = vis.unit.kills || 0;
      if (kills < 3 || selected.has(vis.unit.id)) continue;
      rankRingVisuals.push(vis);
    }
    if (rankRingVisuals.length) {
      const rankRings = ensureRankRingMesh(rankRingVisuals.length);
      for (let i = 0; i < rankRingVisuals.length; i++) {
        const vis = rankRingVisuals[i];
        const kills = vis.unit.kills || 0;
        const r = vis.unit.size * 1.4;
        matrix.compose(
          vecPos.set(vis.x, groundHeight(vis.x, vis.y) + 2.1, vis.y),
          quatIdentity,
          vecScale.set(r, 1, r));
        rankRings.setMatrixAt(i, matrix);
        if (kills >= 16) tmpColor.set(1.05, 0.9, 0.3);
        else if (kills >= 8) tmpColor.set(0.95, 0.7, 0.15);
        else tmpColor.set(0.7, 0.5, 0.12);
        rankRings.setColorAt(i, tmpColor);
      }
      rankRings.count = rankRingVisuals.length;
      rankRings.instanceMatrix.needsUpdate = true;
      if (rankRings.instanceColor) rankRings.instanceColor.needsUpdate = true;
    } else if (rankRingMesh) {
      rankRingMesh.count = 0;
    }

    updatePreview(payload.buildPreview);

    // 水面：整体轻微涨落 + 推进波纹时间
    if (waterMesh) {
      waterMesh.position.y = -2 + Math.sin(payload.time * 0.0011) * 1.2;
      for (let i = 0; i < waterShaders.length; i++) {
        waterShaders[i].uniforms.uTime.value = payload.time * 0.001;
      }
    }

    // 天空流云、地面云影、视空间太阳方向：共享 uniform，一帧只算一次
    skyMaterial.uniforms.uTime.value = payload.time * 0.001;
    cloudTimeUniform.value = payload.time * 0.001;
    armyTimeUniform.value = payload.time * 0.001;
    if (cameraChanged) {
      sunDirViewUniform.value.copy(SUN_DIR).transformDirection(camera.matrixWorldInverse);
    }

    postfx.render(scene, camera, payload.time);
  }

  /* -------------------- 对外接口 -------------------- */

  return {
    get camera() { return camera; },

    resize: function (width, height, dpr) {
      state.width = Math.max(1, width);
      state.height = Math.max(1, height);
      state.dpr = dpr || 1;
      renderer.setPixelRatio(state.dpr);
      renderer.setSize(state.width, state.height, false);
      postfx.setSize(state.width, state.height, state.dpr);
      camera.aspect = state.width / state.height;
      camera.updateProjectionMatrix();
    },

    setQuality: function (options) {
      if (options.shadows != null) {
        // 'off' | 'structures'（只有建筑投影，单位用贴地圆影）| 'all'
        state.shadows = options.shadows;
        const on = state.shadows !== 'off';
        renderer.shadowMap.enabled = on;
        sun.castShadow = on;
        appliedCamX = NaN;
      }
      if (options.lod != null) state.lod = !!options.lod;
      if (options.particleBudget != null) {
        state.particleBudget = Math.max(60, Math.min(EFFECT_MAX, options.particleBudget));
      }
      if (options.fogScale != null && options.fogScale !== state.fogScale) {
        state.fogScale = options.fogScale;
        if (state.map) buildFogPlane();
      }
      if (options.bloom != null) {
        state.bloom = !!options.bloom;
        postfx.setOptions({ enabled: state.bloom, fastBloom: !!options.fastBloom });
      }
      if (options.showProjectiles != null) state.showProjectiles = !!options.showProjectiles;
      if (options.postfx) postfx.setOptions(options.postfx);
    },

    /**
     * 一局开始（或重连收到 full 帧）时调用，刷新静态数据。
     *
     * 地形、道路、矿脉、迷雾画布全部按「地图身份」缓存：同一局里反复
     * 收到 full 帧只更新引用，不碰几何体。返回是否真的重建了世界。
     */
    setMatch: function (map, terrain, resources, sight, spawnPoints) {
      state.map = map;
      state.terrain = terrain || { rivers: [], bridges: [] };
      state.resources = resources || [];
      state.resourceById = new Map();
      state.resources.forEach(function (r) { state.resourceById.set(r.id, r); });
      if (sight) state.sight = sight;
      state.spawnPoints = spawnPoints || state.spawnPoints || [];
      state.terrainDetail = resolveTerrainDetail(map, state.terrain);

      // 每局开新地图时服务端会给 map.seed 一个新随机值，尺寸与地形要素数量
      // 一并入键，防止「换了图但恰好同尺寸」漏判。
      const t = state.terrain;
      const worldKey = [
        map.id || '', map.width, map.height, map.seed,
        t.theme || '',
        (t.rivers || []).length, (t.bridges || []).length,
        (t.mountains || []).length, (t.roads || []).length,
        state.resources.length,
        JSON.stringify(state.terrainDetail)
      ].join('|');
      if (worldKey === builtWorldKey && terrainGroup) {
        return false;
      }
      builtWorldKey = worldKey;

      const themeId = t.theme || 'grassland';
      groundTexture = makeProceduralGroundTexture(themeId);
      groundTexture.repeat.set(map.width / 420, map.height / 420);
      buildTerrain();
      return true;
    },

    setPalette: function (players, viewerId, isFriendly) {
      state.palette.clear();
      players.forEach(function (p) { state.palette.set(p.id, p.color); });
      state.viewerId = viewerId;
      if (isFriendly) state.friendly = isFriendly;
    },

    setCamera: function (view) {
      state.camX = view.x;
      state.camY = view.y;
      state.zoom = view.zoom;
      if (view.yaw != null) state.yaw = view.yaw;
      if (view.pitch != null) state.pitch = view.pitch;
    },

    screenToWorld: screenToWorld,
    worldToScreen: worldToScreen,
    isVisible: isVisible,
    render: render,

    /** 合成好的迷雾贴图，小地图直接叠加使用。 */
    getFogCanvas: function () { return fogCanvas; },

    /** 渲染统计：调优与冒烟测试用。 */
    stats: function () {
      const info = postfx.sceneStats;
      let instanced = 0;
      unitPools.forEach(function (pool) {
        if (pool.mesh) instanced += pool.mesh.count;
        if (pool.simple) instanced += pool.simple.count;
      });
      return {
        drawCalls: info.calls,
        triangles: info.triangles,
        programs: renderer.info.programs ? renderer.info.programs.length : 0,
        units: instanced,
        snapshotUnits: state.snapshotUnits,
        renderedUnits: state.renderedUnits,
        structures: structureNodes.size,
        renderedStructures: state.renderedStructures,
        particles: fireLayer.list.length + smokeLayer.list.length,
        buildTerrainMs: state.buildTerrainMs,
        groundDetailParts: state.groundDetailParts,
        geometries: renderer.info.memory.geometries,
        textures: renderer.info.memory.textures
      };
    },

    /** 单位的插值显示位置，用于点选/框选命中判定。 */
    visualPosition: function (id) { return visual.get(id) || null; },

    /** 在指定点播放一次特效。仅调试/截图脚本使用，不影响任何对局状态。 */
    debugEffect: function (type, x, y, kind) { spawnEffect(type, x, y, kind); },

    /** 某点的地表高度。HUD 叠加层要用它把血条摆到单位正上方。 */
    groundHeight: groundHeight,

    /**
     * 把整张地图标记为已探索。仅用于调试与截图。
     *
     * 这不是作弊入口：客户端迷雾只是表现层，服务端本来就不会下发视野外的
     * 单位与建筑，揭开之后也只能看到地形。
     */
    revealAll: function () {
      if (!exploredCtx) return;
      exploredCtx.fillStyle = '#fff';
      exploredCtx.fillRect(0, 0, exploredCanvas.width, exploredCanvas.height);
    },

    /** 换局时清空所有单位/建筑，避免上一局的模型残留。 */
    clearEntities: function () {
      visual.clear();
      snapshotVisuals.length = 0;
      lastFogGame = null;
      lastEntityGame = null;
      lastRallyGame = null;
      lastOreAt = -Infinity;
      lastBarsAt = -Infinity;
      appliedCamX = NaN;
      fireLayer.list.length = 0;
      smokeLayer.list.length = 0;
      shockLayer.list.length = 0;
      scorchLayer.list.length = 0;
      projectileHintPrev = [];
      if (tracerMesh) tracerMesh.count = 0;
      if (tracerOrbMesh) tracerOrbMesh.count = 0;
      if (tracerShardMesh) tracerShardMesh.count = 0;
      const ids = [];
      structureNodes.forEach(function (_n, id) { ids.push(id); });
      ids.forEach(disposeStructure);
      unitPools.forEach(function (pool) {
        if (pool.mesh) pool.mesh.count = 0;
        if (pool.simple) pool.simple.count = 0;
      });
      if (barBgMesh) barBgMesh.count = 0;
      if (barFillMesh) barFillMesh.count = 0;
      if (barSecMesh) barSecMesh.count = 0;
      if (crateMesh) crateMesh.count = 0;
      if (strikeMesh) strikeMesh.count = 0;
      if (rallyMesh) rallyMesh.count = 0;
      if (exploredCtx) {
        exploredCtx.clearRect(0, 0, exploredCanvas.width, exploredCanvas.height);
      }
    }
  };
}
