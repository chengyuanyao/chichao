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
    Object.values(p.byKind || {}).map(k => '<tr><th>' + esc(k.name) + '</th><td>' + (k.category === 'unit' ? count(k.produced) : '—') +
      '</td><td>' + (k.category === 'unit' ? count(k.initial) + ' / ' + count(k.gifted) : '—') + '</td><td>' + count(k.lost) +
      '</td><td>' + money(k.lostValue) + '</td><td>' + count(k.destroyed) + '</td><td>' + money(k.destroyedValue) + '</td></tr>').join('') +
    '</tbody></table></div><h3>首次科技建筑落成</h3><div class="report-tech-times">' +
    Object.values(p.techTimes || {}).map(t => '<span>' + esc(t.name) + ' <strong>' + battleTime(t.time) +
      (t.initial ? ' · 初始' : '') + '</strong></span>').join('') + '</div></details>').join('') +
    '<p class="report-note">生产仅计实际出厂，不含排队、撤单、初始和精炼厂赠车；折叠 / 展开不重复计产量。击毁价值按完成最后一击的兵种归属，弹丸发射者阵亡后仍可追溯；炮塔与轨道等来源单列，不等于总伤害贡献。</p>' +
    '<p class="report-note">到账中断：首次卸矿后，连续 30 秒无卸矿到账才开始计时，到账、退场或终局结束计时。不含开局找矿时间，正常采矿往返、主动停采也可能触发，不自动判定为敌方骚扰。科技时间计第一次建筑落成，而非开始排队。</p>';
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
    '<button type="button" data-report-tab="operations" aria-pressed="false">兵种与运营</button></nav>' +
    '<section data-report-panel="overview"><div class="report-table-wrap" tabindex="0" aria-label="全员战报，可横向滚动"><table class="report-table">' +
    '<thead><tr><th>指挥官</th><th>采集收入</th><th>击毁<br>兵 / 建筑</th><th>损失<br>兵 / 建筑</th><th>摧毁价值</th><th>损失价值</th><th>交换比</th><th>采样军力峰值</th></tr></thead><tbody>' + rows + '</tbody></table></div>' +
    '<p class="report-note">价值按目录原价计算，包含初始赠送单位。击毁只计敌方玩家；损失含主动自爆、中立和环境伤害，不含出售、基地折叠 / 展开、淘汰撤军及退场后的遗留建筑。交换比＝摧毁价值 ÷ 损失价值。</p></section>' +
    '<section data-report-panel="curves" class="hidden"><div class="report-legend">' + legend + '</div><div class="report-charts">' +
    chart(report, 0, '累计采集收入', '只计矿车卸矿到账，不含初始资金、补给箱或战斗奖励。') +
    chart(report, 2, '现存作战部队价值', '不含矿车、基地车、建筑与队列；按原价计，不随残血或军衔折算。') + '</div>' +
    '<p class="report-note">初始每 5 秒采样；长局自动稀疏，当前采样间隔约 ' + number(report.sampleInterval) +
    ' 秒。峰值为采样峰值，可能略过短暂变化；淘汰后的军力归零是部队退场，不代表全部被击毁。</p></section>' +
    '<section data-report-panel="events" class="hidden"><div class="report-table-wrap"><table class="report-table report-times"><thead><tr><th>指挥官</th><th>首次交战</th><th>退场时间</th><th>最终结果</th></tr></thead><tbody>' + opening +
    '</tbody></table></div><h3>战局节点</h3><ol class="report-events">' + (events || '<li>本局未发生玩家交战或关键建筑损失。</li>') + '</ol>' +
    (report.droppedEvents ? '<p class="report-note">长局已省略 ' + count(report.droppedEvents) + ' 条事件，汇总数值不受影响。</p>' : '') + '</section>' +
    '<section data-report-panel="operations" class="hidden">' + operationsPanel(report,playerId) + '</section>';
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
  rows.push([], ['分兵种统计'], ['玩家','兵种 / 来源','生产完成','初始','赠送','损失数量','损失价值','击毁数量','击毁价值']);
  report.players.forEach(p => Object.values(p.byKind || {}).forEach(k => rows.push([
    p.name,k.name,k.produced,k.initial,k.gifted,k.lost,k.lostValue,k.destroyed,k.destroyedValue])));
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
