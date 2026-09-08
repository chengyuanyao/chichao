import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import vm from 'node:vm';

const app=readFileSync(new URL('../public/app.js',import.meta.url),'utf8');
function sourceFunction(name) {
  const source=app.match(new RegExp('  function '+name+'\\([^]*?\\n  \\}'));
  assert.ok(source,name);return source[0];
}
function sourceListener(target,event) {
  const source=app.match(new RegExp(target+"\\.addEventListener\\('"+event+"', function \\(event\\) \\{[^]*?\\n  \\}\\);"));
  assert.ok(source,target+event);return source[0];
}

// Actual command dispatcher under delayed/reordered HTTP completion.
const sent=[],waiting=[];
const queue={session:{playerId:'me'},gameKey:'room:match1',unitCommandTail:Promise.resolve(),pendingUnitCommands:[],
  performAction(action,payload){sent.push({...payload,unitIds:payload.unitIds?.slice()});
    return new Promise((resolve,reject)=>waiting.push({resolve,reject}));}};
vm.createContext(queue);vm.runInContext(sourceFunction('sendAction'),queue);
const drain=()=>new Promise(resolve=>setImmediate(resolve));
const first=queue.sendAction('command',{command:'patrol',unitIds:['dog'],x:100,y:200});
const second=queue.sendAction('command',{command:'patrol',unitIds:['dog'],x:300,y:400});
const third=queue.sendAction('command',{command:'patrol',unitIds:['dog'],x:500,y:600});
await drain();assert.equal(sent.length,1);
waiting.shift().resolve({});await first;await drain();assert.equal(sent[1].x,300);
waiting.shift().resolve({});await second;await drain();assert.equal(sent[2].x,500);
waiting.shift().resolve({});await third;
const blocked=queue.sendAction('command',{command:'patrol',unitIds:['dog'],x:700,y:600});
await drain();
const unsent=queue.sendAction('command',{command:'patrol',unitIds:['dog'],x:800,y:600});
const stop=queue.sendAction('command',{command:'stop',unitIds:['dog']});
waiting.shift().resolve({});await blocked;await drain();
assert.equal((await unsent).cancelled,true);assert.equal(sent.at(-1).command,'stop');
waiting.shift().resolve({});await stop;
const failure=queue.sendAction('command',{command:'patrol',unitIds:['dog'],x:900,y:600});
const caught=assert.rejects(failure,/test failure/);
const recovery=queue.sendAction('command',{command:'patrol',unitIds:['dog'],x:1000,y:600});
await drain();waiting.shift().reject(new Error('test failure'));await caught;await drain();
assert.equal(sent.at(-1).x,1000);waiting.shift().resolve({});await recovery;
const inFlight=queue.sendAction('command',{command:'patrol',unitIds:['dog'],x:1100,y:600});
await drain();const stale=queue.sendAction('command',{command:'patrol',unitIds:['dog'],x:1200,y:600});
queue.gameKey='room:match2';waiting.shift().resolve({});await inFlight;
assert.equal((await stale).cancelled,true);assert.notEqual(sent.at(-1).x,1200);

// Real pointer handlers: Shift right click must take precedence over contextual
// attacks/mining; ordinary right click and Shift additive left selection remain.
const calls=[],handlers={};
const input={selectedUnits:new Set(['dog']),selectedStructureId:null,selectedResourceId:null,
  buildMode:null,commandMode:null,pointer:{x:20,y:30,worldX:200,worldY:300},
  canvas:{addEventListener:(e,f)=>handlers['canvas:'+e]=f,focus(){},setPointerCapture(){}},
  minimap:{addEventListener:(e,f)=>handlers['minimap:'+e]=f},
  ensureAudio(){},pointerPosition(){},roomState:{game:{}},
  minimapWorldFromEvent:()=>({x:1800,y:1700}),
  issuePatrolCommand:(x,y)=>calls.push(['patrol',x,y]),
  issueContextCommand:(x,y)=>calls.push(['context',x,y]),
  issueGroundCommand:(x,y)=>calls.push(['ground',x,y]),
  cancelModes:()=>calls.push(['cancel']),camera:{},clampCamera(){},commanderPlayActive:()=>false};
vm.createContext(input);
vm.runInContext(sourceFunction('isAdditiveSelect')+sourceListener('canvas','pointerdown')+sourceListener('minimap','pointerdown'),input);
const event={button:2,shiftKey:true,preventDefault(){}};
handlers['canvas:pointerdown'](event);assert.deepEqual(calls.pop(),['patrol',200,300]);
handlers['minimap:pointerdown'](event);assert.deepEqual(calls.pop(),['patrol',1800,1700]);
handlers['canvas:pointerdown']({...event,shiftKey:false});assert.equal(calls.pop()[0],'context');
handlers['minimap:pointerdown']({...event,shiftKey:false});assert.equal(calls.pop()[0],'ground');
handlers['canvas:pointerdown']({...event,button:0});assert.equal(input.dragging.additive,true);
assert.deepEqual([...input.selectedUnits],['dog']);
input.buildMode='power';handlers['canvas:pointerdown'](event);assert.equal(calls.pop()[0],'cancel');
input.buildMode=null;input.selectedUnits.clear();handlers['minimap:pointerdown'](event);assert.equal(calls.length,0);

// Actual route painter is bounded, selected-owner-only and restores canvas state.
const marks=[],lines=[];
const paint={session:{playerId:'me'},selectedUnits:new Set(['dog']),roomState:{game:{patrols:[
  {unitId:'dog',owner:'me',points:[[0,0],[100,100],[200,0]],next:1},
  {unitId:'enemy',owner:'enemy',points:[[5,5],[8,8]],next:1}]}},};
vm.createContext(paint);vm.runInContext(sourceFunction('drawPatrolRoutes'),paint);
const ctx=new Proxy({}, {get:(obj,key)=>obj[key]||((...args)=>{
  if(key==='fillText')marks.push(args[0]);if(key==='lineTo')lines.push(args);}),
  set:(obj,key,value)=>(obj[key]=value,true)});
paint.drawPatrolRoutes(ctx,(x,y)=>({x,y}),false);
assert.deepEqual(marks,['1','2','3']);assert.equal(lines.length,3);
paint.selectedUnits.clear();marks.length=0;paint.drawPatrolRoutes(ctx,(x,y)=>({x,y}),true);assert.equal(marks.length,0);
console.log('Patrol UI: ordered/cancellable commands, stale-match protection, real Shift handlers and selected-only route display passed.');
