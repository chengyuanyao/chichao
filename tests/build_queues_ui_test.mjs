import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
import {BUILD_LANES,buildingQueue,readyBuildings,queueCaption} from '../public/build_queues.js';
const BUILDINGS={power:{name:'电厂',role:'power'},turret:{name:'炮塔',role:'defense'},mtower:{name:'奥术塔',role:'defense'}};
const p={buildQueue:[{id:'a',kind:'power',ready:true,total:8,remaining:0}],defenseQueue:[{id:'b',kind:'turret',ready:true,total:12,remaining:0}]};
assert.equal(buildingQueue(p,'power',BUILDINGS),p.buildQueue);
assert.equal(buildingQueue(p,'turret',BUILDINGS),p.defenseQueue);
assert.equal(buildingQueue(p,'mtower',BUILDINGS),p.defenseQueue);
assert.equal(readyBuildings(p).length,2);
assert.match(queueCaption(p.defenseQueue[0],'防御',BUILDINGS,false),/待展开/);
const app=fs.readFileSync(new URL('../public/app.js',import.meta.url),'utf8');
function fn(name){const source=app.match(new RegExp('  function '+name+'\\([^]*?\\n  \\}'));assert.ok(source,name);return source[0];}
const calls=[],notes=[];
const context=vm.createContext({BUILDINGS,BUILD_LANES,buildingQueue,readyBuildings,queueCaption,Set,
  ownPlayer:()=>p,hasConstructionAuthority:()=>true,lastReadyBuildIds:new Set(),buildMode:null,commandMode:null,
  toast:message=>notes.push(message),sound:()=>{},UNITS:{},
  sendAction:async(action,payload)=>calls.push({action,...payload})});
vm.runInContext('function activateBuildMode(kind){buildMode=kind;} function cancelModes(){buildMode=null;commandMode=null;}',context);
for(const name of ['syncPreparedBuilding','handleBuildingCard','cancelProduction'])vm.runInContext(fn(name),context);
context.syncPreparedBuilding();assert.equal(context.buildMode,'power');assert.equal(notes.length,2);
context.syncPreparedBuilding();assert.equal(notes.length,2,'no repeated completion notifications');
context.buildMode='turret';context.syncPreparedBuilding();assert.equal(context.buildMode,'turret','other lane does not steal cursor');
context.cancelProduction('power',true);await new Promise(setImmediate);
assert.equal(calls[0].structureType,'power');assert.equal(calls[0].queueId,'a');assert.equal(context.buildMode,'turret');
context.handleBuildingCard('turret',{shiftKey:true});await new Promise(setImmediate);
assert.equal(calls[1].structureType,'turret');assert.equal(calls[1].queueId,'b');assert.equal(context.buildMode,null);
context.handleBuildingCard('mtower',{shiftKey:true});await new Promise(setImmediate);
assert.equal(calls.length,2,'wrong card cannot cancel another task in the same lane');
context.buildMode='power';context.hasConstructionAuthority=()=>false;context.syncPreparedBuilding();assert.equal(context.buildMode,null);
context.hasConstructionAuthority=()=>true;context.handleBuildingCard('turret');assert.equal(context.buildMode,'turret');
p.defenseQueue=[];context.syncPreparedBuilding();assert.equal(context.buildMode,null,'stale ghost removed');
context.handleBuildingCard('turret');await new Promise(setImmediate);
assert.equal(calls.at(-1).command,'prepareBuild','ready economy slot does not block defense request');
assert.equal(calls.at(-1).structureType,'turret');

// Exercise the actual production grid's filtering, enabled state and tab switching.
function element(){return {dataset:{},style:{setProperty(){}},classList:{remove(){},add(){},toggle(){},contains(){return false;}},
  setAttribute(){},removeAttribute(){},addEventListener(){},querySelector(selector){return selector.includes('portrait')?{getContext:()=>({drawImage(){}})}:{style:{}};}};}
const cards=[];const grid={dataset:{},set innerHTML(_){cards.length=0;},appendChild(card){cards.push(card);},querySelectorAll(){return cards;}};
for(const b of Object.values(BUILDINGS))Object.assign(b,{requires:[],faction:'tech',cost:100,build:8});
const laneNodes={};for(const key of BUILD_LANES)laneNodes['#'+key+'Status']=element();
Object.assign(context,{$:selector=>laneNodes[selector],$$:()=>[],commandGrid:grid,roomState:{game:{}},currentScreen:'game',gameKey:'test',
  activeTab:'defense',hasOwnActiveHeadquarters:()=>true,hasStructure:()=>true,portraitFor:()=>({}),document:{createElement:element},roomHasMobileConstruction:()=>true});
p.cash=10000;
for(const name of ['renderBuildQueueStatus','renderCommandGrid','activateCommandTab'])vm.runInContext(fn(name),context);
context.renderCommandGrid(true);
assert.ok(cards.length);assert.deepEqual(cards.map(c=>c.dataset.kind),['turret','mtower']);
assert.ok(cards.every(c=>c.dataset.type==='building'&&!c.disabled));
const tab=element();tab.dataset.tab='buildings';context.activateCommandTab(tab);
assert.deepEqual(cards.map(c=>c.dataset.kind),['power']);
tab.dataset.tab='defense';context.activateCommandTab(tab);assert.equal(context.activeTab,'defense');
assert.ok(laneNodes['#buildQueueStatus'].textContent.includes('待部署'));
console.log('Build queue UI passed: faction roles, separate cards, parallel availability, scoped cancel, two ready tasks, authority and stable placement cursor.');
