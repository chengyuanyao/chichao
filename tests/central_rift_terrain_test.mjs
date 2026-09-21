import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {execFileSync} from 'node:child_process';
import vm from 'node:vm';
import * as THREE from '../public/vendor/three.module.min.js';
import {prepareWildernessLandforms,wildernessLandformAt,wildernessNoise,
  makeWeatheredRockGeometry,forestChunkKey} from '../public/wilderness.js';
import {prepareTerrainInput,intersectTerrainInput} from '../public/terrain_input.js';

// Consume the shipped coordinates, not a hand-copied test bridge.
const map=JSON.parse(execFileSync('python',['-c',
  "import json,server; m=server.MAPS['central_rift'].copy(); m['terrainDetail']=server.visual_terrain_detail(m); print(json.dumps(m))"],
  {cwd:new URL('..',import.meta.url),encoding:'utf8'}));
const source=readFileSync(new URL('../public/render3d.js',import.meta.url),'utf8');
assert.ok(source.includes('Math.max(2, Math.ceil(len / 58))'),'river trees budgeted by length');
assert.ok(source.includes('Math.min(110,Math.max(1,Math.ceil(len/30)))'),'gravel budgeted by length');
const context={THREE,wildernessLandformAt,heightField:null,
  state:{map,terrain:map,spawnPoints:map.spawnPoints,terrainDetail:map.terrainDetail,
    landforms:prepareWildernessLandforms(map.landforms)},riverValleyMode:()=>true};
vm.createContext(context);
for(const name of ['pointSegmentDistanceSq','terrainFlatnessAt','rollingHeight',
  'baseGroundHeight','bridgeSurfaceHeightAt','groundHeight']) {
  const code=source.match(new RegExp('  function '+name+'\\([^]*?\\n  \\}'));
  assert.ok(code,name);vm.runInContext(code[0],context);
}
const values=new Float32Array(101*101);
for(let y=0;y<=100;y++) for(let x=0;x<=100;x++) values[y*101+x]=context.rollingHeight(x*40,y*40);
context.heightField={values,cols:101,segX:100,segY:100,width:4000,height:4000};
const input=prepareTerrainInput(context.heightField,map);
let checks=0;
for(const b of map.bridges) {
  const len=Math.hypot(b.x2-b.x1,b.y2-b.y1),ux=(b.x2-b.x1)/len,uy=(b.y2-b.y1)/len;
  for(const along of [-110,-60,0,len*.5,len,len+60,len+110]) {
    const x=b.x1+ux*along,y=b.y1+uy*along;
    assert.ok(Math.abs(context.rollingHeight(x,y))<.001,'bridge approaches flatten surrounding relief');
    const height=context.groundHeight(x,y);
    const expected=b.deckHeight*Math.min(1,Math.max(0,(along+b.ramp)/b.ramp),Math.max(0,(len+b.ramp-along)/b.ramp));
    assert.ok(Math.abs(height-expected)<.001,'unit height matches physical bridge deck/ramp');
    const hit=intersectTerrainInput(new THREE.Ray(new THREE.Vector3(x,1000,y),new THREE.Vector3(0,-1,0)),input);
    assert.ok(hit&&Math.abs(hit.height-height)<.001,'input ray matches unit surface');
    checks++;
  }
}
for(const [x,y] of map.botDeployPoints) {
  assert.ok(Math.abs(context.rollingHeight(x,y)-95)<.001,'deployment terrace level');
  for(const dx of [-58,58]) for(const dy of [-58,58]) {
    assert.ok(Math.abs(context.rollingHeight(x+dx,y+dy)-95)<.001,'HQ corners level');
  }
}
console.log(`Rift terrain: ${checks} bridge/ramp height and picking checks, five level HQ terraces passed.`);

// Exercise the actual static builders after batching: indices/colors survive,
// mountains retain their deterministic rock templates, and materials are shared.
const batches=[];
Object.assign(context,{wildernessNoise,makeWeatheredRockGeometry,forestChunkKey,TAU:Math.PI*2,
  terrainGroup:new THREE.Group(),groundTexture:new THREE.Texture(),
  applyFogMask:m=>m,applyWildernessRock:m=>m,bridgeTrailAt:()=>0,
  mergeParts:parts=>{
    batches.push(parts);
    for(const p of parts) assert.ok(p.matrix.elements.every(Number.isFinite));
    return new THREE.BoxGeometry(1,1,1);
  }});
for(const name of ['buildRiverCliffs','buildRocks']) {
  vm.runInContext(source.match(new RegExp('  function '+name+'\\([^]*?\\n  \\}'))[0],context);
}
context.buildRiverCliffs();
const banks=context.terrainGroup.children.filter(m=>m.name.startsWith('river-stratified-bank-'));
assert.equal(banks.length,15,'one merged two-bank mesh per river segment');
assert.equal(new Set(banks.map(m=>m.material)).size,1,'one shared bank material');
for(const bank of banks) {
  const geo=bank.geometry;
  for(const attr of Object.values(geo.attributes)) assert.ok(attr.array.every(Number.isFinite));
  assert.ok(geo.index.array.every(i=>i<geo.attributes.position.count));
  const normal=geo.attributes.normal;
  assert.ok(Array.from({length:normal.count},(_,i)=>normal.getY(i)).some(y=>y>0));
}
const before=context.terrainGroup.children.length;
context.buildRocks();
assert.equal(context.terrainGroup.children.length-before,
  new Set(map.mountains.map(m=>forestChunkKey(m.x,m.y))).size);
assert.ok(context.terrainGroup.children.length-before<map.mountains.length);
console.log('Rift static batches: valid two-bank geometry, shared material, finite spatially merged rocks passed.');
