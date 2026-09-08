import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import vm from 'node:vm';
import {battleTime, exchangeLabel, renderReportSummary, renderBattleReport, reportCsv} from '../public/battle_report.js';

const me = {id:'p1',name:'指挥官甲',color:'#42d9ff',faction:'tech',team:1,won:true,
  harvested:10000,cash:1000,combatRewardsEarned:100,unitsDestroyed:3,structuresDestroyed:1,
  unitsLost:1,structuresLost:0,destroyedValue:1800,lostValue:900,selfConsumedValue:0,
  peakArmyValue:2800,endingArmyValue:1800,firstCombatAt:0,eliminatedAt:null};
const enemy = {...me,id:'p2',name:'=HYPERLINK("bad")<img src=x onerror=alert(1)>',color:'red;" onload="alert(1)',
  faction:'magic',won:false,eliminatedAt:65,exitReason:'commandLost'};
const report = {matchId:'g-test',mapName:'测试战区',duration:65,firstCombatAt:0,players:[me,enemy],sampleInterval:5,droppedEvents:0,
  samples:[{time:0,players:{p1:[0,6800,0],p2:[0,6800,0]}},{time:65,players:{p1:[10000,1000,1800],p2:[9500,500,0]}}],
  events:[{time:0,type:'firstCombat',sourceId:'p1',playerId:'p2'},
    {time:65,type:'eliminated',playerId:'p2',reason:'commandLost'}]};
assert.equal(battleTime(null),'未发生'); assert.equal(battleTime(0),'0:00'); assert.equal(battleTime(65),'1:05');
assert.equal(exchangeLabel({destroyedValue:100,lostValue:0}),'无损');
assert.equal(exchangeLabel({destroyedValue:0,lostValue:0}),'—');
assert.equal(exchangeLabel(me),'2.00 : 1');
const html = renderBattleReport(report,'p1');
assert.equal((html.match(/data-report-panel=/g)||[]).length,3);
assert.equal((html.match(/class="report-chart"/g)||[]).length,2);
assert.equal((html.match(/<polyline /g)||[]).length,4);
assert.ok(html.includes('report-self') && html.includes('初始每 5 秒'));
assert.ok(!html.includes('<img') && !html.includes('stroke="red;'));
assert.ok(html.includes('&lt;img') && html.includes('失去全部指挥实体'));
assert.ok(renderReportSummary(report,'p1').includes('2.00 : 1'));
assert.ok(reportCsv(report).startsWith('\ufeff'));
assert.ok(reportCsv(report).includes('"\'=HYPERLINK'));
assert.ok(reportCsv(report).includes('采样数据'));
for (const samples of [[],[{time:0,players:{p1:[0,0,0],p2:[0,0,0]}}]]) {
  const empty = renderBattleReport({...report,duration:0,firstCombatAt:null,events:[],samples},'p1');
  assert.ok(!/NaN|Infinity/.test(empty));
}

// Execute the actual async loader: one post-match request, cached result, retry
// state and stale response isolation when the player leaves or starts a new game.
const app=readFileSync(new URL('../public/app.js',import.meta.url),'utf8');
const loader=app.match(/  async function loadBattleReport\([^]*?\n  \}/)[0];
const dom=new Map();
function element(id) {
  if(!dom.has(id)) dom.set(id,{textContent:'',innerHTML:'',disabled:false,classList:{add(){},remove(){}}});
  return dom.get(id);
}
let complete;
const context={session:{roomId:'test',playerId:'p1',token:'test-only'},roomState:{status:'finished',game:{matchId:'g-test'}},
  completedBattleReport:null,reportRequestSerial:0,$:element,
  request:()=>new Promise(resolve=>{complete=resolve;}),renderBattleReport,renderReportSummary,encodeURIComponent};
vm.createContext(context);vm.runInContext(loader,context);
const pending=context.loadBattleReport();complete({report});await pending;
assert.equal(context.completedBattleReport.matchId,'g-test');assert.equal(element('#exportReportBtn').disabled,false);
const old=context.loadBattleReport();context.session=null;complete({report});await old;
assert.equal(element('#battleReport').textContent,'正在整理本局战报…','stale response must not paint another room');
context.session={roomId:'next',playerId:'p1',token:'next'};
const mismatch=context.loadBattleReport();complete({report:{...report,matchId:'wrong'}});await mismatch;
assert.ok(element('#battleReport').textContent.includes('不匹配'));
context.roomState.status='playing';complete=null;await context.loadBattleReport();assert.equal(complete,null);
console.log('Battle report UI: charts, tables, zero denominators, safe CSV/HTML, loader privacy and stale-session isolation passed.');
