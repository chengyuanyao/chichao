import { createRenderer, MAP_DISPLAY_THEMES } from './render3d.js';

(function () {
  'use strict';

  var $ = function (selector) { return document.querySelector(selector); };
  var $$ = function (selector) { return Array.prototype.slice.call(document.querySelectorAll(selector)); };

  var SESSION_KEY = 'steel-front-lan-session';
  var NAME_KEY = 'steel-front-commander-name';

  // 造价/名称/角色/前置只信服务端目录（/api/catalog 与首帧 snapshot.catalog）。
  // 这里只留卡片图标和说明，避免再抄一份会漂移的数字表。
  var BUILDING_VFX = {
    power: { icon: 'ϟ', desc: '提供 120 电力' },
    refinery: { icon: '◆', desc: '接收采矿车资源' },
    barracks: { icon: '♟', desc: '训练步兵单位' },
    factory: { icon: '▰', desc: '生产装甲单位' },
    turret: { icon: '⌖', desc: '自动攻击附近敌军' },
    missile: { icon: '⊿', desc: '远程高伤大溅射，冷却慢' },
    repair: { icon: '✚', desc: '维修受损装甲载具' },
    mpower: { icon: '✦', desc: '提供 120 法力' },
    mrefinery: { icon: '◈', desc: '接收浮游晶簇的水晶' },
    mtemple: { icon: '✠', desc: '训练奥术法师' },
    mcircle: { icon: '⬡', desc: '召唤构装体与魔兽' },
    mtower: { icon: '✵', desc: '自动攻击附近敌军（魔法）' },
    mspring: { icon: '✚', desc: '修复受损构装、巨龙与晶簇；解锁进阶召唤' }
  };
  var UNIT_VFX = {
    rifle: { icon: '♟', desc: '灵活的基础步兵' },
    rocket: { icon: '↟', desc: '远程反装甲单位，克重甲' },
    sniper: { icon: '⌖', desc: '超远狙杀步兵，无力反甲' },
    dog: { icon: '♞', desc: '全场最速近战，扑咬步兵与法师，对载具/建筑/巨龙无效' },
    tank: { icon: '▰', desc: '主力装甲单位，克建筑' },
    scout: { icon: '◆', desc: '高速侦察战车' },
    artillery: { icon: '◉', desc: '极远溅射，克建筑/重甲' },
    tank_destroyer: { icon: '◭', desc: '专杀坦克，×2.1反重甲' },
    v3: { icon: '⊹', desc: '超远程导弹打击，大溅射' },
    overlord: { icon: '⬟', desc: '超重型主战，双管重炮抗线 · 需维修厂' },
    tesla: { icon: '⚡', desc: '动力甲反甲步兵，电弧专电载具 · 需工厂' },
    prism: { icon: '✦', desc: '远程聚焦光束，点杀轻型与建筑 · 需维修厂' },
    harvester: { icon: '▣', desc: '自动采集矿石' },
    mcv: { icon: '⬢', desc: '可展开为新指挥中心' },
    bomb_truck: { icon: '💣', desc: '高速药箱车，贴脸或阵亡大爆炸；克步兵堆与成团建筑' },
    mage: { icon: '✦', desc: '远程奥术弹，熔重甲的反坦克手' },
    frost: { icon: '❄', desc: '命中减速敌军，控制拉扯核心' },
    golem: { icon: '⛰', desc: '构装前排，高血投石溅射' },
    panther: { icon: '♞', desc: '全场最快魔兽，近战侧翼包抄' },
    dragon: { icon: '✹', desc: '重型远程火球，大溅射压轴 · 需圣泉' },
    warden: { icon: '⛊', desc: '晶铠前排，混甲抗磁暴/狙击/军犬 · 需圣泉' },
    colossus: { icon: '☄', desc: '远程晶陨，专拆建筑 · 需圣泉' },
    mharvester: { icon: '◈', desc: '自动采集水晶' },
    mmcv: { icon: '⬡', desc: '可展开为魔法主堡' },
    hexling: { icon: '✶', desc: '符核魔仆，贴脸或阵亡引爆；非载具，军犬能扑' }
  };

  var BUILDINGS = {};
  var UNITS = {};
  var STRUCTURE_NAMES = {};
  var STRUCTURE_ROLES = {};
  var UNIT_ROLES = {};

  function applyCatalog(catalog) {
    if (!catalog || !catalog.buildings || !catalog.units) { return; }
    Object.keys(catalog.buildings).forEach(function (kind) {
      var src = catalog.buildings[kind];
      var vfx = BUILDING_VFX[kind] || {};
      BUILDINGS[kind] = {
        name: src.name,
        cost: src.cost,
        build: src.build,
        size: src.size,
        requires: src.requires || [],
        faction: src.faction || 'tech',
        role: src.role || null,
        icon: vfx.icon || '■',
        desc: vfx.desc || ''
      };
      STRUCTURE_NAMES[kind] = src.name;
      if (src.role) { STRUCTURE_ROLES[kind] = src.role; }
    });
    Object.keys(catalog.units).forEach(function (kind) {
      var src = catalog.units[kind];
      var vfx = UNIT_VFX[kind] || {};
      UNITS[kind] = {
        name: src.name,
        cost: src.cost,
        build: src.build,
        size: src.size,
        producer: src.producer,
        requires: src.requires || [],
        faction: src.faction || 'tech',
        role: src.role || null,
        canDeploy: !!src.canDeploy,
        damageType: src.damageType,
        repairable: !!src.repairable,
        icon: vfx.icon || '▲',
        desc: vfx.desc || ''
      };
      if (src.role) { UNIT_ROLES[kind] = src.role; }
    });
  }

  var catalogPromise = fetch('/api/catalog').then(function (response) {
    return response.json();
  }).then(applyCatalog).catch(function () {});

  // 与 server.BUILD_ANCHOR_RANGES 一样按 role 索引；魔法主堡/法力塔等换皮
  // 建筑通过 STRUCTURE_ROLES 映射到同一半径，否则鬼影永远是红的。
  var BUILD_ANCHOR_RANGES = { hq: 360, power: 220, refinery: 250, barracks: 220, factory: 270, repair: 240 };
  var ENEMY_BUILD_EXCLUSION = 440;

  function structureRole(kind) { return STRUCTURE_ROLES[kind] || null; }
  function unitRole(kind) { return UNIT_ROLES[kind] || null; }

  var FACTION_COPY = {
    tech: {
      infantryTab: '步兵',
      vehicleTab: '载具',
      power: '电力',
      powerLoad: '电力负载',
      harvester: '采矿车',
      hq: '指挥中心',
      mcv: '基地车',
      repairBtn: '维修载具',
      repairTitle: '前往最近维修厂 (R)',
      repairHint: '维修载具',
      repairNeed: '没有可用的战地维修厂',
      repairSelect: '请选择受损的坦克、战车或采矿车',
      repairSent: '辆载具已前往维修厂'
    },
    magic: {
      infantryTab: '圣殿',
      vehicleTab: '法阵',
      power: '法力',
      powerLoad: '法力负载',
      harvester: '晶簇',
      hq: '魔法主堡',
      mcv: '迁徙法阵',
      repairBtn: '修复构装',
      repairTitle: '前往最近圣泉 (R)',
      repairHint: '修复构装',
      repairNeed: '没有可用的圣泉',
      repairSelect: '请选择受损的构装、巨龙或晶簇',
      repairSent: '个单位已前往圣泉'
    }
  };

  function factionCopy() {
    return FACTION_COPY[isOwnMagicFaction() ? 'magic' : 'tech'];
  }

  function applyFactionHud() {
    var copy = factionCopy();
    var infantryTab = document.querySelector('.command-tab[data-tab="infantry"]');
    var vehicleTab = document.querySelector('.command-tab[data-tab="vehicles"]');
    if (infantryTab) { infantryTab.textContent = copy.infantryTab; }
    if (vehicleTab) { vehicleTab.textContent = copy.vehicleTab; }
    var powerLabel = $('#powerLabel');
    if (powerLabel) { powerLabel.textContent = copy.power; }
    var powerColumn = document.querySelector('.power-column');
    if (powerColumn) { powerColumn.title = copy.powerLoad; }
    var harvesterLabel = $('#statHarvesterLabel');
    if (harvesterLabel) { harvesterLabel.textContent = copy.harvester; }
    var powerLoadLabel = $('#statPowerLabel');
    if (powerLoadLabel) { powerLoadLabel.textContent = copy.powerLoad; }
    var repairBtn = $('#repairBtn');
    if (repairBtn) {
      repairBtn.title = copy.repairTitle;
      repairBtn.innerHTML = '<span>✚</span>' + copy.repairBtn;
    }
    var repairHint = $('#repairHint');
    if (repairHint) { repairHint.innerHTML = '<kbd>R</kbd> ' + copy.repairHint; }
  }

  var STRUCTURE_ICONS = {
    hq: '★', power: 'ϟ', refinery: '◆', barracks: '♟', factory: '▰', repair: '✚', turret: '⌖', missile: '⊿',
    mhq: '★', mpower: '✦', mrefinery: '◈', mtemple: '✠', mcircle: '⬡', mspring: '✚', mtower: '✵'
  };

  /* -------------------- 肖像绘制器 --------------------
   * RA3 风格的指挥卡肖像：Unicode 字形在不同兵种间大量复用（♟ 同时是
   * 步兵营和突击兵），卡片无法一眼区分，所以这里改成本机 canvas 手绘
   * 的几何剪影。深红内衬 + 放射线底纹是为了和侧栏的苏军红铁皮语言
   * 呼应；结果缓存起来，命令网格和选中面板共用同一份位图。
   */
  var PORTRAIT_W = 96;
  var PORTRAIT_H = 72;
  var portraitCache = {};

  // 剪影配色只取设计令牌：亮面/暗面/高光/描边 + 黄铜、琥珀、深红点缀
  var P_BODY = '#a89f8a';
  var P_DARK = '#3b3f2e';
  var P_LITE = '#f3e9d4';
  var P_OUT = '#0a0a06';
  var P_BRASS = '#c9a24b';
  var P_BRASS_D = '#8f7530';
  var P_AMBER = '#e8a13a';
  var P_LCD = '#ffd23e';
  var P_RED = '#c8241e';
  var P_GOLD = '#e8c56d';
  // 秘法会配色：奥术紫 / 冰霜蓝 / 龙火橙 / 水晶 / 岩体 / 法袍
  var P_ARCANE = '#b46bff';
  var P_FROST = '#9fe8ff';
  var P_FIRE = '#ff8a3a';
  var P_CRYSTAL = '#9a7fd0';
  var P_STONE = '#5b5566';
  var P_ROBE = '#4a3a5e';
  // 魔法阵营类型集：肖像底子换成暗紫，一眼与钢铁军团的深红区分
  var MAGIC_KINDS = {
    mhq: 1, mpower: 1, mrefinery: 1, mtemple: 1, mcircle: 1, mspring: 1, mtower: 1,
    mage: 1, frost: 1, golem: 1, panther: 1, dragon: 1, warden: 1, colossus: 1,
    mharvester: 1, mmcv: 1, hexling: 1
  };

  function pRect(c, x, y, w, h, fill) {
    c.fillStyle = fill;
    c.fillRect(x, y, w, h);
  }

  function pCirc(c, x, y, r, fill) {
    c.fillStyle = fill;
    c.beginPath();
    c.arc(x, y, r, 0, Math.PI * 2);
    c.fill();
  }

  function pPoly(c, pts, fill) {
    c.fillStyle = fill;
    c.beginPath();
    c.moveTo(pts[0][0], pts[0][1]);
    for (var i = 1; i < pts.length; i++) { c.lineTo(pts[i][0], pts[i][1]); }
    c.closePath();
    c.fill();
  }

  function pLine(c, x1, y1, x2, y2, wd, stroke) {
    c.strokeStyle = stroke;
    c.lineWidth = wd;
    c.lineCap = 'round';
    c.beginPath();
    c.moveTo(x1, y1);
    c.lineTo(x2, y2);
    c.stroke();
  }

  function pStar(c, x, y, r, fill) {
    c.fillStyle = fill;
    c.beginPath();
    for (var i = 0; i < 10; i++) {
      var rad = i % 2 === 0 ? r : r * 0.45;
      var a = -Math.PI / 2 + i * Math.PI / 5;
      var px = x + Math.cos(a) * rad;
      var py = y + Math.sin(a) * rad;
      if (i === 0) { c.moveTo(px, py); } else { c.lineTo(px, py); }
    }
    c.closePath();
    c.fill();
  }

  // 地面阴影：让剪影“坐”在卡片里，而不是浮在红底上
  function pShadow(c, cx, cy, rx) {
    c.save();
    c.fillStyle = 'rgba(10,10,6,.40)';
    c.beginPath();
    c.ellipse(cx, cy, rx, 4, 0, 0, Math.PI * 2);
    c.fill();
    c.restore();
  }

  // 步兵通用胸像：肩部梯形 + 头部圆，细节（头盔/武器）由各兵种自绘
  function pBust(c, coat) {
    pPoly(c, [[27, 63], [69, 63], [61, 42], [35, 42]], coat);
    // 躯干右侧压一笔暗面，胸像立刻有了转折
    pPoly(c, [[69, 63], [55, 63], [52, 42], [61, 42]], 'rgba(10,10,6,.28)');
    pCirc(c, 48, 30, 9.5, coat);
  }

  var PORTRAIT_PAINTERS = {
    /* ---- 建筑 ---- */
    hq: function (c) {
      pShadow(c, 48, 59, 28);
      pPoly(c, [[24, 58], [72, 58], [66, 40], [30, 40]], P_BODY);
      pPoly(c, [[72, 58], [58, 58], [55, 40], [66, 40]], 'rgba(10,10,6,.22)');
      // 顶部穹顶 + 通讯天线：指挥中心的轮廓要一眼区别于普通建筑
      c.beginPath();
      c.fillStyle = P_DARK;
      c.arc(42, 40, 8, Math.PI, 0);
      c.closePath();
      c.fill();
      pLine(c, 62, 40, 68, 16, 2, P_DARK);
      pLine(c, 64, 25, 73, 23, 1.5, P_DARK);
      pLine(c, 65, 31, 74, 30, 1.5, P_DARK);
      pCirc(c, 68, 15, 1.8, P_RED);
      pStar(c, 48, 50, 6.5, P_RED);
      pLine(c, 31, 39.5, 65, 39.5, 1.5, 'rgba(243,233,212,.5)');
    },
    power: function (c) {
      pShadow(c, 48, 59, 24);
      pPoly(c, [[28, 58], [68, 58], [61, 46], [35, 46]], P_DARK);
      pRect(c, 44, 22, 8, 25, P_BODY);
      pRect(c, 49, 22, 3, 25, 'rgba(10,10,6,.25)');
      pCirc(c, 48, 22, 5, P_BODY);
      // 磁能线圈：三圈黄铜环由大到小，配一道电弧
      c.strokeStyle = P_BRASS;
      c.lineWidth = 2.5;
      c.beginPath(); c.ellipse(48, 28, 9, 3, 0, 0, Math.PI * 2); c.stroke();
      c.beginPath(); c.ellipse(48, 34, 8, 3, 0, 0, Math.PI * 2); c.stroke();
      c.beginPath(); c.ellipse(48, 40, 7, 3, 0, 0, Math.PI * 2); c.stroke();
      pLine(c, 48, 16, 52, 10, 2, P_LCD);
      pLine(c, 48, 16, 44, 12, 2, P_LCD);
      pCirc(c, 48, 16, 2, P_LCD);
      pLine(c, 44.8, 24, 44.8, 45, 1.2, 'rgba(243,233,212,.5)');
    },
    refinery: function (c) {
      pShadow(c, 44, 58, 28);
      // 卧式储罐 + 高烟囱：罐体圆头用两个圆补出来
      pRect(c, 24, 37, 34, 19, P_BODY);
      pCirc(c, 24, 46.5, 9.5, P_BODY);
      pCirc(c, 58, 46.5, 9.5, P_BODY);
      pLine(c, 34, 38, 34, 55, 1.5, 'rgba(10,10,6,.3)');
      pLine(c, 44, 38, 44, 55, 1.5, 'rgba(10,10,6,.3)');
      pLine(c, 54, 38, 54, 55, 1.5, 'rgba(10,10,6,.3)');
      pRect(c, 66, 18, 8, 38, P_DARK);
      pCirc(c, 70, 17, 3, P_AMBER);
      pCirc(c, 74, 10, 4, 'rgba(168,159,138,.35)');
      pCirc(c, 79, 5, 5, 'rgba(168,159,138,.22)');
      // 金色矿堆点明「这里收矿」
      pCirc(c, 21, 56, 4, P_GOLD);
      pCirc(c, 28, 58, 4.5, P_GOLD);
      pCirc(c, 24, 53, 3, P_GOLD);
      pCirc(c, 23, 52.5, 1.2, P_LCD);
      pLine(c, 18, 38.5, 60, 38.5, 1.5, 'rgba(243,233,212,.5)');
    },
    barracks: function (c) {
      pShadow(c, 48, 59, 28);
      pRect(c, 24, 42, 44, 16, P_BODY);
      pRect(c, 58, 42, 10, 16, 'rgba(10,10,6,.22)');
      pPoly(c, [[20, 42], [72, 42], [48, 28]], P_DARK);
      pRect(c, 42, 46, 10, 12, P_DARK);
      pCirc(c, 50, 52, 1, P_BRASS);
      pRect(c, 29, 46, 6, 4, P_DARK);
      pRect(c, 57, 46, 6, 4, P_DARK);
      // 军旗是步兵营的记忆点
      pLine(c, 74, 42, 74, 16, 1.5, P_DARK);
      pPoly(c, [[74, 16], [88, 19.5], [74, 23]], P_RED);
      pLine(c, 21, 41.5, 47, 28.5, 1.5, 'rgba(243,233,212,.45)');
    },
    factory: function (c) {
      pShadow(c, 48, 59, 30);
      pRect(c, 20, 40, 56, 18, P_BODY);
      pRect(c, 62, 40, 14, 18, 'rgba(10,10,6,.22)');
      // 锯齿厂房顶 + 琥珀天窗
      pPoly(c, [[20, 40], [20, 28], [36, 40]], P_DARK);
      pPoly(c, [[36, 40], [36, 28], [52, 40]], P_DARK);
      pPoly(c, [[52, 40], [52, 28], [68, 40]], P_DARK);
      pRect(c, 21, 30, 2.5, 7, P_AMBER);
      pRect(c, 37, 30, 2.5, 7, P_AMBER);
      pRect(c, 53, 30, 2.5, 7, P_AMBER);
      pRect(c, 28, 44, 18, 14, P_DARK);
      pRect(c, 28, 42, 18, 3, P_AMBER);
      pLine(c, 31, 45, 34, 42, 1.5, P_OUT);
      pLine(c, 37, 45, 40, 42, 1.5, P_OUT);
      pLine(c, 43, 45, 46, 42, 1.5, P_OUT);
      // 黄铜齿轮示意“重工”
      c.strokeStyle = P_BRASS;
      c.lineWidth = 2;
      c.beginPath(); c.arc(60, 49, 5, 0, Math.PI * 2); c.stroke();
      pCirc(c, 60, 49, 1.5, P_BRASS);
      pLine(c, 21, 40.5, 75, 40.5, 1.2, 'rgba(243,233,212,.4)');
    },
    turret: function (c) {
      pShadow(c, 48, 59, 18);
      pPoly(c, [[36, 58], [60, 58], [55, 46], [41, 46]], P_DARK);
      c.beginPath();
      c.fillStyle = P_BODY;
      c.arc(48, 46, 10, Math.PI, 0);
      c.closePath();
      c.fill();
      pLine(c, 52, 40, 82, 27, 3.5, P_DARK);
      pLine(c, 82, 27, 86, 25.3, 5, P_DARK);
      pCirc(c, 44, 41, 2, P_RED);
      c.strokeStyle = 'rgba(243,233,212,.55)';
      c.lineWidth = 1.5;
      c.beginPath(); c.arc(48, 46, 10, Math.PI * 1.06, Math.PI * 1.5); c.stroke();
    },
    missile: function (c) {
      pShadow(c, 48, 59, 22);
      // 方形发射箱底座
      pPoly(c, [[30, 58], [66, 58], [60, 48], [36, 48]], P_DARK);
      pRect(c, 32, 44, 32, 8, P_BODY);
      // 四联装导弹管：上下两排
      var tubes = [[-8, 0], [-2, 0], [2, 0], [8, 0]];
      tubes.forEach(function (t) {
        pCirc(c, 48 + t[0], 34, 5, P_DARK);
        pCirc(c, 48 + t[0], 34, 3, P_GOLD);
        pCirc(c, 48 + t[0], 34, 1.2, P_RED);
      });
      // 发射箱前沿
      pRect(c, 26, 28, 44, 4, P_BODY);
      pRect(c, 56, 28, 14, 4, 'rgba(10,10,6,.22)');
      // 底座状态灯
      pRect(c, 34, 50, 4, 4, P_BODY);
      pRect(c, 58, 50, 4, 4, P_BODY);
      pCirc(c, 36, 52, 1.2, P_LCD);
      pCirc(c, 60, 52, 1.2, P_LCD);
      // 顶边高光
      pLine(c, 31, 44.5, 65, 44.5, 1.2, 'rgba(243,233,212,.45)');
      // 危险标识条
      pRect(c, 37, 46, 22, 1.5, P_AMBER);
    },
    repair: function (c) {
      pShadow(c, 48, 59, 28);
      // 龙门吊 + 危险条纹横梁：维修位一眼可辨
      pRect(c, 28, 33, 7, 25, P_BODY);
      pRect(c, 61, 33, 7, 25, P_BODY);
      pRect(c, 24, 26, 48, 7, P_AMBER);
      pPoly(c, [[28, 33], [34, 26], [40, 26], [34, 33]], P_OUT);
      pPoly(c, [[44, 33], [50, 26], [56, 26], [50, 33]], P_OUT);
      pPoly(c, [[60, 33], [66, 26], [72, 26], [66, 33]], P_OUT);
      pLine(c, 48, 33, 48, 41, 2, P_DARK);
      c.strokeStyle = P_DARK;
      c.lineWidth = 2;
      c.beginPath(); c.arc(48, 43, 3, Math.PI * 1.5, Math.PI * 0.9); c.stroke();
      // 黄铜扳手徽记
      c.strokeStyle = P_BRASS;
      c.lineWidth = 3;
      c.beginPath(); c.arc(46, 49, 4.5, Math.PI * 0.4, Math.PI * 1.9); c.stroke();
      pLine(c, 49, 52, 57, 58, 4, P_BRASS);
      pLine(c, 25, 26.8, 71, 26.8, 1.2, 'rgba(243,233,212,.5)');
    },
    /* ---- 单位 ---- */
    rifle: function (c) {
      pBust(c, P_BODY);
      // 钢盔 + 帽檐；星徽区分阵营气质
      c.beginPath();
      c.fillStyle = P_DARK;
      c.arc(48, 28, 11, Math.PI, 0);
      c.closePath();
      c.fill();
      pRect(c, 36, 27, 24, 3, P_DARK);
      pStar(c, 48, 24, 2.6, P_RED);
      c.strokeStyle = 'rgba(243,233,212,.6)';
      c.lineWidth = 2;
      c.beginPath(); c.arc(48, 28, 10.5, Math.PI * 1.08, Math.PI * 1.45); c.stroke();
      pLine(c, 28, 58, 74, 32, 3, P_OUT);
      pLine(c, 28, 58, 33, 61, 4.5, P_OUT);
      pRect(c, 49, 45, 4, 7, P_DARK);
    },
    rocket: function (c) {
      pBust(c, P_BODY);
      c.beginPath();
      c.fillStyle = P_DARK;
      c.arc(48, 28, 11, Math.PI, 0);
      c.closePath();
      c.fill();
      // 护目镜双镜片：和突击兵的星徽区分
      pCirc(c, 44, 28, 2.2, P_LCD);
      pCirc(c, 52, 28, 2.2, P_LCD);
      // 肩扛火箭筒：粗管 + 黑洞口 + 黄铜箍
      pLine(c, 30, 57, 76, 22, 8, P_DARK);
      pCirc(c, 76, 22, 5, P_OUT);
      c.strokeStyle = P_BRASS;
      c.lineWidth = 1.5;
      c.beginPath(); c.arc(76, 22, 5, 0, Math.PI * 2); c.stroke();
      c.beginPath(); c.arc(60, 34, 4.8, 0, Math.PI * 2); c.stroke();
      pPoly(c, [[80, 15], [86, 12], [82, 20]], P_RED);
      pLine(c, 34, 53, 72, 24, 1.2, 'rgba(243,233,212,.35)');
    },
    sniper: function (c) {
      // 整身斗篷压暗色：狙击手的剪影要比其他步兵“沉”
      pPoly(c, [[27, 63], [69, 63], [59, 44], [37, 44]], P_DARK);
      pPoly(c, [[38, 44], [58, 44], [56, 26], [48, 19], [40, 26]], P_DARK);
      pRect(c, 43, 30, 10, 4, P_BODY);
      pRect(c, 48, 30, 5, 4, 'rgba(10,10,6,.35)');
      // 加长枪身 + 镜头反光点
      pLine(c, 16, 58, 86, 24, 2, P_OUT);
      pRect(c, 47, 36, 9, 4.5, P_DARK);
      pCirc(c, 54, 38, 1.6, P_LCD);
      pLine(c, 82, 26, 86, 30, 1.5, P_OUT);
      pLine(c, 40, 26, 48, 20, 1.2, 'rgba(243,233,212,.35)');
    },
    dog: function (c) {
      // 侧面剪影：低身长躯、竖耳、翘尾，一眼是条蓄势扑跃的军犬
      pShadow(c, 48, 60, 27);
      // 四条腿
      pRect(c, 50, 48, 3.2, 12, P_DARK);
      pRect(c, 56, 48, 3.2, 12, P_DARK);
      pRect(c, 30, 48, 3.2, 12, P_DARK);
      pRect(c, 36, 48, 3.2, 12, P_DARK);
      // 长而低的躯干 + 深色背鞍
      pPoly(c, [[28, 50], [60, 50], [63, 42], [57, 36], [36, 36], [28, 43]], P_BODY);
      pPoly(c, [[36, 36], [57, 36], [59, 40], [34, 40]], P_DARK);
      // 向后上方翘起的尾巴
      pLine(c, 29, 42, 20, 27, 3.4, P_DARK);
      pLine(c, 20, 27, 23, 22, 2.6, P_DARK);
      // 头颅 + 前伸的深色吻部 + 竖耳
      pPoly(c, [[58, 42], [69, 42], [71, 31], [64, 26], [58, 31]], P_BODY);
      pPoly(c, [[68, 39], [78, 36], [78, 32], [69, 31]], P_DARK);
      pPoly(c, [[60, 28], [64, 17], [68, 27]], P_DARK);
      // 红项圈 + 眼睛
      pLine(c, 59, 41, 62, 30, 3, P_RED);
      pCirc(c, 65, 33, 1.6, P_LCD);
    },
    tank: function (c) {
      pShadow(c, 48, 58, 27);
      pRect(c, 24, 47, 48, 11, P_DARK);
      pCirc(c, 24, 52.5, 5.5, P_DARK);
      pCirc(c, 72, 52.5, 5.5, P_DARK);
      pCirc(c, 32, 52.5, 2.5, P_OUT);
      pCirc(c, 42, 52.5, 2.5, P_OUT);
      pCirc(c, 52, 52.5, 2.5, P_OUT);
      pCirc(c, 62, 52.5, 2.5, P_OUT);
      pPoly(c, [[22, 47], [74, 47], [68, 38], [28, 38]], P_BODY);
      pPoly(c, [[74, 47], [60, 47], [57, 38], [68, 38]], 'rgba(10,10,6,.25)');
      pRect(c, 38, 28, 17, 9, P_BODY);
      pCirc(c, 38, 32.5, 4.5, P_BODY);
      pCirc(c, 55, 32.5, 4.5, P_BODY);
      pRect(c, 55, 30, 26, 3.5, P_DARK);
      pRect(c, 79, 29, 4, 5.5, P_DARK);
      pStar(c, 44, 32.5, 3, P_RED);
      pLine(c, 29, 38.5, 67, 38.5, 1.5, 'rgba(243,233,212,.5)');
      pLine(c, 55, 30.6, 78, 30.6, 1, 'rgba(243,233,212,.4)');
    },
    scout: function (c) {
      pShadow(c, 48, 58, 26);
      pCirc(c, 33, 52, 5.5, P_OUT);
      pCirc(c, 63, 52, 5.5, P_OUT);
      pCirc(c, 33, 52, 2.5, P_DARK);
      pCirc(c, 63, 52, 2.5, P_DARK);
      pPoly(c, [[20, 52], [76, 52], [72, 44], [58, 38], [38, 38], [24, 45]], P_BODY);
      pPoly(c, [[76, 52], [62, 52], [58, 38], [72, 44]], 'rgba(10,10,6,.22)');
      pRect(c, 47, 40, 9, 4.5, P_DARK);
      pLine(c, 70, 44, 77, 24, 1.2, P_DARK);
      pCirc(c, 77, 23, 1.4, P_RED);
      // 速度线：轻型侦察车的“快”
      pLine(c, 8, 42, 21, 42, 2, 'rgba(243,233,212,.25)');
      pLine(c, 6, 48, 17, 48, 2, 'rgba(243,233,212,.16)');
      pLine(c, 39, 38.6, 57, 38.6, 1.5, 'rgba(243,233,212,.5)');
    },
    artillery: function (c) {
      pShadow(c, 50, 58, 24);
      pRect(c, 30, 49, 38, 10, P_DARK);
      pCirc(c, 38, 54, 2.2, P_OUT);
      pCirc(c, 48, 54, 2.2, P_OUT);
      pCirc(c, 58, 54, 2.2, P_OUT);
      // 高仰角长管：攻城炮的核心特征
      pRect(c, 36, 40, 20, 10, P_BODY);
      pPoly(c, [[56, 50], [56, 40], [62, 42], [62, 50]], 'rgba(10,10,6,.25)');
      pLine(c, 44, 44, 84, 14, 5, P_DARK);
      pCirc(c, 85, 13, 3.2, P_DARK);
      pPoly(c, [[30, 49], [23, 59], [33, 59]], P_DARK);
      pLine(c, 45, 42.6, 83, 13.4, 1.2, 'rgba(243,233,212,.4)');
      pLine(c, 37, 40.6, 55, 40.6, 1.2, 'rgba(243,233,212,.45)');
    },
    tank_destroyer: function (c) {
      pShadow(c, 48, 58, 27);
      pRect(c, 24, 49, 46, 10, P_DARK);
      pCirc(c, 32, 54, 2.4, P_OUT);
      pCirc(c, 42, 54, 2.4, P_OUT);
      pCirc(c, 52, 54, 2.4, P_OUT);
      pCirc(c, 62, 54, 2.4, P_OUT);
      // 无炮塔斜面战斗室 + 前伸长管：和先锋坦克的方塔区分
      pPoly(c, [[22, 49], [72, 49], [64, 36], [36, 36], [26, 43]], P_BODY);
      pPoly(c, [[72, 49], [58, 49], [54, 36], [64, 36]], 'rgba(10,10,6,.25)');
      pLine(c, 64, 40, 91, 37.5, 3.5, P_DARK);
      pRect(c, 88, 35, 5, 5, P_DARK);
      pLine(c, 37, 36.5, 63, 36.5, 1.5, 'rgba(243,233,212,.5)');
      pLine(c, 27, 43, 36, 36.8, 1.2, 'rgba(243,233,212,.35)');
    },
    harvester: function (c) {
      pShadow(c, 48, 60, 28);
      pCirc(c, 32, 55, 4.5, P_OUT);
      pCirc(c, 48, 55, 4.5, P_OUT);
      pCirc(c, 64, 55, 4.5, P_OUT);
      pCirc(c, 32, 55, 2, P_DARK);
      pCirc(c, 48, 55, 2, P_DARK);
      pCirc(c, 64, 55, 2, P_DARK);
      pRect(c, 26, 34, 32, 18, P_BODY);
      pRect(c, 50, 34, 8, 18, 'rgba(10,10,6,.2)');
      // 敞口矿斗里冒尖的金矿：采矿车的招牌
      pCirc(c, 34, 33, 4, P_GOLD);
      pCirc(c, 42, 31, 4.5, P_GOLD);
      pCirc(c, 50, 33, 4, P_GOLD);
      pCirc(c, 41, 29.5, 1.4, P_LCD);
      pRect(c, 60, 38, 16, 14, P_BODY);
      pRect(c, 63, 40, 9, 5, P_DARK);
      pLine(c, 63.5, 40.5, 71, 40.5, 1, 'rgba(243,233,212,.5)');
      pPoly(c, [[26, 44], [15, 55], [26, 52]], P_DARK);
      pLine(c, 27, 34.6, 49, 34.6, 1.2, 'rgba(243,233,212,.45)');
    },
    bomb_truck: function (c) {
      // 轮式药箱车：驾驶室 + 后斗炸药桶 + 引信，一眼不是坦克
      pShadow(c, 48, 60, 28);
      pCirc(c, 30, 54, 5.2, P_OUT);
      pCirc(c, 48, 54, 5.2, P_OUT);
      pCirc(c, 66, 54, 5.2, P_OUT);
      pCirc(c, 30, 54, 2.2, P_DARK);
      pCirc(c, 48, 54, 2.2, P_DARK);
      pCirc(c, 66, 54, 2.2, P_DARK);
      pPoly(c, [[22, 50], [74, 50], [70, 40], [40, 38], [26, 44]], P_BODY);
      pRect(c, 24, 34, 18, 12, P_DARK);
      pRect(c, 27, 36, 8, 5, P_LITE);
      pCirc(c, 52, 36, 7, P_RED);
      pCirc(c, 64, 38, 5.5, P_AMBER);
      pCirc(c, 52, 36, 2.4, P_LCD);
      pLine(c, 52, 29, 56, 18, 1.6, P_OUT);
      pCirc(c, 56, 16, 1.8, P_LCD);
      pRect(c, 40, 48, 28, 3, P_AMBER);
      for (var hx = 40; hx < 66; hx += 6) {
        pPoly(c, [[hx, 51], [hx + 3, 48], [hx + 5.4, 48], [hx + 2.4, 51]], P_OUT);
      }
    },
    mcv: function (c) {
      pShadow(c, 48, 61, 30);
      pCirc(c, 30, 56, 4, P_OUT);
      pCirc(c, 42, 56, 4, P_OUT);
      pCirc(c, 56, 56, 4, P_OUT);
      pCirc(c, 68, 56, 4, P_OUT);
      pCirc(c, 30, 56, 1.8, P_DARK);
      pCirc(c, 42, 56, 1.8, P_DARK);
      pCirc(c, 56, 56, 1.8, P_DARK);
      pCirc(c, 68, 56, 1.8, P_DARK);
      pRect(c, 20, 42, 42, 12, P_BODY);
      // 折叠井架：展开成基地的暗示
      pLine(c, 24, 42, 40, 30, 2.5, P_BRASS_D);
      pLine(c, 40, 30, 56, 42, 2.5, P_BRASS_D);
      pLine(c, 32, 36, 48, 36, 2, P_BRASS_D);
      pCirc(c, 40, 30, 2, P_BRASS);
      pRect(c, 62, 36, 16, 18, P_BODY);
      pRect(c, 65, 39, 9, 5, P_DARK);
      pLine(c, 65.5, 39.5, 73, 39.5, 1, 'rgba(243,233,212,.5)');
      // 侧裙上的危险条纹：工程车辆的通用语言
      pRect(c, 22, 50, 38, 3.5, P_AMBER);
      for (var hx = 22; hx < 58; hx += 6) {
        pPoly(c, [[hx, 53.5], [hx + 3, 50], [hx + 5.4, 50], [hx + 2.4, 53.5]], P_OUT);
      }
      pLine(c, 21, 42.6, 61, 42.6, 1.2, 'rgba(243,233,212,.45)');
    },
    overlord: function (c) {
      pShadow(c, 48, 59, 31);
      // 更宽更低的履带底盘 + 六对负重轮：一看就比先锋坦克壮
      pRect(c, 18, 47, 60, 11, P_DARK);
      pCirc(c, 20, 52.5, 6, P_DARK);
      pCirc(c, 76, 52.5, 6, P_DARK);
      pCirc(c, 27, 52.5, 2.6, P_OUT);
      pCirc(c, 37, 52.5, 2.6, P_OUT);
      pCirc(c, 47, 52.5, 2.6, P_OUT);
      pCirc(c, 57, 52.5, 2.6, P_OUT);
      pCirc(c, 67, 52.5, 2.6, P_OUT);
      pPoly(c, [[16, 47], [80, 47], [72, 36], [24, 36]], P_BODY);
      pPoly(c, [[80, 47], [64, 47], [61, 36], [72, 36]], 'rgba(10,10,6,.25)');
      // 低矮宽炮塔 + 招牌双联主炮（上下两根粗管）
      pRect(c, 33, 27, 26, 9, P_BODY);
      pRect(c, 33, 27, 26, 2.5, P_LITE);
      pRect(c, 58, 27.5, 30, 3.2, P_DARK);
      pRect(c, 58, 31.5, 30, 3.2, P_DARK);
      pRect(c, 86, 26.6, 4, 5, P_OUT);
      pRect(c, 86, 30.6, 4, 5, P_OUT);
      pStar(c, 42, 31, 3.2, P_RED);
      pLine(c, 22, 36.6, 70, 36.6, 1.5, 'rgba(243,233,212,.5)');
    },
    tesla: function (c) {
      pBust(c, P_BODY);
      // 全封闭动力甲头盔 + 一字目镜
      c.beginPath();
      c.fillStyle = P_DARK;
      c.arc(48, 28, 11, Math.PI, 0);
      c.closePath();
      c.fill();
      pRect(c, 37, 27, 22, 4, P_DARK);
      pRect(c, 40, 29, 16, 2, P_LCD);
      // 背部磁暴线圈：两根竖杆 + 顶端电弧球，线圈间拉一道闪电
      pLine(c, 36, 42, 36, 20, 2.5, P_BRASS_D);
      pLine(c, 60, 42, 60, 20, 2.5, P_BRASS_D);
      pCirc(c, 36, 18, 2.6, P_LCD);
      pCirc(c, 60, 18, 2.6, P_LCD);
      pPoly(c, [[38, 22], [46, 18], [44, 24], [52, 20], [46, 27], [40, 25]], P_GOLD);
      // 手中的电击叉：叉头两根尖
      pLine(c, 30, 58, 72, 34, 3, P_OUT);
      pLine(c, 72, 34, 80, 28, 2, P_BRASS);
      pLine(c, 72, 34, 82, 34, 2, P_BRASS);
    },
    prism: function (c) {
      pShadow(c, 48, 58, 26);
      pRect(c, 24, 47, 48, 10, P_DARK);
      pCirc(c, 26, 52, 5, P_DARK);
      pCirc(c, 70, 52, 5, P_DARK);
      pCirc(c, 34, 52, 2.4, P_OUT);
      pCirc(c, 44, 52, 2.4, P_OUT);
      pCirc(c, 54, 52, 2.4, P_OUT);
      pCirc(c, 62, 52, 2.4, P_OUT);
      pPoly(c, [[22, 47], [74, 47], [68, 38], [28, 38]], P_BODY);
      pPoly(c, [[74, 47], [60, 47], [57, 38], [68, 38]], 'rgba(10,10,6,.25)');
      // 竖起的棱镜支臂 + 顶端聚焦棱镜（菱形水晶），镜面甩出一道光束
      pLine(c, 46, 40, 56, 22, 3, P_DARK);
      pPoly(c, [[56, 12], [63, 20], [56, 28], [49, 20]], P_LCD);
      pPoly(c, [[56, 12], [63, 20], [56, 20]], '#fff3c9');
      pLine(c, 63, 20, 90, 16, 1.5, P_GOLD);
      pStar(c, 34, 33, 2.6, P_RED);
      pLine(c, 27, 38.6, 65, 38.6, 1.4, 'rgba(243,233,212,.5)');
    },
    /* ---- 秘法会（魔法阵营）建筑 ---- */
    mhq: function (c) {
      pShadow(c, 48, 59, 28);
      // 阶梯圣城 + 中央法塔
      pPoly(c, [[22, 58], [74, 58], [66, 42], [30, 42]], P_STONE);
      pPoly(c, [[74, 58], [58, 58], [55, 42], [66, 42]], 'rgba(10,10,6,.24)');
      pPoly(c, [[34, 42], [62, 42], [57, 22], [41, 22]], '#4a4257');
      // 塔顶悬浮巨水晶 + 环绕符环
      pPoly(c, [[48, 6], [54, 14], [48, 22], [42, 14]], P_ARCANE);
      c.strokeStyle = P_FROST; c.lineWidth = 1.5;
      c.beginPath(); c.ellipse(48, 14, 11, 4, 0, 0, Math.PI * 2); c.stroke();
      // 奥术窗 + 顶边高光
      pRect(c, 44, 30, 3, 6, P_ARCANE);
      pRect(c, 51, 30, 3, 6, P_ARCANE);
      pLine(c, 31, 41.5, 65, 41.5, 1.5, 'rgba(180,107,255,.5)');
    },
    mpower: function (c) {
      pShadow(c, 48, 59, 24);
      // 两根相对的水晶塔
      pPoly(c, [[34, 56], [42, 56], [40, 20], [36, 20]], P_CRYSTAL);
      pPoly(c, [[54, 56], [62, 56], [60, 20], [56, 20]], P_CRYSTAL);
      // 塔身符环
      c.strokeStyle = P_ARCANE; c.lineWidth = 2;
      c.beginPath(); c.ellipse(38, 30, 6, 2.5, 0, 0, Math.PI * 2); c.stroke();
      c.beginPath(); c.ellipse(58, 30, 6, 2.5, 0, 0, Math.PI * 2); c.stroke();
      // 共同托起的悬浮法力球
      pCirc(c, 48, 13, 5, P_ARCANE);
      pCirc(c, 48, 13, 2, '#f2e6ff');
    },
    mrefinery: function (c) {
      pShadow(c, 44, 58, 28);
      pRect(c, 24, 40, 36, 18, P_STONE);
      pRect(c, 56, 40, 8, 18, 'rgba(10,10,6,.22)');
      // 中央待炼巨晶 + 环绕符筒
      pPoly(c, [[38, 40], [44, 16], [50, 40]], P_CRYSTAL);
      pPoly(c, [[44, 16], [47.5, 24], [44, 40]], 'rgba(243,233,212,.18)');
      c.strokeStyle = P_ARCANE; c.lineWidth = 2;
      c.beginPath(); c.ellipse(44, 32, 10, 3.5, 0, 0, Math.PI * 2); c.stroke();
      // 卸晶槽 + 寒蓝晶堆（对应矿厂的金矿堆）
      pRect(c, 62, 30, 8, 26, P_DARK);
      pCirc(c, 22, 55, 3.5, P_FROST);
      pCirc(c, 29, 57, 4, P_FROST);
      pCirc(c, 25, 52, 1.2, '#ffffff');
      pLine(c, 18, 40.5, 58, 40.5, 1.5, 'rgba(159,232,255,.5)');
    },
    mtemple: function (c) {
      pShadow(c, 48, 59, 26);
      // 三角亭顶 + 双柱 + 亭心悬浮符文石
      pPoly(c, [[28, 34], [68, 34], [48, 20]], P_STONE);
      pRect(c, 32, 34, 5, 20, '#4a4257');
      pRect(c, 59, 34, 5, 20, '#4a4257');
      pPoly(c, [[48, 30], [53, 38], [48, 46], [43, 38]], P_ARCANE);
      pCirc(c, 48, 38, 1.6, '#f2e6ff');
      pRect(c, 26, 54, 44, 5, P_STONE);
      pLine(c, 30, 33.5, 66, 33.5, 1.5, 'rgba(180,107,255,.5)');
    },
    mcircle: function (c) {
      pShadow(c, 48, 60, 30);
      pRect(c, 20, 52, 56, 8, P_STONE);
      // 地面召唤阵纹（透视双环）
      c.strokeStyle = P_ARCANE; c.lineWidth = 2;
      c.beginPath(); c.ellipse(48, 50, 24, 6, 0, 0, Math.PI * 2); c.stroke();
      c.beginPath(); c.ellipse(48, 50, 15, 3.6, 0, 0, Math.PI * 2); c.stroke();
      // 竖立符文环 + 环心奥术漩涡
      c.strokeStyle = P_CRYSTAL; c.lineWidth = 3.5;
      c.beginPath(); c.ellipse(48, 29, 9, 16, 0, 0, Math.PI * 2); c.stroke();
      pCirc(c, 48, 29, 6, P_ARCANE);
      pCirc(c, 48, 29, 2.4, '#f2e6ff');
    },
    mspring: function (c) {
      pShadow(c, 48, 60, 28);
      // 石砌泉盆 + 泉心寒蓝圣水，对位维修厂的龙门剪影
      pPoly(c, [[22, 56], [74, 56], [66, 44], [30, 44]], P_STONE);
      pPoly(c, [[74, 56], [58, 56], [55, 44], [66, 44]], 'rgba(10,10,6,.24)');
      pCirc(c, 48, 42, 11, P_FROST);
      pCirc(c, 48, 42, 6, '#d6efff');
      pCirc(c, 48, 40, 2.2, '#ffffff');
      c.strokeStyle = P_ARCANE; c.lineWidth = 1.6;
      c.beginPath(); c.ellipse(48, 42, 14, 5, 0, 0, Math.PI * 2); c.stroke();
      pLine(c, 48, 42, 48, 22, 2, P_FROST);
      pCirc(c, 48, 20, 3.2, P_ARCANE);
      pCirc(c, 48, 20, 1.4, '#f2e6ff');
    },
    mtower: function (c) {
      pShadow(c, 48, 59, 18);
      // 石座 + 收束水晶尖塔
      pPoly(c, [[36, 58], [60, 58], [55, 48], [41, 48]], P_STONE);
      pPoly(c, [[43, 48], [53, 48], [50, 18], [46, 18]], P_CRYSTAL);
      // 塔顶悬浮晶核 + 符环
      pPoly(c, [[48, 8], [53, 15], [48, 22], [43, 15]], P_ARCANE);
      pCirc(c, 48, 15, 1.6, '#f2e6ff');
      c.strokeStyle = P_FROST; c.lineWidth = 1.4;
      c.beginPath(); c.ellipse(48, 15, 9, 3.5, 0, 0, Math.PI * 2); c.stroke();
    },
    /* ---- 秘法会（魔法阵营）单位 ---- */
    mage: function (c) {
      pShadow(c, 48, 60, 20);
      // 长袍 + 尖顶兜帽 + 阴影里的脸
      pPoly(c, [[34, 60], [62, 60], [55, 30], [41, 30]], P_ROBE);
      pPoly(c, [[62, 60], [50, 60], [50, 30], [55, 30]], 'rgba(10,10,6,.28)');
      pPoly(c, [[40, 32], [56, 32], [48, 16]], P_ROBE);
      pCirc(c, 48, 30, 5.5, P_OUT);
      pCirc(c, 46, 29.5, 1, P_ARCANE);
      pCirc(c, 50, 29.5, 1, P_ARCANE);
      // 前举法杖 + 杖顶奥术法球 + 一缕紫光
      pLine(c, 60, 56, 70, 20, 2.6, P_DARK);
      pCirc(c, 70, 18, 3.6, P_ARCANE);
      pCirc(c, 70, 18, 1.6, '#f2e6ff');
      pLine(c, 74, 16, 90, 12, 1.6, P_ARCANE);
    },
    frost: function (c) {
      pShadow(c, 48, 60, 20);
      // 苍蓝长袍 + 冻边 + 苍白面容
      pPoly(c, [[34, 60], [62, 60], [55, 30], [41, 30]], '#6d8aa0');
      pPoly(c, [[62, 60], [50, 60], [50, 30], [55, 30]], 'rgba(10,10,6,.22)');
      pPoly(c, [[33, 60], [63, 60], [60, 54], [36, 54]], P_FROST);
      pCirc(c, 48, 30, 6, '#e9f3fb');
      // 冰晶头冠：三枚冰棱
      pPoly(c, [[42, 27], [44.5, 16], [47, 26]], P_FROST);
      pPoly(c, [[46, 26], [48, 13], [50, 26]], '#d6efff');
      pPoly(c, [[49, 26], [51.5, 16], [54, 27]], P_FROST);
      // 冰霜法杖 + 杖顶寒晶簇
      pLine(c, 60, 56, 70, 20, 2.4, P_FROST);
      pPoly(c, [[70, 10], [74, 18], [70, 26], [66, 18]], P_FROST);
      pPoly(c, [[70, 8], [72, 15], [70, 16], [68, 15]], '#ffffff');
      pCirc(c, 70, 18, 1.6, '#ffffff');
    },
    golem: function (c) {
      pShadow(c, 48, 61, 30);
      // 厚重岩躯 + 巨石双臂 + 水晶拳
      pPoly(c, [[30, 60], [66, 60], [60, 28], [36, 28]], P_STONE);
      pPoly(c, [[66, 60], [50, 60], [50, 28], [60, 28]], 'rgba(10,10,6,.28)');
      pCirc(c, 46, 24, 6.5, P_STONE);
      pRect(c, 24, 34, 8, 20, '#4a4453');
      pRect(c, 64, 34, 8, 20, '#4a4453');
      pRect(c, 24, 52, 8, 7, P_CRYSTAL);
      pRect(c, 64, 52, 8, 7, P_CRYSTAL);
      // 胸口奥术核心 + 双眼
      pCirc(c, 48, 42, 4.5, P_ARCANE);
      pCirc(c, 48, 42, 2, '#f2e6ff');
      pCirc(c, 44, 23, 1.2, P_ARCANE);
      pCirc(c, 48, 23, 1.2, P_ARCANE);
    },
    panther: function (c) {
      pShadow(c, 48, 60, 28);
      // 流线四足 + 上扬长尾 + 脊背魔纹
      pRect(c, 52, 46, 2.6, 13, '#241a33');
      pRect(c, 58, 46, 2.6, 13, '#241a33');
      pRect(c, 30, 46, 2.6, 13, '#241a33');
      pRect(c, 36, 46, 2.6, 13, '#241a33');
      pPoly(c, [[26, 50], [62, 50], [66, 41], [58, 34], [36, 34], [26, 42]], '#33254a');
      pLine(c, 27, 42, 16, 26, 3, '#241a33');
      pPoly(c, [[60, 42], [72, 42], [74, 32], [66, 27], [60, 32]], '#33254a');
      pPoly(c, [[70, 39], [80, 36], [80, 33], [71, 32]], '#241a33');
      pPoly(c, [[62, 29], [65, 19], [68, 28]], '#241a33');
      pLine(c, 34, 35.5, 58, 35.5, 1.5, P_ARCANE);
      pCirc(c, 67, 33, 1.5, P_ARCANE);
    },
    dragon: function (c) {
      pShadow(c, 50, 61, 30);
      // 长尾 + 扁长躯干 + 腿，俯视一眼是龙
      pLine(c, 30, 48, 6, 54, 3.2, '#31402a');
      pPoly(c, [[22, 52], [64, 50], [62, 38], [28, 40]], '#3a4a2c');
      pPoly(c, [[64, 50], [48, 50], [48, 38], [62, 38]], 'rgba(10,10,6,.25)');
      pRect(c, 32, 50, 3.2, 10, '#31402a');
      pRect(c, 50, 49, 3.2, 11, '#31402a');
      // 大后掠双翼
      pPoly(c, [[28, 40], [46, 6], [58, 38]], '#46582f');
      pPoly(c, [[36, 40], [68, 10], [62, 40]], '#2c3823');
      pPoly(c, [[40, 38], [72, 20], [60, 40]], '#1e2618');
      // 长颈 + 头 + 水晶角
      pLine(c, 60, 40, 76, 22, 5.2, '#3a4a2c');
      pPoly(c, [[72, 24], [88, 18], [90, 25], [74, 30]], '#3a4a2c');
      pPoly(c, [[74, 22], [77, 10], [80, 21]], P_CRYSTAL);
      // 口中龙火 + 眼
      pPoly(c, [[90, 20], [102, 16], [92, 27]], P_FIRE);
      pCirc(c, 80, 22, 1.6, '#ffd9a0');
    },
    warden: function (c) {
      pShadow(c, 48, 61, 28);
      // 晶铠卫士：比傀儡更像披甲构装——盾 + 晶刃，不是又一坨岩石
      pPoly(c, [[34, 60], [62, 60], [58, 28], [38, 28]], P_STONE);
      pPoly(c, [[62, 60], [50, 60], [50, 28], [58, 28]], 'rgba(10,10,6,.26)');
      pPoly(c, [[36, 42], [60, 42], [57, 30], [39, 30]], P_CRYSTAL);
      pCirc(c, 47, 24, 6, P_STONE);
      pPoly(c, [[18, 34], [32, 30], [34, 56], [16, 54]], P_CRYSTAL);
      pPoly(c, [[18, 34], [26, 32], [26, 54], [16, 54]], 'rgba(243,233,212,.18)');
      pLine(c, 64, 56, 78, 16, 3.2, P_DARK);
      pPoly(c, [[76, 8], [82, 18], [76, 24], [70, 18]], P_ARCANE);
      pCirc(c, 48, 38, 3.4, P_ARCANE);
      pCirc(c, 48, 38, 1.4, '#f2e6ff');
      pCirc(c, 45, 23, 1.1, P_ARCANE);
      pCirc(c, 49, 23, 1.1, P_ARCANE);
    },
    colossus: function (c) {
      pShadow(c, 50, 62, 32);
      // 裂地晶兽：四足晶兽 + 背上晶陨鞍塔，肖像一眼是攻城兽不是傀儡/晶铠
      pRect(c, 28, 48, 3.4, 14, P_STONE);
      pRect(c, 36, 48, 3.4, 14, P_STONE);
      pRect(c, 54, 48, 3.2, 14, P_STONE);
      pRect(c, 62, 48, 3.2, 14, P_STONE);
      pCirc(c, 30, 61, 2.2, P_CRYSTAL);
      pCirc(c, 38, 61, 2.2, P_CRYSTAL);
      pCirc(c, 56, 61, 2.0, P_CRYSTAL);
      pCirc(c, 64, 61, 2.0, P_CRYSTAL);
      pPoly(c, [[24, 52], [68, 50], [70, 38], [30, 40]], P_STONE);
      pPoly(c, [[68, 50], [50, 50], [50, 38], [70, 38]], 'rgba(10,10,6,.26)');
      pPoly(c, [[66, 42], [80, 40], [82, 32], [70, 30]], P_STONE);
      pPoly(c, [[72, 30], [75, 20], [78, 30]], P_CRYSTAL);
      pPoly(c, [[32, 40], [56, 38], [54, 28], [36, 30]], P_CRYSTAL);
      pLine(c, 48, 32, 86, 10, 5.2, P_CRYSTAL);
      pPoly(c, [[82, 4], [90, 12], [84, 18], [76, 10]], P_ARCANE);
      pCirc(c, 86, 10, 2.2, '#f2e6ff');
      pCirc(c, 76, 34, 1.4, P_ARCANE);
      pCirc(c, 44, 36, 2.8, P_ARCANE);
      pCirc(c, 44, 36, 1.2, '#f2e6ff');
    },
    mharvester: function (c) {
      pShadow(c, 48, 60, 26);
      // 悬浮底座托着一簇参差水晶
      pPoly(c, [[28, 52], [68, 52], [62, 46], [34, 46]], P_DARK);
      pPoly(c, [[40, 46], [44, 24], [48, 46]], P_CRYSTAL);
      pPoly(c, [[48, 46], [53, 30], [57, 46]], '#8a6fc0');
      pPoly(c, [[33, 46], [37, 33], [41, 46]], '#8a6fc0');
      // 悬浮光环 + 主晶顶光 + 底座悬浮核心
      pLine(c, 30, 55.5, 66, 55.5, 1.5, P_FROST);
      pCirc(c, 44, 22, 1.6, P_ARCANE);
      pCirc(c, 48, 49, 2, P_ARCANE);
    },
    mmcv: function (c) {
      pShadow(c, 48, 61, 28);
      // 悬浮平台 + 竖立符文环 + 环心漩涡
      pPoly(c, [[22, 52], [74, 52], [66, 45], [30, 45]], P_STONE);
      c.strokeStyle = P_CRYSTAL; c.lineWidth = 4;
      c.beginPath(); c.ellipse(48, 33, 8, 14, 0, 0, Math.PI * 2); c.stroke();
      pCirc(c, 48, 33, 5, P_ARCANE);
      pCirc(c, 48, 33, 2, '#f2e6ff');
      pRect(c, 32, 40, 4, 8, '#4a4453');
      pRect(c, 60, 40, 4, 8, '#4a4453');
      pLine(c, 26, 55.5, 70, 55.5, 1.5, P_FROST);
    },
    hexling: function (c) {
      // 爆裂魔仆：矮小符核活体 + 腰环 + 胸口晶核，不是卡车剪影
      pShadow(c, 48, 60, 18);
      pRect(c, 40, 46, 4, 12, P_STONE);
      pRect(c, 52, 46, 4, 12, P_STONE);
      pPoly(c, [[36, 50], [60, 50], [56, 30], [40, 30]], P_CRYSTAL);
      pPoly(c, [[60, 50], [50, 50], [50, 30], [56, 30]], 'rgba(10,10,6,.26)');
      pCirc(c, 48, 26, 7, P_STONE);
      pPoly(c, [[44, 22], [48, 12], [52, 22]], P_ARCANE);
      pCirc(c, 48, 38, 4.2, P_ARCANE);
      pCirc(c, 48, 38, 1.8, '#f2e6ff');
      c.strokeStyle = P_FROST; c.lineWidth = 1.8;
      c.beginPath(); c.ellipse(48, 42, 12, 4, 0, 0, Math.PI * 2); c.stroke();
      pCirc(c, 45, 24, 1.1, P_ARCANE);
      pCirc(c, 51, 24, 1.1, P_ARCANE);
    }
  };

  // 深红内衬 + 低透明放射线 + 径向明暗：所有肖像共用的底子。
  // magic 时换暗紫，与钢铁军团的深红底阵营对撞一眼可辨。
  function portraitBackdrop(c, w, h, magic) {
    c.fillStyle = magic ? '#2a1140' : '#4a1013';
    c.fillRect(0, 0, w, h);
    c.save();
    c.translate(w / 2, h * 0.62);
    c.fillStyle = magic ? 'rgba(150,80,220,.16)' : 'rgba(200,36,30,.16)';
    for (var i = 0; i < 12; i++) {
      var a0 = i * Math.PI / 6;
      c.beginPath();
      c.moveTo(0, 0);
      c.arc(0, 0, w, a0, a0 + Math.PI / 17);
      c.closePath();
      c.fill();
    }
    c.restore();
    var g = c.createRadialGradient(w / 2, h * 0.45, 8, w / 2, h * 0.5, w * 0.72);
    if (magic) {
      g.addColorStop(0, 'rgba(96,44,150,.5)');
      g.addColorStop(0.55, 'rgba(42,17,64,0)');
      g.addColorStop(1, 'rgba(10,10,6,.6)');
    } else {
      g.addColorStop(0, 'rgba(90,18,22,.5)');
      g.addColorStop(0.55, 'rgba(74,16,19,0)');
      g.addColorStop(1, 'rgba(10,10,6,.6)');
    }
    c.fillStyle = g;
    c.fillRect(0, 0, w, h);
  }

  // 顶部玻璃高光 + 底部压暗：两笔给整卡做出体积
  function portraitGloss(c, w, h) {
    var g = c.createLinearGradient(0, 4, 0, h - 4);
    g.addColorStop(0, 'rgba(243,233,212,.13)');
    g.addColorStop(0.32, 'rgba(243,233,212,0)');
    g.addColorStop(0.8, 'rgba(10,10,6,0)');
    g.addColorStop(1, 'rgba(10,10,6,.38)');
    c.fillStyle = g;
    c.fillRect(0, 0, w, h);
  }

  // 黄铜细框 + 内圈黑 keyline，和侧栏卡片描边呼应
  function portraitFrame(c, w, h) {
    c.strokeStyle = 'rgba(10,10,6,.8)';
    c.lineWidth = 1;
    c.strokeRect(1.5, 1.5, w - 3, h - 3);
    c.strokeStyle = P_BRASS_D;
    c.strokeRect(0.5, 0.5, w - 1, h - 1);
  }

  function portraitFor(kind, isBuilding) {
    var key = (isBuilding ? 'b:' : 'u:') + kind;
    var hit = portraitCache[key];
    if (hit) { return hit; }
    var cv = document.createElement('canvas');
    cv.width = PORTRAIT_W;
    cv.height = PORTRAIT_H;
    var c = cv.getContext('2d');
    portraitBackdrop(c, PORTRAIT_W, PORTRAIT_H, !!MAGIC_KINDS[kind]);
    var painter = PORTRAIT_PAINTERS[kind];
    if (painter) {
      c.save();
      painter(c);
      c.restore();
    } else {
      // 未知类型兜底：黄铜星，至少不会画出空红卡
      pStar(c, 48, 38, 14, P_BRASS);
    }
    portraitGloss(c, PORTRAIT_W, PORTRAIT_H);
    portraitFrame(c, PORTRAIT_W, PORTRAIT_H);
    portraitCache[key] = cv;
    return cv;
  }

  // 生成一份可入 DOM 的肖像副本；badge > 0 时叠加右下角编队数角标。
  // 缓存画布永远不进 DOM，避免同一节点被多个面板抢来抢去。
  function makePortraitCanvas(kind, isBuilding, badge) {
    var cv = document.createElement('canvas');
    cv.width = PORTRAIT_W;
    cv.height = PORTRAIT_H;
    var c = cv.getContext('2d');
    c.drawImage(portraitFor(kind, isBuilding), 0, 0);
    if (badge) {
      c.fillStyle = 'rgba(10,10,6,.85)';
      c.beginPath();
      c.arc(81, 57, 11, 0, Math.PI * 2);
      c.fill();
      c.strokeStyle = P_BRASS;
      c.lineWidth = 1.5;
      c.stroke();
      c.fillStyle = P_LCD;
      c.font = 'bold 11px Consolas, monospace';
      c.textAlign = 'center';
      c.textBaseline = 'middle';
      c.fillText(String(badge), 81, 58);
    }
    return cv;
  }

  var homeScreen = $('#homeScreen');
  var lobbyScreen = $('#lobbyScreen');
  var gameScreen = $('#gameScreen');
  var playerNameInput = $('#playerName');
  var roomNameInput = $('#roomName');
  var roomCodeInput = $('#roomCodeInput');
  var roomList = $('#roomList');
  var serverStatus = $('#serverStatus');
  // 首页的地址栏信息直接取自当前页面地址，不再硬编码某台机器的 IP 和端口
  (function showNetworkCard() {
    var host = $('#netHost');
    var port = $('#netPort');
    if (host) { host.textContent = location.hostname || '127.0.0.1'; }
    if (port) {
      port.textContent = location.port ||
        (location.protocol === 'https:' ? '443' : '80');
    }
  })();
  var createRoomBtn = $('#createRoomBtn');
  var joinCodeBtn = $('#joinCodeBtn');
  var refreshRoomsBtn = $('#refreshRoomsBtn');
  var lobbyRoomName = $('#lobbyRoomName');
  var lobbyRoomCode = $('#lobbyRoomCode');
  var playerRoster = $('#playerRoster');
  var playerCount = $('#playerCount');
  var readyBtn = $('#readyBtn');
  var addBotBtn = $('#addBotBtn');
  var startGameBtn = $('#startGameBtn');
  var randomTeamBtn = $('#randomTeamBtn');
  var randomSpawnBtn = $('#randomSpawnBtn');
  var lobbyHint = $('#lobbyHint');
  var lobbyChatMessages = $('#lobbyChatMessages');
  var lobbyChatForm = $('#lobbyChatForm');
  var lobbyChatInput = $('#lobbyChatInput');
  var mapNameDisplay = $('#mapNameDisplay');
  var mapBriefingDisplay = $('#mapBriefingDisplay');
  var mapSizeDisplay = $('#mapSizeDisplay');
  var mapMaxPlayersDisplay = $('#mapMaxPlayersDisplay');
  var mapSpawnPreviews = $('#mapSpawnPreviews');
  var mapSelectHost = $('#mapSelectHost');
  var mapSelectDropdown = $('#mapSelectDropdown');
  var BUILTIN_MAPS = {
    north_conflict: { id: 'north_conflict', name: '北境冲突区', width: 9600, height: 6000, maxPlayers: 6, theme: 'grassland', spawnLabels: ['左上', '中上', '右上', '左下', '中下', '右下'], spawnPoints: [[900,800],[4800,700],[8700,800],[900,5200],[4800,5300],[8700,5200]] },
    narrow_standoff: { id: 'narrow_standoff', name: '狭路对峙', width: 4800, height: 3200, maxPlayers: 2, theme: 'arid', spawnLabels: ['左翼阵地', '右翼阵地'], spawnPoints: [[700,1600],[4100,1600]] },
    triple_pass: { id: 'triple_pass', name: '三岔隘口', width: 5400, height: 4200, maxPlayers: 3, theme: 'arid', spawnLabels: ['西境营地', '东北营地', '东南营地'], spawnPoints: [[700,2100],[3700,368],[3700,3832]] },
    gold_crater: { id: 'gold_crater', name: '赤金陨坑', width: 10000, height: 6400, maxPlayers: 5, theme: 'crater', briefing: '五方围着一口超级矿坑打。家矿比北境肥一圈，正中金库有炮塔、突击兵和火箭兵看守。外环邻里路口被熔水河切开，只能从公路桥过。', spawnLabels: ['北岗', '东北高地', '东南谷地', '西南谷地', '西北高地'], spawnPoints: [[5000,750],[7330,2443],[6440,5182],[3560,5182],[2670,2443]] },
    gold_crater_small: { id: 'gold_crater_small', name: '赤金陨坑·紧凑', width: 6400, height: 6400, maxPlayers: 5, theme: 'crater', briefing: '赤金陨坑的紧凑版：五方围着陨石核打，地图小一圈，邻里火拼更早打响。', spawnLabels: ['北岗', '东北高地', '东南谷地', '西南谷地', '西北高地'], spawnPoints: [[3200,750],[4691,2443],[4122,5182],[2278,5182],[1709,2443]] },
    island_hop: { id: 'island_hop', name: '三谷争夺', width: 7200, height: 6000, maxPlayers: 4, theme: 'grassland', spawnLabels: ['西北高地', '东北高地', '西南高地', '东南高地'], spawnPoints: [[900,900],[6300,900],[900,5100],[6300,5100]] },
    urban_siege: { id: 'urban_siege', name: '围城战', width: 6400, height: 6400, maxPlayers: 4, theme: 'urban', spawnLabels: ['西区', '北区', '东区', '南区'], spawnPoints: [[900,3200],[3200,900],[5500,3200],[3200,5500]] },
    valley_clash: { id: 'valley_clash', name: '峡谷交锋', width: 6400, height: 4800, maxPlayers: 4, theme: 'grassland', spawnLabels: ['左路前哨', '左路后哨', '右路前哨', '右路后哨'], spawnPoints: [[800,1800],[800,3000],[5600,1800],[5600,3000]] }
  };

  // 地图目录只在大厅和首帧下发，缓存住供整局使用
  var cachedMaps = null;

  function getMaps() {
    var maps = (roomState && roomState.maps) || cachedMaps || BUILTIN_MAPS;
    var keys = Object.keys(maps);
    if (keys.length === 0) { maps = BUILTIN_MAPS; }
    return maps;
  }

  function getMapConfig() {
    if (roomState && roomState.mapConfig && roomState.mapConfig.id) {
      return roomState.mapConfig;
    }
    return BUILTIN_MAPS.north_conflict;
  }
  var canvas = $('#gameCanvas');
  var view3d = createRenderer(canvas);
  // 调试/冒烟测试用的观察窗口
  window.__ironFront = {
    view3d: view3d,
    state: function () { return roomState; },
    camera: function () { return camera; }
  };
  var hudCanvas = $('#hudCanvas');
  var hudCtx = hudCanvas.getContext('2d');
  var minimap = $('#minimapCanvas');
  var miniCtx = minimap.getContext('2d');
  var selectionBox = $('#selectionBox');
  var buildCursorLabel = $('#buildCursorLabel');
  var commandGrid = $('#commandGrid');
  var selectionInfo = $('#selectionInfo');
  var scoreboard = $('#scoreboard');
  var battleChatMessages = $('#battleChatMessages');
  var battleChatForm = $('#battleChatForm');
  var battleChatInput = $('#battleChatInput');
  var connectionBadge = $('#connectionBadge');

  var session = null;
  var roomState = null;
  var eventSource = null;
  var currentScreen = 'home';
  var roomRefreshTimer = null;
  var lastRoomRenderKey = '';
  var lastChatRenderKey = '';
  var gameKey = null;
  var resultShown = false;
  var activeTab = 'buildings';
  var selectedUnits = new Set();
  var selectedStructureId = null;
  var buildMode = null;
  var commandMode = null;
  var viewWidth = 0;
  var viewHeight = 0;
  var lastViewWidth = 0;
  var lastViewHeight = 0;
  var dpr = 1;
  var lastDpr = 0;
  // 自动动态分辨率只调内部像素密度，不换模型、不改单位外形。低帧持续一段
  // 时间才降档，恢复也使用更长的迟滞，避免在两个档位之间来回抖动。
  var renderScale = 1;
  var renderScaleSteps = [1, 0.90, 0.80, 0.70, 0.60];
  var lowFpsSamples = 0;
  var highFpsSamples = 0;
  var adaptiveStartedAt = 0;
  // yaw = 视角旋转，pitch = 俯角（弧度）
  var camera = { x: 1200, y: 750, zoom: 0.78, yaw: 0, pitch: 0.94 };
  var pointer = { x: 0, y: 0, worldX: 0, worldY: 0, inside: false };
  var dragging = null;
  var pressedKeys = new Set();
  var stopKeyDownAt = 0;
  var controlGroups = {};
  var lastGroupTap = {};
  var structureHpSnap = {};
  var structureAlertUntil = {};
  var displayedCash = 0;
  // 资金 LCD 的“已上屏”缓存：-1 保证首帧一定会写一次 DOM
  var lastPaintedCash = -1;
  var cashValueEl = null;
  var lastFrame = performance.now();
  var lastMinimapDraw = 0;
  var lastSnapshotAt = 0;
  var fpsHistory = [];
  var fpsLastSample = 0;
  var fpsElement = null;
  var seenEffects = new Set();
  // 小地图矿点只在己方/盟友真正探到后登记，并在本局内永久保留。
  // 不能直接遍历静态 resources 全画，否则会泄露所有中立矿的位置。
  var discoveredResourceIds = new Set();
  var audioContext = null;
  var renderStarted = false;
  var actionInFlight = false;
  var lastHudUpdate = 0;
  var lastHudOverlayAt = -Infinity;
  var lastReadyBuildId = null;
  var ambientNode = null;
  // 静态开局数据：服务端只在每条 SSE 流的首帧（以及 REST 拉取时）下发
  var matchStatic = null;

  function startAmbient() {
    if (ambientNode || !audioContext) return;
    try {
      var buf = audioContext.createBuffer(1, audioContext.sampleRate * 2, audioContext.sampleRate);
      var d = buf.getChannelData(0);
      for (var i = 0; i < d.length; i++) { d[i] = (Math.random() * 2 - 1) * 0.03; }
      ambientNode = audioContext.createBufferSource();
      ambientNode.buffer = buf;
      ambientNode.loop = true;
      var f = audioContext.createBiquadFilter();
      f.type = 'lowpass';
      f.frequency.value = 180;
      var g = audioContext.createGain();
      g.gain.value = 0.03;
      ambientNode.connect(f);
      f.connect(g);
      g.connect(audioContext.destination);
      ambientNode.start();
    } catch (_) {}
  }

  function stopAmbient() {
    if (ambientNode) { try { ambientNode.stop(); } catch (_) {} ambientNode = null; }
  }

  var SETTINGS_KEY = 'steel-front-settings';
  var settings = { masterVolume: 70, sfxVolume: 80, particleQuality: 'low', fogQuality: 'low', shadowQuality: 'structures', bloomQuality: 'off', projectileQuality: 'on' };
  // 性能模式硬参数
  var PERF_PARTICLE_BUDGET = { low: 60, medium: 150, high: 300 };
  var PERF_FOG_SCALE = { low: 14, medium: 9, high: 6 };
  (function loadSettings() {
    try {
      var saved = JSON.parse(localStorage.getItem(SETTINGS_KEY));
      if (saved) { Object.keys(settings).forEach(function (k) { if (saved[k] != null) settings[k] = saved[k]; }); }
      // 旧默认把阴影关了，战场看起来像一块绿板。只升级一次。
      if (saved && !saved.mapDisplayV2) {
        if (settings.shadowQuality === 'off') settings.shadowQuality = 'structures';
        settings.mapDisplayV2 = 1;
        try { localStorage.setItem(SETTINGS_KEY, JSON.stringify(settings)); } catch (_) {}
      }
    } catch (_) {}
    // 2D 版本存的是 on/off；3D 版的阴影档位换成了 off/structures/all
    if (settings.shadowQuality === 'on') { settings.shadowQuality = 'structures'; }
    if (['off', 'structures', 'all'].indexOf(settings.shadowQuality) < 0) {
      settings.shadowQuality = 'structures';
    }
    settings.mapDisplayV2 = 1;
    applySettings();
  })();

  function saveSettings() {
    try { localStorage.setItem(SETTINGS_KEY, JSON.stringify(settings)); } catch (_) {}
  }

  function applySettings() {
    view3d.setQuality({
      shadows: settings.shadowQuality === 'off' ? 'off'
        : (settings.shadowQuality === 'all' ? 'all' : 'structures'),
      particleBudget: PERF_PARTICLE_BUDGET[settings.particleQuality] || 200,
      fogScale: PERF_FOG_SCALE[settings.fogQuality] || 9,
      bloom: settings.bloomQuality !== 'off',
      fastBloom: settings.bloomQuality === 'low',
      showProjectiles: settings.projectileQuality !== 'off',
      lod: true
    });
  }

  function showSettings() {
    var m = $('#settingsModal');
    m.classList.remove('hidden');
    $('#masterVolume').value = settings.masterVolume;
    $('#sfxVolume').value = settings.sfxVolume;
    $('#particleQuality').value = settings.particleQuality;
    $('#fogQuality').value = settings.fogQuality;
    $('#shadowQuality').value = settings.shadowQuality;
    if ($('#bloomQuality')) { $('#bloomQuality').value = settings.bloomQuality; }
    if ($('#projectileQuality')) { $('#projectileQuality').value = settings.projectileQuality; }
  }

  function htmlEscape(value) {
    var div = document.createElement('div');
    div.textContent = String(value == null ? '' : value);
    return div.innerHTML;
  }

  function lobbySpawnCount(mapConfig) {
    var config = mapConfig || getMapConfig() || {};
    if (config.spawnPoints && config.spawnPoints.length) {
      return config.spawnPoints.length;
    }
    if (config.spawnLabels && config.spawnLabels.length) {
      return config.spawnLabels.length;
    }
    return 6;
  }

  function takeFreeSpawn(used, preferred, totalSpawns) {
    if (preferred >= 0 && preferred < totalSpawns && !used[preferred]) {
      used[preferred] = true;
      return preferred;
    }
    for (var i = 0; i < totalSpawns; i++) {
      if (!used[i]) {
        used[i] = true;
        return i;
      }
    }
    return -1;
  }

  function autoAssignSpawns() {
    if (!roomState || !roomState.players) { return; }
    var me = ownPlayer();
    if (!me || !me.isHost) { return; }

    var mapConfig = getMapConfig();
    var totalSpawns = lobbySpawnCount(mapConfig);
    var spawnsPerSide = Math.max(1, Math.floor(totalSpawns / 2));

    // Group players by team
    var teamGroups = {};
    roomState.players.forEach(function (p) {
      var t = (p.team || 0);
      var key = t > 0 ? t : p.id;
      if (!teamGroups[key]) { teamGroups[key] = []; }
      teamGroups[key].push(p);
    });

    // Sort groups: larger teams first, consistent ordering
    var sides = [{}, {}];
    var groupKeys = Object.keys(teamGroups).sort(function (a, b) {
      return teamGroups[b].length - teamGroups[a].length || a.localeCompare(b);
    });

    groupKeys.forEach(function (key, gi) {
      var group = teamGroups[key];
      var teamNum = parseInt(key, 10);
      var side = (teamNum === 1) ? 0 : (teamNum === 2) ? 1 : (gi % 2);
      if (!sides[side]) { sides[side] = {}; }
      sides[side][key] = group;
    });

    // One unique seat per seated player. FFA groups are size 1, so a
    // per-group index of 0 used to hand the same side-slot to every
    // solo player and skip the rest — 4人图只写出两个出生点。
    var used = {};
    var assignments = [];
    [0, 1].forEach(function (side) {
      var offset = side * spawnsPerSide;
      var sideCount = (side === 0) ? spawnsPerSide : (totalSpawns - spawnsPerSide);
      var seat = 0;
      Object.keys(sides[side] || {}).forEach(function (key) {
        (sides[side][key] || []).forEach(function (p) {
          var preferred = (seat < sideCount) ? (offset + seat) : -1;
          var sp = takeFreeSpawn(used, preferred, totalSpawns);
          if (sp >= 0) { assignments.push({ player: p, spawn: sp }); }
          seat += 1;
        });
      });
    });

    assignments.forEach(function (entry) {
      var currentSpawn = entry.player.spawn == null ? -1 : entry.player.spawn;
      if (currentSpawn !== entry.spawn) {
        sendAction('setSpawn', { playerId: entry.player.id, spawn: entry.spawn });
      }
    });
  }

  async function randomAssignSpawns(rs, mapConfig) {
    var totalSpawns = lobbySpawnCount(mapConfig);
    var spawnsPerSide = Math.max(1, Math.floor(totalSpawns / 2));
    var players = rs.players.slice().sort(function () { return Math.random() - 0.5; });

    var side0 = [];
    var side1 = [];
    players.forEach(function (p) {
      var t = p.team || 0;
      if (t === 1) { side0.push(p); }
      else if (t === 2) { side1.push(p); }
      else if (side0.length <= side1.length) { side0.push(p); }
      else { side1.push(p); }
    });

    function shuffle(a) {
      for (var i = a.length - 1; i > 0; i--) {
        var j = Math.floor(Math.random() * (i + 1));
        var tmp = a[i]; a[i] = a[j]; a[j] = tmp;
      }
    }
    function pool(start, end) {
      var items = [];
      for (var n = start; n < end; n++) { items.push(n); }
      shuffle(items);
      return items;
    }
    shuffle(side0);
    shuffle(side1);

    var used = {};
    var pools = [pool(0, spawnsPerSide), pool(spawnsPerSide, totalSpawns)];
    var spawnList = [];
    function assignSide(sidePlayers, side) {
      sidePlayers.forEach(function (p) {
        var preferred = pools[side].length ? pools[side].shift() : -1;
        var sp = takeFreeSpawn(used, preferred, totalSpawns);
        if (sp >= 0) { spawnList.push({ player: p, spawn: sp }); }
      });
    }
    assignSide(side0, 0);
    assignSide(side1, 1);

    for (var k = 0; k < spawnList.length; k++) {
      var entry = spawnList[k];
      var currentSpawn = entry.player.spawn == null ? -1 : entry.player.spawn;
      if (currentSpawn !== entry.spawn) {
        await sendAction('setSpawn', { playerId: entry.player.id, spawn: entry.spawn });
      }
    }
  }

  function setScreen(name) {
    if (name === 'game' && currentScreen !== 'game') { startAmbient(); }
    if (name !== 'game' && currentScreen === 'game') { stopAmbient(); }
    currentScreen = name;
    homeScreen.classList.toggle('hidden', name !== 'home');
    lobbyScreen.classList.toggle('hidden', name !== 'lobby');
    gameScreen.classList.toggle('hidden', name !== 'game');
    homeScreen.style.transition = 'opacity .3s';
    lobbyScreen.style.transition = 'opacity .3s';
    gameScreen.style.transition = 'opacity .3s';
    document.body.style.overflow = name === 'game' ? 'hidden' : '';
    if (name === 'home') {
      startRoomRefresh();
    } else {
      stopRoomRefresh();
    }
  }

  function getCommanderName() {
    var name = playerNameInput.value.trim();
    if (!name) {
      showHomeError('请先填写指挥官代号');
      playerNameInput.focus();
      return null;
    }
    localStorage.setItem(NAME_KEY, name);
    return name.slice(0, 16);
  }

  function showHomeError(message) {
    serverStatus.className = 'server-status offline';
    serverStatus.querySelector('span:last-child').textContent = message;
  }

  async function request(path, options) {
    options = options || {};
    var response = await fetch(path, {
      method: options.method || 'GET',
      headers: options.body ? { 'Content-Type': 'application/json' } : undefined,
      body: options.body ? JSON.stringify(options.body) : undefined,
      cache: 'no-store'
    });
    var data;
    try {
      data = await response.json();
    } catch (_error) {
      throw new Error('服务器响应异常');
    }
    if (!response.ok || data.ok === false) {
      throw new Error(data.error || '请求失败');
    }
    return data;
  }

  async function sendAction(action, payload, silent) {
    if (!session) {
      throw new Error('会话已失效');
    }
    try {
      var data = await request('/api/action', {
        method: 'POST',
        body: {
          roomId: session.roomId,
          playerId: session.playerId,
          token: session.token,
          action: action,
          payload: payload || {}
        }
      });
      if (data.room) {
        applyRoomState(data.room);
      }
      return data;
    } catch (error) {
      if (!silent) {
        toast(error.message, 'error');
        sound('error');
      }
      throw error;
    }
  }

  function saveSession(value) {
    session = value;
    if (value) {
      sessionStorage.setItem(SESSION_KEY, JSON.stringify(value));
    } else {
      sessionStorage.removeItem(SESSION_KEY);
    }
  }

  async function createRoom() {
    var name = getCommanderName();
    if (!name || actionInFlight) {
      return;
    }
    actionInFlight = true;
    createRoomBtn.disabled = true;
    try {
      var data = await request('/api/create', {
        method: 'POST',
        body: {
          playerName: name,
          roomName: roomNameInput.value.trim()
        }
      });
      saveSession(data.session);
      applyRoomState(data.room);
      connectEvents();
      sound('confirm');
    } catch (error) {
      showHomeError(error.message);
    } finally {
      actionInFlight = false;
      createRoomBtn.disabled = false;
    }
  }

  async function joinRoom(roomId) {
    var name = getCommanderName();
    roomId = String(roomId || '').trim().toUpperCase();
    if (!name || !roomId || actionInFlight) {
      if (!roomId) {
        showHomeError('请输入房间码');
      }
      return;
    }
    actionInFlight = true;
    joinCodeBtn.disabled = true;
    try {
      var data = await request('/api/join', {
        method: 'POST',
        body: { playerName: name, roomId: roomId }
      });
      saveSession(data.session);
      applyRoomState(data.room);
      connectEvents();
      sound('confirm');
    } catch (error) {
      showHomeError(error.message);
    } finally {
      actionInFlight = false;
      joinCodeBtn.disabled = false;
    }
  }

  async function restoreSession() {
    var stored = sessionStorage.getItem(SESSION_KEY);
    if (!stored) {
      return false;
    }
    try {
      session = JSON.parse(stored);
      var query = new URLSearchParams(session).toString();
      var data = await request('/api/state?' + query);
      applyRoomState(data.room);
      connectEvents();
      return true;
    } catch (_error) {
      saveSession(null);
      return false;
    }
  }

  function connectEvents() {
    if (!session) {
      return;
    }
    if (eventSource) {
      eventSource.close();
    }
    var query = new URLSearchParams(session).toString();
    eventSource = new EventSource('/api/events?' + query);
    setConnectionState(false);
    eventSource.addEventListener('state', function (event) {
      try {
        var state = JSON.parse(event.data);
        lastSnapshotAt = performance.now();
        setConnectionState(true);
        applyRoomState(state);
      } catch (_error) {
        setConnectionState(false);
      }
    });
    eventSource.onopen = function () {
      setConnectionState(true);
    };
    eventSource.onerror = function () {
      setConnectionState(false);
    };
  }

  function setConnectionState(connected) {
    if (!connectionBadge) {
      return;
    }
    connectionBadge.classList.toggle('reconnecting', !connected);
    connectionBadge.innerHTML = connected ? '<i></i> 已连接' : '<i></i> 正在重连';
  }

  async function refreshRooms() {
    try {
      var data = await request('/api/rooms');
      renderRoomList(data.rooms);
      serverStatus.className = 'server-status online';
      serverStatus.querySelector('span:last-child').textContent = '作战服务器在线 · ' + data.rooms.length + ' 个战场';
    } catch (error) {
      showHomeError('无法连接服务器：' + error.message);
      roomList.innerHTML = '<div class="empty-state"><div class="radar-icon"></div><strong>服务器离线</strong><span>请确认游戏服务已经启动</span></div>';
    }
  }

  function renderRoomList(rooms) {
    roomList.innerHTML = '';
    if (!rooms.length) {
      roomList.innerHTML = '<div class="empty-state"><div class="radar-icon"><i></i><i></i></div><strong>暂时没有公开战场</strong><span>创建一个房间，邀请同事加入</span></div>';
      return;
    }
    var template = $('#roomItemTemplate');
    rooms.forEach(function (room) {
      var node = template.content.firstElementChild.cloneNode(true);
      node.querySelector('.room-title').textContent = room.name;
      node.querySelector('.room-meta').textContent = '房主 ' + room.hostName + ' · 房间码 ' + room.id;
      node.querySelector('.room-capacity').textContent = room.players + ' / ' + room.maxPlayers;
      var button = node.querySelector('.join-button');
      if (room.status !== 'lobby') {
        button.textContent = '战斗中';
        button.disabled = true;
      } else if (room.players >= room.maxPlayers) {
        button.textContent = '已满';
        button.disabled = true;
      } else {
        button.addEventListener('click', function () { joinRoom(room.id); });
      }
      roomList.appendChild(node);
    });
  }

  function startRoomRefresh() {
    stopRoomRefresh();
    refreshRooms();
    roomRefreshTimer = setInterval(refreshRooms, 2600);
  }

  function stopRoomRefresh() {
    if (roomRefreshTimer) {
      clearInterval(roomRefreshTimer);
      roomRefreshTimer = null;
    }
  }

  function ownPlayer() {
    if (!roomState || !session) {
      return null;
    }
    return roomState.players.find(function (player) { return player.id === session.playerId; }) || null;
  }

  function isOwnMagicFaction() {
    var me = ownPlayer();
    return !!(me && (me.faction || 'tech') === 'magic');
  }

  function playerById(id) {
    return roomState ? roomState.players.find(function (player) { return player.id === id; }) : null;
  }

  /**
   * 补回快照里被省略的静态数据。
   *
   * 服务端只在每条 SSE 流的首帧（以及每次 REST 拉取）发送地图、地形、
   * 矿脉布局、视距表和建造目录；之后每帧只带矿脉余量 `ore`。这里把缓存
   * 的静态部分贴回去，让后面的代码仍然看到一个完整的 game 对象。
   *
   * 返回这一帧是否可用于渲染：还没收到过任何 full 帧就先来了增量帧的话，
   * 手上没有地图与地形，补不出完整对象，只能整帧丢弃等下一帧。
   */
  function hydrateGame(game, mapConfig) {
    if (!game) { return true; }
    if (game.full) {
      if (game.catalog) { applyCatalog(game.catalog); }
      var byId = {};
      (game.resources || []).forEach(function (r) { byId[r.id] = r; });
      matchStatic = {
        map: game.map,
        terrain: game.terrain,
        resources: game.resources || [],
        resourceById: byId,
        sight: game.sight
      };
      // setMatch 内部按地图身份判等：同一局里重复收到 full 帧不会重建世界，
      // 那么小地图的静态层同样不该重画。
      if (view3d.setMatch(game.map, game.terrain, game.resources, game.sight,
          (mapConfig && mapConfig.spawnPoints) || [])) {
        minimapStaticKey = '';
      }
    } else if (!matchStatic) {
      // 还没拿到过任何 full 帧就收到增量帧：没有地图与地形，渲染不出东西。
      // 丢掉这一帧的战场数据，等 SSE 首帧或 /api/state 补上静态块。
      return false;
    } else {
      game.map = matchStatic.map;
      game.terrain = matchStatic.terrain;
      game.resources = matchStatic.resources;
      game.sight = matchStatic.sight;
    }
    if (game.ore && matchStatic) {
      for (var i = 0; i < game.ore.length; i++) {
        var node = matchStatic.resourceById[game.ore[i][0]];
        if (node) {
          node.amount = game.ore[i][1];
          node.guarded = !!game.ore[i][2];
        }
      }
      game.resources = matchStatic.resources;
    }
    if (!game.resources) { game.resources = []; }
    return true;
  }

  function applyRoomState(state) {
    var previousStatus = roomState && roomState.status;
    if (state.maps) { cachedMaps = state.maps; }
    if (!hydrateGame(state.game, state.mapConfig)) {
      delete state.game;
    }
    roomState = state;
    if (state.players) {
      var nextPaletteKey = (session && session.playerId || '') + '|' + state.players.map(function (p) {
        return p.id + ':' + p.color + ':' + (p.team || 0);
      }).join(';');
      if (nextPaletteKey !== paletteStateKey) {
        paletteStateKey = nextPaletteKey;
        playerColorById = {};
        playerTeamById = {};
        state.players.forEach(function (p) {
          playerColorById[p.id] = p.color;
          playerTeamById[p.id] = p.team || 0;
        });
        view3d.setPalette(state.players, session && session.playerId, isFriendly);
      }
    }

    if (state.status === 'lobby') {
      if (currentScreen !== 'lobby') {
        setScreen('lobby');
      }
      renderLobby();
    } else if (state.status === 'playing' || state.status === 'finished') {
      if (currentScreen !== 'game') {
        setScreen('game');
        enterGame();
      }
      if (previousStatus !== state.status && state.status === 'finished') {
        renderResult();
      }
      syncPreparedBuilding();
      if (performance.now() - lastHudUpdate > 180 || previousStatus !== state.status) {
        lastHudUpdate = performance.now();
        updateGameHud();
      }
      processEffects();
      pruneSelection();
      if (state.status === 'finished' && !resultShown) {
        renderResult();
      }
    }
  }

  function renderLobby() {
    if (!roomState) {
      return;
    }
    var me = ownPlayer();
    var mapConfig = getMapConfig();
    lobbyRoomName.textContent = roomState.name;
    lobbyRoomCode.textContent = roomState.id;
    playerCount.textContent = roomState.players.length + ' / ' + mapConfig.maxPlayers;

    mapNameDisplay.textContent = mapConfig.name;
    mapSizeDisplay.textContent = mapConfig.width + ' \u00d7 ' + mapConfig.height;
    mapMaxPlayersDisplay.textContent = mapConfig.maxPlayers;
    if (mapBriefingDisplay) {
      var mapsForBrief = getMaps();
      var fullBrief = (mapConfig.id && mapsForBrief[mapConfig.id]) || mapConfig;
      var briefing = mapConfig.briefing || fullBrief.briefing || '';
      mapBriefingDisplay.textContent = briefing;
      mapBriefingDisplay.style.display = briefing ? '' : 'none';
    }

    renderMapPreview(mapConfig);
    renderMapSelect(me, roomState);

    // Only rebuild the roster DOM when something actually changed.
    // Rebuilding on every SSE tick destroys open dropdowns instantly.
    var rosterKey = roomState.players.map(function (p) {
      return p.id + ':' + p.team + ':' + (p.spawn == null ? -1 : p.spawn) + ':' +
             p.ready + ':' + p.isBot + ':' + p.name + ':' + p.color + ':' + (p.faction || 'tech');
    }).join('|') + (me && me.isHost ? '|host' : '') + '|' + roomState.selectedMap;
    if (playerRoster.dataset.key === rosterKey) {
      renderChat(lobbyChatMessages, roomState.chat, 30);
      return;
    }
    playerRoster.dataset.key = rosterKey;
    playerRoster.innerHTML = '';

    roomState.players.forEach(function (player, index) {
      var slot = document.createElement('div');
      slot.className = 'player-slot';
      slot.style.setProperty('--player-color', player.color);
      var hostText = player.isHost ? ' · 房主' : '';
      var botText = player.isBot ? '战术 AI' : '人类指挥官';
      var teamLabel = '';
      if (player.team && player.team > 0) {
        var teamNames = ['', '红队', '蓝队', '绿队', '黄队'];
        teamLabel = ' · ' + (teamNames[player.team] || ('第' + player.team + '队'));
      }
      slot.innerHTML =
        '<i class="player-color"></i>' +
        '<div class="player-avatar">' + String(index + 1).padStart(2, '0') + '</div>' +
        '<div class="player-details"><strong>' + htmlEscape(player.name) + '</strong><span>' + botText + hostText + teamLabel + '</span></div>' +
        '<div class="ready-state ' + (player.ready || player.isHost ? 'ready' : '') + '">' +
        (player.isHost ? '房主' : (player.ready ? '已准备' : '未准备')) + '</div>';
      if (me && me.isHost && player.isBot) {
        var removeButton = document.createElement('button');
        removeButton.className = 'remove-bot';
        removeButton.textContent = '×';
        removeButton.title = '移除 AI';
        removeButton.addEventListener('click', function () {
          sendAction('removeBot', { botId: player.id });
        });
        slot.appendChild(removeButton);
      }
      if (me && me.isHost) {
        var teamSelect = document.createElement('select');
        teamSelect.className = 'team-select';
        // 外观交给样式表的 .team-select（苏军皮肤），这里只管布局归位
        [0, 1, 2, 3, 4].forEach(function (t) {
          var opt = document.createElement('option');
          opt.value = t;
          opt.textContent = t === 0 ? '无队伍' : (['', '红队', '蓝队', '绿队', '黄队'][t] || ('队' + t));
          if ((player.team || 0) === t) { opt.selected = true; }
          teamSelect.appendChild(opt);
        });
        teamSelect.addEventListener('change', function () {
          var newTeam = parseInt(teamSelect.value, 10);
          sendAction('setTeam', { playerId: player.id, team: newTeam });
          autoAssignSpawns(newTeam);
        });
        slot.appendChild(teamSelect);

        var spawnSelect = document.createElement('select');
        spawnSelect.className = 'spawn-select';
        // 同上：样式表的 .spawn-select 负责外观
        var spawnLabels = mapConfig.spawnLabels || ['左上', '中上', '右上', '左下', '中下', '右下'];
        var optAuto = document.createElement('option');
        optAuto.value = -1;
        optAuto.textContent = '自动';
        if ((player.spawn == null ? -1 : player.spawn) === -1) { optAuto.selected = true; }
        spawnSelect.appendChild(optAuto);
        spawnLabels.forEach(function (label, i) {
          var opt = document.createElement('option');
          opt.value = i;
          opt.textContent = ('0' + (i + 1)).slice(-2) + ' ' + label;
          if ((player.spawn == null ? -1 : player.spawn) === i) { opt.selected = true; }
          spawnSelect.appendChild(opt);
        });
        spawnSelect.addEventListener('change', function () {
          sendAction('setSpawn', { playerId: player.id, spawn: parseInt(spawnSelect.value, 10) });
        });
        slot.appendChild(spawnSelect);
      }

      // 阵营选择（自助）：本人随时可改；AI 由房主指定；其它玩家只读
      var factionSelect = document.createElement('select');
      factionSelect.className = 'faction-select';
      factionSelect.title = '选择阵营：钢铁军团(科技) / 秘法会(魔法)';
      [['tech', '⚙ 钢铁军团'], ['magic', '✦ 秘法会']].forEach(function (pair) {
        var opt = document.createElement('option');
        opt.value = pair[0];
        opt.textContent = pair[1];
        if ((player.faction || 'tech') === pair[0]) { opt.selected = true; }
        factionSelect.appendChild(opt);
      });
      var canEditFaction = (me && player.id === me.id) || (me && me.isHost && player.isBot);
      factionSelect.disabled = !canEditFaction;
      if (canEditFaction) {
        factionSelect.addEventListener('change', function () {
          sendAction('setFaction', { playerId: player.id, faction: factionSelect.value });
        });
      }
      slot.appendChild(factionSelect);
      playerRoster.appendChild(slot);
    });

    for (var i = roomState.players.length; i < mapConfig.maxPlayers; i += 1) {
      var empty = document.createElement('div');
      empty.className = 'player-slot empty';
      empty.style.setProperty('--player-color', '#4b5b5d');
      empty.innerHTML =
        '<i class="player-color"></i><div class="player-avatar">--</div>' +
        '<div class="player-details"><strong>等待接入</strong><span>空闲作战席位</span></div>';
      playerRoster.appendChild(empty);
    }

    if (!me) {
      return;
    }
    readyBtn.classList.toggle('hidden', me.isHost);
    readyBtn.classList.toggle('active', me.ready);
    readyBtn.textContent = me.ready ? '取消准备' : '准备作战';
    addBotBtn.classList.toggle('hidden', !me.isHost || roomState.players.length >= mapConfig.maxPlayers);
    startGameBtn.classList.toggle('hidden', !me.isHost);
    randomTeamBtn.classList.toggle('hidden', !me.isHost || roomState.players.length < 2);
    randomSpawnBtn.classList.toggle('hidden', !me.isHost || roomState.players.length < 2);
    var guestsReady = roomState.players.filter(function (p) { return !p.isBot && !p.isHost; }).every(function (p) { return p.ready; });
    startGameBtn.disabled = roomState.players.length < 2 || !guestsReady;

    if (me.isHost) {
      if (roomState.players.length < 2) {
        lobbyHint.textContent = '请等待玩家加入，或添加一个 AI 对手';
      } else if (!guestsReady) {
        lobbyHint.textContent = '等待其他指挥官准备';
      } else {
        lobbyHint.textContent = '作战序列已就绪，可以开始战斗';
      }
    } else {
      lobbyHint.textContent = me.ready ? '已进入战备状态，等待房主开始' : '准备后即可参加战斗';
    }
    renderChat(lobbyChatMessages, roomState.chat, 30);
  }

  function renderMapPreview(mapConfig) {
    if (!mapSpawnPreviews) { return; }
    var points = mapConfig.spawnPoints;
    var mw = mapConfig.width;
    var mh = mapConfig.height;
    var key = mapConfig.id + '|' + (points ? points.join(',') : '');
    if (mapSpawnPreviews.dataset.key === key) { return; }
    mapSpawnPreviews.dataset.key = key;
    mapSpawnPreviews.innerHTML = '';
    var cvs = document.createElement('canvas');
    cvs.width = mapSpawnPreviews.clientWidth || 300;
    cvs.height = mapSpawnPreviews.clientHeight || 210;
    var w = cvs.width, h = cvs.height;
    var sx = w / mw, sy = h / mh;
    var ctx = cvs.getContext('2d');
    // 优先取地图目录里的完整条目：真实地形字段（若服务端下发）挂在那里，
    // 不再画那条与实际地形无关的假贝塞尔河
    var maps = getMaps();
    var full = (mapConfig.id && maps[mapConfig.id]) || mapConfig;
    var terrain = {
      theme: full.theme || mapConfig.theme,
      rivers: full.rivers || mapConfig.rivers,
      mountains: full.mountains || mapConfig.mountains,
      roads: full.roads || mapConfig.roads,
      bridges: full.bridges || mapConfig.bridges
    };
    paintGrassBase(ctx, w, h, full.theme || mapConfig.theme);
    paintTerrainFeatures(ctx, terrain, sx, sy);
    // 矿脉数据若在目录里也一并点出来；没有就跳过
    var previewResources = full.resources || mapConfig.resources;
    if (previewResources && previewResources.length) {
      previewResources.forEach(function (r) {
        var rx = (r.x != null ? r.x : r[0]) * sx;
        var ry = (r.y != null ? r.y : r[1]) * sy;
        // 外层琥珀光晕
        var g = ctx.createRadialGradient(rx, ry, 1, rx, ry, 5);
        g.addColorStop(0, 'rgba(255,180,40,.38)');
        g.addColorStop(1, 'rgba(255,180,40,0)');
        ctx.fillStyle = g;
        ctx.fillRect(rx - 5, ry - 5, 10, 10);
        // 核心亮金点
        ctx.fillStyle = '#ffcc44';
        ctx.fillRect(rx - 2, ry - 2, 4, 4);
      });
    }
    // 轻暗角 + 内描边，与小地图同一套收边语言
    var vg = ctx.createRadialGradient(w / 2, h / 2, Math.min(w, h) * 0.45,
      w / 2, h / 2, Math.hypot(w, h) * 0.62);
    vg.addColorStop(0, 'rgba(10,10,6,0)');
    vg.addColorStop(1, 'rgba(10,10,6,.32)');
    ctx.fillStyle = vg;
    ctx.fillRect(0, 0, w, h);
    ctx.strokeStyle = 'rgba(10,10,6,.65)';
    ctx.lineWidth = 1;
    ctx.strokeRect(0.5, 0.5, w - 1, h - 1);
    if (points) {
      points.forEach(function (p, i) {
        var px = p[0] * sx, py = p[1] * sy;
        // 出生点用琥珀 LCD 色：开战前还没有队伍色，青色留给战场
        ctx.fillStyle = '#ffd23e';
        ctx.strokeStyle = '#0a0a06';
        ctx.lineWidth = 1.5;
        ctx.beginPath();
        ctx.arc(px, py, 6, 0, Math.PI * 2);
        ctx.fill();
        ctx.stroke();
        ctx.fillStyle = '#f3e9d4';
        ctx.font = '9px Consolas, monospace';
        ctx.textAlign = 'center';
        ctx.strokeStyle = 'rgba(10,10,6,.85)';
        ctx.lineWidth = 2;
        var lbl = mapConfig.spawnLabels[i] || String(i + 1);
        ctx.strokeText(lbl, px, py + 3);
        ctx.fillText(lbl, px, py + 3);
      });
    }
    mapSpawnPreviews.appendChild(cvs);
  }

  function renderMapSelect(me, roomState) {
    if (!mapSelectHost || !mapSelectDropdown) { return; }
    if (!me || !me.isHost) {
      mapSelectHost.style.display = 'none';
      return;
    }
    mapSelectHost.style.display = '';
    var maps = getMaps();
    var mapConfig = getMapConfig();
    var selected = mapConfig.id || 'north_conflict';
    var currentKey = selected + '|' + Object.keys(maps).join();
    if (mapSelectDropdown.dataset.key === currentKey) { return; }
    mapSelectDropdown.dataset.key = currentKey;
    mapSelectDropdown.innerHTML = '';
    var mapIds = Object.keys(maps).sort();
    for (var i = 0; i < mapIds.length; i += 1) {
      var m = maps[mapIds[i]];
      var opt = document.createElement('option');
      opt.value = m.id;
      opt.textContent = m.name + ' (' + m.width + '\u00d7' + m.height + ', ' + m.maxPlayers + '人)';
      if (m.id === selected) { opt.selected = true; }
      mapSelectDropdown.appendChild(opt);
    }
    if (!mapSelectDropdown.dataset.listenerAttached) {
      mapSelectDropdown.dataset.listenerAttached = '1';
      mapSelectDropdown.addEventListener('change', function () {
        sendAction('selectMap', { mapId: mapSelectDropdown.value });
      });
    }
  }

  function renderChat(container, messages, limit) {
    var key = messages.map(function (m) { return m.id; }).join(',');
    var localKey = container.id + ':' + key;
    if (container.dataset.renderKey === localKey) {
      return;
    }
    container.dataset.renderKey = localKey;
    container.innerHTML = '';
    messages.slice(-limit).forEach(function (message) {
      var line = document.createElement('p');
      line.className = 'chat-line' + (message.system ? ' system' : '');
      if (message.system) {
        line.textContent = '▸ ' + message.message;
      } else {
        var sender = document.createElement('b');
        sender.textContent = message.sender + '：';
        line.appendChild(sender);
        line.appendChild(document.createTextNode(message.message));
      }
      container.appendChild(line);
    });
    container.scrollTop = container.scrollHeight;
  }

  async function leaveRoom() {
    if (session) {
      try {
        await sendAction('leave', {}, true);
      } catch (_error) {
        // Leaving locally is still safe if the connection disappeared.
      }
    }
    if (eventSource) {
      eventSource.close();
      eventSource = null;
    }
    saveSession(null);
    roomState = null;
    gameKey = null;
    resultShown = false;
    selectedUnits.clear();
    selectedStructureId = null;
    setScreen('home');
  }

  function enterGame() {
    if (!roomState || !roomState.game) {
      return;
    }
    var nextKey = roomState.id + ':' + roomState.createdAt;
    if (gameKey !== nextKey) {
      gameKey = nextKey;
      resultShown = false;
      selectedUnits.clear();
      selectedStructureId = null;
      buildMode = null;
      commandMode = null;
      view3d.clearEntities();
      seenEffects.clear();
      discoveredResourceIds.clear();
      lastReadyBuildId = null;
      commandGrid.dataset.key = '';
      selectionInfo.dataset.key = '';
      minimapStaticKey = '';
      adaptiveStartedAt = performance.now();
      lowFpsSamples = 0;
      highFpsSamples = 0;
      lastHudOverlayAt = -Infinity;
      camera.yaw = 0;
      var hq = roomState.game.structures.find(function (s) {
        return s.owner === session.playerId && structureRole(s.kind) === 'hq';
      });
      camera.x = hq ? hq.x : roomState.game.map.width / 2;
      camera.y = hq ? hq.y : roomState.game.map.height / 2;
      camera.zoom = 1.0;   // 开局视角更贴近基地
      toast('战斗开始：保护' + factionCopy().hq + '，摧毁所有敌方总部', 'success');
      sound('start');
    }
    resizeCanvas();
    renderCommandGrid(true);
    if (!renderStarted) {
      renderStarted = true;
      requestAnimationFrame(frame);
    }
    canvas.focus();
  }

  var activeProposalFromId = null;
  var activeProposalFromName = null;

  // 侧栏中段的战场态势读数。原本这里是一大块空白，现在放常看的几个数字。
  function updateTacticalReadout(me, forceCount) {
    var readout = $('#tacticalReadout');
    if (!readout) { return; }
    var units = roomState.game.units;
    var harvesters = 0;
    for (var i = 0; i < units.length; i++) {
      if (units[i].owner === me.id && unitRole(units[i].kind) === 'harvester') { harvesters++; }
    }
    var buildings = roomState.game.structures.filter(function (s) {
      return s.owner === me.id;
    }).length;

    var set = function (id, value) {
      var el = $(id);
      if (el && el.textContent !== value) { el.textContent = value; }
    };
    set('#statUnits', String(forceCount));
    set('#statBuildings', String(buildings));
    set('#statHarvesters', String(harvesters));
    set('#statHarvested', Math.floor(me.harvested || 0).toLocaleString('zh-CN'));
    set('#statKills', String(me.kills || 0));
    set('#statLost', String(me.unitsLost || 0));

    var load = me.powerSupply > 0 ? me.powerUse / me.powerSupply : (me.powerUse ? 1.4 : 0);
    var fill = $('#statPowerFill');
    if (fill) {
      fill.style.width = Math.min(100, load * 100) + '%';
      fill.classList.toggle('overload', load > 1);
    }
    set('#statPowerText', Math.round(load * 100) + '%');
  }

  function updateGameHud() {
    if (!roomState || !roomState.game) {
      return;
    }
    var me = ownPlayer();
    if (!me) {
      return;
    }
    // 资金读数由 frame() 里的插值滚动负责，这里直写会让 LCD 数字来回跳
    $('#powerValue').textContent = me.powerUse + ' / ' + me.powerSupply;
    $('#powerValue').style.color = me.powerUse > me.powerSupply ? '#ff7479' : '';
    var forceCount = roomState.game.units.filter(function (unit) { return unit.owner === me.id; }).length;
    $('#forceValue').textContent = String(forceCount);
    var elapsed = Math.max(0, Math.floor(roomState.game.elapsed));
    $('#matchClock').textContent = pad(Math.floor(elapsed / 60)) + ':' + pad(elapsed % 60);
    updateTacticalReadout(me, forceCount);

    var strikeBtn = $('#strikeBtn');
    if (strikeBtn) {
      var charges = me.strikeCharges || 0;
      strikeBtn.classList.toggle('hidden', charges <= 0);
      strikeBtn.classList.toggle('ready', charges > 0);
    }

    applyFactionHud();
    var repairBtn = $('#repairBtn');
    if (repairBtn) {
      repairBtn.classList.remove('hidden');
    }
    var repairHint = $('#repairHint');
    if (repairHint) {
      repairHint.classList.remove('hidden');
    }

    var ownHQ = roomState.game.structures.find(function (s) { return s.owner === me.id && structureRole(s.kind) === 'hq' && s.active; });
    var gameScreenEl = document.querySelector('.game-screen');
    if (ownHQ && ownHQ.hp / ownHQ.maxHp < 0.30) {
      var pulse = Math.sin(elapsed * 4) * 0.5 + 0.5;
      gameScreenEl.style.boxShadow = 'inset 0 0 ' + (20 + pulse * 60) + 'px rgba(255,20,20,' + (0.08 + pulse * 0.2) + ')';
    } else {
      gameScreenEl.style.boxShadow = '';
    }

    if (roomState.game.structures) {
      var now = performance.now();
      roomState.game.structures.forEach(function (s) {
        if (s.owner !== me.id) return;
        var prev = structureHpSnap[s.id];
        if (prev != null && s.hp < prev - 0.5 && s.active) {
          structureAlertUntil[s.id] = now + 2500;
        }
        structureHpSnap[s.id] = s.hp;
      });
    }

    var scoreKey = roomState.players.map(function (player) {
      return player.id + ':' + player.eliminated + ':' + player.kills + ':' + (player.team || 0);
    }).join('|');
    if (scoreboard.dataset.key !== scoreKey) {
      scoreboard.dataset.key = scoreKey;
      scoreboard.innerHTML = '';
      var myTeam = (me.team || 0);
      var sorted = roomState.players.slice().sort(function (a, b) {
        if (a.team !== b.team && myTeam > 0) { return (a.team === myTeam ? -1 : (b.team === myTeam ? 1 : 0)); }
        return b.kills - a.kills;
      });
      sorted.forEach(function (player) {
        var item = document.createElement('div');
        item.className = 'score-player' + (player.eliminated ? ' eliminated' : '') + (isFriendly(player.id) ? ' ally' : '') + (player.id === me.id ? ' self' : '');
        item.style.setProperty('--player-color', player.color);
        item.title = player.name + ' · 击毁 ' + player.kills + ' · 损失 ' + player.unitsLost + (player.team ? ' · 队伍' + player.team : '');
        item.innerHTML = '<i></i><span>' + htmlEscape(player.name) + '</span><small>' + player.kills + '</small>';
        if (player.id !== me.id && !player.isBot) {
          item.addEventListener('click', function () { handleScoreboardClick(player.id, player.name); });
        }
        scoreboard.appendChild(item);
      });
    }

    // Handle incoming alliance proposal
    if (roomState.incomingProposal && roomState.incomingProposal.fromId !== activeProposalFromId) {
      activeProposalFromId = roomState.incomingProposal.fromId;
      activeProposalFromName = roomState.incomingProposal.fromName;
      showAllianceProposal(activeProposalFromId, activeProposalFromName);
    } else if (!roomState.incomingProposal && activeProposalFromId) {
      activeProposalFromId = null;
      activeProposalFromName = null;
      dismissAllianceProposal();
    }

    renderCommandGrid();
    renderSelectionInfo();
    renderChat(battleChatMessages, roomState.chat, 7);
  }

  function pad(number) {
    return String(number).padStart(2, '0');
  }

  function handleScoreboardClick(playerId, playerName) {
    var me = ownPlayer();
    if (!me || me.eliminated) { return; }
    if (isFriendly(playerId)) {
      sendAction('breakAlliance', {}).catch(function () {});
      toast('已退出与 ' + playerName + ' 的结盟');
    } else {
      sendAction('proposeAlliance', { playerId: playerId }).catch(function () {});
      toast('已向 ' + playerName + ' 发起结盟提议');
    }
  }

  function showAllianceProposal(fromId, fromName) {
    var stack = $('#toastStack');
    if (!stack) { return; }
    dismissAllianceProposal();
    var item = document.createElement('div');
    item.className = 'toast alliance-toast';
    item.id = 'alliance-proposal-toast';
    item.innerHTML =
      '<span>' + htmlEscape(fromName) + ' 邀请你结盟</span>' +
      '<div class="alliance-actions">' +
      '<button class="alliance-accept">接受 (Y)</button>' +
      '<button class="alliance-reject">拒绝 (N)</button>' +
      '</div>';
    item.querySelector('.alliance-accept').addEventListener('click', function () {
      sendAction('acceptAlliance', {}).catch(function () {});
      item.remove();
      activeProposalFromId = null;
    });
    item.querySelector('.alliance-reject').addEventListener('click', function () {
      sendAction('rejectAlliance', {}).catch(function () {});
      item.remove();
      activeProposalFromId = null;
    });
    stack.appendChild(item);
  }

  function dismissAllianceProposal() {
    var existing = document.getElementById('alliance-proposal-toast');
    if (existing) { existing.remove(); }
  }

  function hasStructure(kind) {
    return !!(roomState && roomState.game && roomState.game.structures.some(function (s) {
      return s.owner === session.playerId && s.kind === kind && s.active && s.hp > 0;
    }));
  }

  function activateBuildMode(kind, automatic) {
    buildMode = kind;
    commandMode = null;
    canvas.classList.add('command-mode');
    buildCursorLabel.classList.remove('hidden');
    buildCursorLabel.textContent = '部署：' + (BUILDINGS[kind] || {}).name + ' · 右键取消';
    if (!automatic) {
      toast('建筑已就绪，请在基地控制区内选择位置');
    }
    sound('select');
  }

  function syncPreparedBuilding() {
    var me = ownPlayer();
    var item = me && me.buildQueue && me.buildQueue[0];
    if (!item) {
      lastReadyBuildId = null;
      return;
    }
    if (item.ready && item.id !== lastReadyBuildId) {
      lastReadyBuildId = item.id;
      activateBuildMode(item.kind, true);
      toast(((BUILDINGS[item.kind] || {}).name || item.kind) + ' 已生产完成，等待部署', 'success');
      sound('complete');
    }
  }

  function handleBuildingCard(kind, event) {
    var me = ownPlayer();
    if (!me) {
      return;
    }
    var item = me.buildQueue && me.buildQueue[0];
    if (event && event.shiftKey && item) {
      sendAction('command', { command: 'cancelBuild' }).then(function () {
        cancelModes();
        toast('已取消建筑生产，资金已返还');
        sound('confirm');
      }).catch(function () {});
      return;
    }
    if (item) {
      if (item.kind === kind && item.ready) {
        activateBuildMode(kind, false);
      } else {
        toast(item.ready ? '请先部署已完成的建筑' :
          ((BUILDINGS[item.kind] || {}).name || item.kind) + ' 还需 ' + Math.ceil(item.remaining) + ' 秒');
      }
      return;
    }
    sendAction('command', { command: 'prepareBuild', structureType: kind }).then(function () {
      toast(((BUILDINGS[kind] || {}).name || kind) + ' 开始生产');
      sound('confirm');
    }).catch(function () {});
  }

  /** 撤销生产：建筑走 cancelBuild，单位走 cancelTrain，服务端负责退款。 */
  function cancelProduction(kind, isBuilding) {
    var label = (isBuilding ? BUILDINGS[kind] : UNITS[kind]);
    var name = label ? label.name : kind;
    if (isBuilding) {
      var me = ownPlayer();
      var queue = (me && me.buildQueue) || [];
      if (!queue.length || queue[0].kind !== kind) {
        toast('该建筑没有在生产');
        return;
      }
      sendAction('command', { command: 'cancelBuild' }).then(function () {
        // 取消已经造好待放置的建筑时，顺手退出放置模式
        if (buildMode === kind) { cancelModes(); }
        toast('已取消 ' + name + '，资金已退回', 'success');
        sound('cancel');
      }).catch(function () {});
      return;
    }
    sendAction('command', { command: 'cancelTrain', unitType: kind }).then(function () {
      toast('已取消 ' + name + '，资金已退回', 'success');
      sound('cancel');
    }).catch(function () {});
  }

  function renderCommandGrid(force) {
    if (!roomState || !roomState.game || currentScreen !== 'game') {
      return;
    }
    var me = ownPlayer();
    if (!me) {
      return;
    }
    var myFaction = (me && me.faction) || 'tech';
    // 阵营过滤：科技/魔法各看各的建造树；缺 faction 字段的按科技处理
    var sameFaction = function (entry) { return (entry.faction || 'tech') === myFaction; };
    var definitions;
    if (activeTab === 'buildings') {
      definitions = {};
      Object.keys(BUILDINGS).forEach(function (key) {
        if (BUILDINGS[key].role === 'hq') { return; }
        if (sameFaction(BUILDINGS[key])) { definitions[key] = BUILDINGS[key]; }
      });
    } else if (activeTab === 'infantry') {
      // 步兵页 = 兵营/奥术圣殿出的单位
      definitions = {};
      Object.keys(UNITS).forEach(function (key) {
        var u = UNITS[key];
        if ((u.producer === 'barracks' || u.producer === 'mtemple') && sameFaction(u)) { definitions[key] = u; }
      });
    } else {
      // 载具页 = 工厂/召唤法阵出的单位
      definitions = {};
      Object.keys(UNITS).forEach(function (key) {
        var u = UNITS[key];
        if ((u.producer === 'factory' || u.producer === 'mcircle') && sameFaction(u)) { definitions[key] = u; }
      });
    }
    var gridKey = String(gameKey) + ':' + activeTab;
    if (force || commandGrid.dataset.key !== gridKey) {
      commandGrid.dataset.key = gridKey;
      commandGrid.innerHTML = '';
      Object.keys(definitions).forEach(function (kind) {
        var definition = definitions[kind];
        var isBuilding = activeTab === 'buildings';
        var button = document.createElement('button');
        button.className = 'command-card';
        button.dataset.kind = kind;
        button.dataset.type = isBuilding ? 'building' : 'unit';
        // DOM 结构是与样式层的跨线契约（DESIGN_V3 第 1 条），顺序不可调
        button.innerHTML =
          '<canvas class="command-portrait" width="96" height="72"></canvas>' +
          '<span class="command-progress"></span>' +
          '<strong class="command-name">' + definition.name + '</strong>' +
          '<small class="command-status"></small>';
        // 肖像位图是共享缓存，这里只 blit 一份进卡片自己的画布
        var portraitCanvas = button.querySelector('.command-portrait');
        portraitCanvas.getContext('2d').drawImage(portraitFor(kind, isBuilding), 0, 0);
        button.addEventListener('click', function (event) {
          ensureAudio();
          if (isBuilding) {
            handleBuildingCard(kind, event);
          } else {
            sendAction('command', { command: 'train', unitType: kind }).then(function () {
              sound('confirm');
            }).catch(function () {});
          }
        });
        // 右键撤销：建筑撤掉建造队列，单位从生产队列末尾撤一个，都全额退款
        button.addEventListener('contextmenu', function (event) {
          event.preventDefault();
          ensureAudio();
          cancelProduction(kind, isBuilding);
        });
        commandGrid.appendChild(button);
      });
    }

    Array.prototype.forEach.call(commandGrid.querySelectorAll('.command-card'), function (button) {
      var kind = button.dataset.kind;
      var definition = button.dataset.type === 'building' ? BUILDINGS[kind] : UNITS[kind];
      var isBuilding = button.dataset.type === 'building';
      var requirementsMet = isBuilding
        ? definition.requires.every(hasStructure)
        : hasStructure(definition.producer) && (definition.requires || []).every(hasStructure);
      var status = button.querySelector('.command-status');
      var progress = 0;
      var queued = 0;
      button.classList.remove('queued', 'ready');

      if (isBuilding) {
        var buildItem = me.buildQueue && me.buildQueue[0];
        var isCurrent = buildItem && buildItem.kind === kind;
        if (isCurrent) {
          queued = 1;
          progress = buildItem.ready ? 1 : 1 - buildItem.remaining / Math.max(0.01, buildItem.total);
          button.classList.add('queued');
          button.classList.toggle('ready', !!buildItem.ready);
          status.textContent = buildItem.ready ? '点击部署' : Math.ceil(buildItem.remaining) + ' 秒';
          button.disabled = !!me.eliminated;
          button.title = definition.desc + ' · Shift+点击取消';
        } else {
          var queueBusy = !!buildItem;
          status.textContent = queueBusy ? '队列占用' : '◆ ' + definition.cost.toLocaleString('zh-CN');
          button.disabled = queueBusy || !requirementsMet || me.cash < definition.cost || me.eliminated;
          button.title = definition.desc + ' · 生产 ' + definition.build + ' 秒';
        }
      } else {
        var queuedItems = [];
        roomState.game.structures.forEach(function (structure) {
          if (structure.owner === me.id) {
            structure.queue.forEach(function (item) {
              if (item.kind === kind) { queuedItems.push(item); }
            });
          }
        });
        queued = queuedItems.length;
        if (queued) {
          progress = 1 - queuedItems[0].remaining / Math.max(0.01, queuedItems[0].total);
          button.classList.add('queued');
          status.textContent = Math.ceil(queuedItems[0].remaining) + ' 秒';
        } else {
          status.textContent = '◆ ' + definition.cost.toLocaleString('zh-CN');
        }
        button.disabled = !requirementsMet || me.cash < definition.cost || me.eliminated;
        button.title = definition.desc;
      }
      button.style.setProperty('--progress', Math.max(0, Math.min(1, progress)) * 360 + 'deg');
      if (queued) {
        button.setAttribute('data-queue', String(queued));
      } else {
        button.removeAttribute('data-queue');
      }
    });
  }

  function renderSelectionInfo() {
    if (!roomState || !roomState.game) {
      return;
    }
    if (selectionInfo.matches(':hover')) {
      return;
    }
    var units = roomState.game.units.filter(function (unit) { return selectedUnits.has(unit.id); });
    var deployBtn = $('#deployBtn');
    if (deployBtn) {
      var hasMcv = units.some(function (u) { return unitRole(u.kind) === 'mcv' && u.owner === session.playerId; });
      deployBtn.classList.toggle('hidden', !hasMcv);
    }
    if (units.length) {
      var totalHp = units.reduce(function (sum, unit) { return sum + unit.hp; }, 0);
      var totalMax = units.reduce(function (sum, unit) { return sum + unit.maxHp; }, 0);
      var one = units.length === 1 ? units[0] : null;
      var label = one ? ((UNITS[one.kind] || {}).name || one.kind) : units.length + ' 个作战单位';
      var rank = one ? unitRank(one.kills || 0) : 0;
      var rankLabels = ['', ' ★ 老兵', ' ★★ 精英', ' ★★★ 王牌'];
      var detail = one && one.repairing ?
        '维修中 · 生命 ' + Math.ceil(one.hp) + ' / ' + Math.ceil(one.maxHp) :
        (one && unitRole(one.kind) === 'harvester' ?
        '载矿 ' + Math.floor(one.cargo) + ' / ' + Math.floor(one.capacity) :
        (one ? '生命 ' + Math.ceil(one.hp) + ' / ' + Math.ceil(one.maxHp) + rankLabels[rank] : '混合编队'));
      // 混编时用主导兵种的肖像打底，右下角标注编队规模
      var kindCounts = {};
      var domKind = units[0].kind;
      units.forEach(function (unit) {
        kindCounts[unit.kind] = (kindCounts[unit.kind] || 0) + 1;
        if (kindCounts[unit.kind] > kindCounts[domKind]) { domKind = unit.kind; }
      });
      var unitInfoKey = 'u|' + units.map(function (unit) {
        return unit.id + ':' + Math.ceil(unit.hp) + ':' + Math.floor(unit.cargo || 0) + ':' +
          (unit.kills || 0) + ':' + (unit.repairing ? 1 : 0);
      }).join(',');
      if (selectionInfo.dataset.key === unitInfoKey) { return; }
      selectionInfo.dataset.key = unitInfoKey;
      selectionInfo.innerHTML =
        '<div class="selected-summary">' +
        '<div class="selected-portrait"></div>' +
        '<div><strong>' + label + '</strong><small>' + detail + '</small>' +
        '<div class="health-track"><i style="width:' + Math.max(0, totalHp / totalMax * 100) + '%"></i></div></div>' +
        '<small>' + units.length + ' UNIT</small></div>';
      selectionInfo.querySelector('.selected-portrait')
        .appendChild(makePortraitCanvas(domKind, false, units.length > 1 ? units.length : 0));
      return;
    }
    var structure = roomState.game.structures.find(function (item) { return item.id === selectedStructureId; });
    if (structure) {
      var activeText = structure.active ? '运转正常' : '建造中 ' + Math.floor((1 - structure.buildRemaining / Math.max(0.01, structure.buildTotal)) * 100) + '%';
      if (structure.owner === 'neutral') {
        activeText = '中立矿区守卫 · 清除全部守军后解锁矿脉';
      }
      if (structure.queue.length) {
        activeText = '生产 ' + ((UNITS[structure.queue[0].kind] || {}).name || structure.queue[0].kind) + ' · ' +
          Math.floor((1 - structure.queue[0].remaining / structure.queue[0].total) * 100) + '%';
      } else if (structure.active && structureRole(structure.kind) === 'repair') {
        activeText = isOwnMagicFaction() ?
          '圣泉待命 · 右键派遣构装' : '维修系统待命 · 右键派遣载具';
      }
      var sell = structure.owner === session.playerId && structureRole(structure.kind) !== 'hq' ?
        '<button class="sell-button" id="sellSelectedBtn">出售</button>' : '<span></span>';
      var packBtn = structure.owner === session.playerId && structureRole(structure.kind) === 'hq' && structure.packable ?
        '<button class="sell-button" id="packSelectedBtn" style="color:#6dd897;border-color:rgba(109,216,151,.4)">折叠</button>' : '';
      var structureInfoKey = 's|' + structure.id + ':' + Math.ceil(structure.hp) + ':' +
        activeText + ':' + (structure.packable ? 1 : 0);
      if (selectionInfo.dataset.key === structureInfoKey) { return; }
      selectionInfo.dataset.key = structureInfoKey;
      selectionInfo.innerHTML =
        '<div class="selected-summary"><div class="selected-portrait"></div>' +
        '<div><strong>' + (STRUCTURE_NAMES[structure.kind] || structure.kind) + '</strong><small>' + activeText + '</small>' +
        '<div class="health-track"><i style="width:' + Math.max(0, structure.hp / structure.maxHp * 100) + '%"></i></div></div>' +
        packBtn + sell + '</div>';
      selectionInfo.querySelector('.selected-portrait')
        .appendChild(makePortraitCanvas(structure.kind, true, 0));
      var sellButton = $('#sellSelectedBtn');
      if (sellButton) {
        sellButton.addEventListener('click', function () {
          sendAction('command', { command: 'sell', structureId: structure.id }).then(function () {
            selectedStructureId = null;
            sound('confirm');
          }).catch(function () {});
        });
      }
      var packButton = $('#packSelectedBtn');
      if (packButton) {
        packButton.addEventListener('click', function () {
          sendAction('command', { command: 'undeploy', structureId: structure.id }).then(function () {
            selectedStructureId = null;
            renderSelectionInfo();
            toast(factionCopy().hq + '已折叠为' + factionCopy().mcv, 'success');
            sound('confirm');
          }).catch(function (err) {
            toast(err.message || '折叠失败', 'error');
          });
        });
      }
      return;
    }
    if (selectionInfo.dataset.key === 'empty') { return; }
    selectionInfo.dataset.key = 'empty';
    selectionInfo.innerHTML =
      '<div class="selection-empty"><span class="selection-reticle">⌖</span>' +
      '<strong>未选择作战单位</strong><small>左键单选或拖拽框选</small></div>';
  }

  function pruneSelection() {
    if (!roomState || !roomState.game) {
      return;
    }
    var liveIds = new Set(roomState.game.units.map(function (u) { return u.id; }));
    selectedUnits.forEach(function (id) {
      if (!liveIds.has(id)) {
        selectedUnits.delete(id);
      }
    });
    if (selectedStructureId && !roomState.game.structures.some(function (s) { return s.id === selectedStructureId; })) {
      selectedStructureId = null;
    }
  }

  // 本帧新出现的特效，交给 3D 层生成粒子后清空
  var pendingEffects = [];
  var hqSalute = null;

  function processEffects() {
    if (!roomState || !roomState.game) {
      return;
    }
    var playExplosion = false;
    var playComplete = false;
    var playPromote = false;
    var playSalute = false;
    roomState.game.effects.forEach(function (effect) {
      if (seenEffects.has(effect.id)) {
        return;
      }
      seenEffects.add(effect.id);
      // 粒子交给 3D 层生成，这里只负责去重和音效
      pendingEffects.push(effect);
      if (effect.type === 'explosion') {
        playExplosion = true;
      } else if (effect.type === 'complete') {
        playComplete = true;
      } else if (effect.type === 'promote') {
        playPromote = true;
      } else if (effect.type === 'hq_salute') {
        playSalute = true;
        hqSalute = { x: effect.x, y: effect.y, until: performance.now() + 2400 };
      }
    });
    if (playExplosion) {
      sound('explosion');
    }
    if (playComplete) {
      sound('complete');
    }
    if (playPromote) {
      sound('promote');
    }
    if (playSalute) {
      sound('confirm');
    }
    if (seenEffects.size > 1200) {
      seenEffects.clear();
      roomState.game.effects.forEach(function (effect) {
        seenEffects.add(effect.id);
      });
    }
  }

  function resizeCanvas() {
    if (currentScreen !== 'game') {
      return;
    }
    var rect = canvas.getBoundingClientRect();
    dpr = Math.min(1, window.devicePixelRatio || 1) * renderScale;
    viewWidth = Math.max(1, rect.width);
    viewHeight = Math.max(1, rect.height);
    if (viewWidth === lastViewWidth && viewHeight === lastViewHeight && dpr === lastDpr) {
      return;
    }
    lastViewWidth = viewWidth;
    lastViewHeight = viewHeight;
    lastDpr = dpr;
    var width = Math.round(viewWidth * dpr);
    var height = Math.round(viewHeight * dpr);
    if (hudCanvas.width !== width || hudCanvas.height !== height) {
      hudCanvas.width = width;
      hudCanvas.height = height;
    }
    view3d.resize(viewWidth, viewHeight, dpr);
  }

  // 3D 下这两个换算不再是简单的线性变换：屏幕坐标要投射到地面平面上，
  // 世界坐标要经过投影矩阵。统一交给渲染层。
  function worldToScreen(x, y) {
    return view3d.worldToScreen(x, y, 0);
  }

  function screenToWorld(x, y) {
    return view3d.screenToWorld(x, y);
  }

  function updatePointerWorld() {
    var world = screenToWorld(pointer.x, pointer.y);
    pointer.worldX = world.x;
    pointer.worldY = world.y;
  }

  var homeBgCanvas = null;
  var homeBgCtx = null;
  // 重设 canvas.width 会清空画布并重置全部上下文状态，以前每帧都做等于
  // 白白多付一次全屏重建的代价——尺寸缓存下来，窗口真的变了才赋值
  var homeBgW = 0;
  var homeBgH = 0;
  var homeBaseLayer = null;   // 静态底：黑绿渐变 + 地平线微光 + 暗角
  var homeEdgeLayer = null;   // 红色警报边缘光：预渲染，每帧只调 globalAlpha

  function rebuildHomeLayers(w, h) {
    homeBaseLayer = document.createElement('canvas');
    homeBaseLayer.width = w;
    homeBaseLayer.height = h;
    var c = homeBaseLayer.getContext('2d');
    var g = c.createLinearGradient(0, 0, 0, h);
    g.addColorStop(0, '#0a0a06');
    g.addColorStop(0.55, '#15170f');
    g.addColorStop(1, '#0a0a06');
    c.fillStyle = g;
    c.fillRect(0, 0, w, h);
    // 地平线上一点冷灰绿，避免画面沉成纯黑
    var hz = c.createRadialGradient(w * 0.5, h * 0.78, 10, w * 0.5, h * 0.78, w * 0.7);
    hz.addColorStop(0, 'rgba(42,45,32,.5)');
    hz.addColorStop(1, 'rgba(42,45,32,0)');
    c.fillStyle = hz;
    c.fillRect(0, 0, w, h);
    var vg = c.createRadialGradient(w / 2, h / 2, Math.min(w, h) * 0.35, w / 2, h / 2, Math.hypot(w, h) * 0.6);
    vg.addColorStop(0, 'rgba(10,10,6,0)');
    vg.addColorStop(1, 'rgba(10,10,6,.55)');
    c.fillStyle = vg;
    c.fillRect(0, 0, w, h);

    homeEdgeLayer = document.createElement('canvas');
    homeEdgeLayer.width = w;
    homeEdgeLayer.height = h;
    var e = homeEdgeLayer.getContext('2d');
    var depth = Math.max(70, Math.min(w, h) * 0.14);
    var edges = [
      [0, 0, 0, depth, 0, 0, w, depth],
      [0, h, 0, h - depth, 0, h - depth, w, depth],
      [0, 0, depth, 0, 0, 0, depth, h],
      [w, 0, w - depth, 0, w - depth, 0, depth, h]
    ];
    for (var i = 0; i < edges.length; i++) {
      var ed = edges[i];
      var eg = e.createLinearGradient(ed[0], ed[1], ed[2], ed[3]);
      eg.addColorStop(0, 'rgba(200,36,30,.42)');
      eg.addColorStop(1, 'rgba(200,36,30,0)');
      e.fillStyle = eg;
      e.fillRect(ed[4], ed[5], ed[6], ed[7]);
    }
  }

  // 大团烟雾：径向渐变一次画一团，颜色带透明度直接淡出到底色
  function drawSmokeBlob(c, x, y, r, color) {
    var g = c.createRadialGradient(x, y, r * 0.05, x, y, r);
    g.addColorStop(0, color);
    g.addColorStop(1, 'rgba(10,10,6,0)');
    c.fillStyle = g;
    c.fillRect(x - r, y - r, r * 2, r * 2);
  }

  // 探照光束：底部亮、尖端透明的细长梯形，angle 以竖直向上为 0
  function drawSearchBeam(c, x, y, angle, len, color) {
    var half = len * 0.085;
    c.save();
    c.translate(x, y);
    c.rotate(angle);
    var g = c.createLinearGradient(0, 0, 0, -len);
    g.addColorStop(0, color);
    g.addColorStop(1, 'rgba(243,233,212,0)');
    c.fillStyle = g;
    c.beginPath();
    c.moveTo(-6, 0);
    c.lineTo(6, 0);
    c.lineTo(half, -len);
    c.lineTo(-half, -len);
    c.closePath();
    c.fill();
    c.restore();
  }

  function drawHomeBackground(timestamp) {
    if (!homeBgCanvas) {
      homeBgCanvas = document.getElementById('homeBg');
      if (!homeBgCanvas) return;
      homeBgCtx = homeBgCanvas.getContext('2d');
    }
    var w = window.innerWidth;
    var h = window.innerHeight;
    if (w !== homeBgW || h !== homeBgH) {
      homeBgW = w;
      homeBgH = h;
      homeBgCanvas.width = w;
      homeBgCanvas.height = h;
      rebuildHomeLayers(w, h);
    }
    var c = homeBgCtx;
    // 10 秒无缝循环：所有周期项都用 ph 的整数倍频率，跨过循环点不会跳变
    var LOOP = 10;
    var tl = (timestamp * 0.001) % LOOP;
    var ph = tl / LOOP * Math.PI * 2;
    var big = Math.max(w, h);
    c.drawImage(homeBaseLayer, 0, 0);

    // 烟雾层：三团深红/灰绿的大渐变团按不同倍频漂移，形成远近层次
    drawSmokeBlob(c, w * (0.24 + 0.05 * Math.sin(ph)), h * (0.30 + 0.04 * Math.cos(ph * 2)), big * 0.42, 'rgba(74,16,19,.34)');
    drawSmokeBlob(c, w * (0.78 + 0.06 * Math.sin(ph * 2 + 2.1)), h * (0.62 + 0.05 * Math.sin(ph + 4.2)), big * 0.5, 'rgba(58,13,16,.4)');
    drawSmokeBlob(c, w * (0.5 + 0.08 * Math.sin(ph * 3 + 1.2)), h * (0.85 + 0.03 * Math.cos(ph)), big * 0.36, 'rgba(42,45,32,.5)');

    // 探照光束：来回摆动（sin 本身跨循环连续），一左一右错开相位
    drawSearchBeam(c, w * 0.16, h + 60, -0.42 + 0.38 * Math.sin(ph), h * 1.5, 'rgba(243,233,212,.055)');
    drawSearchBeam(c, w * 0.86, h + 60, 0.46 + 0.3 * Math.sin(ph * 2 + 2.6), h * 1.4, 'rgba(243,233,212,.04)');

    // 屏幕边缘红色警报呼吸：只调预渲染层的透明度，代价近乎为零
    c.globalAlpha = 0.35 + 0.3 * (0.5 + 0.5 * Math.sin(ph * 3));
    c.drawImage(homeEdgeLayer, 0, 0);
    c.globalAlpha = 1;

    // 上升余烬：确定性伪随机（cellHash），同一颗粒子每圈走同一条路，
    // 淡入淡出用 sin(pπ) 保证在循环两端都是 0，不会闪现
    for (var i = 0; i < 42; i++) {
      var seed = cellHash(i, 101);
      var seed2 = cellHash(i, 202);
      var p = (tl / LOOP + seed) % 1;
      var ex = seed2 * w + Math.sin(ph * 2 + i * 1.7) * 16;
      var ey = h * (1.04 - 1.1 * p);
      var sz = 0.8 + seed * 1.7;
      c.globalAlpha = Math.sin(p * Math.PI) * (0.3 + 0.5 * seed2);
      c.fillStyle = i % 3 === 0 ? '#ffd23e' : '#e8a13a';
      c.fillRect(ex, ey, sz, sz);
    }
    c.globalAlpha = 1;
  }

  function clampCamera() {
    if (!roomState || !roomState.game) {
      return;
    }
    // 3D 下相机盯着一个地面焦点，把焦点限制在地图内即可（留一点余量，
    // 让玩家能把边角推到屏幕中间）。
    var map = roomState.game.map;
    var margin = 240;
    camera.x = Math.max(-margin, Math.min(map.width + margin, camera.x));
    camera.y = Math.max(-margin, Math.min(map.height + margin, camera.y));
  }

  function frame(timestamp) {
    var dt = Math.min(0.05, Math.max(0.001, (timestamp - lastFrame) / 1000));
    lastFrame = timestamp;

    // FPS 统计：滚动 0.5 秒窗口取均值
    fpsHistory.push(timestamp);
    while (fpsHistory.length > 1 && fpsHistory[fpsHistory.length - 1] - fpsHistory[0] > 500) {
      fpsHistory.shift();
    }
    if (timestamp - fpsLastSample > 200) {
      fpsLastSample = timestamp;
      if (!fpsElement) { fpsElement = $('#fpsMeter'); }
      var fps = fpsHistory.length > 1
        ? Math.round((fpsHistory.length - 1) / ((fpsHistory[fpsHistory.length - 1] - fpsHistory[0]) / 1000))
        : 0;
      if (currentScreen === 'game' && !document.hidden &&
          timestamp - adaptiveStartedAt > 2000) {
        // 60FPS 的预算只有 16.7ms，等掉到 43FPS 再处理已经太迟。连续约
        // 0.6 秒低于 56 就降一级；严重掉帧会加速降档。恢复则要求约 12 秒
        // 接近满帧，避免复杂战场中分辨率来回震荡。
        if (fps > 0 && fps < 56) {
          lowFpsSamples += fps < 48 ? 2 : 1;
          highFpsSamples = 0;
        } else if (fps >= 59) {
          highFpsSamples++;
          lowFpsSamples = 0;
        } else {
          lowFpsSamples = Math.max(0, lowFpsSamples - 1);
          highFpsSamples = Math.max(0, highFpsSamples - 1);
        }
        if (lowFpsSamples >= 3) {
          for (var down = 1; down < renderScaleSteps.length; down++) {
            if (renderScale > renderScaleSteps[down] + 0.001) {
              renderScale = renderScaleSteps[down];
              lastDpr = -1;
              break;
            }
          }
          lowFpsSamples = 0;
        } else if (highFpsSamples >= 60 && renderScale < 1) {
          for (var up = renderScaleSteps.length - 2; up >= 0; up--) {
            if (renderScale < renderScaleSteps[up] - 0.001) {
              renderScale = renderScaleSteps[up];
              lastDpr = -1;
              break;
            }
          }
          highFpsSamples = 0;
        }
      }
      var color = fps >= 55 ? '#7dd85f' : fps >= 30 ? '#f0b83c' : '#e04a3a';
      fpsElement.innerHTML = fps + ' <small style="color:' + color + '">FPS</small>' +
        (renderScale < 1 ? ' <small>· ' + Math.round(renderScale * 100) + '%</small>' : '');
      var perfStats = view3d.stats();
      fpsElement.title = '画面单位 ' + perfStats.renderedUnits + ' / ' + perfStats.snapshotUnits +
        '，绘制调用 ' + perfStats.drawCalls;
      fpsElement.style.display = currentScreen === 'game' ? '' : 'none';
    }

    if (currentScreen === 'game' && roomState && roomState.game) {
      resizeCanvas();
      updateCamera(dt);
      drawGame(dt, timestamp);
      var me = ownPlayer();
      if (me) {
        var targetCash = Math.floor(me.cash);
        displayedCash += (targetCash - displayedCash) * Math.min(1, dt * 8);
        if (Math.abs(targetCash - displayedCash) < 0.5) displayedCash = targetCash;
        // 上次写入 DOM 的整数值记在变量里做比较，不再用正则把文本解析回数字
        var shownCash = Math.floor(displayedCash);
        if (shownCash !== lastPaintedCash) {
          lastPaintedCash = shownCash;
          if (!cashValueEl) { cashValueEl = $('#cashValue'); }
          cashValueEl.textContent = '$ ' + shownCash.toLocaleString('zh-CN');
        }
      }
      if (timestamp - lastMinimapDraw >= 100) {
        lastMinimapDraw = timestamp;
        drawMinimap();
      }
      if (performance.now() - lastSnapshotAt > 2500) {
        setConnectionState(false);
      }
    } else if (currentScreen === 'home') {
      drawHomeBackground(timestamp);
    }
    requestAnimationFrame(frame);
  }

  function updateCamera(dt) {
    var speed = 600 / camera.zoom;
    var dx = 0;
    var dy = 0;
    if (pressedKeys.has('KeyW') || pressedKeys.has('ArrowUp')) { dy -= 1; }
    if (pressedKeys.has('KeyS') || pressedKeys.has('ArrowDown')) { dy += 1; }
    if (pressedKeys.has('KeyA') || pressedKeys.has('ArrowLeft')) { dx -= 1; }
    if (pressedKeys.has('KeyD') || pressedKeys.has('ArrowRight')) { dx += 1; }
    if (pointer.inside && !dragging) {
      if (pointer.x < 10) { dx -= 1; }
      if (pointer.x > viewWidth - 10) { dx += 1; }
      if (pointer.y < 10) { dy -= 1; }
      if (pointer.y > viewHeight - 10) { dy += 1; }
    }
    if (dx && dy) {
      dx *= 0.707;
      dy *= 0.707;
    }

    // 旋转视角：[ / ] 或按住中键拖动
    if (pressedKeys.has('BracketLeft')) { camera.yaw -= dt * 1.5; }
    if (pressedKeys.has('BracketRight')) { camera.yaw += dt * 1.5; }
    // 调整俯角：PageUp / PageDown
    if (pressedKeys.has('PageUp')) { camera.pitch = Math.min(1.45, camera.pitch + dt); }
    if (pressedKeys.has('PageDown')) { camera.pitch = Math.max(0.42, camera.pitch - dt); }

    // 平移方向要跟着视角转，否则旋转后 WASD 会「反向」
    var cos = Math.cos(camera.yaw);
    var sin = Math.sin(camera.yaw);
    camera.x += (dx * cos + dy * sin) * speed * dt;
    camera.y += (dy * cos - dx * sin) * speed * dt;
    clampCamera();
    updatePointerWorld();
  }

  /* ------------------------------------------------------------------ *
   * 3D 渲染接线
   *
   * 战场本身全部交给 render3d.js。这里只留下：摄像机状态、HUD 叠加层
   * （血条 / 建造进度 / 载重），以及小地图 —— 这些用 2D 画布画更清晰、
   * 也比在 3D 里做广告牌便宜得多。
   * ------------------------------------------------------------------ */

  function visibleAt(x, y, padding) {
    var point = view3d.worldToScreen(x, y, 0);
    if (point.behind) { return false; }
    var pad = (padding || 0) * camera.zoom + 90;
    return point.x > -pad && point.x < viewWidth + pad &&
      point.y > -pad && point.y < viewHeight + pad;
  }

  function nearestBuildAnchor(x, y) {
    if (!roomState || !roomState.game) { return null; }
    var best = null;
    var bestDist = Infinity;
    roomState.game.structures.forEach(function (s) {
      var radius = BUILD_ANCHOR_RANGES[structureRole(s.kind)];
      if (!radius || !isFriendly(s.owner) || !s.active || s.hp <= 0) { return; }
      var dist = Math.hypot(s.x - x, s.y - y);
      if (dist < bestDist) {
        bestDist = dist;
        best = { x: s.x, y: s.y, radius: radius };
      }
    });
    return best;
  }

  function buildPreviewState() {
    if (!buildMode) { return null; }
    var definition = BUILDINGS[buildMode];
    if (!definition) { return null; }
    var anchor = nearestBuildAnchor(pointer.worldX, pointer.worldY);
    return {
      kind: buildMode,
      size: definition.size,
      x: pointer.worldX,
      y: pointer.worldY,
      valid: positionValidClient(buildMode, pointer.worldX, pointer.worldY),
      anchorX: anchor ? anchor.x : 0,
      anchorY: anchor ? anchor.y : 0,
      anchorRadius: anchor ? anchor.radius : 0
    };
  }

  function drawGame(dt, timestamp) {
    view3d.setCamera(camera);
    view3d.render({
      game: roomState.game,
      dt: dt,
      time: timestamp,
      selectedUnitIds: selectedUnits,
      selectedStructureId: selectedStructureId,
      buildPreview: buildPreviewState(),
      newEffects: pendingEffects,
      hqSalute: hqSalute
    });
    pendingEffects.length = 0;
    // 2D HUD 需要清整张透明画布，没必要和 3D 模型同频。维修/军衔图标与
    // 信标用 20Hz 更新仍然流畅，能显著减少高分辨率下的 Canvas 带宽。
    if (timestamp - lastHudOverlayAt >= 50) {
      lastHudOverlayAt = timestamp;
      drawHudOverlay(timestamp);
    }
  }

  /* -------------------- HUD 叠加层 -------------------- */

  function unitRank(kills) {
    if (kills >= 16) { return 3; }
    if (kills >= 8) { return 2; }
    if (kills >= 3) { return 1; }
    return 0;
  }

  // 保留给小地图用：把颜色往白提亮，让单位色点在深色草底上不丢失
  var lightenCache = {};
  function lightenColor(hex, amount) {
    var key = hex + '|' + amount;
    if (lightenCache[key]) { return lightenCache[key]; }
    if (!/^#[0-9a-fA-F]{6}$/.test(hex)) { lightenCache[key] = hex; return hex; }
    var num = parseInt(hex.slice(1), 16);
    var r = (num >> 16) & 255;
    var g = (num >> 8) & 255;
    var b = num & 255;
    r = Math.round(r + (255 - r) * amount);
    g = Math.round(g + (255 - g) * amount);
    b = Math.round(b + (255 - b) * amount);
    var result = 'rgb(' + r + ',' + g + ',' + b + ')';
    lightenCache[key] = result;
    return result;
  }

  function drawHudOverlay(timestamp) {
    hudCtx.setTransform(dpr, 0, 0, dpr, 0, 0);
    hudCtx.clearRect(0, 0, viewWidth, viewHeight);
    var game = roomState.game;

    // 血条已迁移到 GPU（render3d.js 的 updateBars），这里只画无法用实例化
    // 网格高效完成的少量图标：维修标记、老兵星标、地图信标。

    game.units.forEach(function (unit) {
      var rank = unitRank(unit.kills || 0);
      // 绝大多数普通单位没有任何 2D 标记。先跳过，避免大军团时为每个单位
      // 每帧做两次 3D→屏幕投影；模型与 GPU 血条仍由 render3d.js 正常绘制。
      if (!unit.repairing && rank === 0) { return; }
      var vis = view3d.visualPosition(unit.id) || unit;
      if (!visibleAt(vis.x, vis.y, unit.size)) { return; }
      var top = view3d.worldToScreen(vis.x, vis.y,
        (vis.groundY == null ? view3d.groundHeight(vis.x, vis.y) : vis.groundY)
          + unit.size * 1.9 + 12);
      if (top.behind) { return; }

      if (unit.repairing) {
        hudCtx.fillStyle = 'rgba(110, 240, 180, .95)';
        hudCtx.font = '11px Consolas, monospace';
        hudCtx.textAlign = 'center';
        hudCtx.fillText('✚', top.x, top.y - 4);
      }
      if (rank > 0) {
        var chevronY = top.y - (unit.repairing ? 12 : 6);
        var chevronColor = rank >= 3 ? '#ffcc00' : rank >= 2 ? '#ff9900' : '#ffd700';
        hudCtx.fillStyle = chevronColor;
        hudCtx.strokeStyle = 'rgba(0,0,0,0.6)';
        hudCtx.lineWidth = 1;
        hudCtx.font = (rank >= 2 ? 'bold ' : '') + '10px Consolas, monospace';
        hudCtx.textAlign = 'center';
        var chevronText = rank >= 3 ? '▲▲▲' : rank >= 2 ? '▲▲' : '▲';
        hudCtx.strokeText(chevronText, top.x, chevronY);
        hudCtx.fillText(chevronText, top.x, chevronY);
      }
    });

    // 地图信标
    (game.pings || []).forEach(function (ping) {
      var point = view3d.worldToScreen(ping.x, ping.y,
        view3d.groundHeight(ping.x, ping.y) + 10);
      if (point.behind) { return; }
      var pulse = (timestamp * 0.002) % 1;
      hudCtx.strokeStyle = ownerColor(ping.owner);
      hudCtx.lineWidth = 2;
      hudCtx.globalAlpha = 1 - pulse;
      hudCtx.beginPath();
      hudCtx.arc(point.x, point.y, 8 + pulse * 34, 0, Math.PI * 2);
      hudCtx.stroke();
      hudCtx.globalAlpha = 1;
    });
  }
  var playerColorById = {};
  var playerTeamById = {};
  var paletteStateKey = '';

  function isOwn(playerId) {
    return playerId === session.playerId;
  }

  function isFriendly(playerId) {
    if (playerId === session.playerId) { return true; }
    var myTeam = playerTeamById[session.playerId] || 0;
    var theirTeam = playerTeamById[playerId] || 0;
    return myTeam > 0 && myTeam === theirTeam;
  }

  function ownerColor(ownerId) {
    if (ownerId === 'neutral') { return '#c79545'; }
    return playerColorById[ownerId] || '#a5b1b1';
  }

  function positionValidClient(kind, x, y) {
    var definition = BUILDINGS[kind];
    if (!definition || !roomState || !roomState.game) {
      return false;
    }
    // 客户端也要挡住山体，否则预览显示可建、服务端却拒绝
    var mountains = (roomState.game.terrain && roomState.game.terrain.mountains) || [];
    for (var mi = 0; mi < mountains.length; mi++) {
      var m = mountains[mi];
      if (Math.hypot(m.x - x, m.y - y) < m.r + definition.size * 0.6) {
        return false;
      }
    }
    var map = roomState.game.map;
    if (x < definition.size + 12 || y < definition.size + 12 ||
        x > map.width - definition.size - 12 || y > map.height - definition.size - 12) {
      return false;
    }
    var nearOwn = roomState.game.structures.some(function (s) {
      var radius = BUILD_ANCHOR_RANGES[structureRole(s.kind)];
      return isFriendly(s.owner) && s.active && s.hp > 0 && radius &&
        Math.hypot(s.x - x, s.y - y) <= radius;
    });
    if (!nearOwn) {
      return false;
    }
    var collision = roomState.game.structures.some(function (s) {
      return s.hp > 0 && Math.hypot(s.x - x, s.y - y) < s.size + definition.size + 18;
    });
    if (collision) {
      return false;
    }
    var enemyZone = roomState.game.structures.some(function (s) {
      return !isFriendly(s.owner) && s.hp > 0 &&
        Math.hypot(s.x - x, s.y - y) < ENEMY_BUILD_EXCLUSION + s.size * 0.35;
    });
    if (enemyZone) {
      return false;
    }
    return !roomState.game.resources.some(function (r) {
      return r.amount > 0 && Math.hypot(r.x - x, r.y - y) < r.radius + definition.size + 16;
    });
  }
  var minimapStaticCanvas = document.createElement('canvas');
  var minimapStaticCtx = minimapStaticCanvas.getContext('2d');
  var minimapStaticKey = '';

  // 确定性哈希噪声：同一格永远同一个值，静态层重画多少次都不会“闪”
  function cellHash(ix, iy) {
    var n = (ix * 374761393 + iy * 668265263) >>> 0;
    n = ((n ^ (n >>> 13)) * 1274126177) >>> 0;
    return ((n ^ (n >>> 16)) >>> 0) / 4294967296;
  }

  // 草地基底：整张贴图缩到 200px 只剩噪点，改成基色 + 分块明暗微变化，
  // 缩略图上反而更有“航拍草原”的质感。小地图和大厅地图预览共用。
  function mapDisplayTheme(themeId) {
    return MAP_DISPLAY_THEMES[themeId] || MAP_DISPLAY_THEMES.grassland;
  }

  function paintGrassBase(c, w, h, themeId) {
    var swatch = mapDisplayTheme(themeId).minimap;
    c.fillStyle = swatch.base;
    c.fillRect(0, 0, w, h);
    var cell = 6;
    for (var iy = 0; iy * cell < h; iy++) {
      for (var ix = 0; ix * cell < w; ix++) {
        var v = cellHash(ix, iy);
        if (v > 0.94) {
          c.fillStyle = swatch.dry;
        } else if (v > 0.62) {
          c.fillStyle = swatch.light + ((v - 0.62) * 0.16).toFixed(3) + ')';
        } else if (v < 0.3) {
          c.fillStyle = swatch.dark + ((0.3 - v) * 0.3).toFixed(3) + ')';
        } else {
          continue;
        }
        c.fillRect(ix * cell, iy * cell, cell, cell);
      }
    }
  }

  // 按地形数据绘制山地/河流/桥梁；小地图静态层与大厅预览共用。
  // 道路只留玩法加成，不再画成贴在图上的线条。
  function paintTerrainFeatures(c, terrain, sx, sy) {
    if (!terrain) { return; }
    var rivers = terrain.rivers || [];
    var mountains = terrain.mountains || [];
    var bridges = terrain.bridges || [];
    var swatch = mapDisplayTheme(terrain.theme).minimap;
    var i;
    // 山地：灰色径向渐变外缘淡出到草色，再加放射棱脊笔触画出山体走向
    for (i = 0; i < mountains.length; i++) {
      var m = mountains[i];
      var mx = m.x * sx;
      var my = m.y * sy;
      var mr = Math.max(3, m.r * sx);
      var grad = c.createRadialGradient(mx, my, 1, mx, my, mr);
      grad.addColorStop(0, swatch.mountain);
      grad.addColorStop(0.65, 'rgba(59,63,46,.85)');
      grad.addColorStop(1, 'rgba(59,63,46,0)');
      c.fillStyle = grad;
      c.beginPath();
      c.arc(mx, my, mr, 0, Math.PI * 2);
      c.fill();
      c.lineWidth = 1;
      for (var k = 0; k < 6; k++) {
        var ang = (k / 6) * Math.PI * 2 + cellHash(i + 31, k) * 0.9;
        var len = mr * (0.55 + cellHash(k, i + 17) * 0.35);
        // 朝西北的棱脊受光、其余背光，圆丘立刻有了体积
        c.strokeStyle = (ang > Math.PI * 0.9 && ang < Math.PI * 1.6) ?
          'rgba(243,233,212,.30)' : 'rgba(10,10,6,.28)';
        c.beginPath();
        c.moveTo(mx, my);
        c.lineTo(mx + Math.cos(ang) * len, my + Math.sin(ang) * len);
        c.stroke();
      }
    }
    // 沟壑：干土外发光 → 深色底 → 亮土色芯，三遍各画完整条沟，
    // 分段折线的接头会被同一遍的圆头笔帽自然焊上
    if (rivers.length) {
      c.save();
      c.lineCap = 'round';
      c.lineJoin = 'round';
      var passes = [
        ['rgba(82,58,36,.35)', 6, 0],
        ['#33241a', 2.5, 0],
        ['#5b3f28', 0, 0.55]
      ];
      for (var p = 0; p < passes.length; p++) {
        c.strokeStyle = passes[p][0];
        for (i = 0; i < rivers.length; i++) {
          var rv = rivers[i];
          var base = rv.width * sx;
          c.lineWidth = passes[p][2] ? Math.max(1.4, base * passes[p][2]) : base + passes[p][1];
          c.beginPath();
          c.moveTo(rv.x1 * sx, rv.y1 * sy);
          c.lineTo(rv.x2 * sx, rv.y2 * sy);
          c.stroke();
        }
      }
      c.restore();
    }
    // 桥梁：亮木面 + 桥板细缝 + 描边，在沟壑上要一眼认出「这里能过」
    for (i = 0; i < bridges.length; i++) {
      var b = bridges[i];
      var bx = (b.x - b.w / 2) * sx;
      var by = (b.y - b.h / 2) * sy;
      var bw = Math.max(3, b.w * sx);
      var bh = Math.max(3, b.h * sy);
      c.fillStyle = '#8f7530';
      c.fillRect(bx, by, bw, bh);
      c.fillStyle = '#e6c87a';
      c.fillRect(bx, by, bw, 1);
      c.fillStyle = 'rgba(10,10,6,.35)';
      if (bw >= bh) {
        for (var px = bx + 3; px < bx + bw - 1; px += 3) { c.fillRect(px, by, 1, bh); }
      } else {
        for (var py = by + 3; py < by + bh - 1; py += 3) { c.fillRect(bx, py, bw, 1); }
      }
      c.strokeStyle = 'rgba(10,10,6,.5)';
      c.lineWidth = 1;
      c.strokeRect(bx + 0.5, by + 0.5, bw - 1, bh - 1);
    }
  }

  function buildMinimapStatic() {
    if (!roomState || !roomState.game) { return; }
    var map = roomState.game.map;
    var width = minimap.width;
    var height = minimap.height;
    // 缓存键要带上地形指纹：换地图但尺寸相同时，静态层必须重画
    var terrain = roomState.game.terrain || {};
    var key = 'v5_' + map.width + 'x' + map.height +
      '_' + (terrain.theme || '') +
      '_' + ((terrain.rivers || []).length) +
      '_' + ((terrain.mountains || []).length);
    if (minimapStaticKey === key && minimapStaticCanvas.width === width) { return; }
    minimapStaticCanvas.width = width;
    minimapStaticCanvas.height = height;
    var c = minimapStaticCtx;
    var sx = width / map.width;
    var sy = height / map.height;
    paintGrassBase(c, width, height, terrain.theme);
    paintTerrainFeatures(c, roomState.game.terrain, sx, sy);
    // 轻暗角 + 1px 内描边：把小地图“装进”金属框，边界不再发虚
    var vg = c.createRadialGradient(width / 2, height / 2, Math.min(width, height) * 0.45,
      width / 2, height / 2, Math.hypot(width, height) * 0.62);
    vg.addColorStop(0, 'rgba(10,10,6,0)');
    vg.addColorStop(1, 'rgba(10,10,6,.32)');
    c.fillStyle = vg;
    c.fillRect(0, 0, width, height);
    c.strokeStyle = 'rgba(10,10,6,.65)';
    c.lineWidth = 1;
    c.strokeRect(0.5, 0.5, width - 1, height - 1);
    minimapStaticKey = key;
  }

  function drawMinimap() {
    if (!roomState || !roomState.game) {
      return;
    }
    buildMinimapStatic();
    var map = roomState.game.map;
    var width = minimap.width;
    var height = minimap.height;
    var sx = width / map.width;
    var sy = height / map.height;
    miniCtx.drawImage(minimapStaticCanvas, 0, 0);
    // 矿脉：只有进入过己方/盟友视野的矿才登记到小地图；登记后永久保留，
    // 与“探开后不再重新变黑”的探索逻辑一致。采空后仍会自动消失。
    roomState.game.resources.forEach(function (resource, idx) {
      if (resource.amount <= 0) { return; }
      if (!discoveredResourceIds.has(resource.id)) {
        if (!view3d.isVisible(resource.x, resource.y)) { return; }
        discoveredResourceIds.add(resource.id);
      }
      var rx = resource.x * sx;
      var ry = resource.y * sy;
      // 大号光晕 — 亮琥珀色，缩略图上能一眼定位
      miniCtx.fillStyle = 'rgba(255,180,40,.28)';
      miniCtx.beginPath();
      miniCtx.arc(rx, ry, 7, 0, Math.PI * 2);
      miniCtx.fill();
      // 内圈更亮
      miniCtx.fillStyle = 'rgba(255,200,60,.22)';
      miniCtx.beginPath();
      miniCtx.arc(rx, ry, 4, 0, Math.PI * 2);
      miniCtx.fill();
      // 矿点核心：从原来的一个点变成 3x3 亮块
      miniCtx.fillStyle = '#ffcc44';
      for (var k = 0; k < 4; k++) {
        var ox = (cellHash(idx + 3, k) - 0.5) * 7;
        var oy = (cellHash(k, idx + 11) - 0.5) * 6;
        miniCtx.fillRect(rx + ox - 1.5, ry + oy - 1.5, 3, 3);
      }
      if (resource.public && resource.guarded) {
        miniCtx.strokeStyle = 'rgba(255,74,48,.95)';
        miniCtx.lineWidth = 1.5;
        miniCtx.beginPath();
        miniCtx.arc(rx, ry, 9, 0, Math.PI * 2);
        miniCtx.stroke();
      }
    });
    // 建筑：3-6px 队伍色方块 + 1px 黑描边（先铺大一号的黑块，代价最低）
    roomState.game.structures.forEach(function (structure) {
      var size = structureRole(structure.kind) === 'hq' ? 6 :
        (structure.size >= 52 ? 5 : (structure.size <= 32 ? 3 : 4));
      var px = structure.x * sx;
      var py = structure.y * sy;
      miniCtx.fillStyle = '#0a0a06';
      miniCtx.fillRect(px - size / 2 - 1, py - size / 2 - 1, size + 2, size + 2);
      miniCtx.fillStyle = ownerColor(structure.owner);
      miniCtx.fillRect(px - size / 2, py - size / 2, size, size);
    });
    // 单位：2.5px 亮点 + 黑描边，提亮一档让散兵在草色上不被吃掉
    roomState.game.units.forEach(function (unit) {
      var ux = unit.x * sx;
      var uy = unit.y * sy;
      miniCtx.fillStyle = '#0a0a06';
      miniCtx.fillRect(ux - 2.25, uy - 2.25, 4.5, 4.5);
      miniCtx.fillStyle = lightenColor(ownerColor(unit.owner), 0.22);
      miniCtx.fillRect(ux - 1.25, uy - 1.25, 2.5, 2.5);
    });
    // 补给箱：彩色脉冲光点
    var crates = roomState.game.crates || [];
    crates.forEach(function (crate) {
      var cx = crate.x * sx;
      var cy = crate.y * sy;
      var pulse = 1 + 0.4 * Math.sin(performance.now() * 0.006);
      miniCtx.fillStyle = crate.kind === 'cash' ? '#ffd700' :
        crate.kind === 'heal' ? '#7dff5f' : '#ff3b3b';
      miniCtx.beginPath();
      miniCtx.arc(cx, cy, 5.5 * pulse, 0, Math.PI * 2);
      miniCtx.fill();
      miniCtx.strokeStyle = 'rgba(10,10,6,.6)';
      miniCtx.lineWidth = 1;
      miniCtx.stroke();
    });
    var fog = view3d.getFogCanvas();
    if (fog) {
      miniCtx.save();
      miniCtx.globalAlpha = 0.72;
      miniCtx.drawImage(fog, 0, 0, width, height);
      miniCtx.restore();
      // 未探索区仍要能读出山脉、沟壑和桥梁，否则雷达就是一块黑盒子
      miniCtx.save();
      miniCtx.globalAlpha = 0.42;
      paintTerrainFeatures(miniCtx, roomState.game.terrain, sx, sy);
      miniCtx.restore();
    }
    var alertNow = performance.now();
    roomState.game.structures.forEach(function (s) {
      var until = structureAlertUntil[s.id];
      if (!until || alertNow > until || s.hp <= 0) return;
      var pulse = Math.sin(alertNow * 0.015) * 0.5 + 0.5;
      miniCtx.fillStyle = 'rgba(255,30,30,' + (0.3 + pulse * 0.5) + ')';
      miniCtx.beginPath();
      miniCtx.arc(s.x * sx, s.y * sy, 5 + pulse * 4, 0, Math.PI * 2);
      miniCtx.fill();
      miniCtx.strokeStyle = 'rgba(255,80,80,' + (0.7 + pulse * 0.3) + ')';
      miniCtx.lineWidth = 1.5;
      miniCtx.stroke();
    });
    roomState.game.pings.forEach(function (ping) {
      miniCtx.strokeStyle = ownerColor(ping.owner);
      miniCtx.beginPath();
      miniCtx.arc(ping.x * sx, ping.y * sy, 6 + ping.ttl, 0, Math.PI * 2);
      miniCtx.stroke();
    });
    // 透视相机下可视区是个梯形，把四个屏幕角投到地面上画出来
    var corners = [
      view3d.screenToWorld(0, 0),
      view3d.screenToWorld(viewWidth, 0),
      view3d.screenToWorld(viewWidth, viewHeight),
      view3d.screenToWorld(0, viewHeight)
    ];
    miniCtx.strokeStyle = 'rgba(255,255,255,.8)';
    miniCtx.lineWidth = 1.5;
    miniCtx.beginPath();
    corners.forEach(function (corner, index) {
      var px = corner.x * sx;
      var py = corner.y * sy;
      if (index === 0) { miniCtx.moveTo(px, py); } else { miniCtx.lineTo(px, py); }
    });
    miniCtx.closePath();
    miniCtx.stroke();
  }

  function entityAt(worldX, worldY) {
    if (!roomState || !roomState.game) {
      return null;
    }
    var best = null;
    var bestDistance = Infinity;
    roomState.game.units.forEach(function (unit) {
      var visual = view3d.visualPosition(unit.id) || unit;
      var dist = Math.hypot(visual.x - worldX, visual.y - worldY);
      var tolerance = unit.size + 8 / camera.zoom;
      if (dist <= tolerance && dist < bestDistance) {
        best = unit;
        bestDistance = dist;
      }
    });
    roomState.game.structures.forEach(function (structure) {
      var dx = Math.abs(structure.x - worldX);
      var dy = Math.abs(structure.y - worldY);
      if (dx <= structure.size && dy <= structure.size) {
        var dist = Math.hypot(dx, dy);
        if (!best || dist < bestDistance * 1.3) {
          best = structure;
          bestDistance = dist;
        }
      }
    });
    return best;
  }

  function updateSelectionBox() {
    if (!dragging) {
      return;
    }
    var left = Math.min(dragging.startX, pointer.x);
    var top = Math.min(dragging.startY, pointer.y);
    var width = Math.abs(pointer.x - dragging.startX);
    var height = Math.abs(pointer.y - dragging.startY);
    selectionBox.style.left = left + 'px';
    selectionBox.style.top = top + 'px';
    selectionBox.style.width = width + 'px';
    selectionBox.style.height = height + 'px';
    selectionBox.classList.toggle('hidden', width < 3 && height < 3);
  }

  function isAdditiveSelect(event) {
    return !!(event && (event.shiftKey || event.ctrlKey || event.metaKey));
  }

  function selectedUnitIdList() {
    // Copy at command time so a later selection change cannot rewrite an
    // in-flight move/stop payload.
    return Array.from(selectedUnits);
  }

  function selectAt(worldX, worldY, additive) {
    var entity = entityAt(worldX, worldY);
    if (!additive) {
      selectedUnits.clear();
      selectedStructureId = null;
    }
    if (!entity) {
      renderSelectionInfo();
      return;
    }
    if (entity.id.charAt(0) === 'u' && entity.owner === session.playerId) {
      if (additive && selectedUnits.has(entity.id)) {
        selectedUnits.delete(entity.id);
      } else {
        selectedUnits.add(entity.id);
      }
      selectedStructureId = null;
      sound('select');
    } else {
      selectedUnits.clear();
      selectedStructureId = entity.id;
      sound('select');
      if (session && entity.owner === session.playerId && structureRole(entity.kind) === 'hq') {
        sendAction('command', { command: 'tapHq', structureId: entity.id }).catch(function () {});
      }
    }
    renderSelectionInfo();
  }

  function selectAllOfType(worldX, worldY) {
    var entity = entityAt(worldX, worldY);
    if (!entity || entity.id.charAt(0) !== 'u' || entity.owner !== session.playerId) {
      return false;
    }
    var kind = entity.kind;
    selectedUnits.clear();
    selectedStructureId = null;
    roomState.game.units.forEach(function (unit) {
      if (unit.owner === session.playerId && unit.kind === kind) {
        selectedUnits.add(unit.id);
      }
    });
    sound('select');
    renderSelectionInfo();
    return true;
  }

  function selectBoxUnits(startX, startY, endX, endY, additive) {
    if (!additive) {
      selectedUnits.clear();
    }
    selectedStructureId = null;
    var left = Math.min(startX, endX);
    var right = Math.max(startX, endX);
    var top = Math.min(startY, endY);
    var bottom = Math.max(startY, endY);
    roomState.game.units.forEach(function (unit) {
      if (unit.owner !== session.playerId) {
        return;
      }
      var visual = view3d.visualPosition(unit.id) || unit;
      var screen = worldToScreen(visual.x, visual.y);
      if (screen.x >= left && screen.x <= right && screen.y >= top && screen.y <= bottom) {
        selectedUnits.add(unit.id);
      }
    });
    if (selectedUnits.size) {
      sound('select');
    }
    renderSelectionInfo();
  }

  async function placeCurrentBuilding() {
    if (!buildMode) {
      return;
    }
    var kind = buildMode;
    if (!positionValidClient(kind, pointer.worldX, pointer.worldY)) {
      toast('这里无法部署：只能依托已完成的核心建筑逐步扩张', 'error');
      sound('error');
      return;
    }
    try {
      await sendAction('command', {
        command: 'placeBuild',
        structureType: kind,
        x: pointer.worldX,
        y: pointer.worldY
      });
      cancelModes();
      lastReadyBuildId = null;
      toast(((BUILDINGS[kind] || {}).name || kind) + ' 已部署，施工阶段可被攻击', 'success');
      sound('confirm');
    } catch (_error) {}
  }

  function cancelModes() {
    buildMode = null;
    commandMode = null;
    canvas.classList.remove('command-mode');
    canvas.classList.remove('strike-mode');
    buildCursorLabel.classList.add('hidden');
    $('#attackMoveBtn').classList.remove('active');
    $('#pingBtn').classList.remove('active');
    $('#strikeBtn').classList.remove('active');
  }

  // 下达指令反馈（水波纹效果已移除，保留函数避免调用处报错）
  function markOrder(x, y, type) {}

  function issueGroundCommand(x, y, unitIds) {
    var ids = unitIds || selectedUnitIdList();
    if (!ids.length) {
      toast('请先选择部队');
      return;
    }
    var command = commandMode === 'attackMove' ? 'attackMove' : 'move';
    markOrder(x, y, command === 'attackMove' ? 'attack' : 'move');
    sendAction('command', {
      command: command,
      unitIds: ids,
      x: x,
      y: y
    }).then(function () { sound('move'); }).catch(function () {});
    if (commandMode) {
      cancelModes();
    }
  }

  function issueContextCommand(worldX, worldY, event) {
    // 选中兵营/重装工厂且无部队选中时，右键设集结点
    if (selectedStructureId && !selectedUnits.size) {
      var prod = roomState.game.structures.find(function (s) {
        return s.id === selectedStructureId && s.owner === session.playerId
          && (structureRole(s.kind) === 'barracks' || structureRole(s.kind) === 'factory');
      });
      if (prod) {
        sendAction('command', {
          command: 'setRally',
          structureId: prod.id,
          x: worldX, y: worldY
        }).then(function () { sound('confirm'); }).catch(function () {});
        return;
      }
    }
    var target = entityAt(worldX, worldY);
    // Own-unit context click is a selection change, never a move/stop.
    // Otherwise a right-click or macOS ctrl-click meant to pick group B
    // would re-order group A onto B's feet and abort A's march.
    if (target && target.id.charAt(0) === 'u' && target.owner === session.playerId) {
      selectAt(worldX, worldY, isAdditiveSelect(event));
      return;
    }
    if (target && !isFriendly(target.owner) && selectedUnits.size) {
      markOrder(target.x, target.y, 'attack');
      sendAction('command', {
        command: 'attack',
        unitIds: selectedUnitIdList(),
        targetId: target.id
      }).then(function () { sound('attack'); }).catch(function () {});
    } else if (target && isFriendly(target.owner) && structureRole(target.kind) === 'repair' && selectedUnits.size) {
      issueRepairCommand(target);
    } else {
      issueGroundCommand(worldX, worldY);
    }
  }

  function selectedDamagedVehicles() {
    return roomState.game.units.filter(function (unit) {
      var def = UNITS[unit.kind] || {};
      return selectedUnits.has(unit.id) && def.repairable && unit.hp < unit.maxHp - 0.1;
    });
  }

  function issueRepairCommand(repairBay) {
    var vehicles = selectedDamagedVehicles();
    var copy = factionCopy();
    if (!vehicles.length) {
      toast(copy.repairSelect, 'error');
      sound('error');
      return;
    }
    sendAction('command', {
      command: 'repair',
      unitIds: vehicles.map(function (unit) { return unit.id; }),
      structureId: repairBay.id
    }).then(function () {
      toast(vehicles.length + ' ' + copy.repairSent, 'success');
      sound('repair');
    }).catch(function () {});
  }

  function repairSelectedAtNearestBay() {
    if (!roomState || !roomState.game) {
      return;
    }
    var copy = factionCopy();
    var vehicles = selectedDamagedVehicles();
    if (!vehicles.length) {
      toast(copy.repairSelect, 'error');
      sound('error');
      return;
    }
    var bays = roomState.game.structures.filter(function (structure) {
      return structure.owner === session.playerId && structureRole(structure.kind) === 'repair' && structure.active;
    });
    if (!bays.length) {
      toast(copy.repairNeed, 'error');
      sound('error');
      return;
    }
    var lead = vehicles[0];
    bays.sort(function (a, b) {
      return Math.hypot(a.x - lead.x, a.y - lead.y) - Math.hypot(b.x - lead.x, b.y - lead.y);
    });
    issueRepairCommand(bays[0]);
  }

  function setCommandMode(mode) {
    if (!selectedUnits.size && mode === 'attackMove') {
      toast('请先选择部队');
      return;
    }
    if (mode === 'strike') {
      var me = ownPlayer();
      if (!me || !me.strikeCharges) {
        toast('没有超级武器充能');
        sound('error');
        return;
      }
    }
    buildMode = null;
    commandMode = commandMode === mode ? null : mode;
    canvas.classList.toggle('command-mode', !!commandMode);
    canvas.classList.toggle('strike-mode', commandMode === 'strike');
    buildCursorLabel.classList.toggle('hidden', !commandMode);
    $('#attackMoveBtn').classList.toggle('active', commandMode === 'attackMove');
    $('#pingBtn').classList.toggle('active', commandMode === 'ping');
    $('#strikeBtn').classList.toggle('active', commandMode === 'strike');
    if (commandMode) {
      buildCursorLabel.textContent = commandMode === 'ping' ? '放置信标 · 右键取消'
        : commandMode === 'strike' ? '选择打击坐标 · 右键取消'
        : '选择攻击移动位置 · 右键取消';
      sound('select');
    }
  }

  function stopSelected() {
    if (!selectedUnits.size) {
      return;
    }
    sendAction('command', {
      command: 'stop',
      unitIds: selectedUnitIdList()
    }).then(function () { sound('select'); }).catch(function () {});
  }

  function centerOnBase() {
    if (!roomState || !roomState.game) {
      return;
    }
    var hq = roomState.game.structures.find(function (s) {
      return s.owner === session.playerId && structureRole(s.kind) === 'hq';
    });
    if (hq) {
      camera.x = hq.x;
      camera.y = hq.y;
      clampCamera();
    }
  }

  function toast(message, type) {
    var stack = $('#toastStack');
    if (!stack) return;
    var icons = { error: '✕', success: '✓', info: '●' };
    var icon = icons[type] || '●';
    var item = document.createElement('div');
    item.className = 'toast' + (type ? ' ' + type : '');
    item.innerHTML = '<span class="toast-icon">' + icon + '</span><span class="toast-msg">' + htmlEscape(message) + '</span><div class="toast-bar"></div>';
    stack.appendChild(item);
    var bar = item.querySelector('.toast-bar');
    var duration = 2800;
    // 进度条交给合成器：toast-drain 的 keyframes（宽度 100%→0）由样式层
    // 提供，JS 只设时长，不再用 16ms 定时器逐帧改 style.width
    bar.style.animation = 'toast-drain ' + duration + 'ms linear forwards';
    setTimeout(function () {
      item.style.opacity = '0';
      item.style.transform = 'translateY(-6px)';
      setTimeout(function () { item.remove(); }, 220);
    }, duration);
  }

  function ensureAudio() {
    if (!audioContext) {
      var AudioCtor = window.AudioContext || window.webkitAudioContext;
      if (AudioCtor) {
        audioContext = new AudioCtor();
      }
    }
    if (audioContext && audioContext.state === 'suspended') {
      audioContext.resume();
    }
  }

  function sound(type) {
    if (!audioContext || audioContext.state !== 'running') return;
    var volMul = (settings.masterVolume / 100) * (settings.sfxVolume / 100);
    if (volMul < 0.001) return;
    var now = audioContext.currentTime;

    function out(gainNode) {
      if (Math.abs(volMul - 1) < 0.001) { gainNode.connect(audioContext.destination); return; }
      var mg = audioContext.createGain();
      mg.gain.setValueAtTime(volMul, now);
      gainNode.connect(mg);
      mg.connect(audioContext.destination);
    }

    if (type === 'explosion') {
      var noiseLen = 0.28;
      var noiseBuffer = audioContext.createBuffer(1, noiseLen * audioContext.sampleRate, audioContext.sampleRate);
      var noiseData = noiseBuffer.getChannelData(0);
      for (var i = 0; i < noiseData.length; i++) { noiseData[i] = (Math.random() * 2 - 1); }
      var noiseSrc = audioContext.createBufferSource();
      noiseSrc.buffer = noiseBuffer;
      var noiseGain = audioContext.createGain();
      noiseGain.gain.setValueAtTime(0.22, now);
      noiseGain.gain.exponentialRampToValueAtTime(0.0001, now + noiseLen);
      var noiseFilter = audioContext.createBiquadFilter();
      noiseFilter.type = 'lowpass';
      noiseFilter.frequency.setValueAtTime(800, now);
      noiseFilter.frequency.exponentialRampToValueAtTime(60, now + noiseLen);
      noiseSrc.connect(noiseFilter);
      noiseFilter.connect(noiseGain);
      out(noiseGain);
      noiseSrc.start(now);
      noiseSrc.stop(now + noiseLen + 0.05);
      var boom = audioContext.createOscillator();
      var boomGain = audioContext.createGain();
      boom.type = 'sine';
      boom.frequency.setValueAtTime(110, now);
      boom.frequency.exponentialRampToValueAtTime(24, now + 0.22);
      boomGain.gain.setValueAtTime(0.18, now);
      boomGain.gain.exponentialRampToValueAtTime(0.0001, now + 0.24);
      boom.connect(boomGain);
      out(boomGain);
      boom.start(now);
      boom.stop(now + 0.26);
      return;
    }
    if (type === 'start') {
      var sOsc = audioContext.createOscillator();
      var sGain = audioContext.createGain();
      sOsc.type = 'triangle';
      sOsc.frequency.setValueAtTime(380, now);
      sOsc.frequency.setValueAtTime(580, now + 0.08);
      sOsc.frequency.setValueAtTime(660, now + 0.16);
      sGain.gain.setValueAtTime(0.08, now);
      sGain.gain.setValueAtTime(0.08, now + 0.18);
      sGain.gain.exponentialRampToValueAtTime(0.0001, now + 0.35);
      sOsc.connect(sGain);
      out(sGain);
      sOsc.start(now);
      sOsc.stop(now + 0.37);
      return;
    }
    if (type === 'complete') {
      var c1 = audioContext.createOscillator();
      var c1g = audioContext.createGain();
      c1.type = 'sine';
      c1.frequency.setValueAtTime(600, now);
      c1.frequency.setValueAtTime(880, now + 0.06);
      c1g.gain.setValueAtTime(0.06, now);
      c1g.gain.exponentialRampToValueAtTime(0.0001, now + 0.22);
      c1.connect(c1g);
      out(c1g);
      c1.start(now);
      c1.stop(now + 0.24);
      var c2 = audioContext.createOscillator();
      var c2g = audioContext.createGain();
      c2.type = 'sine';
      c2.frequency.setValueAtTime(900, now + 0.04);
      c2.frequency.setValueAtTime(1200, now + 0.1);
      c2g.gain.setValueAtTime(0, now);
      c2g.gain.setValueAtTime(0.05, now + 0.04);
      c2g.gain.exponentialRampToValueAtTime(0.0001, now + 0.26);
      c2.connect(c2g);
      out(c2g);
      c2.start(now + 0.04);
      c2.stop(now + 0.28);
      return;
    }
    if (type === 'promote') {
      // 晋升：上扬的大调琶音（do-mi-sol-do），短促明亮，与爆炸/完工的音色区分开
      var notes = [523.25, 659.25, 783.99, 1046.5];
      for (var ni = 0; ni < notes.length; ni++) {
        var pOsc = audioContext.createOscillator();
        var pGain = audioContext.createGain();
        var t0 = now + ni * 0.06;
        pOsc.type = 'triangle';
        pOsc.frequency.setValueAtTime(notes[ni], t0);
        pGain.gain.setValueAtTime(0, t0);
        pGain.gain.linearRampToValueAtTime(0.07, t0 + 0.015);
        pGain.gain.exponentialRampToValueAtTime(0.0001, t0 + 0.22);
        pOsc.connect(pGain);
        out(pGain);
        pOsc.start(t0);
        pOsc.stop(t0 + 0.24);
      }
      return;
    }
    var config = {
      select: [520, 0.04, 0.035, 'square'],
      move: [260, 0.05, 0.06, 'sine'],
      attack: [160, 0.07, 0.09, 'sawtooth'],
      confirm: [680, 0.06, 0.07, 'triangle'],
      repair: [740, 0.045, 0.12, 'triangle'],
      cancel: [330, 0.055, 0.11, 'square'],
      error: [110, 0.05, 0.14, 'square']
    }[type];
    if (!config) return;
    var osc = audioContext.createOscillator();
    var gain = audioContext.createGain();
    osc.type = config[3];
    osc.frequency.setValueAtTime(config[0], now);
    if (type === 'attack') { osc.frequency.exponentialRampToValueAtTime(42, now + config[2]); }
    if (type === 'error') { osc.frequency.setValueAtTime(config[0], now); osc.frequency.setValueAtTime(88, now + 0.06); }
    // 撤销：下滑音，和确认的上扬音形成对照
    if (type === 'cancel') { osc.frequency.exponentialRampToValueAtTime(150, now + config[2]); }
    gain.gain.setValueAtTime(config[1], now);
    gain.gain.exponentialRampToValueAtTime(0.0001, now + config[2]);
    osc.connect(gain);
    out(gain);
    osc.start(now);
    osc.stop(now + config[2] + 0.02);
  }

  function renderResult() {
    if (!roomState || !roomState.game) {
      return;
    }
    resultShown = true;
    var me = ownPlayer();
    var won = roomState.game.winnerId === session.playerId;
    var card = $('#resultModal .result-card');
    card.classList.toggle('defeat', !won);
    $('#resultEmblem').textContent = won ? '★' : '✕';
    $('#resultKicker').textContent = won ? 'MISSION ACCOMPLISHED' : 'MISSION FAILED';
    $('#resultTitle').textContent = won ? '战斗胜利' : '战线失守';
    $('#resultText').textContent = won ? '敌方指挥体系已经瓦解，战区控制权已确认。' : '你的' + factionCopy().hq + '已被摧毁，部队退出战区。';
    $('#resultStats').innerHTML =
      '<div><span>击毁单位</span><strong>' + (me ? me.kills : 0) + '</strong></div>' +
      '<div><span>损失单位</span><strong>' + (me ? me.unitsLost : 0) + '</strong></div>' +
      '<div><span>采集资金</span><strong>$' + (me ? Math.floor(me.harvested).toLocaleString('zh-CN') : 0) + '</strong></div>' +
      '<div><span>作战时间</span><strong>' + $('#matchClock').textContent + '</strong></div>';
    $('#resultModal').classList.remove('hidden');
    sound(won ? 'complete' : 'error');
  }

  function pointerPosition(event) {
    var rect = canvas.getBoundingClientRect();
    pointer.x = event.clientX - rect.left;
    pointer.y = event.clientY - rect.top;
    updatePointerWorld();
  }

  canvas.addEventListener('pointerenter', function () { pointer.inside = true; });
  canvas.addEventListener('pointerleave', function () { pointer.inside = false; });
  canvas.addEventListener('pointermove', function (event) {
    pointerPosition(event);
    updateSelectionBox();
    if (buildMode || commandMode) {
      buildCursorLabel.style.left = Math.min(viewWidth - 180, pointer.x + 15) + 'px';
      buildCursorLabel.style.top = Math.max(4, pointer.y - 30) + 'px';
    }
  });
  canvas.addEventListener('pointerdown', function (event) {
    ensureAudio();
    pointerPosition(event);
    canvas.focus();
    if (event.button === 2) {
      event.preventDefault();
      if (buildMode || commandMode) {
        cancelModes();
      } else {
        issueContextCommand(pointer.worldX, pointer.worldY, event);
      }
      return;
    }
    if (event.button !== 0) {
      return;
    }
    if (buildMode) {
      placeCurrentBuilding();
      return;
    }
    if (commandMode === 'attackMove') {
      issueGroundCommand(pointer.worldX, pointer.worldY);
      return;
    }
    if (commandMode === 'ping') {
      sendAction('command', { command: 'ping', x: pointer.worldX, y: pointer.worldY })
        .then(function () { sound('confirm'); }).catch(function () {});
      cancelModes();
      return;
    }
    if (commandMode === 'strike') {
      sendAction('command', { command: 'callStrike', x: pointer.worldX, y: pointer.worldY })
        .then(function () { toast('轨道打击已呼叫', 'success'); sound('confirm'); })
        .catch(function () {});
      cancelModes();
      return;
    }
    dragging = { startX: pointer.x, startY: pointer.y, additive: isAdditiveSelect(event) };
    canvas.setPointerCapture(event.pointerId);
  });
  canvas.addEventListener('pointerup', function (event) {
    if (event.button !== 0 || !dragging) {
      return;
    }
    pointerPosition(event);
    var moved = Math.hypot(pointer.x - dragging.startX, pointer.y - dragging.startY);
    if (moved < 6) {
      selectAt(pointer.worldX, pointer.worldY, dragging.additive);
    } else {
      selectBoxUnits(dragging.startX, dragging.startY, pointer.x, pointer.y, dragging.additive);
    }
    dragging = null;
    selectionBox.classList.add('hidden');
  });
  canvas.addEventListener('dblclick', function (event) {
    if (event.button !== 0) { return; }
    pointerPosition(event);
    selectAllOfType(pointer.worldX, pointer.worldY);
  });
  canvas.addEventListener('pointercancel', function () {
    dragging = null;
    selectionBox.classList.add('hidden');
  });
  canvas.addEventListener('contextmenu', function (event) { event.preventDefault(); });
  canvas.addEventListener('wheel', function (event) {
    event.preventDefault();
    pointerPosition(event);
    var before = screenToWorld(pointer.x, pointer.y);
    var factor = Math.exp(-event.deltaY * 0.0012);
    // 地图变大后放宽缩放范围：拉远能看全战线，拉近能看清单位细节
    camera.zoom = Math.max(0.30, Math.min(2.60, camera.zoom * factor));
    var after = screenToWorld(pointer.x, pointer.y);
    camera.x += before.x - after.x;
    camera.y += before.y - after.y;
    clampCamera();
  }, { passive: false });

  minimap.addEventListener('mousedown', function (event) {
    if (!roomState || !roomState.game) {
      return;
    }
    event.preventDefault();
    var rect = minimap.getBoundingClientRect();
    var wx = (event.clientX - rect.left) / rect.width * roomState.game.map.width;
    var wy = (event.clientY - rect.top) / rect.height * roomState.game.map.height;
    if (event.button === 2) {
      // 右键小地图：派遣选中单位
      if (selectedUnits.size) {
        var cmd = commandMode === 'attackMove' ? 'attackMove' : 'move';
        sendAction('command', {
          command: cmd,
          unitIds: selectedUnitIdList(),
          x: wx,
          y: wy
        }).then(function () { sound('move'); }).catch(function () {});
        if (commandMode) { cancelModes(); }
      }
    } else if (event.button === 0) {
      // 左键小地图：移动视角
      camera.x = wx;
      camera.y = wy;
      clampCamera();
    }
  });
  minimap.addEventListener('contextmenu', function (event) { event.preventDefault(); });

  window.addEventListener('resize', resizeCanvas);
  window.addEventListener('keydown', function (event) {
    var editing = event.target instanceof HTMLInputElement;
    if (editing) {
      if (event.code === 'Escape' && currentScreen === 'game') {
        battleChatForm.classList.add('hidden');
        canvas.focus();
      }
      return;
    }
    if (currentScreen !== 'game') {
      return;
    }
    pressedKeys.add(event.code);
    if (event.code >= 'Digit1' && event.code <= 'Digit9') {
      var groupNum = parseInt(event.code.slice(5));
      if (event.ctrlKey) {
        event.preventDefault();
        if (selectedUnits.size > 0) {
          controlGroups[groupNum] = Array.from(selectedUnits);
          toast('编队 ' + groupNum + ' 已保存 · ' + selectedUnits.size + ' 个单位');
          sound('confirm');
        }
      } else {
        event.preventDefault();
        var group = controlGroups[groupNum];
        if (group && group.length > 0) {
          var now = performance.now();
          if (lastGroupTap[groupNum] && now - lastGroupTap[groupNum] < 400) {
            var cx = 0, cy = 0, count = 0;
            roomState.game.units.forEach(function (u) {
              if (group.indexOf(u.id) >= 0) { cx += u.x; cy += u.y; count++; }
            });
            if (count > 0) { camera.x = cx / count; camera.y = cy / count; clampCamera(); }
            lastGroupTap[groupNum] = 0;
          } else {
            selectedUnits.clear();
            selectedStructureId = null;
            group.forEach(function (id) { selectedUnits.add(id); });
            pruneSelection();
            renderSelectionInfo();
            sound('select');
            lastGroupTap[groupNum] = now;
          }
        }
      }
    } else if (event.code === 'KeyQ') {
      event.preventDefault();
      setCommandMode('attackMove');
    } else if (event.code === 'KeyS') {
      event.preventDefault();
      // Tap S = stop. Hold S = camera pan (WASD). Immediate stop-on-keydown
      // cancelled marches while the player panned to pick another group.
      if (!event.repeat && !stopKeyDownAt) {
        stopKeyDownAt = performance.now();
      }
    } else if (event.code === 'KeyR') {
      event.preventDefault();
      repairSelectedAtNearestBay();
    } else if (event.code === 'KeyU') {
      event.preventDefault();
      if (selectedStructureId && roomState && roomState.game) {
        var hq = roomState.game.structures.find(function (s) { return s.id === selectedStructureId && structureRole(s.kind) === 'hq' && s.owner === session.playerId && s.packable; });
        if (hq) {
          sendAction('command', { command: 'undeploy', structureId: hq.id }).then(function () {
            selectedStructureId = null;
            renderSelectionInfo();
            toast(factionCopy().hq + '已折叠为' + factionCopy().mcv, 'success');
            sound('confirm');
          }).catch(function (err) { toast(err.message || '折叠失败', 'error'); });
        }
      }
    } else if (event.code === 'KeyG') {
      event.preventDefault();
      setCommandMode('ping');
    } else if (event.code === 'KeyX') {
      event.preventDefault();
      setCommandMode('strike');
    } else if (event.code === 'Space') {
      event.preventDefault();
      centerOnBase();
    } else if (event.code === 'Enter') {
      event.preventDefault();
      battleChatForm.classList.remove('hidden');
      battleChatInput.focus();
    } else if (event.code === 'Escape') {
      cancelModes();
    } else if (event.code === 'KeyY' && activeProposalFromId) {
      event.preventDefault();
      sendAction('acceptAlliance', {}).catch(function () {});
      dismissAllianceProposal();
      activeProposalFromId = null;
    } else if (event.code === 'KeyN' && activeProposalFromId) {
      event.preventDefault();
      sendAction('rejectAlliance', {}).catch(function () {});
      dismissAllianceProposal();
      activeProposalFromId = null;
    }
  });
  window.addEventListener('keyup', function (event) {
    pressedKeys.delete(event.code);
    if (event.code === 'KeyS' && stopKeyDownAt) {
      var heldMs = performance.now() - stopKeyDownAt;
      stopKeyDownAt = 0;
      if (heldMs < 220 && currentScreen === 'game') {
        stopSelected();
      }
    }
  });
  window.addEventListener('blur', function () {
    pressedKeys.clear();
    stopKeyDownAt = 0;
  });

  createRoomBtn.addEventListener('click', createRoom);
  refreshRoomsBtn.addEventListener('click', refreshRooms);
  joinCodeBtn.addEventListener('click', function () { joinRoom(roomCodeInput.value); });
  roomCodeInput.addEventListener('input', function () {
    roomCodeInput.value = roomCodeInput.value.toUpperCase().replace(/[^A-Z0-9]/g, '');
  });
  roomCodeInput.addEventListener('keydown', function (event) {
    if (event.key === 'Enter') {
      joinRoom(roomCodeInput.value);
    }
  });
  roomNameInput.addEventListener('keydown', function (event) {
    if (event.key === 'Enter') {
      createRoom();
    }
  });
  $('#leaveLobbyBtn').addEventListener('click', leaveRoom);
  $('#copyRoomCode').addEventListener('click', function () {
    var code = roomState ? roomState.id : '';
    if (navigator.clipboard && window.isSecureContext) {
      navigator.clipboard.writeText(code).then(function () {
        lobbyHint.textContent = '房间码已复制：' + code;
      });
    } else {
      var helper = document.createElement('textarea');
      helper.value = code;
      document.body.appendChild(helper);
      helper.select();
      document.execCommand('copy');
      helper.remove();
      lobbyHint.textContent = '房间码已复制：' + code;
    }
  });
  readyBtn.addEventListener('click', function () {
    var me = ownPlayer();
    if (me) {
      sendAction('ready', { ready: !me.ready }).then(function () { sound('confirm'); }).catch(function () {});
    }
  });
  addBotBtn.addEventListener('click', function () {
    sendAction('addBot').then(function () { sound('confirm'); }).catch(function () {});
  });
  randomTeamBtn.addEventListener('click', async function () {
    if (!roomState || !roomState.players) { return; }
    var mapConfig = getMapConfig();
    var humans = roomState.players.filter(function (p) { return !p.isBot; });
    if (humans.length < 2) { toast('至少需要2名人类玩家', 'error'); return; }
    randomTeamBtn.disabled = true;
    try {
      var shuffled = humans.slice().sort(function () { return Math.random() - 0.5; });
      var mid = Math.ceil(shuffled.length / 2);
      for (var i = 0; i < shuffled.length; i++) {
        var p = shuffled[i];
        var t = i < mid ? 1 : 2;
        if ((p.team || 0) !== t) {
          await sendAction('setTeam', { playerId: p.id, team: t });
        }
      }
      await randomAssignSpawns(roomState, mapConfig);
      toast('随机分组完成', 'success');
      sound('confirm');
    } catch (err) {
      toast(err.message || '分组失败', 'error');
    } finally {
      randomTeamBtn.disabled = false;
    }
  });
  randomSpawnBtn.addEventListener('click', async function () {
    if (!roomState || !roomState.players) { return; }
    var mapConfig = getMapConfig();
    randomSpawnBtn.disabled = true;
    try {
      await randomAssignSpawns(roomState, mapConfig);
      toast('随机出生完成', 'success');
      sound('confirm');
    } catch (err) {
      toast(err.message || '分配失败', 'error');
    } finally {
      randomSpawnBtn.disabled = false;
    }
  });
  startGameBtn.addEventListener('click', function () {
    sendAction('start').then(function () { sound('start'); }).catch(function () {});
  });
  lobbyChatForm.addEventListener('submit', function (event) {
    event.preventDefault();
    var message = lobbyChatInput.value.trim();
    if (!message) {
      return;
    }
    lobbyChatInput.value = '';
    sendAction('chat', { message: message }).catch(function () {});
  });
  battleChatForm.addEventListener('submit', function (event) {
    event.preventDefault();
    var message = battleChatInput.value.trim();
    battleChatInput.value = '';
    battleChatForm.classList.add('hidden');
    canvas.focus();
    if (message) {
      sendAction('chat', { message: message }).catch(function () {});
    }
  });
  $$('.command-tab').forEach(function (button) {
    button.addEventListener('click', function () {
      activeTab = button.dataset.tab;
      $$('.command-tab').forEach(function (tab) { tab.classList.toggle('active', tab === button); });
      renderCommandGrid(true);
      sound('select');
    });
  });
  $('#attackMoveBtn').addEventListener('click', function () { setCommandMode('attackMove'); });
  $('#repairBtn').addEventListener('click', repairSelectedAtNearestBay);
  $('#stopBtn').addEventListener('click', stopSelected);
  $('#pingBtn').addEventListener('click', function () { setCommandMode('ping'); });
  $('#strikeBtn').addEventListener('click', function () { setCommandMode('strike'); });
  $('#deployBtn').addEventListener('click', function () {
    if (!selectedUnits.size || !roomState || !roomState.game) { return; }
    var mcvIds = roomState.game.units.filter(function (u) { return selectedUnits.has(u.id) && unitRole(u.kind) === 'mcv' && u.owner === session.playerId; }).map(function (u) { return u.id; });
    if (!mcvIds.length) { return; }
    sendAction('command', {
      command: 'deploy',
      unitIds: mcvIds
    }).then(function () { toast(factionCopy().mcv + '已展开为新' + factionCopy().hq, 'success'); sound('confirm'); })
      .catch(function (err) { toast(err.message || '展开失败', 'error'); });
  });
  $('#counterToggle').addEventListener('click', function () {
    $('#counterPanel').classList.toggle('open');
  });
  $('#gameMenuBtn').addEventListener('click', function () { $('#gameMenu').classList.remove('hidden'); });
  $('#resumeBtn').addEventListener('click', function () { $('#gameMenu').classList.add('hidden'); canvas.focus(); });
  $('#leaveGameBtn').addEventListener('click', function () {
    $('#gameMenu').classList.add('hidden');
    leaveRoom();
  });
  $('#openSettingsBtn').addEventListener('click', function () {
    $('#gameMenu').classList.add('hidden');
    showSettings();
  });
  $('#settingsCloseBtn').addEventListener('click', function () {
    settings.masterVolume = parseInt($('#masterVolume').value);
    settings.sfxVolume = parseInt($('#sfxVolume').value);
    settings.particleQuality = $('#particleQuality').value;
    settings.fogQuality = $('#fogQuality').value;
    settings.shadowQuality = $('#shadowQuality').value;
    if ($('#bloomQuality')) { settings.bloomQuality = $('#bloomQuality').value; }
    if ($('#projectileQuality')) { settings.projectileQuality = $('#projectileQuality').value; }
    saveSettings();
    applySettings();
    $('#settingsModal').classList.add('hidden');
  });
  $('#settingsModal').addEventListener('click', function (e) {
    if (e.target === $('#settingsModal')) { $('#settingsModal').classList.add('hidden'); }
  });
  $('#returnHomeBtn').addEventListener('click', function () {
    $('#resultModal').classList.add('hidden');
    leaveRoom();
  });
  document.addEventListener('pointerdown', ensureAudio, { once: true });

  // 截图与调试钩子：揭开迷雾只是表现层（服务端本就不下发视野外的实体），
  // 供自动化截图脚本检查地形渲染用。
  window.__iflDebug = {
    revealAll: function () { view3d.revealAll(); },
    jumpTo: function (x, y, zoom) {
      camera.x = x; camera.y = y;
      if (zoom) camera.zoom = zoom;
    },
    terrain: function () {
      return roomState && roomState.game ? {
        map: roomState.game.map,
        terrain: roomState.game.terrain
      } : null;
    },
    boom: function (type, x, y, kind) { view3d.debugEffect(type || 'explosion', x, y, kind); },
    cameraPos: function () { return { x: camera.x, y: camera.y, zoom: camera.zoom }; }
  };

  // All controls are bound at this point. The small bootstrap guard in
  // index.html only reports errors that happen before the lobby is usable.
  window.__ironFrontBooted = true;
  playerNameInput.value = localStorage.getItem(NAME_KEY) || ('指挥官' + String(Math.floor(Math.random() * 900 + 100)));
  catalogPromise.then(function () {
    return restoreSession();
  }).then(function (restored) {
    if (!restored) {
      setScreen('home');
    }
    if (!renderStarted) {
      renderStarted = true;
      requestAnimationFrame(frame);
    }
  });
}());
