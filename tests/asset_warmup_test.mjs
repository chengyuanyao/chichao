import assert from 'node:assert/strict';
import vm from 'node:vm';
import {readFileSync} from 'node:fs';
import * as THREE from '../public/vendor/three.module.min.js';
import {warmAssetTasks,solidSurface} from '../public/asset_warmup.js';
import {createBattleAudio} from '../public/battle_audio.js';

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

const source=readFileSync(new URL('../public/render3d.js',import.meta.url),'utf8');
const start=source.indexOf('  const warmRoots ='),end=source.indexOf('\n  return {\n    get camera()',start);
assert.ok(start>0&&end>start);
let builds=0,compiles=0;
const geometry=new THREE.BoxGeometry(),material=new THREE.MeshPhongMaterial();
const mesh=()=>new THREE.InstancedMesh(geometry,material,64);
const fixture={THREE,console,warmAssetTasks,scene:new THREE.Scene(),camera:new THREE.PerspectiveCamera(),
  flashPool:[{light:{visible:false}},{light:{visible:true}}],
  makeRiverMaterial:()=>material,applyEmissiveByVertexColor:m=>solidSurface(m),
  CLOTH_UNIT_KINDS:{},HIDE_UNIT_KINDS:{},MAGIC_UNIT_KINDS:{},MAGIC_STRUCTURE_KINDS:{},
  unitGeometry(){builds++;return {body:geometry,simple:geometry};},
  structureGeometries(){builds++;return {team:geometry,head:{team:geometry,y:10}};},
  ensureTracerMesh:mesh,ensureTracerOrbMesh:mesh,ensureTracerShardMesh:mesh,
  ensureApocArmMesh:mesh,ensureDragonOrbitMesh:mesh,
  postfx:{enabled:true,sceneTarget:{}},
  renderer:{getRenderTarget(){return null;},setRenderTarget(){},async compileAsync(){compiles++;}}};
vm.createContext(fixture);vm.runInContext(source.slice(start,end),fixture);
const catalog={units:{tank:{},dragon:{}},buildings:{hq:{size:90}}};
await fixture.prepareAssets(catalog);assert.equal(builds,10);assert.equal(compiles,9);
assert.deepEqual(fixture.flashPool.map(f=>f.light.visible),[false,true],'lighting state restored after compile');
await fixture.prepareAssets(catalog);assert.equal(builds,10,'reconnect does not rebuild all assets');
assert.equal(vm.runInContext('assetWarmup.ready',fixture),true);
assert.doesNotMatch(source,/node\.teamMat\.transparent = true/,'construction is solid too');
console.log('Asset warmup passed: yielding, cancellation, silent audio cache, two model families, shader compilation, deduplication and opaque depth.');
