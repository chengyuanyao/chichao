import assert from 'node:assert/strict';
import vm from 'node:vm';
import {readFileSync} from 'node:fs';
import * as THREE from '../public/vendor/three.module.min.js';
import {warmAssetTasks,solidSurface} from '../public/asset_warmup.js';
import {createBattleAudio} from '../public/battle_audio.js';
import {applyBuildingCollapse} from '../public/battlefield_finish.js';

const order=[];
const running=warmAssetTasks([()=>order.push(1),()=>order.push(2)]);
assert.deepEqual(order,[],'no synchronous asset burst');
await running;assert.deepEqual(order,[1,2]);
await warmAssetTasks([()=>assert.fail('cancelled work ran')],()=>true);
const solid=solidSurface(new THREE.MeshStandardMaterial({transparent:true,opacity:.3,depthWrite:false}));
assert.equal(solid.opacity,1);assert.equal(solid.transparent,false);assert.equal(solid.depthWrite,true);

let buffers=0;
const node=()=>({gain:{},threshold:{},knee:{},ratio:{},attack:{},release:{},pan:{},playbackRate:{},connect(){},disconnect(){},start(){},stop(){}});
const context={state:'running',currentTime:1,sampleRate:8000,destination:{},createGain:node,
  createDynamicsCompressor:node,createStereoPanner:node,createBufferSource:node,
  createBuffer(c,n){buffers++;return {getChannelData:()=>new Float32Array(n)};}};
const audio=createBattleAudio(context);const promise=audio.prewarm();
assert.equal(audio.prewarm(),promise,'warmup is deduplicated');await promise;
const count=buffers;assert.ok(count>=20);assert.equal(audio.stats().voices,0,'silent preload');
for(const kind of ['bullet','shell','siege','tesla','arcane','frost','meteor','bite']) {
  context.currentTime++;audio.events([{type:'muzzle',kind,x:0,y:0}],{x:0,y:0});audio.clear();
}
assert.equal(buffers,count,'first weapons use already synthesized samples');
audio.dispose();assert.equal(await audio.prewarm(),false);
const cancelled=createBattleAudio(context),pending=cancelled.prewarm();cancelled.dispose();
await pending;assert.equal(cancelled.stats().cachedSamples,0,'dispose cancels outstanding work');

const originalFetch=globalThis.fetch;
try {
  const requests=[];
  globalThis.fetch=async url=>{requests.push(url);return {ok:true,arrayBuffer:async()=>new ArrayBuffer(4)};};
  const decodedContext={...context,decodeAudioData:async()=>({getChannelData:()=>new Float32Array(256).fill(.2)})};
  const recordedAudio=createBattleAudio(decodedContext);await recordedAudio.prewarm();
  assert.equal(recordedAudio.stats().recordedSamples,3);
  assert.equal(recordedAudio.stats().voices,0,'decoding does not play voices');
  context.currentTime++;
  recordedAudio.events([{type:'explosion',x:0,y:0}],{x:0,y:0});
  assert.equal(requests.length,3,'weapon path never fetches');recordedAudio.dispose();
  globalThis.fetch=async()=>({ok:false});
  const fallback=createBattleAudio(decodedContext);await fallback.prewarm();
  assert.equal(fallback.stats().recordedSamples,0);assert.equal(fallback.stats().cachedSamples,20);fallback.dispose();
  let releaseDecode;
  globalThis.fetch=async()=>({ok:true,arrayBuffer:async()=>new ArrayBuffer(4)});
  const delayed=createBattleAudio({...context,decodeAudioData:()=>new Promise(resolve=>{releaseDecode=resolve;})});
  const delayedWarm=delayed.prewarm();
  for(let i=0;i<8&&!releaseDecode;i++) await Promise.resolve();
  assert.ok(releaseDecode);delayed.dispose();releaseDecode({getChannelData:()=>new Float32Array(1)});
  await delayedWarm;assert.equal(delayed.stats().recordedSamples,0);assert.equal(delayed.stats().cachedSamples,0);
} finally {globalThis.fetch=originalFetch;}

const source=readFileSync(new URL('../public/render3d.js',import.meta.url),'utf8');
const start=source.indexOf('  const warmRoots ='),end=source.indexOf('\n  return {\n    get camera()',start);
assert.ok(start>0&&end>start);
let builds=0,compiles=0;
const geometry=new THREE.BoxGeometry(),material=new THREE.MeshPhongMaterial();
const mesh=()=>new THREE.InstancedMesh(geometry,material,64);
const fixture={THREE,console,warmAssetTasks,applyBuildingCollapse,scene:new THREE.Scene(),camera:new THREE.PerspectiveCamera(),
  flashPool:[{light:{visible:false}},{light:{visible:true}}],
  makeRiverMaterial:()=>new THREE.MeshStandardMaterial(),applyEmissiveByVertexColor:m=>solidSurface(m),
  CLOTH_UNIT_KINDS:{},HIDE_UNIT_KINDS:{},MAGIC_UNIT_KINDS:{},MAGIC_STRUCTURE_KINDS:{},
  unitGeometry(){builds++;return {body:geometry,simple:geometry};},
  structureGeometries(){builds++;return {team:geometry,head:{team:geometry,y:10}};},
  ensureTracerMesh:mesh,ensureTracerOrbMesh:mesh,ensureTracerShardMesh:mesh,
  ensureApocArmMesh:mesh,ensureDragonOrbitMesh:mesh,
  postfx:{enabled:true,sceneTarget:{}},
  renderer:{getRenderTarget(){return null;},setRenderTarget(){},initTexture(){},render(){},async compileAsync(){compiles++;}}};
fixture.blastSurface=new THREE.Texture();
for(const key of ['shockLayer','scorchLayer','trackLayer']) {
  fixture[key]={mesh:mesh()};fixture.scene.add(fixture[key].mesh);
}
fixture.wreckLayers=[{mesh:mesh()},{mesh:mesh()},{mesh:mesh()}];
for(const l of fixture.wreckLayers) fixture.scene.add(l.mesh);
for(const key of ['fireLayer','smokeLayer']) {
  fixture[key]={points:new THREE.Points(geometry,material)};fixture.scene.add(fixture[key].points);
}
vm.createContext(fixture);vm.runInContext(source.slice(start,end),fixture);
const catalog={units:{tank:{},dragon:{}},buildings:{hq:{size:90}}};
await fixture.prepareAssets(catalog);assert.equal(builds,10);assert.equal(compiles,9);
assert.deepEqual(fixture.flashPool.map(f=>f.light.visible),[false,true],'lighting state restored after compile');
await fixture.prepareAssets(catalog);assert.equal(builds,10,'reconnect does not rebuild all assets');
assert.equal(vm.runInContext('assetWarmup.ready',fixture),true);
assert.equal(fixture.trackLayer.mesh.parent,fixture.scene,'GPU warmup restores parents');
assert.equal(fixture.trackLayer.mesh.count,64,'GPU warmup restores instance counts');
const app=readFileSync(new URL('../public/app.js',import.meta.url),'utf8');
const gateStart=app.indexOf('  async function awaitBattleAssets()');
const gateSource=app.slice(gateStart,app.indexOf('\n  }',gateStart)+4);
const gate={session:{roomId:'a',playerId:'p',token:'t'},roomState:{status:'lobby'},catalogPromise:Promise.resolve(),
  battleAssetsPromise:Promise.resolve(),view3d:{stats:()=>({assetWarmup:{ready:true}})}};
vm.createContext(gate);vm.runInContext(gateSource,gate);await gate.awaitBattleAssets();
gate.view3d.stats=()=>({assetWarmup:{ready:false}});
await assert.rejects(gate.awaitBattleAssets(),/加载/);
gate.view3d.stats=()=>({assetWarmup:{ready:true}});
let releaseGate;gate.battleAssetsPromise=new Promise(resolve=>releaseGate=resolve);
const pendingGate=gate.awaitBattleAssets();gate.session={roomId:'b',playerId:'p',token:'t'};
releaseGate();await assert.rejects(pendingGate,/房间/);
assert.match(app,/if\(!me.ready\) await awaitBattleAssets\(\)/,'guest ready waits for GPU warmup');
assert.match(app,/await awaitBattleAssets\(\);\s*return sendAction\('start'\)/,'host start waits too');
assert.doesNotMatch(source,/node\.teamMat\.transparent = true/,'construction is solid too');
console.log('Asset warmup passed: yielding, cancellation, silent audio cache, two model families, shader compilation, deduplication and opaque depth.');
