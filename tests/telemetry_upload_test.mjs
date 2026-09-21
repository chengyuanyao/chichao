import assert from 'node:assert/strict';
import {createPerformanceRecorder} from '../public/performance_report.js';
import {createTelemetryUploader} from '../public/telemetry_upload.js';
import {renderDiagnostics,reportCsv} from '../public/battle_report.js';
const r=createPerformanceRecorder();r.start('match','p');r.frame(0,true,0);r.frame(20,true,0);
r.received(0,0,1);r.received(125,0,2);r.received(900,1,3);
r.network('probe',80,true,1);r.network('command',120,true,1);r.network('probe',0,false,1);r.network('reconnect',0,false,1);
let data=r.snapshot('match','p');
assert.equal(data.netGapSamples,2);assert.equal(data.netGapMs,900);assert.equal(data.netOver500,1);
assert.equal(data.probeSamples,1);assert.equal(data.probeFailures,1);assert.equal(data.commandMs,120);
r.pause();r.received(10000,10,1);assert.equal(r.snapshot('match','p').netGapSamples,2);
let ctx={roomId:'room',playerId:'p',token:'token',matchId:'match'},calls=0,done,probes=[];
const uploader=createTelemetryUploader({context:()=>ctx,snapshot:(id,p,detail)=>r.snapshot(id,p,detail),probe:(...v)=>probes.push(v),
  fetcher:async(path,options)=>{calls++;assert.equal(path,'/api/telemetry');const body=JSON.parse(options.body);assert.equal(body.performance.matchId,'match');
    if(calls===1){assert.equal(body.performance.periods.length,0);assert.ok(options.body.length<6000);}else{assert.ok(body.performance.periods.length);}
    return new Promise(resolve=>{done=()=>resolve({ok:true,json:async()=>({ok:true})});});}});
const first=uploader.send();uploader.send();assert.equal(calls,1,'one in flight');done();assert.equal(await first,true);
await uploader.send();assert.equal(calls,1,'30 second throttle');assert.equal(probes.length,1);
const next=uploader.send(true);ctx={...ctx,matchId:'new'};done();await next;assert.equal(probes.length,1,'old request cannot contaminate new match');
const fail=createTelemetryUploader({context:()=>({...ctx,matchId:'match'}),snapshot:()=>data,probe:(ms,ok)=>assert.equal(ok,false),fetcher:async()=>{throw Error('offline');}});
assert.equal(await fail.send(),false,'network failures never break game commands');
const doc={matchId:'match',status:'playing',players:[{id:'p',name:'<bad>'},{id:'missing',name:'missing'}],clients:{p:{runs:[data]}},server:{tickWorkMs:{count:2,sum:8,max:5}}};
assert.ok(renderDiagnostics(doc).includes('尚未收到上报'));assert.ok(!renderDiagnostics(doc).includes('<bad>'));
assert.ok(reportCsv({matchId:'match',duration:1,players:[],serverDiagnostics:doc}).includes('全员客户端诊断'));
console.log('Telemetry: bounded counters, visibility reset, single flight, throttle, stale match isolation, failures and escaped aggregate exports passed.');
// A queued terminal upload must not accidentally flush the next match.
let finishRequest,queuedCalls=0;
ctx={...ctx,matchId:'match'};
const queued=createTelemetryUploader({context:()=>ctx,snapshot:()=>data,probe:()=>{},fetcher:async()=>{
  queuedCalls++;return new Promise(resolve=>{finishRequest=()=>resolve({ok:true,json:async()=>({ok:true})});});
}});
const active=queued.send(),terminal=queued.send(true);
assert.equal(queued.send(true),terminal,'only one queued terminal request');
ctx={...ctx,matchId:'next-match'};finishRequest();await active;await terminal;
assert.equal(queuedCalls,1,'queued old-match terminal cannot upload a new match');
