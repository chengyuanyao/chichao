// Pure report presentation. No animation loop, live game state or chart library.
const esc = value => String(value == null ? '' : value).replace(/[&<>"']/g, c =>
  ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[c]));
const number = value => Math.max(0, Number(value) || 0);
const count = value => Math.floor(number(value)).toLocaleString('zh-CN');
const money = value => '$' + count(value);
const color = value => /^#[0-9a-f]{6}$/i.test(value || '') ? value : '#d8cba7';

export function battleTime(value) {
  if (value == null) return '未发生';
  const seconds = Math.floor(number(value));
  return Math.floor(seconds / 60) + ':' + String(seconds % 60).padStart(2, '0');
}

export function exchangeLabel(row) {
  if (!number(row.lostValue)) return number(row.destroyedValue) ? '无损' : '—';
  return (number(row.destroyedValue) / number(row.lostValue)).toFixed(2) + ' : 1';
}

function status(row) {
  return row.won ? '胜利' : row.exitReason === 'left' ? '离场' : row.eliminatedAt != null ? '淘汰' : '结束';
}

function playerLabel(row, mine) {
  return '<span class="report-player-dot" style="background:' + color(row.color) + '"></span>' +
    '<span>' + esc(row.name) + (mine ? ' <small>我</small>' : '') + '</span>';
}

export function renderReportSummary(report, playerId) {
  const me = report.players.find(row => row.id === playerId) || {};
  return [['作战时间', battleTime(report.duration)], ['首次交战 · 全场', battleTime(report.firstCombatAt)],
    ['我的战损交换比', exchangeLabel(me)], ['我的采样军力峰值', money(me.peakArmyValue)]]
    .map(([label, value]) => '<div><span>' + esc(label) + '</span><strong>' + esc(value) + '</strong></div>').join('');
}

function chart(report, metric, title, subtitle) {
  const samples = report.samples || [];
  const width = 640, height = 240, left = 58, top = 16, right = 18, bottom = 34;
  const plotWidth = width - left - right, plotHeight = height - top - bottom;
  const duration = Math.max(1, number(report.duration), ...samples.map(p => number(p.time)));
  let max = 1;
  samples.forEach(point => report.players.forEach(row => {
    max = Math.max(max, number((point.players[row.id] || [])[metric]));
  }));
  const step = Math.pow(10, Math.floor(Math.log10(max)));
  max = Math.ceil(max / step) * step;
  const x = time => left + number(time) / duration * plotWidth;
  const y = value => top + (1 - number(value) / max) * plotHeight;
  let svg = '<svg viewBox="0 0 640 240" role="img" aria-label="' + esc(title) + '"><title>' + esc(title) + '</title>';
  for (let i = 0; i <= 4; i++) {
    const value = max * i / 4, py = y(value).toFixed(1);
    svg += '<line class="report-chart-grid" x1="58" x2="622" y1="' + py + '" y2="' + py + '"/>' +
      '<text x="50" y="' + (Number(py) + 4) + '" text-anchor="end">' +
      (value >= 10000 ? (value / 10000).toFixed(1) + '万' : Math.round(value)) + '</text>';
    svg += '<text x="' + x(duration * i / 4).toFixed(1) + '" y="230" text-anchor="middle">' + battleTime(duration * i / 4) + '</text>';
  }
  report.players.forEach((row, index) => {
    const points = samples.map(point => [x(point.time), y((point.players[row.id] || [])[metric])]);
    if (!points.length) return;
    const dash = ['', '8 3', '3 3', '10 3 2 3', '2 2'][index % 5];
    svg += '<polyline fill="none" stroke="' + color(row.color) + '" stroke-width="2.2" stroke-dasharray="' + dash +
      '" points="' + points.map(p => p.map(v => v.toFixed(1)).join(',')).join(' ') + '"><title>' + esc(row.name) + '</title></polyline>';
    const end = points[points.length - 1];
    svg += '<circle cx="' + end[0].toFixed(1) + '" cy="' + end[1].toFixed(1) + '" r="3" fill="' + color(row.color) + '"/>';
  });
  return '<article class="report-chart"><h3>' + title + '</h3><p>' + subtitle + '</p>' + svg + '</svg></article>';
}

function eventText(event, players) {
  const owner = players[event.playerId] || {name: '未知玩家'};
  const source = players[event.sourceId];
  if (event.type === 'firstCombat') return (source ? source.name : '敌军') + ' 与 ' + owner.name + ' 首次交战';
  if (event.type === 'eliminated') return owner.name + (event.reason === 'left' ? ' 主动离开本局' : ' 失去全部指挥实体，退出战区');
  if (event.type === 'techCompleted') return owner.name + ' 首次完成 ' + event.name;
  if (event.type === 'harvesterLost') return owner.name + ' 损失 ' + event.name + (source ? ' · 进攻方：' + source.name : '');
  if (event.type === 'incomeGap') return owner.name + ' 到账中断 ' + battleTime(event.duration) + '（' + battleTime(event.startedAt) + ' 起）';
  return owner.name + ' 的' + (event.name || event.kind) + '被摧毁' +
    (source ? ' · ' + (event.cause === 'enemy' ? '进攻方：' : '伤害来源：') + source.name : ' · 中立或环境伤害');
}

function operationsPanel(report, playerId) {
  if (number(report.version) < 2) return '<p class="report-note">旧版战报未记录分兵种和运营数据。</p>';
  return report.players.map(p => '<details class="report-operations"' + (p.id === playerId ? ' open' : '') + '><summary>' +
    esc(p.name) + ' · 矿车损失 ' + count(p.harvestersLost) + ' · 到账中断 ' + count(p.incomeGapCount) + ' 次 / ' + battleTime(p.incomeGapSeconds) +
    ' · 最长 ' + battleTime(p.longestIncomeGap) + '</summary><div class="report-table-wrap"><table class="report-table">' +
    '<thead><tr><th>兵种 / 火力来源</th><th>生产完成</th><th>初始 / 赠送</th><th>损失数量</th><th>损失价值</th><th>击毁数量</th><th>击毁价值</th></tr></thead><tbody>' +
    Object.values(p.byKind || {}).map(k => '<tr><th>' + esc(k.name) + '</th><td>' + (k.category === 'unit' || (report.version >= 3 && k.category === 'structure') ? count(k.produced) : '—') +
      '</td><td>' + (k.category === 'unit' || (report.version >= 3 && k.category === 'structure') ? count(k.initial) + ' / ' + count(k.gifted) : '—') + '</td><td>' + count(k.lost) +
      '</td><td>' + money(k.lostValue) + '</td><td>' + count(k.destroyed) + '</td><td>' + money(k.destroyedValue) + '</td></tr>').join('') +
    '</tbody></table></div><h3>首次科技建筑落成</h3><div class="report-tech-times">' +
    Object.values(p.techTimes || {}).map(t => '<span>' + esc(t.name) + ' <strong>' + battleTime(t.time) +
      (t.initial ? ' · 初始' : '') + '</strong></span>').join('') + '</div></details>').join('') +
    '<p class="report-note">生产仅计实际出厂，不含排队、撤单、初始和精炼厂赠车；折叠 / 展开不重复计产量。击毁价值按完成最后一击的兵种归属，弹丸发射者阵亡后仍可追溯；炮塔与轨道等来源单列，不等于总伤害贡献。</p>' +
    '<p class="report-note">到账中断：首次卸矿后，连续 30 秒无卸矿到账才开始计时，到账、退场或终局结束计时。不含开局找矿时间，正常采矿往返、主动停采也可能触发，不自动判定为敌方骚扰。科技时间计第一次建筑落成，而非开始排队。</p>';
}

const lossCauseLabels = {enemy:'敌方玩家击毁', self:'主动自爆消耗', other:'中立 / 友伤 / 环境等'};
const flowLabels = {harvest:'卸矿收入',rewards:'战斗奖励',crates:'补给收入',unitRefund:'撤单退款 · 兵',structureRefund:'撤单退款 · 建筑',
  sales:'出售回款',unitSpend:'造兵扣款',structureSpend:'建造扣款',unitRepair:'单位维修',structureRepair:'建筑维修',adjustments:'调试扣款'};
const flowIncome = new Set(['harvest','rewards','crates','unitRefund','structureRefund','sales']);
const delayLabels = {unitPowerLoss:'造兵缺电损失',buildPowerLoss:'建筑队列缺电损失',constructionPowerLoss:'落地施工缺电损失',authorityPause:'无建造授权暂停'};
const exactMoney = value => '$' + (Number(value) || 0).toLocaleString('zh-CN',{minimumFractionDigits:2,maximumFractionDigits:2});

function phaseRows(report, player) {
  return (report.phases || []).filter(phase => phase.time <= number(player.eliminatedAt ?? report.duration)).map(phase => {
    const m = (phase.players || {})[player.id] || {};
    return [battleTime(phase.time) + '—' + battleTime(Math.min(phase.time + report.phaseSeconds, player.eliminatedAt ?? report.duration)),
      money(m.harvest), money(m.unitProducedValue), money(m.structureProducedValue), money(m.destroyedValue), money(m.lostValue),
      exchangeLabel(m), count(m.unitsLost) + ' / ' + count(m.structuresLost), count(m.harvestersLost),
      money(number(m.unitSpend) + number(m.structureSpend) + number(m.unitRepair) + number(m.structureRepair)),
      money(number(m.unitRefund) + number(m.structureRefund) + number(m.sales)),
      money(number(m.rewards) + number(m.crates)),
      m.cashObservedSeconds ? money(number(m.cashSeconds) / m.cashObservedSeconds) : '—',
      battleTime(m.highCashSeconds || 0)];
  });
}
const phaseHeaders = ['阶段','采集收入','完成造兵原价','完成建筑原价','击毁价值','损失价值','交换比','损失兵 / 建筑','其中矿车',
  '生产与维修支出','退款 / 出售','奖励 / 补给','平均持币','持币 ≥ 5000 时长'];

function engagementRows(report, episode) {
  return Object.entries(episode.players || {}).map(([id, side]) => {
    const player = report.players.find(p => p.id === id) || {};
    const other = Object.entries(episode.players || {}).find(([pid]) => pid !== id)?.[1] || {};
    const kinds = Object.entries(side.byKind || {}).map(([kind,n]) => ((player.byKind || {})[kind]?.name || kind) + ' × ' + count(n)).join('、');
    return [player.name || '未知玩家',kinds || '无损失',money(side.lostValue),money(other.lostValue),exchangeLabel({lostValue:side.lostValue,destroyedValue:other.lostValue})];
  });
}

function phasesPanel(report, playerId) {
  return '<p class="report-note">按事件发生时间累计，初始每分钟一段；长局合并相邻时间段但保留合计，当前每段 ' +
    battleTime(report.phaseSeconds) + '。区间左闭右开，终局恰在边界发生的事件单列。完成产出不是当期支出，战损包含自爆和非玩家伤害。</p>' +
    report.players.map(p => {
      const rows = phaseRows(report,p);
      return '<details class="report-operations"' + (p.id === playerId ? ' open' : '') + '><summary>' + esc(p.name) +
        ' · 分阶段收获与战损</summary><h3>生产与交战</h3>' + detailTable(phaseHeaders.slice(0,9),rows.map(r => r.slice(0,9))) +
        '<h3>资金利用</h3>' + detailTable([phaseHeaders[0],phaseHeaders[1],...phaseHeaders.slice(9)],rows.map(r => [r[0],r[1],...r.slice(9)])) + '</details>';
    }).join('') +
    '<h3>关键战损片段 · 按双方损失价值排序</h3><p class="report-note">同一对手之间，相邻敌对击毁间隔不超过 20 秒则合并；不代表单一地点的一场战斗，可能包含多处交火。不含未造成击毁的骚扰、主动自爆或环境损失。最多保留 24 个高价值片段，省略 ' +
    count(report.omittedEngagements) + ' 个，其战损仍计入总表和分阶段统计。</p>' +
    ((report.engagements || []).map(e => '<details class="report-operations"><summary>' + battleTime(e.start) + '—' + battleTime(e.end) +
      ' · 双方损失 ' + money(e.value) + '</summary>' + detailTable(['玩家','损失构成','损失价值','击毁对方价值','交换比'],engagementRows(report,e)) + '</details>').join('') || '<p>本局没有敌对击毁片段。</p>');
}

function financePanel(report, playerId) {
  return '<p class="report-note">记录实际扣款与回款；排队时即付费，退款独立展示，不与生产完成原价混用。平均持币按资金变动间隔加权，退场后停止计时。持币 ≥ $5,000 不一定是失误，也可能正在攒高级单位。</p>' +
    report.players.map(p => {
      const flow = p.cashFlow || {};
      return '<details class="report-operations"' + (p.id === playerId ? ' open' : '') + '><summary>' + esc(p.name) +
        ' · 平均持币 ' + exactMoney(p.averageCash) + ' · 持币 ≥ $5,000 时长 ' + battleTime(p.highCashSeconds) + '</summary>' +
        detailTable(['项目','流入','流出'],Object.entries(flowLabels).map(([key,label]) => [label,flowIncome.has(key) ? exactMoney(flow[key]) : '—',
          flowIncome.has(key) ? '—' : exactMoney(flow[key])])) +
        detailTable(['开局资金','退场 / 终局资金','收支核对差额'],[[exactMoney(p.openingCash),exactMoney(p.closingCash),exactMoney(p.cashReconciliation)]]) +
        '<h3>生产受阻 · 等效秒数</h3>' + detailTable(['原因','等效损失时间'],Object.entries(delayLabels).map(([key,label]) =>
          [label,(number((p.productionDelay || {})[key])).toFixed(2) + ' 秒'])) + '</details>';
    }).join('') + '<p class="report-note">核对差额＝开局资金＋全部流入－全部流出－结束资金，正常约为 0；非零说明有未记录资金变动，不能当作经济损失。缺电项累计“工作时长 × (1－生产倍率)”，多生产建筑并行时叠加，不是整局停电时长。无建造授权暂停单列，不计空队列。</p>';
}

function performancePanel(report) {
  const p=report.clientPerformance;
  if(!p || p.matchId!==report.matchId)return '';
  const fixed=v=>number(v).toFixed(1);
  return '<h3>本机性能摘要</h3><p class="report-note">仅此浏览器前台对局期间，非全员性能；不含后台和菜单。帧间隔不是 GPU 耗时，也不能单独判断网络卡顿。负载约每秒采样，峰值不代表同时发生。</p>' +
    detailTable(['平均 FPS','p95 帧间隔','超过 50ms 帧数','其中超过 100ms','最低渲染比例','记录时长'],[[fixed(p.averageFps),
      (p.p95Overflow?'≥ ':'')+fixed(p.p95Ms)+' ms',count(p.over50),count(p.over100),Math.round(number(p.minScale)*100)+'%',battleTime(p.ms/1000)]]) +
    detailTable(['对局时间','平均 FPS','>50ms 帧','>100ms 帧','最多画面单位','绘制调用峰值','粒子峰值','几何资源','纹理资源','最低比例'],
      (p.periods || []).filter(r=>r.frames).map(r=>[battleTime(r.time),fixed(r.averageFps),count(r.over50),count(r.over100),
        count(r.maxUnits),count(r.maxDrawCalls),count(r.maxParticles),count(r.maxGeometries),count(r.maxTextures),Math.round(number(r.minScale)*100)+'%'])) +
    '<p class="report-note">每行起点对应约 '+count(p.interval)+' 秒窗口，长局自动合并。几何/纹理为资源数量，不是显存字节数；新出现的兵种会建立缓存，增长不自动等于泄漏。</p>';
}

export function renderDiagnostics(data) {
  if(!data)return '';
  const avg=(p,sum,count)=>p[count]?number(p[sum]/p[count]).toFixed(1):'—';
  const rows=[];
  for(const player of data.players||[]) {
    const entry=(data.clients||{})[player.id];
    if(!entry?.runs?.length) {rows.push([player.name,player.isBot?'AI，无浏览器':'尚未收到上报','—','—','—','—','—','—','—','—']);continue;}
    for(const [index,p] of entry.runs.entries()) {
      const age=Math.max(0,Date.now()/1000-number(p.receivedAt));
      rows.push([player.name+' / 会话 '+(index+1),(data.status==='playing'?(age>75?'上报过期 '+Math.round(age)+' 秒':'已收到'):'已保存')+(p.detailReceivedAt?' · 含详细记录':' · 仅摘要'),
        number(p.averageFps).toFixed(1),number(p.p95Ms)+' ms',avg(p,'probeMs','probeSamples'),avg(p,'commandMs','commandSamples'),
        avg(p,'netGapMs','netGapSamples'),number(p.netMaxGapMs).toFixed(0),count(p.netOver500),count(p.probeFailures)+' / '+count(p.reconnects)]);
    }
  }
  const metricRows=Object.entries(data.server||{}).map(([key,m])=>[({tickWorkMs:'模拟计算',tickIntervalMs:'模拟帧间隔（目标约 50ms）',tickLockWaitMs:'模拟等待房间锁',snapshotBuildMs:'生成状态（含等锁）',snapshotEncodeMs:'状态编码'}[key]||key),count(m.count),m.count?(m.sum/m.count).toFixed(2):'—',number(m.max).toFixed(2)]);
  return '<h3>服务器汇总：各玩家画面与网络</h3>'+detailTable(['玩家 / 浏览器会话','数据状态','平均 FPS','p95 帧间隔','探测 RTT 均值 ms','指令 RTT 均值 ms','状态间隔均值 ms','最长状态间隔 ms','>500ms 间隔','探测失败 / 重连事件'],rows)+
    '<h3>服务器处理耗时</h3>'+detailTable(['环节','样本数','平均 ms','最大 ms'],metricRows)+
    '<p class="report-note">RTT 包含调度和服务端处理，不是纯网络 ping；状态间隔不是单程延迟；指令 RTT 不含本地命令队列等待。每人最多保留 4 个浏览器会话，超出数量见 JSON omittedRuns。客户端关闭前未送达的数据无法追补。详细时间段、发送字节与写出耗时保存在 JSON / CSV。</p>';
}

function detailTable(headers, rows) {
  return '<div class="report-table-wrap" tabindex="0"><table class="report-table"><thead><tr>' +
    headers.map(h => '<th>' + esc(h) + '</th>').join('') + '</tr></thead><tbody>' +
    (rows.length ? rows.map(row => '<tr>' + row.map(v => '<td>' + esc(v) + '</td>').join('') + '</tr>').join('') :
      '<tr><td colspan="' + headers.length + '">暂无记录</td></tr>') + '</tbody></table></div>';
}

function detailedPanel(report, playerId) {
  const players = Object.fromEntries(report.players.map(p => [p.id,p]));
  return '<p class="report-note">有效伤害仅计敌对玩家实际扣血，排除溢出伤害、中立单位和友伤；按命中时敌我关系统计。伤害贡献与最后一击击毁价值分开计算。以下数量均为整局累计，存量为终局快照。</p>' +
    report.players.map(p => '<details class="report-operations"' + (p.id === playerId ? ' open' : '') + '><summary>' +
      esc(p.name) + ' · 有效伤害 ' + count(p.damageDealt) + ' · 承伤 ' + count(p.damageTaken) +
      ' · 矿车携矿损失 ' + money(p.cargoLost) + '</summary><h3>兵种与建筑贡献</h3>' +
      detailTable(['兵种 / 来源','产出原价','首次完成','末次完成','对兵伤害','对建筑伤害','有效承伤','终局存量','存量原价'],
        Object.values(p.byKind || {}).map(k => [k.name,money(k.producedValue),battleTime(k.firstProducedAt),battleTime(k.lastProducedAt),
          count(k.unitDamage),count(k.structureDamage),count(k.damageTaken),count(k.remaining),money(k.remainingValue)])) +
      '<h3>与各玩家的交战</h3>' + detailTable(['对手','造成伤害','受到伤害','击毁兵 / 建筑','其中矿车','击毁价值','被其击毁价值','交换比'],
        Object.entries(p.opponents || {}).map(([id,o]) => [(players[id] || {}).name || '未知玩家',count(o.damageDealt),count(o.damageTaken),
          count(o.unitsDestroyed) + ' / ' + count(o.structuresDestroyed),count(o.harvestersDestroyed),money(o.destroyedValue),money(o.lostValue),exchangeLabel(o)])) +
      '<h3>战损来源</h3>' + detailTable(['原因','单位损失','建筑损失','损失原价'],
        Object.entries(p.lossCauses || {}).map(([cause,s]) => [lossCauseLabels[cause] || cause,count(s.units),count(s.structures),money(s.value)])) + '</details>').join('') +
    '<p class="report-note">产出原价不是实际支出：只统计完成的生产 / 建造，不含撤单、在建、初始赠送和基地折叠展开。存量不含已淘汰玩家的遗留实体或未完工建筑。携矿损失为被毁矿车尚未卸载的矿，不计入单位原价战损，避免重复计价。伤害可因维修和回血超过目标最大生命。旧版档案不会补造历史数据。</p>';
}

export function renderBattleReport(report, playerId) {
  const players = Object.fromEntries(report.players.map(row => [row.id, row]));
  const rows = report.players.map(row => '<tr' + (row.id === playerId ? ' class="report-self"' : '') + '><th scope="row">' +
    '<div class="report-player">' + playerLabel(row, row.id === playerId) + '</div><small>' +
    (row.faction === 'magic' ? '秘法会' : '钢铁军团') + ' · ' + status(row) +
    (row.team ? ' · 第' + number(row.team) + '队' : '') + '</small></th><td>' + money(row.harvested) +
    '<small>战利 +' + money(row.combatRewardsEarned) + '</small></td><td>' + count(row.unitsDestroyed) + ' / ' + count(row.structuresDestroyed) +
    '</td><td>' + count(row.unitsLost) + ' / ' + count(row.structuresLost) + '</td><td>' + money(row.destroyedValue) +
    '</td><td>' + money(row.lostValue) + '<small>自爆 ' + money(row.selfConsumedValue) + '</small></td><td>' +
    exchangeLabel(row) + '</td><td>' + money(row.peakArmyValue) + '<small>终局 ' + money(row.endingArmyValue) + '</small></td></tr>').join('');
  const opening = report.players.map(row => '<tr><th scope="row">' + esc(row.name) + '</th><td>' + battleTime(row.firstCombatAt) +
    '</td><td>' + (row.eliminatedAt == null ? '存活至终局' : battleTime(row.eliminatedAt)) + '</td><td>' + status(row) + '</td></tr>').join('');
  const events = (report.events || []).map(event => '<li><time>' + battleTime(event.time) + '</time><span>' +
    esc(eventText(event, players)) + '</span></li>').join('');
  const legend = report.players.map((row, index) => '<span><svg width="24" height="8" aria-hidden="true"><line x1="0" x2="24" y1="4" y2="4" stroke="' +
    color(row.color) + '" stroke-width="2" stroke-dasharray="' + ['', '8 3', '3 3', '10 3 2 3', '2 2'][index % 5] + '"/></svg>' + esc(row.name) + '</span>').join('');
  return '<div class="report-heading"><span>战区档案 / AFTER ACTION REPORT</span><strong>' + esc(report.mapName) + '</strong></div>' +
    '<nav class="report-tabs" aria-label="战报栏目"><button type="button" data-report-tab="overview" aria-pressed="true">全员总览</button>' +
    '<button type="button" data-report-tab="curves" aria-pressed="false">经济与军力</button><button type="button" data-report-tab="events" aria-pressed="false">关键时间线</button>' +
    '<button type="button" data-report-tab="operations" aria-pressed="false">兵种与运营</button>' +
    (report.version >= 3 ? '<button type="button" data-report-tab="details" aria-pressed="false">交战与贡献明细</button>' : '') +
    (report.version >= 4 ? '<button type="button" data-report-tab="phases" aria-pressed="false">阶段复盘</button><button type="button" data-report-tab="finance" aria-pressed="false">资金收支</button>' : '') + '</nav>' +
    '<section data-report-panel="overview"><div class="report-table-wrap" tabindex="0" aria-label="全员战报，可横向滚动"><table class="report-table">' +
    '<thead><tr><th>指挥官</th><th>采集收入</th><th>击毁<br>兵 / 建筑</th><th>损失<br>兵 / 建筑</th><th>摧毁价值</th><th>损失价值</th><th>交换比</th><th>采样军力峰值</th></tr></thead><tbody>' + rows + '</tbody></table></div>' +
    '<p class="report-note">价值按目录原价计算，包含初始赠送单位。击毁只计敌方玩家；损失含主动自爆、中立和环境伤害，不含出售、基地折叠 / 展开、淘汰撤军及退场后的遗留建筑。交换比＝摧毁价值 ÷ 损失价值。</p></section>' +
    '<section data-report-panel="curves" class="hidden"><div class="report-legend">' + legend + '</div><div class="report-charts">' +
    chart(report, 0, '累计采集收入', '只计矿车卸矿到账，不含初始资金、补给箱或战斗奖励。') +
    chart(report, 2, '现存作战部队价值', '不含矿车、基地车、建筑与队列；按原价计，不随残血或军衔折算。') + '</div>' +
    '<p class="report-note">初始每 5 秒采样；长局自动稀疏，当前采样间隔约 ' + number(report.sampleInterval) +
    ' 秒。峰值为采样峰值，可能略过短暂变化；淘汰后的军力归零是部队退场，不代表全部被击毁。</p>' + performancePanel(report) + renderDiagnostics(report.serverDiagnostics) + '</section>' +
    '<section data-report-panel="events" class="hidden"><div class="report-table-wrap"><table class="report-table report-times"><thead><tr><th>指挥官</th><th>首次交战</th><th>退场时间</th><th>最终结果</th></tr></thead><tbody>' + opening +
    '</tbody></table></div><h3>战局节点</h3><ol class="report-events">' + (events || '<li>本局未发生玩家交战或关键建筑损失。</li>') + '</ol>' +
    (report.droppedEvents ? '<p class="report-note">长局已省略 ' + count(report.droppedEvents) + ' 条事件，汇总数值不受影响。</p>' : '') + '</section>' +
    '<section data-report-panel="operations" class="hidden">' + operationsPanel(report,playerId) + '</section>' +
    (report.version >= 3 ? '<section data-report-panel="details" class="hidden">' + detailedPanel(report,playerId) + '</section>' : '') +
    (report.version >= 4 ? '<section data-report-panel="phases" class="hidden">' + phasesPanel(report,playerId) + '</section>' +
      '<section data-report-panel="finance" class="hidden">' + financePanel(report,playerId) + '</section>' : '');
}

export function reportCsv(report) {
  // Defuse spreadsheet formulas in player names before quoting cells.
  const cell = value => {
    let text = String(value == null ? '' : value);
    if (/^[\s]*[=+@-]/.test(text) || /^[\t\r\n]/.test(text)) text = "'" + text;
    return '"' + text.replace(/"/g, '""') + '"';
  };
  const players = Object.fromEntries(report.players.map(row => [row.id, row]));
  const rows = [['赤潮战报', report.mapName, '时长', battleTime(report.duration)],
    ['统计口径', '价值按原价；损失含自爆/环境，不含出售/折叠/淘汰撤离/退场后遗留建筑；采集不含初始/补给/奖励；军力不含矿车/基地车/建筑'],
    ['玩家', '阵营', '最终队伍', '结果', '采集资金', '战斗奖励', '击毁单位', '击毁建筑', '损失单位', '损失建筑',
      '摧毁价值', '损失价值', '自爆消耗', '交换比', '采样军力峰值', '终局军力', '首次交战', '退场时间']];
  report.players.forEach(p => rows.push([p.name, p.faction === 'magic' ? '秘法会' : '钢铁军团', p.team, status(p),
    p.harvested, p.combatRewardsEarned, p.unitsDestroyed, p.structuresDestroyed, p.unitsLost, p.structuresLost,
    p.destroyedValue, p.lostValue, p.selfConsumedValue, exchangeLabel(p), p.peakArmyValue, p.endingArmyValue,
    battleTime(p.firstCombatAt), p.eliminatedAt == null ? '存活至终局' : battleTime(p.eliminatedAt)]));
  const perf=report.clientPerformance;
  if(report.incomplete)rows.push([],['存档状态','中途快照，非终局战报，结果和终局数值可能未形成']);
  const diagnostics=report.serverDiagnostics;
  if(diagnostics) {
    rows.push([],['服务器诊断口径','客户端性能为玩家自报；RTT含调度/服务端处理；状态间隔非ping；无样本不是零延迟']);
    rows.push(['服务器耗时'],['环节','次数','合计ms','最大ms']);
    Object.entries(diagnostics.server||{}).forEach(([k,m])=>rows.push([k,m.count,m.sum,m.max]));
    rows.push([],['服务器耗时时间段'],['起始秒','区间秒数','环节','次数','合计ms','最大ms']);
    (diagnostics.periods||[]).forEach(p=>Object.entries(p.metrics||{}).forEach(([k,m])=>rows.push([p.time,diagnostics.interval,k,m.count,m.sum,m.max])));
    const fields=['time','frames','ms','averageFps','over50','over100','maxMs','minScale','maxUnits','maxDrawCalls','maxTriangles','maxParticles','maxGeometries','maxTextures','probeSamples','probeMs','probeMaxMs','probeFailures','commandSamples','commandMs','commandMaxMs','commandFailures','netMessages','netGapSamples','netGapMs','netMaxGapMs','netOver500','parseMs','parseMaxMs','reconnects'];
    rows.push([],['全员客户端诊断'],['玩家','浏览器会话','区间秒数','服务器收到时间',...fields]);
    for(const player of diagnostics.players||[]) {
      const entry=(diagnostics.clients||{})[player.id];
      if(!entry?.runs?.length){rows.push([player.name,player.isBot?'AI':'未收到上报']);continue;}
      for(const p of entry.runs) {
        rows.push([player.name,p.clientRunId,'整次会话',p.receivedAt,...fields.map(k=>p[k])]);
        rows.push([player.name,p.clientRunId,'明细收到时间',p.detailReceivedAt||'未收到','p95帧间隔ms',p.p95Ms,'画面设置',JSON.stringify(p.settings||{})]);
        for(const r of p.periods||[])rows.push([player.name,p.clientRunId,p.interval,p.receivedAt,...fields.map(k=>r[k])]);
      }
      rows.push([player.name,'省略浏览器会话',entry.omittedRuns]);
      rows.push([player.name,'服务端发送统计（snapshotBytes单位为字节、writeMs为毫秒）',JSON.stringify(entry.transport||{})]);
    }
  }
  if(perf && perf.matchId===report.matchId) {
    rows.push([],['本机性能摘要'],['记录玩家','平均FPS','p95帧间隔ms','p95是否超量程','超过50ms帧数','超过100ms帧数','记录毫秒','记录帧数','最低渲染比例'],
      [(players[perf.viewerId] || {}).name || perf.viewerId,perf.averageFps,perf.p95Ms,!!perf.p95Overflow,perf.over50,perf.over100,perf.ms,perf.frames,perf.minScale]);
    rows.push([],['本机性能时间段'],['起始秒','区间秒数','平均FPS','帧数','记录毫秒','超过50ms帧数','超过100ms帧数','最长帧ms','画面单位峰值','绘制调用峰值','三角形峰值','粒子峰值','几何资源峰值','纹理资源峰值','最低渲染比例']);
    (perf.periods || []).forEach(r=>rows.push([r.time,perf.interval,r.averageFps,r.frames,r.ms,r.over50,r.over100,r.maxMs,r.maxUnits,r.maxDrawCalls,r.maxTriangles,r.maxParticles,r.maxGeometries,r.maxTextures,r.minScale]));
    rows.push([],['性能口径','仅本机前台；帧间隔不是GPU耗时；负载每秒采样；资源数不是显存；不同峰值不一定同时发生。'],['开局画面配置',JSON.stringify(perf.settings || {})]);
  }
  rows.push([], ['分兵种统计'], ['玩家','兵种 / 来源','生产完成','初始','赠送','损失数量','损失价值','击毁数量','击毁价值']);
  report.players.forEach(p => Object.values(p.byKind || {}).forEach(k => rows.push([
    p.name,k.name,k.produced,k.initial,k.gifted,k.lost,k.lostValue,k.destroyed,k.destroyedValue])));
  if (report.version >= 3) {
    rows.push([], ['伤害与携矿损失'], ['玩家','有效伤害','有效承伤','被毁矿车携矿损失']);
    report.players.forEach(p => rows.push([p.name,p.damageDealt,p.damageTaken,p.cargoLost]));
    rows.push([], ['兵种与建筑贡献'], ['玩家','兵种 / 来源','产出原价','首次完成','末次完成','有效伤害','对兵伤害','对建筑伤害','有效承伤','终局存量','存量原价']);
    report.players.forEach(p => Object.values(p.byKind || {}).forEach(k => rows.push([p.name,k.name,k.producedValue,
      battleTime(k.firstProducedAt),battleTime(k.lastProducedAt),k.damageDealt,k.unitDamage,k.structureDamage,k.damageTaken,k.remaining,k.remainingValue])));
    rows.push([], ['玩家交战明细'], ['玩家','对手','造成伤害','受到伤害','击毁单位','击毁建筑','其中矿车','击毁价值','被其击毁价值','交换比']);
    report.players.forEach(p => Object.entries(p.opponents || {}).forEach(([id,o]) => rows.push([p.name,(players[id] || {}).name || '未知玩家',
      o.damageDealt,o.damageTaken,o.unitsDestroyed,o.structuresDestroyed,o.harvestersDestroyed,o.destroyedValue,o.lostValue,exchangeLabel(o)])));
    rows.push([], ['战损来源'], ['玩家','原因','单位损失','建筑损失','损失原价']);
    report.players.forEach(p => Object.entries(p.lossCauses || {}).forEach(([cause,s]) => rows.push([p.name,lossCauseLabels[cause] || cause,s.units,s.structures,s.value])));
    rows.push([], ['明细口径','伤害仅计敌对玩家实际扣血，不含溢出、中立与友伤；击毁归最后一击；产出为目录原价非实际支出，折叠展开不计生产；终局存量不含在建或已淘汰遗留实体；携矿损失单列，不并入原价战损。']);
  }
  if (report.version >= 4) {
    rows.push([], ['分阶段复盘'], ['玩家',...phaseHeaders]);
    report.players.forEach(p => phaseRows(report,p).forEach(row => rows.push([p.name,...row])));
    rows.push([], ['真实资金收支'], ['玩家','项目','流入','流出']);
    report.players.forEach(p => Object.entries(flowLabels).forEach(([key,label]) => rows.push([p.name,label,
      flowIncome.has(key) ? (p.cashFlow || {})[key] || 0 : 0,flowIncome.has(key) ? 0 : (p.cashFlow || {})[key] || 0])));
    rows.push([], ['持币与核对'], ['玩家','开局资金','结束资金','平均持币','持币不少于5000秒数','观察秒数','收支核对差额']);
    report.players.forEach(p => rows.push([p.name,p.openingCash,p.closingCash,p.averageCash,p.highCashSeconds,p.cashObservedSeconds,p.cashReconciliation]));
    rows.push([], ['生产受阻'], ['玩家','原因','等效损失秒数']);
    report.players.forEach(p => Object.entries(delayLabels).forEach(([key,label]) => rows.push([p.name,label,(p.productionDelay || {})[key] || 0])));
    rows.push([], ['关键战损片段'], ['开始','结束','双方损失价值','玩家','损失构成','损失价值','击毁对方价值','交换比']);
    (report.engagements || []).forEach(e => engagementRows(report,e).forEach(row => rows.push([battleTime(e.start),battleTime(e.end),e.value,...row])));
    rows.push([], ['阶段口径','时间段左闭右开；长局合并保留合计；片段按同一对手20秒内连续击毁合并，不等于单一地点的战斗；仅保留高价值24段。'],
      ['省略片段',report.omittedEngagements || 0],['资金口径','真实支付与产出原价分开；退款回款单列；缺电等效损失多队列叠加；高持币不自动判定为失误。']);
  }
  rows.push([], ['运营统计'], ['玩家','矿车损失','到账中断次数','中断秒数','最长中断秒数']);
  report.players.forEach(p => rows.push([p.name,p.harvestersLost,p.incomeGapCount,p.incomeGapSeconds,p.longestIncomeGap]));
  rows.push([], ['首次科技建筑落成'], ['玩家','建筑','时间','初始建筑']);
  report.players.forEach(p => Object.values(p.techTimes || {}).forEach(t => rows.push([p.name,t.name,battleTime(t.time),t.initial ? '是' : '否'])));
  rows.push([], ['运营口径','首次卸矿后，连续 30 秒无卸矿到账才开始计中断；正常往返和主动停采也可能触发，不自动归因为骚扰。击毁按最后一击归属，不是伤害贡献。']);
  rows.push([], ['关键时间线'], ['时间', '事件']);
  (report.events || []).forEach(event => rows.push([battleTime(event.time), eventText(event, players)]));
  rows.push([], ['采样数据'], ['时间（秒）', '玩家', '累计采集', '持有资金', '作战部队价值']);
  (report.samples || []).forEach(point => report.players.forEach(player => {
    rows.push([point.time, player.name, ...(point.players[player.id] || [0, 0, 0])]);
  }));
  return '\ufeff' + rows.map(row => row.map(cell).join(',')).join('\r\n');
}
