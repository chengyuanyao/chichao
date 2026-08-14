/**
 * 赤潮：钢铁前线 — 3D 渲染层
 *
 * 服务端仍是纯 2D 权威模拟（x/y 平面）。这一层只负责把快照画成 3D：
 *   世界 (x, y)  ->  场景 (x, 高度, y)      X 向东，Y 向上，Z 向南
 *
 * 单位用 InstancedMesh 按兵种合批（数百单位 = 每种一次 draw call），
 * 建筑数量少，用普通 Mesh 以便播放建造/受损动画。
 * 所有网格程序化生成，不依赖任何美术资源。
 */

import * as THREE from './vendor/three.module.min.js';
import { createPostFX } from './postfx.js';

const TAU = Math.PI * 2;

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
  // 撒草木时一张图要合并上万个零件，clone 一份 BufferGeometry 再
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
      rgb: part.rgb || null
    });
  }

  const position = new Float32Array(total * 3);
  const normal = new Float32Array(total * 3);
  const color = new Float32Array(total * 3);
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
    }
    offset += item.count;
  }

  const merged = new THREE.BufferGeometry();
  merged.setAttribute('position', new THREE.BufferAttribute(position, 3));
  merged.setAttribute('normal', new THREE.BufferAttribute(normal, 3));
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

function box(w, h, d, x, y, z, paint, rotY) {
  const m = new THREE.Matrix4();
  if (rotY) m.makeRotationY(rotY);
  m.setPosition(x, y, z);
  return Object.assign({ geo: new THREE.BoxGeometry(w, h, d), matrix: m }, tint(paint));
}

function cyl(rTop, rBottom, h, seg, x, y, z, paint, rot) {
  const m = new THREE.Matrix4();
  if (rot) m.multiply(rot);
  m.setPosition(x, y, z);
  return Object.assign({
    geo: new THREE.CylinderGeometry(rTop, rBottom, h, seg),
    matrix: m
  }, tint(paint));
}

function sph(r, seg, x, y, z, paint) {
  const m = new THREE.Matrix4();
  m.setPosition(x, y, z);
  return Object.assign({
    geo: new THREE.SphereGeometry(r, seg, Math.max(3, seg >> 1)), matrix: m
  }, tint(paint));
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
  glass: [0.16, 0.24, 0.29],
  warnYellow: [0.66, 0.54, 0.12],
  copper: [0.48, 0.30, 0.15],
  // 军犬被毛：黄褐主色 + 深色背鞍/吻部/爪（天然色，不跟团队色走）
  furTan: [0.46, 0.34, 0.20],
  furDark: [0.23, 0.18, 0.14],
  // 自发光（分量 > 1）
  exhaust: [2.4, 0.95, 0.28],
  furnace: [2.6, 1.35, 0.35],
  oreGlow: [2.5, 1.7, 0.42],
  hazard: [2.6, 0.5, 0.35],
  teslaArc: [0.55, 1.65, 2.6],
  prismGlow: [1.5, 2.3, 2.4]
};

const ROT_X90 = new THREE.Matrix4().makeRotationX(Math.PI / 2);
const ROT_Z90 = new THREE.Matrix4().makeRotationZ(Math.PI / 2);

/**
 * 方形棱台：顶面和底面可以是不同尺寸的矩形。
 *
 * 用 4 段圆柱旋转 45° 得到方形截面，再逐顶点按上下分别缩放。斜面装甲比纯方块
 * 更像军事载具，而且法线不再全部轴对齐，光照能打出层次。
 */
function taperedBox(botW, botD, topW, topD, h, x, y, z, paint, rotY) {
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
    // 躯干做成上窄下宽的护甲块
    taperedBox(7.6, 5.4, 6.4, 4.6, 8.4, 0, 7.2, 0, 0.9),
    box(3.0, 2.2, 8.6, -0.2, 10.4, 0, 0.55),           // 肩甲横梁
    taperedBox(5.4, 5.0, 4.4, 4.2, 4.0, 0.2, 13.2, 0, 1.05),  // 头盔
    box(2.4, 5.8, 2.4, -0.6, 3.0, 2.7, MAT.olive),     // 腿
    box(2.4, 5.8, 2.4, -0.6, 3.0, -2.7, MAT.olive),
    box(3.2, 2.0, 3.2, -0.6, 0.9, 2.7, MAT.rubber),    // 靴
    box(3.2, 2.0, 3.2, -0.6, 0.9, -2.7, MAT.rubber),
    box(3.6, 5.2, 6.0, -3.6, 8.6, 0, MAT.olive)        // 背包
  ];
  const glow = [
    box(0.7, 1.5, 3.6, 2.4, 13.4, 0, GLOW_HOT),        // 面罩
    box(2.2, 0.5, 0.5, -3.6, 11.2, 0, GLOW_SOFT)       // 背包指示灯
  ];

  if (weapon === 'rifle') {
    body.push(box(10, 1.4, 1.4, 4.8, 8.2, 1.9, MAT.gunmetal));
    body.push(box(2.6, 2.4, 0.9, 1.6, 8.2, 1.9, MAT.darkSteel));
    glow.push(box(1.0, 0.5, 0.5, 9.4, 8.2, 1.9, GLOW_SOFT));
  } else if (weapon === 'rocket') {
    body.push(cyl(1.9, 1.9, 13, 8, 4.0, 9.6, 1.6, MAT.olive, ROT_Z90));
    body.push(cyl(2.6, 1.8, 2.6, 8, -2.6, 9.6, 1.6, MAT.gunmetal, ROT_Z90));
    glow.push(cyl(1.4, 1.4, 0.8, 8, -3.6, 9.6, 1.6, MAT.exhaust, ROT_Z90));
  } else if (weapon === 'sniper') {
    body.push(box(14.0, 1.1, 1.1, 6.4, 8.8, 1.6, MAT.gunmetal));
    body.push(box(2.6, 1.8, 1.1, 2.4, 9.9, 1.6, MAT.darkSteel));
    body.push(box(3.4, 0.7, 0.7, 12.4, 8.2, 1.6, MAT.darkSteel));
    glow.push(box(0.9, 0.6, 0.6, 3.6, 9.9, 1.6, GLOW_HOT));
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
    const body = [
      box(16.0, 5.6, 5.6, 0, 6.8, 0, MAT.furTan),              // 主躯干
      box(6.0, 6.4, 6.2, 6.2, 7.2, 0, MAT.furTan),             // 前胸更壮
      box(11.0, 1.6, 5.9, -1.6, 9.4, 0, MAT.furDark),          // 背鞍（黑背）
      box(5.4, 4.6, 4.8, 9.4, 9.0, 0, MAT.furTan),             // 头颅
      box(3.6, 2.6, 3.0, 12.6, 8.0, 0, MAT.furDark),           // 吻部
      box(1.1, 3.0, 1.3, 7.8, 12.4, 1.7, MAT.furDark),         // 竖耳
      box(1.1, 3.0, 1.3, 7.8, 12.4, -1.7, MAT.furDark),
      box(7.5, 3.4, 6.3, 1.0, 7.4, 0, 0.9),                    // 战术背心（团队色）
      cyl(0.9, 0.55, 6.0, 6, -9.2, 9.0, 0, MAT.furDark, tailRot) // 翘尾
    ];
    [5.2, -5.2].forEach(function (px) {
      [2.0, -2.0].forEach(function (pz) {
        body.push(box(1.9, 5.0, 1.9, px, 2.5, pz, MAT.furDark)); // 四条腿
      });
    });
    return {
      body: body,
      glow: [
        box(1.3, 4.8, 5.4, 7.0, 8.2, 0, GLOW_SOFT),            // 发光项圈
        sph(0.6, 5, 11.6, 9.8, 1.5, GLOW_HOT),                 // 眼
        sph(0.6, 5, 11.6, 9.8, -1.5, GLOW_HOT)
      ]
    };
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
  return { parts: parts, add: add, taper: taper };
}

function structureParts(kind, size) {
  const c = partCollector();
  const add = c.add;
  const taper = c.taper;
  const s = size;

  // 共用地基：混凝土台 + 四角警示灯，让建筑「坐」在地上而不是浮着
  taper(HULL, s * 2.1, s * 2.1, s * 1.95, s * 1.95, 3.4, 0, 1.7, 0, MAT.concrete);
  add(HULL, new THREE.BoxGeometry(s * 2.16, 1.2, s * 2.16), 0, 3.5, 0, MAT.concreteDark);
  [[1, 1], [-1, -1], [1, -1], [-1, 1]].forEach(function (q) {
    add(GLOW, new THREE.BoxGeometry(s * 0.16, 0.9, s * 0.16),
      q[0] * s * 0.95, 4.0, q[1] * s * 0.95, GLOW_SOFT);
  });

  if (kind === 'hq') {
    taper(HULL, s * 1.72, s * 1.72, s * 1.5, s * 1.5, s * 0.62, 0, s * 0.31 + 3.4, 0, MAT.concrete);
    // 主塔
    taper(TEAM, s * 1.02, s * 1.02, s * 0.86, s * 0.86, s * 0.92, 0, s * 1.08 + 3.4, 0, 1.0);
    add(TEAM, new THREE.BoxGeometry(s * 1.12, s * 0.08, s * 1.12), 0, s * 1.56, 0, 0.55);
    // 环绕窗带
    [0.78, 1.22].forEach(function (h) {
      add(GLOW, new THREE.BoxGeometry(s * 1.05, s * 0.07, s * 0.9), 0, s * h, 0, GLOW_SOFT);
      add(GLOW, new THREE.BoxGeometry(s * 0.9, s * 0.07, s * 1.05), 0, s * h, 0, GLOW_SOFT);
    });
    // 四角碉堡
    [[1, 1], [-1, -1], [1, -1], [-1, 1]].forEach(function (q) {
      taper(HULL, s * 0.34, s * 0.34, s * 0.26, s * 0.26, s * 0.56,
        q[0] * s * 0.7, s * 0.28 + 3.4, q[1] * s * 0.7, MAT.concreteDark);
      add(GLOW, new THREE.BoxGeometry(s * 0.2, s * 0.05, s * 0.2),
        q[0] * s * 0.7, s * 0.58, q[1] * s * 0.7, GLOW_HOT);
    });
    // 桅杆
    add(HULL, new THREE.CylinderGeometry(s * 0.06, s * 0.09, s * 0.5, 8), 0, s * 1.78, 0, 0.7);
  } else if (kind === 'power') {
    taper(HULL, s * 1.62, s * 1.28, s * 1.45, s * 1.14, s * 0.5, 0, s * 0.25 + 3.4, 0, MAT.concrete);
    [-1, 1].forEach(function (side) {
      // 磁能塔：三段收束 + 顶部线圈
      taper(TEAM, s * 0.5, s * 0.5, s * 0.36, s * 0.36, s * 1.05,
        side * s * 0.44, s * 0.52 + 3.4, 0, 1.0);
      add(HULL, new THREE.TorusGeometry(s * 0.3, s * 0.055, 6, 12),
        side * s * 0.44, s * 1.14, 0, MAT.copper, ROT_X90);
      add(HULL, new THREE.TorusGeometry(s * 0.24, s * 0.05, 6, 12),
        side * s * 0.44, s * 1.36, 0, MAT.copper, ROT_X90);
      add(GLOW, new THREE.SphereGeometry(s * 0.16, 10, 6),
        side * s * 0.44, s * 1.56, 0, GLOW_HOT);
      add(GLOW, new THREE.CylinderGeometry(s * 0.05, s * 0.05, s * 0.5, 6),
        side * s * 0.44, s * 1.3, 0, GLOW_SOFT);
    });
    // 母线
    add(GLOW, new THREE.BoxGeometry(s * 0.9, s * 0.06, s * 0.1), 0, s * 1.46, 0, GLOW_SOFT);
    add(HULL, new THREE.BoxGeometry(s * 0.5, s * 0.4, s * 0.6), 0, s * 0.42, s * 0.5, MAT.darkSteel);
  } else if (kind === 'refinery') {
    taper(HULL, s * 1.76, s * 1.34, s * 1.6, s * 1.2, s * 0.56, 0, s * 0.28 + 3.4, 0, MAT.concrete);
    // 主储罐
    add(TEAM, new THREE.CylinderGeometry(s * 0.4, s * 0.48, s * 1.0, 12), s * 0.42, s * 0.85, 0);
    add(HULL, new THREE.ConeGeometry(s * 0.44, s * 0.5, 12), s * 0.42, s * 1.6, 0, MAT.rust);
    add(HULL, new THREE.CylinderGeometry(s * 0.06, s * 0.06, s * 0.3, 6), s * 0.42, s * 1.95, 0, MAT.steel);
    add(GLOW, new THREE.SphereGeometry(s * 0.05, 8, 6), s * 0.42, s * 2.1, 0, GLOW_HOT);
    add(GLOW, new THREE.TorusGeometry(s * 0.46, s * 0.035, 6, 14), s * 0.42, s * 1.1, 0, GLOW_SOFT, ROT_X90);
    // 加工塔
    taper(HULL, s * 0.66, s * 0.7, s * 0.54, s * 0.58, s * 0.86, -s * 0.5, s * 0.43 + 3.4, 0, MAT.steel);
    add(GLOW, new THREE.BoxGeometry(s * 0.6, s * 0.06, s * 0.66), -s * 0.5, s * 0.72, 0, GLOW_SOFT);
    // 卸矿槽（矿石的琥珀色辉光）
    add(HULL, new THREE.BoxGeometry(s * 1.4, s * 0.1, s * 0.34), 0, s * 1.02, s * 0.44, MAT.rust);
    add(GLOW, new THREE.BoxGeometry(s * 1.2, s * 0.09, s * 0.2), 0, s * 1.09, s * 0.44, MAT.oreGlow);
    add(HULL, new THREE.CylinderGeometry(s * 0.08, s * 0.08, s * 0.7, 6), s * 0.9, s * 0.75, -s * 0.4, MAT.steel);
  } else if (kind === 'barracks') {
    taper(TEAM, s * 1.66, s * 1.3, s * 1.5, s * 1.16, s * 0.56, 0, s * 0.28 + 3.4, 0, 1.0);
    // 三棱柱屋顶
    add(HULL, new THREE.CylinderGeometry(s * 0.7, s * 0.7, s * 1.66, 3), 0, s * 0.7, 0, MAT.olive,
      new THREE.Matrix4().makeRotationZ(Math.PI / 2));
    // 大门 + 门框灯
    add(HULL, new THREE.BoxGeometry(s * 0.12, s * 0.44, s * 0.56), s * 0.82, s * 0.25 + 3.4, 0, MAT.gunmetal);
    add(GLOW, new THREE.BoxGeometry(s * 0.06, s * 0.44, s * 0.06), s * 0.86, s * 0.25 + 3.4, s * 0.3, GLOW_HOT);
    add(GLOW, new THREE.BoxGeometry(s * 0.06, s * 0.44, s * 0.06), s * 0.86, s * 0.25 + 3.4, -s * 0.3, GLOW_HOT);
    // 侧窗带
    add(GLOW, new THREE.BoxGeometry(s * 1.3, s * 0.06, s * 1.2), 0, s * 0.52, 0, GLOW_SOFT);
    add(HULL, new THREE.BoxGeometry(s * 0.3, s * 0.3, s * 0.3), -s * 0.56, s * 1.06, 0, MAT.darkSteel);
    add(HULL, new THREE.CylinderGeometry(s * 0.03, s * 0.04, s * 0.5, 6), -s * 0.56, s * 1.4, 0, MAT.steel);
  } else if (kind === 'factory') {
    taper(HULL, s * 1.82, s * 1.56, s * 1.64, s * 1.4, s * 0.72, 0, s * 0.36 + 3.4, 0, MAT.concrete);
    add(TEAM, new THREE.BoxGeometry(s * 1.55, s * 0.14, s * 1.34), 0, s * 0.83, 0, 1.0);
    // 拱形屋顶
    add(HULL, new THREE.CylinderGeometry(s * 0.66, s * 0.66, s * 1.5, 8, 1, false, 0, Math.PI),
      0, s * 0.86, 0, MAT.steel, new THREE.Matrix4().makeRotationZ(Math.PI / 2));
    // 出车口：门洞发光
    add(HULL, new THREE.BoxGeometry(s * 0.16, s * 0.6, s * 1.1), s * 0.92, s * 0.3 + 3.4, 0, MAT.gunmetal);
    add(GLOW, new THREE.BoxGeometry(s * 0.06, s * 0.52, s * 0.9), s * 0.99, s * 0.3 + 3.4, 0, MAT.furnace);
    add(HULL, new THREE.BoxGeometry(s * 1.1, s * 0.07, s * 0.6), s * 1.4, 3.6, 0, MAT.warnYellow);
    // 烟囱
    for (let i = -1; i <= 1; i++) {
      add(HULL, new THREE.CylinderGeometry(s * 0.1, s * 0.13, s * 0.66, 6),
        i * s * 0.4, s * 1.2, -s * 0.42, MAT.rust);
      add(GLOW, new THREE.CylinderGeometry(s * 0.08, s * 0.08, s * 0.06, 6),
        i * s * 0.4, s * 1.53, -s * 0.42, MAT.furnace);
    }
    add(GLOW, new THREE.BoxGeometry(s * 1.5, s * 0.06, s * 0.08), 0, s * 0.63, s * 0.7, GLOW_SOFT);
    add(GLOW, new THREE.BoxGeometry(s * 1.5, s * 0.06, s * 0.08), 0, s * 0.63, -s * 0.7, GLOW_SOFT);
  } else if (kind === 'repair') {
    taper(HULL, s * 1.6, s * 1.4, s * 1.5, s * 1.3, s * 0.34, 0, s * 0.17 + 3.4, 0, MAT.concrete);
    // 龙门架
    [[-1, -1], [1, -1], [-1, 1], [1, 1]].forEach(function (q) {
      add(HULL, new THREE.BoxGeometry(s * 0.15, s * 0.95, s * 0.15),
        q[0] * s * 0.64, s * 0.5, q[1] * s * 0.58, MAT.warnYellow);
    });
    [-1, 1].forEach(function (side) {
      add(TEAM, new THREE.BoxGeometry(s * 1.5, s * 0.14, s * 0.2), 0, s * 1.0, side * s * 0.58);
      add(GLOW, new THREE.BoxGeometry(s * 1.36, s * 0.05, s * 0.07), 0, s * 0.93, side * s * 0.58, GLOW_SOFT);
    });
    add(TEAM, new THREE.BoxGeometry(s * 0.34, s * 0.3, s * 1.26), 0, s * 1.02, 0, 0.9);
    // 停机坪十字
    add(GLOW, new THREE.BoxGeometry(s * 0.72, s * 0.04, s * 0.16), 0, s * 0.36, 0, GLOW_HOT);
    add(GLOW, new THREE.BoxGeometry(s * 0.16, s * 0.04, s * 0.72), 0, s * 0.36, 0, GLOW_HOT);
    add(HULL, new THREE.BoxGeometry(s * 0.36, s * 0.5, s * 0.36), -s * 0.66, s * 0.42, 0, MAT.darkSteel);
  } else if (kind === 'turret') {
    taper(HULL, s * 1.5, s * 1.5, s * 1.05, s * 1.05, s * 0.42, 0, s * 0.21 + 3.4, 0, MAT.concrete);
    add(TEAM, new THREE.CylinderGeometry(s * 0.5, s * 0.56, s * 0.2, 10), 0, s * 0.62, 0);
    add(GLOW, new THREE.TorusGeometry(s * 0.5, s * 0.035, 6, 14), 0, s * 0.58, 0, GLOW_SOFT, ROT_X90);
  } else if (kind === 'missile') {
    taper(HULL, s * 1.6, s * 1.6, s * 1.15, s * 1.15, s * 0.46, 0, s * 0.23 + 3.4, 0, MAT.concrete);
    add(TEAM, new THREE.CylinderGeometry(s * 0.55, s * 0.6, s * 0.22, 10), 0, s * 0.66, 0);
    add(GLOW, new THREE.TorusGeometry(s * 0.54, s * 0.035, 6, 14), 0, s * 0.62, 0, GLOW_SOFT, ROT_X90);
    // 底座上的状态灯
    [[1, 1], [-1, -1], [1, -1], [-1, 1]].forEach(function (q) {
      add(GLOW, new THREE.BoxGeometry(s * 0.1, s * 0.04, s * 0.1),
        q[0] * s * 0.6, s * 0.75, q[1] * s * 0.6, GLOW_HOT);
    });
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

// 相机拉到这个距离以外才换用可辨识的兵种剪影。单位数量不再触发全场
// 硬切低模：InstancedMesh 的绘制调用本来就按兵种合批，数量阈值只会造成
// 模型突然一起变成盒子，却没有省下任何 draw call。
const UNIT_LOD_DISTANCE = 900;
// 渲染出来的桥比碰撞尺寸长这么多倍，用来跨过做了抖动加宽的可见水面
const BRIDGE_RENDER_SPAN = 2.0;

/**
 * 单位模型的视觉放大系数（纯表现，不影响碰撞/选取，那些仍用服务端 size）。
 *
 * 服务端的 size 是给 2D 俯视图定的碰撞半径；照搬到 3D 里，从 RTS 常用的
 * 视距看步兵只有几个像素，根本认不出兵种。这里按兵种放大到能辨识的比例。
 */
const UNIT_VISUAL_SCALE = {
  rifle: 1.75, rocket: 1.75, sniper: 1.75, tesla: 1.75, dog: 1.7,
  tank: 1.25, scout: 1.3, tank_destroyer: 1.25,
  artillery: 1.25, harvester: 1.16, mcv: 1.30, v3: 1.25,
  overlord: 1.28, prism: 1.25
};

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

  // 三点布光：高对比暖阳 + 冷天光 + 背后的轮廓光 —— 大晴天的「玩具战争」
  // 布光：主光要亮到能把顶面打出高光，暗面靠天光补出冷蓝，不能发闷。
  const hemi = new THREE.HemisphereLight(0xaed9ff, 0x55603a, 0.75);
  scene.add(hemi);

  const sun = new THREE.DirectionalLight(0xffedc2, 2.3);
  sun.castShadow = true;
  // 阴影默认关闭、开了就是要画质，所以给到 1024，软边的细节才出得来
  sun.shadow.mapSize.set(1024, 1024);
  sun.shadow.camera.near = 50;
  sun.shadow.camera.far = 3200;
  sun.shadow.bias = -0.0012;
  sun.shadow.normalBias = 1.2;
  scene.add(sun);
  scene.add(sun.target);

  const fill = new THREE.DirectionalLight(0x9ab4c4, 0.32);
  scene.add(fill);
  const rim = new THREE.DirectionalLight(0xa8e2f2, 0.55);
  scene.add(rim);

  const worldRoot = new THREE.Group();
  scene.add(worldRoot);

  const state = {
    width: 1, height: 1, dpr: 1,
    map: null, terrain: null,
    camX: 0, camY: 0, zoom: 0.78, yaw: 0, pitch: 0.94,
    shadows: 'structures', lod: true, fogScale: 6, particleBudget: 600,
    bloom: true, scatter: true, scatterCount: 0, scatterChunks: 0,
    showProjectiles: true,
    buildTerrainMs: 0, buildScatterMs: 0,
    snapshotUnits: 0, renderedUnits: 0, renderedStructures: 0,
    sight: null,
    palette: new Map(),
    friendly: function () { return false; },
    viewerId: null
  };

  /* -------------------- 地形 -------------------- */

  const textureLoader = new THREE.TextureLoader();
  let groundTexture = null;
  let terrainGroup = null;
  let waterMesh = null;
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

  function applyEmissiveByVertexColor(material) {
    material.onBeforeCompile = function (shader) {
      shader.uniforms.uSunDirView = sunDirViewUniform;
      // three.js 的 <color_vertex> 已经把 instanceColor 乘进 vColor，
      // 所以另存一份未乘的原始顶点色，供固有色零件使用。
      shader.vertexShader = 'attribute float aTeam;\nvarying float vTeamMix;\n' +
        'varying vec3 vOwnColor;\n' + shader.vertexShader.replace(
          '#include <color_vertex>',
          '#include <color_vertex>\n  vTeamMix = aTeam;\n  vOwnColor = color;');
      shader.fragmentShader = 'varying float vTeamMix;\nvarying vec3 vOwnColor;\n' +
        'uniform vec3 uSunDirView;\n' +
        shader.fragmentShader
          .replace('#include <color_fragment>',
            '#include <color_fragment>\n' +
            // vTeamMix=0 走固有色，=1 走「团队色 × 明暗系数」
            '  diffuseColor.rgb = mix(vOwnColor, diffuseColor.rgb, vTeamMix);\n' +
            '  vec3 gBase = diffuseColor.rgb;\n' +
            '  float gEmissive = clamp(max(max(gBase.r, gBase.g), gBase.b) - 1.0, 0.0, 1.0);')
          .replace('#include <normal_fragment_begin>',
            '#include <normal_fragment_begin>\n' +
            // 手绘式明暗：顶面提亮、底面压暗。参考画面里的单位像是被
            // 画师从上方「刷」了一层亮色，纯物理光照出不来这个反差。
            '  vec3 gUpView = normalize((viewMatrix * vec4(0.0, 1.0, 0.0, 0.0)).xyz);\n' +
            '  diffuseColor.rgb *= mix(0.78, 1.10, smoothstep(-0.45, 1.0, dot(normal, gUpView)));')
          .replace('#include <dithering_fragment>',
            '#include <dithering_fragment>\n' +
            '  {\n' +
            '    vec3 gN = normalize(normal);\n' +
            '    vec3 gV = normalize(vViewPosition);\n' +
            // 冷色边缘光：视角相关的菲涅尔项，把单位从绿色地表上「剥」出来。
            // 比一盏背后的平行光更稳定 —— 无论相机转到哪边都描边。
            '    float gRim = pow(1.0 - clamp(dot(gN, gV), 0.0, 1.0), 3.0);\n' +
            // 阳光镜面高光：装甲的金属感来自这一点点闪光
            '    vec3 gH = normalize(gV + uSunDirView);\n' +
            '    float gSpec = pow(max(dot(gN, gH), 0.0), 36.0);\n' +
            '    gl_FragColor.rgb += (vec3(0.42, 0.60, 0.78) * gRim * 0.34\n' +
            '      + vec3(1.0, 0.93, 0.78) * gSpec * 0.5) * (1.0 - gEmissive);\n' +
            '    gl_FragColor.rgb = mix(gl_FragColor.rgb, gBase, gEmissive);\n' +
            '  }');
    };
    material.customProgramCacheKey = function () { return 'teamOrOwn2'; };
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

  /**
   * 给地面材质再叠一层逐像素细节，与迷雾注入串联使用。
   *
   * 顶点密度封顶 5 万面片，大地图上一格 40+ 世界单位，纯顶点法线的地面
   * 在低角度阳光下是一整片均匀亮度 —— 平得像桌布。这里用带解析导数的
   * 值噪声在片元里扰动法线，光照立刻碎成自然的明暗斑；再顺手把照片
   * 纹理的土黄色偏压掉一半，色相交还给顶点色（草绿 / 金沙 / 灰岩）。
   */
  function applyTerrainDetail(material) {
    const prevCompile = material.onBeforeCompile;
    material.onBeforeCompile = function (shader) {
      if (prevCompile) prevCompile(shader);
      shader.fragmentShader = shader.fragmentShader
        .replace('#include <map_fragment>',
          '  vec4 tdTex = texture2D(map, vMapUv);\n' +
          '  tdTex.rgb = mix(vec3(dot(tdTex.rgb, vec3(0.333))), tdTex.rgb, 0.4);\n' +
          '  tdTex.rgb = mix(vec3(0.52), tdTex.rgb, 0.55) * 1.16;\n' +
          '  diffuseColor *= tdTex;')
        .replace('#include <normal_fragment_begin>',
          '#include <normal_fragment_begin>\n' +
          '  {\n' +
          // iq 的带导数值噪声：同一次采样既给高度又给梯度
          '    vec2 tdP1 = vFogWorld.xz * 0.055;\n' +
          '    vec2 tdP2 = vFogWorld.xz * 0.21;\n' +
          '    vec2 tdI = floor(tdP1); vec2 tdF = fract(tdP1);\n' +
          '    vec2 tdU = tdF * tdF * (3.0 - 2.0 * tdF);\n' +
          '    vec2 tdDu = 6.0 * tdF * (1.0 - tdF);\n' +
          '    float tdA = fmHash(tdI), tdB = fmHash(tdI + vec2(1.0, 0.0));\n' +
          '    float tdC = fmHash(tdI + vec2(0.0, 1.0)), tdD = fmHash(tdI + vec2(1.0, 1.0));\n' +
          '    float tdK1 = tdB - tdA, tdK2 = tdC - tdA, tdK3 = tdA - tdB - tdC + tdD;\n' +
          '    vec2 tdG1 = tdDu * (vec2(tdK1, tdK2) + tdK3 * tdU.yx);\n' +
          '    tdI = floor(tdP2); tdF = fract(tdP2);\n' +
          '    tdU = tdF * tdF * (3.0 - 2.0 * tdF);\n' +
          '    tdDu = 6.0 * tdF * (1.0 - tdF);\n' +
          '    tdA = fmHash(tdI); tdB = fmHash(tdI + vec2(1.0, 0.0));\n' +
          '    tdC = fmHash(tdI + vec2(0.0, 1.0)); tdD = fmHash(tdI + vec2(1.0, 1.0));\n' +
          '    tdK1 = tdB - tdA; tdK2 = tdC - tdA; tdK3 = tdA - tdB - tdC + tdD;\n' +
          '    vec2 tdG2 = tdDu * (vec2(tdK1, tdK2) + tdK3 * tdU.yx);\n' +
          '    vec2 tdGrad = tdG1 * 0.6 + tdG2 * 0.14;\n' +
          // 远处渐隐：地平线附近的高频扰动只会闪烁。强度压低 —— 要的是
          // 「阳光下起伏的草皮」，太强会变成一地霉斑。
          '    float tdFade = 1.0 - smoothstep(700.0, 1800.0, length(vViewPosition));\n' +
          '    normal = normalize(normal + (viewMatrix *\n' +
          '      vec4(-tdGrad.x, 0.0, -tdGrad.y, 0.0)).xyz * (0.55 * tdFade));\n' +
          '  }');
    };
    const prevKey = material.customProgramCacheKey;
    material.customProgramCacheKey = function () {
      return (prevKey ? prevKey.call(material) : '') + '+terraindetail';
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
   * 地表高度。地形网格、道路贴花、单位与建筑的落点都用这一个函数，
   * 否则各算各的就会出现「单位悬空」「路飘在坡上」这类错位。
   */
  const _ghCache = new Map();
  function rollingHeight(x, y) {
    return Math.sin(x * 0.0016) * Math.cos(y * 0.0021) * 7
      + Math.sin(x * 0.0007 + y * 0.0011) * 5
      + Math.sin(x * 0.0068 + y * 0.0043) * 1.6
      + Math.cos(x * 0.0121 - y * 0.0097) * 0.8;
  }

  function groundHeight(x, y) {
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
    const depth = riverDepthAt(x, y);
    const roll = rollingHeight(x, y);
    const result = roll - depth * depth * 66 + mountainHeightAt(x, y);
    _ghCache.set(key, result);
    return result;
  }

  /**
   * 把泥地照片「洗」成干净的细节贴图（Apple/Google 式干净地表的关键一步）。
   *
   * 原图偏暗、饱和、颗粒重，直接乘在顶点色上整张地图发闷、发脏。这里一次性
   * 处理成：降采样软化颗粒 → 大幅去饱和（固有色交给顶点色分层）→ 提亮并压
   * 对比（围绕一个亮基调收拢，泥点变成细腻的明暗颗粒）。贴图从此只提供微观
   * 质感，宏观颜色全由顶点色决定 —— 这正是干净地图「颜色是大块平滑形状」的
   * 做法。原图加载失败或处理异常时回退原图，绝不让地面渲染开天窗。
   */
  function cleanGroundTexture(image) {
    const size = 512;                 // 顺手降采样：canvas 缩放自带柔化
    const cv = document.createElement('canvas');
    cv.width = cv.height = size;
    const ctx = cv.getContext('2d');
    ctx.drawImage(image, 0, 0, size, size);
    const img = ctx.getImageData(0, 0, size, size);
    const d = img.data;
    // 泥感主要来自脏褐的色相和重颗粒，不是单纯的暗。所以重点去饱和 + 柔化，
    // 亮度只适度提（BASE 150 ≈ 0.59，比原图 ~0.37 亮但留给 AgX 足够高光余量）。
    const KEEP_SAT = 0.22;             // 只留一点点固有色
    const BASE = 150, CONTRAST = 0.42; // 适度提亮 + 收对比
    for (let i = 0; i < d.length; i += 4) {
      const lum = 0.299 * d[i] + 0.587 * d[i + 1] + 0.114 * d[i + 2];
      for (let k = 0; k < 3; k++) {
        const v = lum + (d[i + k] - lum) * KEEP_SAT;       // 去饱和
        const lifted = BASE + (v - 128) * CONTRAST;         // 提亮 + 收对比
        d[i + k] = lifted < 0 ? 0 : (lifted > 255 ? 255 : lifted);
      }
    }
    ctx.putImageData(img, 0, 0);
    const tex = new THREE.CanvasTexture(cv);
    tex.colorSpace = THREE.SRGBColorSpace;
    return tex;
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
      const height = rollingHeight(wx, wz) - depth * depth * 66 + rock;
      heights[i] = height;
      pos.setY(i, height);

      // 地表分层着色。参考 Apple/Google 地图的「干净地表」：色相聚拢成柔和的
      // 鼠尾草绿、压小明度差，另叠一层随海拔的拓扑明暗（坡顶受光、谷底背光），
      // 让大地形不靠噪点也有层次。河道仍是干涸沟壑，但沟底从黑泥抬成暖褐干沟。
      const stone = Math.min(1, rock / 70);
      // 沟壑带：越深越靠近沟底，色越干越暗
      const ravine = Math.min(1, depth * 1.4);
      // 风化土岸沿：沟口那一圈浅色干土亮边
      const bank = Math.max(0, 1 - Math.abs(depth - 0.10) / 0.14) * (depth > 0.005 ? 1 : 0);
      // 低频噪声决定草木茂盛程度，和撒草木用的是同一套噪声，色块和植被对得上
      const lush = clumpNoise(wx, wz);
      // 归一化海拔 → 拓扑光影：坡顶微亮、谷底微暗，所有分区最后统一乘上
      const topo = 1 + Math.max(-1, Math.min(1, height / 24)) * 0.08;

      // 柔和春绿：降一点峰值饱和、抬一点蓝，绿得不再「荧光」，更像鼠尾草
      let r = 0.70 + lush * 0.12;
      let g = 1.00 + lush * 0.30;
      let b = 0.56 + lush * 0.12;
      // 干土斑块：晒黄的草皮（收一点，别那么燥）
      const dry = Math.max(0, 0.42 - lush) * 1.6;
      r += dry * 0.30; g += dry * 0.03; b -= dry * 0.06;
      // 风化土岸沿：绿地和沟壑之间的那道干土亮边
      r = r * (1 - bank) + 0.80 * bank;
      g = g * (1 - bank) + 0.64 * bank;
      b = b * (1 - bank) + 0.42 * bank;
      // 岩石：带一点暖意的灰，不是水泥灰
      r = r * (1 - stone * 0.5) + stone * 0.62;
      g = g * (1 - stone * 0.46) + stone * 0.60;
      b = b * (1 - stone * 0.40) + stone * 0.57;
      // 沟壑底：抬成暖褐干沟，不再是吸光的黑泥
      r = r * (1 - ravine) + 0.46 * ravine;
      g = g * (1 - ravine) + 0.38 * ravine;
      b = b * (1 - ravine) + 0.27 * ravine;
      r *= topo; g *= topo; b *= topo;
      colors[i * 3] = r;
      colors[i * 3 + 1] = g;
      colors[i * 3 + 2] = b;
    }
    geo.setAttribute('color', new THREE.BufferAttribute(colors, 3));
    geo.computeVertexNormals();

    const material = applyFogMask(new THREE.MeshLambertMaterial({
      map: groundTexture, vertexColors: true
    }));
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

    // 河道不画水面：按干涸的沟壑处理。地形已沿河挖出一条深槽（groundHeight
    // 里的 riverDepthAt），沟底由上面的顶点着色压成土岩色，桥跨在槽上。
    // 没有水，也没有蓝板子 —— 走到河边看到的是真的过不去的深沟。
    waterMesh = null;

    // 桥梁：唯一能跨过沟壑的地方，必须一眼看得出来。桥面比路面略高，
    // 两侧加护栏和桥墩，让它在深沟上「立」起来而不是一块贴图。
    // 所有桥合并成一个网格：一张图上只有三五座桥，分开做剔除没意义，
    // 合并后从五十多次绘制调用降到一次。
    const bridges = (state.terrain && state.terrain.bridges) || [];
    if (bridges.length) {
      // 深色做旧木料：新光照 + 高曝光下原来的浅木色会晒成一块白板。
      // 两种板色交替 + 深色底板缝，桥面才有「一块块木板」的读感。
      const DECK = [0.16, 0.12, 0.075];
      const PLANK = [0.46, 0.36, 0.22];
      const PLANK_B = [0.34, 0.26, 0.155];
      const PIER = [0.22, 0.19, 0.155];
      const parts = [];
      const slab = function (w, h, d, x, y, z, rgb) {
        parts.push({
          geo: new THREE.BoxGeometry(w, h, d),
          matrix: new THREE.Matrix4().setPosition(x, y, z),
          rgb: rgb
        });
      };
      bridges.forEach(function (b) {
        const along = b.w >= b.h;          // 桥的走向
        // 渲染用的桥长要比碰撞尺寸长：岸线做了抖动加宽之后，可见水面比
        // 服务端的碰撞河宽宽出不少，照原尺寸画的桥会「够不到两岸」。
        // 碰撞尺寸是玩法数据（决定哪里能过河），一个字都不能动，
        // 所以只把画出来的那一截加长。
        const bw = along ? b.w * BRIDGE_RENDER_SPAN : b.w;
        const bh = along ? b.h : b.h * BRIDGE_RENDER_SPAN;
        slab(bw, 6, bh, b.x, 2.2, b.y, DECK);
        // 桥板纹理：两种木色交替的枕木，板缝露出深色底板
        const planks = Math.max(5, Math.round((along ? bw : bh) / 20));
        for (let i = 0; i < planks; i++) {
          const t = (i + 0.5) / planks - 0.5;
          const wood = i % 2 ? PLANK_B : PLANK;
          if (along) {
            slab(bw / planks * 0.78, 1.4, bh * 0.94, b.x + t * bw, 5.6, b.y, wood);
          } else {
            slab(bw * 0.94, 1.4, bh / planks * 0.78, b.x, 5.6, b.y + t * bh, wood);
          }
        }
        [-1, 1].forEach(function (side) {
          if (along) {
            // 侧缘纵梁 + 护栏 + 桥墩
            slab(bw, 3.2, 7, b.x, 6.6, b.y + side * (bh / 2 - 3.5), PIER);
            slab(bw, 6, 3.5, b.x, 11, b.y + side * (bh / 2 - 2), PLANK_B);
            slab(9, 46, bh * 0.7, b.x + side * bw * 0.30, -20, b.y, PIER);
          } else {
            slab(7, 3.2, bh, b.x + side * (bw / 2 - 3.5), 6.6, b.y, PIER);
            slab(3.5, 6, bh, b.x + side * (bw / 2 - 2), 11, b.y, PLANK_B);
            slab(bw * 0.7, 46, 9, b.x, -20, b.y + side * bh * 0.30, PIER);
          }
        });
      });
      const bridgeMesh = new THREE.Mesh(
        mergeParts(parts),
        applyFogMask(new THREE.MeshLambertMaterial({ vertexColors: true })));
      bridgeMesh.castShadow = state.shadows !== 'off';
      bridgeMesh.receiveShadow = true;
      bridgeMesh.frustumCulled = false;
      terrainGroup.add(bridgeMesh);
    }

    // 地图边界：一圈向外倾斜下沉的裙边，颜色贴近雾色，让边缘融进远景而
    // 不是留下一道生硬的黑边
    const edgeMat = applyFogMask(new THREE.MeshLambertMaterial({
      color: 0x5c6a48, fog: true, side: THREE.DoubleSide
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

    buildRoads();
    buildRocks();
    buildOreField();
    state.buildTerrainMs = Math.round(performance.now() - buildStarted);
    const scatterStarted = performance.now();
    buildScatter();
    state.buildScatterMs = Math.round(performance.now() - scatterStarted);
  }

  /**
   * 道路：沿路径切成小段的贴地带状网格，逐点采样地表高度。
   * 用一个平面贴上去会在起伏处穿模，所以必须跟着地形走。
   */
  function buildRoads() {
    const roads = (state.terrain && state.terrain.roads) || [];
    if (!roads.length) return;

    const positions = [];
    const colors = [];
    const LIFT = 1.8;                 // 略微抬离地表，避免 z-fighting
    const bridges = (state.terrain && state.terrain.bridges) || [];
    const BRIDGE_DECK = 4.4;          // 桥面顶部高度，与 buildTerrain 里一致

    const onBridge = function (x, y) {
      for (let i = 0; i < bridges.length; i++) {
        const b = bridges[i];
        // 用渲染桥长判定，路面才会正好停在桥头而不是水里
        const along = b.w >= b.h;
        const bw = (along ? b.w * BRIDGE_RENDER_SPAN : b.w) * 0.5 + 12;
        const bh = (along ? b.h : b.h * BRIDGE_RENDER_SPAN) * 0.5 + 12;
        if (Math.abs(x - b.x) <= bw && Math.abs(y - b.y) <= bh) return true;
      }
      return false;
    };
    // 路面在过桥处要抬到桥面高度，否则会沉进河床里
    const roadHeight = function (x, y) {
      return onBridge(x, y) ? BRIDGE_DECK : groundHeight(x, y) + LIFT;
    };
    // 桥面本身就是路：那一段不铺路面，否则会把桥的栏杆和木纹整个盖住。
    // 沟壑里又没有桥的地方同样不铺 —— 那段本来就走不了。
    const skipRoad = function (x, y) {
      return onBridge(x, y) || riverDepthAt(x, y) > 0.35;
    };

    roads.forEach(function (road) {
      const dx = road.x2 - road.x1;
      const dy = road.y2 - road.y1;
      const length = Math.hypot(dx, dy);
      if (length < 1) return;
      const steps = Math.max(2, Math.ceil(length / 40));
      const nx = -dy / length;        // 路面法向（水平面内）
      const ny = dx / length;
      const half = road.width * 0.5;

      let prev = null;
      for (let i = 0; i <= steps; i++) {
        const t = i / steps;
        const cx = road.x1 + dx * t;
        const cy = road.y1 + dy * t;
        const lx = cx + nx * half;
        const ly = cy + ny * half;
        const rx = cx - nx * half;
        const ry = cy - ny * half;
        const cur = {
          l: [lx, roadHeight(lx, ly), ly],
          c: [cx, roadHeight(cx, cy), cy],
          r: [rx, roadHeight(rx, ry), ry],
          skip: skipRoad(cx, cy)
        };
        if (prev && !prev.skip && !cur.skip) {
          // 左半幅与右半幅各两个三角形；中缝顶点更亮，形成中线
          const quad = function (a1, a2, b1, b2, shadeA, shadeB) {
            positions.push(a1[0], a1[1], a1[2], b1[0], b1[1], b1[2], a2[0], a2[1], a2[2]);
            positions.push(a2[0], a2[1], a2[2], b1[0], b1[1], b1[2], b2[0], b2[1], b2[2]);
            const push = function (v) { colors.push(v, v, v); };
            push(shadeA); push(shadeB); push(shadeA);
            push(shadeA); push(shadeB); push(shadeB);
          };
          // 路肩压暗、路心提亮，形成一条自然的中线
          quad(prev.l, cur.l, prev.c, cur.c, 0.5, 1.25);
          quad(prev.c, cur.c, prev.r, cur.r, 1.25, 0.5);
        }
        prev = cur;
      }
    });

    if (!positions.length) return;
    const geo = new THREE.BufferGeometry();
    geo.setAttribute('position', new THREE.BufferAttribute(new Float32Array(positions), 3));
    geo.setAttribute('color', new THREE.BufferAttribute(new Float32Array(colors), 3));
    geo.computeVertexNormals();
    const material = applyFogMask(new THREE.MeshLambertMaterial({
      color: 0x7d7160, vertexColors: true, side: THREE.DoubleSide,
      polygonOffset: true, polygonOffsetFactor: -2, polygonOffsetUnits: -2
    }));
    const mesh = new THREE.Mesh(geo, material);
    mesh.receiveShadow = true;
    mesh.renderOrder = 1;
    terrainGroup.add(mesh);
  }

  /* -------------------- 植被与地面杂物 -------------------- *
   *
   * 空旷的棕色平原是「像素游戏」和「成品 RTS」最直观的差距 —— 参考画面里到处
   * 是松树、灌木、碎石。这里按确定性哈希在地图上撒点，再按 1400 单位见方分块
   * 把每块里的所有草木烘焙成一个合并网格。
   *
   * 为什么烘焙而不是 InstancedMesh：一块地里有松树、灌木、石头好几种几何体，
   * 实例化就得每种一个 mesh（可见区块 × 种类 = 几十次绘制调用）；合并之后
   * 一个可见区块只要一次绘制调用，而且 three.js 会自动按包围球做视锥剔除。
   *
   * 这些完全是装饰：服务端不知道它们存在，不参与寻路也不阻挡射击。用地图
   * 数据本身做种子，所以每个客户端撒出来的位置一致。
   */

  const SCATTER_CHUNK = 1400;
  let scatterGroup = null;
  // 取消令牌：新的 buildScatter 会让仍在分块构建的旧任务自动放弃（重连/改画质）。
  let scatterBuildToken = 0;

  // 各主题的配色：松林 / 荒漠 / 城区废墟
  const SCATTER_THEMES = {
    grassland: {
      trunk: [0.42, 0.30, 0.19],
      // 灰绿/橄榄（抬红蓝、压一点绿峰），和洗干净的鼠尾草地面同色系，不刺眼
      foliage: [[0.30, 0.50, 0.30], [0.38, 0.60, 0.37], [0.25, 0.41, 0.27]],
      bush: [[0.38, 0.54, 0.33], [0.46, 0.61, 0.39]],
      rock: [[0.40, 0.39, 0.36], [0.32, 0.31, 0.29]],
      reed: [[0.42, 0.50, 0.30], [0.50, 0.57, 0.34]],
      density: 1.0
    },
    arid: {
      trunk: [0.34, 0.26, 0.17],
      foliage: [[0.34, 0.34, 0.19], [0.40, 0.38, 0.22], [0.28, 0.28, 0.16]],
      bush: [[0.38, 0.34, 0.20], [0.44, 0.39, 0.24]],
      rock: [[0.46, 0.41, 0.33], [0.36, 0.32, 0.26]],
      reed: [[0.48, 0.45, 0.24], [0.56, 0.50, 0.30]],
      density: 0.55
    },
    urban: {
      trunk: [0.28, 0.26, 0.24],
      foliage: [[0.22, 0.30, 0.20], [0.26, 0.34, 0.23], [0.18, 0.25, 0.18]],
      bush: [[0.30, 0.30, 0.28], [0.36, 0.35, 0.32]],
      rock: [[0.42, 0.41, 0.40], [0.33, 0.32, 0.31]],
      reed: [[0.34, 0.42, 0.26], [0.42, 0.48, 0.30]],
      density: 0.7
    }
  };

  /** 位置哈希：同一张地图每次撒出来的草木完全一致。 */
  function hash2(x, y) {
    let h = (Math.imul(x | 0, 374761393) ^ Math.imul(y | 0, 668265263)) >>> 0;
    h = Math.imul(h ^ (h >>> 13), 1274126177) >>> 0;
    return ((h ^ (h >>> 16)) >>> 0) / 4294967296;
  }

  /** 低频噪声：决定哪里成林、哪里空旷，避免草木均匀铺满显得假。 */
  function clumpNoise(x, y) {
    return (Math.sin(x * 0.00085 + y * 0.00042) * 0.5
      + Math.sin(x * 0.00031 - y * 0.00097) * 0.35
      + Math.sin((x + y) * 0.00058) * 0.25) * 0.5 + 0.5;
  }

  /**
   * 草木零件的几何模板，全局只建一次。
   *
   * 每棵树都 new 一组 ConeGeometry 的话，一张大图要造上万个几何体对象，
   * 开局会明显卡一下，显存也吃不消。模板 + 矩阵缩放把这部分开销降到常数。
   * 面数也压到最低：一棵松树约 40 个三角形，撒一两千棵才不会失控。
   */
  const SCATTER_GEO = {
    trunk: new THREE.CylinderGeometry(0.055, 0.095, 1, 4),
    cone: new THREE.ConeGeometry(1, 1, 5),
    blob: new THREE.DodecahedronGeometry(1, 0),
    disc: new THREE.CircleGeometry(1, 6).rotateX(-Math.PI / 2)
  };

  function scaled(geo, sx, sy, sz, x, y, z, rgb) {
    const m = new THREE.Matrix4().makeScale(sx, sy, sz);
    m.setPosition(x, y, z);
    return { geo: geo, matrix: m, rgb: rgb };
  }

  function pineParts(scale, rand, theme) {
    const trunkH = 17 * scale;
    return [
      scaled(SCATTER_GEO.trunk, 17 * scale, trunkH, 17 * scale,
        0, trunkH / 2, 0, theme.trunk),
      scaled(SCATTER_GEO.cone, 13 * scale, 22 * scale, 13 * scale,
        0, trunkH * 0.72 + 11 * scale, 0, theme.foliage[0]),
      scaled(SCATTER_GEO.cone, 8.5 * scale, 17 * scale, 8.5 * scale,
        0, trunkH * 0.72 + 22 * scale, 0, theme.foliage[1]),
      scaled(SCATTER_GEO.disc, 11 * scale, 1, 11 * scale,
        0, 0.6, 0, [0.06, 0.07, 0.05])
    ];
  }

  function bushParts(scale, rand, theme) {
    const parts = [];
    for (let i = 0; i < 2; i++) {
      const a = rand() * TAU;
      const d = 3.2 * scale * rand();
      const r = (5.4 - i * 1.2) * scale;
      parts.push(scaled(SCATTER_GEO.blob, r, r * 0.8, r,
        Math.cos(a) * d, r * 0.7, Math.sin(a) * d,
        theme.bush[i % theme.bush.length]));
    }
    parts.push(scaled(SCATTER_GEO.disc, 7 * scale, 1, 7 * scale,
      0, 0.5, 0, [0.07, 0.08, 0.06]));
    return parts;
  }

  /** 岸边芦苇：几根细长锥体，把水陆边界接起来。 */
  function reedParts(scale, rand, theme) {
    const parts = [];
    const blades = 4;
    for (let i = 0; i < blades; i++) {
      const a = rand() * TAU;
      const d = 3.5 * scale * rand();
      const h = (13 + rand() * 11) * scale;
      parts.push(scaled(SCATTER_GEO.cone, 1.5 * scale, h, 1.5 * scale,
        Math.cos(a) * d, h * 0.5, Math.sin(a) * d, theme.reed[i % theme.reed.length]));
    }
    return parts;
  }

  function pebbleParts(scale, rand, theme) {
    const parts = [];
    const count = 2;
    for (let i = 0; i < count; i++) {
      const a = rand() * TAU;
      const d = 5 * scale * rand();
      const r = (2.8 + rand() * 2.2) * scale;
      parts.push(scaled(SCATTER_GEO.blob, r, r * 0.7, r * 1.1,
        Math.cos(a) * d, r * 0.5, Math.sin(a) * d,
        theme.rock[i % theme.rock.length]));
    }
    return parts;
  }

  /** 这个点能不能长草木：水里、山上、路上、基地和矿区附近都不行。 */
  function scatterAllowed(x, y, spawnPoints, resources) {
    // 允许长到浅岸上：光秃秃的岸线不真实，芦苇和滩石能把水陆接起来
    if (riverDepthAt(x, y) > 0.34) return false;
    if (mountainHeightAt(x, y) > 6) return false;
    const roads = (state.terrain && state.terrain.roads) || [];
    for (let i = 0; i < roads.length; i++) {
      const r = roads[i];
      const dx = r.x2 - r.x1;
      const dy = r.y2 - r.y1;
      const lenSq = dx * dx + dy * dy;
      let t = lenSq < 1 ? 0 : ((x - r.x1) * dx + (y - r.y1) * dy) / lenSq;
      t = Math.max(0, Math.min(1, t));
      const cx = r.x1 + t * dx;
      const cy = r.y1 + t * dy;
      if (Math.hypot(x - cx, y - cy) < r.width * 0.5 + 26) return false;
    }
    for (let i = 0; i < spawnPoints.length; i++) {
      const s = spawnPoints[i];
      if (Math.hypot(x - s[0], y - s[1]) < 620) return false;   // 给基地留出空地
    }
    for (let i = 0; i < resources.length; i++) {
      const res = resources[i];
      if (Math.hypot(x - res.x, y - res.y) < res.radius + 90) return false;
    }
    return true;
  }

  function buildScatter() {
    // 取消任何仍在分块构建的旧任务，并清掉旧植被
    const token = ++scatterBuildToken;
    if (scatterGroup) {
      worldRoot.remove(scatterGroup);
      scatterGroup.traverse(function (o) { if (o.geometry) o.geometry.dispose(); });
      scatterGroup = null;
    }
    state.scatterCount = 0;
    state.scatterChunks = 0;
    if (!state.scatter || !state.map) return;

    const mw = state.map.width;
    const mh = state.map.height;
    const theme = SCATTER_THEMES[(state.terrain && state.terrain.theme)] ||
      SCATTER_THEMES.grassland;
    const spawnPoints = state.spawnPoints || [];
    const resources = state.resources || [];

    const material = applyFogMask(new THREE.MeshLambertMaterial({
      vertexColors: true, flatShading: true
    }));

    const chunksX = Math.ceil(mw / SCATTER_CHUNK);
    const chunksY = Math.ceil(mh / SCATTER_CHUNK);
    const step = 84 / theme.density;      // 采样间距，越小越密
    const group = new THREE.Group();
    let placed = 0;

    // 单个 1400 单位见方区块的采样与合并（原同步双重循环的循环体，逻辑原样保留）
    function buildChunk(cx, cy) {
      const parts = [];
      const x0 = cx * SCATTER_CHUNK;
      const y0 = cy * SCATTER_CHUNK;
      const x1 = Math.min(mw, x0 + SCATTER_CHUNK);
      const y1 = Math.min(mh, y0 + SCATTER_CHUNK);

      for (let sx = x0; sx < x1; sx += step) {
        for (let sy = y0; sy < y1; sy += step) {
          const h1 = hash2(sx * 7.3, sy * 3.1);
          // 成林/空地：低频噪声决定这一带的密度
          const clump = clumpNoise(sx, sy);
          if (h1 > 0.10 + clump * 0.78) continue;   // 噪声高的地方成密林

          // 在格子里抖动，避免看出网格
          const jx = sx + (hash2(sx * 1.7, sy * 9.4) - 0.5) * step * 1.6;
          const jy = sy + (hash2(sx * 5.1, sy * 2.9) - 0.5) * step * 1.6;
          if (jx < 40 || jy < 40 || jx > mw - 40 || jy > mh - 40) continue;
          if (!scatterAllowed(jx, jy, spawnPoints, resources)) continue;

          let seed = Math.floor(hash2(jx * 3.7, jy * 8.2) * 1e9);
          const rand = function () {
            seed = (seed * 1103515245 + 12345) & 0x7fffffff;
            return seed / 0x7fffffff;
          };

          const kind = rand();
          const scale = 1.15 + rand() * 0.95;
          const nearRavine = riverDepthAt(jx, jy) > 0.04;
          let items;
          if (nearRavine) {
            // 沟壑坡面不长草木，只有碎石
            items = pebbleParts(scale * 1.3, rand, theme);
          } else if (kind < 0.62) items = pineParts(scale, rand, theme);
          else if (kind < 0.86) items = bushParts(scale * 1.1, rand, theme);
          else items = pebbleParts(scale, rand, theme);

          const place = new THREE.Matrix4()
            .makeRotationY(rand() * TAU)
            .setPosition(jx, groundHeight(jx, jy), jy);
          items.forEach(function (part) {
            part.matrix = place.clone().multiply(part.matrix);
            parts.push(part);
          });
          placed++;
        }
      }

      if (!parts.length) return;
      const mesh = new THREE.Mesh(mergeParts(parts), material);
      // 每块单独一个 mesh，three.js 按包围球自动视锥剔除；
      // 再加一个到相机的距离剔除（见 render 里的 scatterCull）。
      mesh.frustumCulled = true;
      mesh.castShadow = false;
      mesh.receiveShadow = false;
      mesh.userData.cx = (x0 + x1) / 2;
      mesh.userData.cy = (y0 + y1) / 2;
      group.add(mesh);
    }

    // 撒草木是纯装饰：单位落地、拾取、迷雾都不依赖它。原先它在地形构建末尾
    // 一次性跑完（上万零件的合并），开局会明显卡一下。改成首帧之后按块构建，
    // 每帧最多约 8ms；全部建完才整体挂进场景，避免树木逐块「蹦」出来。
    let cx = 0, cy = 0;
    const stepFrame = function () {
      if (token !== scatterBuildToken) {
        // 被更新的 buildScatter 取代（重连 / 改画质），丢弃这个半成品
        group.traverse(function (o) { if (o.geometry) o.geometry.dispose(); });
        return;
      }
      const deadline = performance.now() + 8;
      while (cy < chunksY) {
        buildChunk(cx, cy);
        cx++;
        if (cx >= chunksX) { cx = 0; cy++; }
        if (performance.now() >= deadline) break;
      }
      if (cy < chunksY) {
        requestAnimationFrame(stepFrame);
      } else {
        scatterGroup = group;
        worldRoot.add(scatterGroup);
        state.scatterCount = placed;
        state.scatterChunks = group.children.length;
      }
    };
    requestAnimationFrame(stepFrame);
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

  /* -------------------- 矿脉 -------------------- */

  let oreGroup = null;
  const oreMeshes = new Map();

  function buildOreField() {
    if (oreGroup) worldRoot.remove(oreGroup);
    oreGroup = new THREE.Group();
    worldRoot.add(oreGroup);
    oreMeshes.clear();
    if (!state.resources) return;

    // 水晶用 Basic 材质，加自发光系数 >1 让辉光后处理提取出来
    const crystalMat = new THREE.MeshStandardMaterial({
      color: 0xffd966, emissive: 0xffaa00, emissiveIntensity: 1.8,
      roughness: 0.55, metalness: 0.3, vertexColors: false
    });
    const crystalGeo = new THREE.ConeGeometry(1, 1, 5);
    // 地面辉光环：让矿脉在绿色草皮上有一个「发光底座」，拉远也不会消失
    const discGeo = new THREE.CircleGeometry(1, 18).rotateX(-Math.PI / 2);
    const discMat = new THREE.MeshBasicMaterial({
      color: 0xffc840, transparent: true, opacity: 0.32,
      depthWrite: false, fog: false, side: THREE.DoubleSide
    });
    const guardRingGeo = new THREE.RingGeometry(0.82, 1.0, 32).rotateX(-Math.PI / 2);
    const guardRingMat = new THREE.MeshBasicMaterial({
      color: 0xff3f2f, transparent: true, opacity: 0.82,
      depthWrite: false, fog: false, side: THREE.DoubleSide
    });
    state.resources.forEach(function (res) {
      const cluster = new THREE.Group();
      cluster.position.set(res.x, groundHeight(res.x, res.y), res.y);
      cluster.userData.resourceId = res.id;

      // 地面辉光底座：大小跟随矿脉范围，始终贴地
      const disc = new THREE.Mesh(discGeo, discMat);
      disc.scale.set(res.radius * 0.85, 1, res.radius * 0.85);
      disc.position.y = 2.6;
      disc.renderOrder = 2;
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
      const count = Math.max(10, Math.round(res.radius / 7));
      for (let i = 0; i < count; i++) {
        const a = rand() * TAU;
        const rr = Math.sqrt(rand()) * res.radius * 0.9;
        const h = 10 + rand() * 26;
        const crystal = new THREE.Mesh(crystalGeo, crystalMat);
        crystal.position.set(Math.cos(a) * rr, h / 2 + 2, Math.sin(a) * rr);
        crystal.scale.set(4 + rand() * 4, h, 4 + rand() * 4);
        crystal.rotation.y = rand() * TAU;
        crystal.castShadow = false;
        cluster.add(crystal);
      }
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
      const ratio = res && res.maxAmount ? Math.max(0, ore[i][1] / res.maxAmount) : 1;
      cluster.visible = ratio > 0.001;
      const s = 0.25 + ratio * 0.75;
      cluster.scale.set(1, s, 1);
      if (cluster.userData.guardRing) {
        cluster.userData.guardRing.visible = !!ore[i][2] && ratio > 0.001;
        cluster.userData.guardRing.material.opacity =
          0.62 + 0.22 * Math.sin(time * 0.006 + i);
      }
      // 晶体脉冲：矿量越满闪得越亮，远处也看得见
      if (cluster.children.length > 0 && cluster.children[0].material) {
        const disc = cluster.children[0];
        if (disc.material && disc.material.opacity !== undefined) {
          const pulse = 0.28 + 0.16 * Math.sin((time * 0.003 + ore[i][0].charCodeAt(0)) * 1.7);
          disc.material.opacity = pulse * ratio;
        }
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
  const STRIKE_RADIUS = 180;          // 与服务端 STRIKE_RADIUS 对齐
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
      // 外圈：危险区
      quat.setFromAxisAngle(upAxis, rot);
      matrix.compose(vecAux.set(s.x, gy, s.y), quat, vecScale.set(STRIKE_RADIUS, 1, STRIKE_RADIUS));
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

  function updateFog() {
    if (!fogCtx) return;
    const fw = fogCanvas.width;
    const fh = fogCanvas.height;
    const inv = 1 / state.fogScale;

    // 红警 2 式黑幕：把每次走到的视野永久画进 exploredCanvas，之后不会
    // 因单位离开而重新压暗。边缘使用软渐变，探图边界不会像圆规画出来。
    exploredCtx.globalCompositeOperation = 'source-over';
    for (let i = 0; i < visionSources.length; i += 3) {
      const cx = visionSources[i] * inv;
      const cy = visionSources[i + 1] * inv;
      const r = visionSources[i + 2] * inv;
      const d = r * 2;
      exploredCtx.drawImage(fogGradientCanvas, cx - r, cy - r, d, d);
    }

    // 只剩“未探索 / 已探索”两种状态：已探索区域完全清除黑幕，不再有
    // 当前视野之外的二次灰雾。敌方移动单位仍按服务端实时视野规则隐藏。
    fogCtx.globalCompositeOperation = 'source-over';
    fogCtx.fillStyle = 'rgba(3, 7, 9, 0.94)';
    fogCtx.fillRect(0, 0, fw, fh);
    fogCtx.globalCompositeOperation = 'destination-out';
    fogCtx.drawImage(exploredCanvas, 0, 0);
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
  const unitMaterial = applyEmissiveByVertexColor(
    new THREE.MeshLambertMaterial({ vertexColors: true }));
  const unitPools = new Map();     // kind -> { mesh, glow, simple, capacity }
  const shadowGeo = new THREE.CircleGeometry(1, 12).rotateX(-Math.PI / 2);
  const shadowMaterial = new THREE.MeshBasicMaterial({
    color: 0x000000, transparent: true, opacity: 0.3, depthWrite: false, fog: false
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
    const infantry = [
      taperedBox(7, 5, 5.5, 4, 10, 0, 7, 0, 0.9),
      box(3, 5, 7, -2.5, 8, 0, MAT.olive)
    ];
    if (kind === 'rifle') {
      return infantry.concat([box(12, 1.5, 1.5, 5, 9, 2, MAT.gunmetal)]);
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
      new THREE.MeshLambertMaterial({ color: 0xffffff, vertexColors: true }));
    const group = structureGroup(structure.kind, structure.size, teamMat);
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

  const tracerGeo = new THREE.CylinderGeometry(0.9, 0.9, 1, 6).rotateZ(Math.PI / 2);
  const tracerMaterial = new THREE.MeshBasicMaterial({ vertexColors: true, fog: false });
  let tracerMesh = null;

  const PROJECTILE_STYLE = {
    bullet: { len: 16, thick: 0.8, color: 0xfff0b0, arc: 0 },
    rocket: { len: 22, thick: 1.7, color: 0xff9a4a, arc: 34 },
    shell: { len: 18, thick: 1.5, color: 0xffd07a, arc: 22 },
    sniper: { len: 34, thick: 0.6, color: 0xbfe9ff, arc: 0 },
    siege: { len: 24, thick: 2.4, color: 0xffb347, arc: 120 },
    ap: { len: 26, thick: 1.0, color: 0xd8f0ff, arc: 6 },
    missile: { len: 32, thick: 2.8, color: 0xff6633, arc: 140 },
    // 磁暴电弧：短促、近乎笔直的蓝白电光
    tesla: { len: 16, thick: 1.4, color: 0x86b8ff, arc: 0 },
    // 光棱聚焦光束：细长、笔直、亮青色，指哪打哪
    laser: { len: 30, thick: 0.9, color: 0xa8f4ff, arc: 0 }
  };

  function ensureTracerMesh(needed) {
    if (tracerMesh && tracerMesh.instanceMatrix.count >= needed) return tracerMesh;
    if (tracerMesh) {
      worldRoot.remove(tracerMesh);
      tracerMesh.dispose();
    }
    tracerMesh = new THREE.InstancedMesh(tracerGeo, tracerMaterial,
      Math.max(64, Math.ceil(needed * 1.6)));
    tracerMesh.instanceMatrix.setUsage(THREE.DynamicDrawUsage);
    tracerMesh.frustumCulled = false;
    tracerMesh.count = 0;
    worldRoot.add(tracerMesh);
    return tracerMesh;
  }

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

  function flashAt(x, y) {
    let best = flashPool[0];
    for (let i = 1; i < flashPool.length; i++) {
      if (flashPool[i].life < best.life) best = flashPool[i];
    }
    best.life = best.maxLife;
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

  function spawnEffect(type, x, y) {
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
    } else if (type === 'impact') {
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
    } else if (type === 'muzzle') {
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
    // 草木剔除。两层：
    //   1) 拉远到战略视角时整组隐藏 —— 那个距离下草木只剩亚像素
    //   2) 否则按到相机的距离逐块剔除。光靠视锥不行：远裁剪面一万二，
    //      正前方的块全都「在视锥内」，但它们早被场景雾吃没了。
    if (scatterGroup) {
      const showScatter = camDist < 1800;
      scatterGroup.visible = showScatter;
      if (showScatter) {
        const cutoff = scene.fog.far * 0.92;
        const cutoffSq = cutoff * cutoff;
        const cx = camera.position.x;
        const cz = camera.position.z;
        const chunks = scatterGroup.children;
        for (let i = 0; i < chunks.length; i++) {
          const dx = chunks[i].userData.cx - cx;
          const dz = chunks[i].userData.cy - cz;
          chunks[i].visible = dx * dx + dz * dz < cutoffSq;
        }
      }
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
        node.spinner.rotation.y += dt * node.spinner.userData.speed;
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
    if (state.showProjectiles && projectiles.length) {
      const tracers = ensureTracerMesh(projectiles.length);
      let tracerCount = 0;
      for (let i = 0; i < projectiles.length; i++) {
        const p = projectiles[i];
        // 军犬的扑咬是近战：不画弹道，命中反馈交给服务端的 impact 特效
        if (p.kind === 'bite') continue;
        const pdx = p.x - state.camX;
        const pdy = p.y - state.camY;
        if (!inViewportBounds(p.x, p.y)) continue;
        const style = PROJECTILE_STYLE[p.kind] || PROJECTILE_STYLE.bullet;
        const t = p.t == null ? 0.5 : p.t;
        const height = 14 + style.arc * Math.sin(Math.PI * t);
        const dx = p.targetX - p.x;
        const dy = p.targetY - p.y;
        const yaw = Math.atan2(dy, dx);
        quat.setFromAxisAngle(upAxis, -yaw);
        matrix.compose(
          vecPos.set(p.x, height, p.y),
          quat,
          vecScale.set(style.len, style.thick, style.thick));
        tracers.setMatrixAt(tracerCount, matrix);
        tmpColor.setHex(style.color);
        tracers.setColorAt(tracerCount, tmpColor);
        tracerCount++;
      }
      tracers.count = tracerCount;
      tracers.instanceMatrix.needsUpdate = true;
      if (tracers.instanceColor) tracers.instanceColor.needsUpdate = true;
    } else if (tracerMesh) {
      tracerMesh.count = 0;
    }

    /* --- 特效 --- */
    // app.js 已经按 id 去重过，这里收到的都是本帧新出现的
    const fresh = payload.newEffects || [];
    for (let i = 0; i < fresh.length; i++) {
      spawnEffect(fresh[i].type, fresh[i].x, fresh[i].y);
    }
    updateEffects(dt);

    /* --- 选中环 --- */
    const selected = payload.selectedUnitIds;
    const rings = ensureRingMesh(selected.size + 1);
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
      if (options.scatter != null && !!options.scatter !== state.scatter) {
        state.scatter = !!options.scatter;
        if (state.map) buildScatter();
      }
      if (options.showProjectiles != null) state.showProjectiles = !!options.showProjectiles;
      if (options.postfx) postfx.setOptions(options.postfx);
    },

    /** 一局开始（或重连收到 full 帧）时调用，重建地形与静态数据。 */
    setMatch: function (map, terrain, resources, sight, spawnPoints) {
      state.map = map;
      state.terrain = terrain || { rivers: [], bridges: [] };
      state.resources = resources || [];
      state.resourceById = new Map();
      state.resources.forEach(function (r) { state.resourceById.set(r.id, r); });
      if (sight) state.sight = sight;
      // 撒草木时要避开出生点，给基地留出空地
      state.spawnPoints = spawnPoints || state.spawnPoints || [];

      const rebuild = function () { buildTerrain(); };
      if (!groundTexture) {
        groundTexture = textureLoader.load('/terrain-ground.png', function () {
          try {
            // 洗成干净细节贴图后再上地面；repeat 已在下面按地图尺寸设好，抄过来
            const cleaned = cleanGroundTexture(groundTexture.image);
            cleaned.wrapS = cleaned.wrapT = THREE.RepeatWrapping;
            cleaned.anisotropy = groundTexture.anisotropy;
            cleaned.repeat.copy(groundTexture.repeat);
            groundTexture = cleaned;
          } catch (err) {
            // 清洗失败就退回原图，地面照常渲染
            groundTexture.colorSpace = THREE.SRGBColorSpace;
          }
          rebuild();
        });
        groundTexture.wrapS = THREE.RepeatWrapping;
        groundTexture.wrapT = THREE.RepeatWrapping;
        groundTexture.anisotropy = Math.min(8, renderer.capabilities.getMaxAnisotropy());
        groundTexture.colorSpace = THREE.SRGBColorSpace;
      }
      // 重复更密：900 一贴在近景会被拉糊，看起来像低分辨率网格
      groundTexture.repeat.set(map.width / 420, map.height / 420);
      rebuild();
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
        scatter: state.scatterCount,
        scatterChunks: state.scatterChunks,
        buildTerrainMs: state.buildTerrainMs,
        buildScatterMs: state.buildScatterMs,
        geometries: renderer.info.memory.geometries,
        textures: renderer.info.memory.textures
      };
    },

    /** 单位的插值显示位置，用于点选/框选命中判定。 */
    visualPosition: function (id) { return visual.get(id) || null; },

    /** 在指定点播放一次特效。仅调试/截图脚本使用，不影响任何对局状态。 */
    debugEffect: function (type, x, y) { spawnEffect(type, x, y); },

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
