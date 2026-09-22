import assert from 'node:assert/strict';
import {createStateStream} from '../public/state_stream.js';

let time=0, active=true, tick, stopped=false, reconnects=0;
const sources=[], accepted=[], statuses=[];
const stream=createStateStream({url:'/test', now:()=>time, isActive:()=>active,
  schedule:fn=>(tick=fn,1),unschedule:()=>{stopped=true;},
  makeSource:()=>{const source={closed:false,addEventListener:(name,fn)=>{source[name]=fn;},close:()=>{source.closed=true;}};sources.push(source);return source;},
  onState:event=>{if(event.data==='bad')return false;accepted.push(event.data);},
  onStatus:value=>statuses.push(value),onReconnect:()=>reconnects++});
const advance=ms=>{time+=ms;tick();};
// Reproduce a half-open connection: no onerror, no new bytes, yet readyState
// could still be OPEN. Old app only changed badge; new client replaces stream.
sources[0].state({data:'first'});
sources[0].onerror();assert.equal(sources.length,1); // native reconnect isn't duplicated immediately
advance(1499);assert.equal(sources.length,1);
advance(1);assert.equal(sources.length,2);assert.equal(sources[0].closed,true);
sources[0].state({data:'stale queued event'});assert.deepEqual(accepted,['first']);
// No reconnect storm on complete outage; allow initial full frame time.
advance(9999);assert.equal(sources.length,2);
advance(1);assert.equal(sources.length,3);
advance(11999);assert.equal(sources.length,3);
advance(1);assert.equal(sources.length,4);
// Eight healthy frames restore the normal gap threshold.
for(let i=0;i<8;i++){sources.at(-1).state({data:'healthy'});advance(125);}
advance(1375);assert.equal(sources.length,5);
// Hidden tab and return grace do not create reconnect loops.
active=false;advance(60000);assert.equal(sources.length,5);
active=true;advance(1);assert.equal(sources.length,5);
sources.at(-1).state({data:'bad'});assert.equal(statuses.at(-1),false);
const count=accepted.length;
stream.close();assert.equal(stopped,true);assert.equal(sources.at(-1).closed,true);
sources.at(-1).state({data:'after teardown'});advance(60000);
assert.equal(accepted.length,count);assert.equal(sources.length,5);
assert.equal(reconnects,5);
console.log('SSE watchdog: silent-stall reproduction, stream replacement, backoff, hidden-tab grace and stale-event teardown passed.');
