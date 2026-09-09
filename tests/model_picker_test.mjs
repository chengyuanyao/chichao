import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {execFileSync} from 'node:child_process';
import vm from 'node:vm';
import {performance} from 'node:perf_hooks';
import * as THREE from '../public/vendor/three.module.min.js';
import {createModelPicker} from '../public/model_picker.js';

const source = readFileSync(new URL('../public/render3d.js', import.meta.url), 'utf8');
const app = readFileSync(new URL('../public/app.js', import.meta.url), 'utf8');
function sourceFunction(text, name) {
  const match = text.match(new RegExp('  function ' + name + '\\([^]*?\\n  \\}'));
  assert.ok(match, name); return match[0];
}
const modelEnd = source.indexOf('/* ------------------------------------------------------------------ *\n * 渲染器');
assert.ok(modelEnd > 0);
const models = source.slice(0, modelEnd).replace(/^import\s[\s\S]*?;$/mg,'').replace(/^export /mg,'');
const factories = new Function('THREE', `${models}
  const UNIT_GEOMETRY_CACHE = new Map();
  ${sourceFunction(source, 'simpleUnitParts')}
  ${sourceFunction(source, 'unitGeometry')}
  return {unitGeometry, structureGroup, kinds:Object.keys(UNIT_BUILDERS), apocalypseArmParts};
`)(THREE);
const catalog = JSON.parse(execFileSync(process.platform === 'win32' ? 'py' : 'python3',
  ['-c','import json,catalog; print(json.dumps(catalog.STRUCTURE_TYPES))'],
  {cwd:new URL('..',import.meta.url),encoding:'utf8'}));
const picker = createModelPicker();
const mat = new THREE.MeshBasicMaterial();
const camera = new THREE.PerspectiveCamera(46, 1280/720, 12, 12000);
camera.position.set(0,440,440); camera.lookAt(0,40,0); camera.updateMatrixWorld();
function screen(point) {
  const p=point.clone().project(camera);
  return {x:(p.x*.5+.5)*1280,y:(.5-p.y*.5)*720};
}
function pick(point, accept) {
  const p=screen(point);return picker.pick(camera,1280,720,p.x,p.y,accept);
}
function trianglePoint(geo) {
  const a=new THREE.Vector3(),b=new THREE.Vector3(),c=new THREE.Vector3();
  const p=geo.attributes.position;
  const ids=geo.index;
  for(let i=0;i<(ids?ids.count:p.count);i+=3) {
    a.fromBufferAttribute(p,ids?ids.getX(i):i);
    b.fromBufferAttribute(p,ids?ids.getX(i+1):i+1);
    c.fromBufferAttribute(p,ids?ids.getX(i+2):i+2);
    if(new THREE.Triangle(a,b,c).getArea()>.01) return a.add(b).add(c).divideScalar(3);
  }
  throw new Error('No non-degenerate triangle');
}
const unit={id:'u1',owner:'me',kind:'tank',hp:100};
const building={id:'s1',owner:'enemy',kind:'hq',hp:100};

// Every unit shape and both LODs; yaw, scale, and terrain height are taken from
// actual instance transforms, not the entity's (deliberately wrong) position.
let cases=0;
for(const kind of factories.kinds) {
  for(const geo of Object.values(factories.unitGeometry(kind))) {
    const mesh=new THREE.InstancedMesh(geo,mat,1);
    const matrix=new THREE.Matrix4().compose(new THREE.Vector3(18,35,9),
      new THREE.Quaternion().setFromAxisAngle(new THREE.Vector3(0,1,0),.63),new THREE.Vector3(1.6,1.6,1.6));
    mesh.setMatrixAt(0,matrix); mesh.count=1;
    picker.begin(); picker.addInstances(mesh,()=>unit);
    assert.equal(pick(trianglePoint(geo).applyMatrix4(matrix)),unit,kind);
    mesh.dispose(); cases++;
  }
}
// All 15 buildings, including their heads, spinners and construction scaling.
for(const [kind,def] of Object.entries(catalog)) {
  const group=factories.structureGroup(kind,def.size,mat);
  group.position.set(0,22,0);group.scale.y=.6;group.rotation.y=.4;
  picker.begin();picker.addObject(group,building);
  group.traverse(mesh=>{
    if(!mesh.isMesh) return;
    assert.equal(pick(trianglePoint(mesh.geometry).applyMatrix4(mesh.matrixWorld)),building,kind);
    cases++;
  });
}
const hq=factories.structureGroup('hq',58,mat);
picker.begin();picker.addObject(hq,building);
const roofPoint=new THREE.Vector3(0,100,0);
assert.equal(pick(roofPoint),building,'roof is selectable outside the ground footprint');
const groundRay=new THREE.Ray(camera.position,roofPoint.clone().sub(camera.position).normalize());
const ground=groundRay.intersectPlane(new THREE.Plane(new THREE.Vector3(0,1,0),0),new THREE.Vector3());
assert.ok(Math.abs(ground.z)>58,'regression point really misses the old footprint');

// A unit bounding box overlaps a roof, but the empty middle of its real geometry
// must not win. Also verify true front-to-back ordering across entity types.
const hole=new THREE.Mesh(new THREE.RingGeometry(18,35,32),mat);
hole.position.set(0,180,0);hole.lookAt(camera.position);
const behind=new THREE.Mesh(new THREE.BoxGeometry(20,20,20),mat);
behind.position.copy(camera.position).lerp(hole.position,1.35);
picker.begin();picker.addObject(hole,unit);picker.addObject(behind,building);
assert.equal(pick(hole.position),building,'model holes do not steal building clicks');
picker.begin();picker.addObject(hole,unit);
assert.equal(pick(hole.position),null,'empty model bounding-box area stays ground');
const foreground=new THREE.Mesh(new THREE.BoxGeometry(12,12,12),mat);
foreground.position.copy(camera.position).lerp(hole.position,.7);
for(const frontIsUnit of [true,false]) {
  const frontEntity=frontIsUnit?unit:building,backEntity=frontIsUnit?building:unit;
  picker.begin();picker.addObject(behind,backEntity);picker.addObject(foreground,frontEntity);
  assert.equal(pick(foreground.position),frontEntity,'nearest model wins regardless of entity type');
  picker.begin();picker.addObject(foreground,frontEntity);picker.addObject(behind,backEntity);
  assert.equal(pick(foreground.position),frontEntity,'candidate iteration order does not matter');
}
assert.equal(pick(foreground.position,entity=>entity===unit),unit,'visibility rejects hidden enemy surfaces');

// Fog/hidden/removed instances, ignored aprons, moved instances, LOD toggles,
// exact hit before tolerance, and explicit match reset.
const box=new THREE.BoxGeometry(10,10,10);
const pool=new THREE.InstancedMesh(box,mat,2);
const pos=new THREE.Matrix4().makeTranslation(0,50,0);
pool.setMatrixAt(0,pos);pool.setMatrixAt(1,new THREE.Matrix4().makeTranslation(120,50,0));
pool.count=1;
picker.begin();picker.addInstances(pool,i=>i===0?unit:building);
assert.equal(pick(new THREE.Vector3(120,50,0)),null,'unused pool slots are not selectable');
pool.setMatrixAt(0,new THREE.Matrix4().makeTranslation(120,50,0));
picker.begin();picker.addInstances(pool,()=>unit);
assert.equal(pick(new THREE.Vector3(0,50,0)),null);
assert.equal(pick(new THREE.Vector3(120,50,0)),unit,'moving transform refreshes without stale bounds');
pool.visible=false;picker.begin();picker.addInstances(pool,()=>unit);
assert.equal(pick(new THREE.Vector3(120,50,0)),null,'hidden LOD is not pickable');
pool.visible=true;picker.begin();picker.addInstances(pool,()=>null);
assert.equal(pick(new THREE.Vector3(120,50,0)),null,'removed entity cannot be recovered from stale display');
behind.userData.pickIgnore=true;picker.begin();picker.addObject(behind,building);
assert.equal(pick(behind.position),null,'apron/effect is ignored');behind.userData.pickIgnore=false;
const small=new THREE.Mesh(new THREE.PlaneGeometry(1,1),mat);
small.position.set(0,50,0);small.lookAt(camera.position);
picker.begin();picker.addObject(small,unit);
const center=screen(small.position);
assert.equal(picker.pick(camera,1280,720,center.x+3,center.y),unit,'thin-model click tolerance');
assert.equal(picker.pick(camera,1280,720,center.x+8,center.y),null,'no oversized empty-space fallback');
const background=new THREE.Mesh(new THREE.PlaneGeometry(100,100),mat);
background.position.copy(camera.position).lerp(small.position,1.2);background.lookAt(camera.position);
picker.addObject(background,building);
assert.equal(picker.pick(camera,1280,720,center.x+3,center.y),building,'exact building hit precedes nearby unit halo');
picker.clear();assert.equal(pick(small.position),null,'new match drops old candidates');

// Actual renderer wiring: published entity lists gate stale ids, active LOD and
// animated attachment transforms are used, and clearEntities clears the picker.
const wiring={modelPicker:picker,state:{map:{},width:1280,height:720,viewerId:'me',friendly:()=>false},
  camera,unitPools:new Map([['tank',{mesh:pool,simple:null}]]),structureNodes:new Map(),
  apocArmMesh:null,dragonOrbitMesh:null,apocArmVisuals:[],dragonOrbitVisuals:[],isVisible:()=>true};
pool.userData.instanceIds=['u1'];
vm.createContext(wiring);vm.runInContext(sourceFunction(source,'collectPickModels')+sourceFunction(source,'pickEntityAt'),wiring);
let pixel=screen(new THREE.Vector3(120,50,0));
assert.equal(wiring.pickEntityAt({units:[unit],structures:[]},pixel.x,pixel.y),unit);
assert.equal(wiring.pickEntityAt({units:[],structures:[]},pixel.x,pixel.y),null);
wiring.unitPools.clear();wiring.apocArmMesh=pool;wiring.apocArmVisuals=[{unit}];
assert.equal(wiring.pickEntityAt({units:[unit],structures:[]},pixel.x,pixel.y),unit,'animated arm owner mapping');
wiring.apocArmMesh=null;wiring.dragonOrbitMesh=pool;wiring.dragonOrbitVisuals=[{unit}];
assert.equal(wiring.pickEntityAt({units:[unit],structures:[]},pixel.x,pixel.y),unit,'orbit owner mapping');
wiring.dragonOrbitMesh=null;wiring.structureNodes.set(building.id,{group:hq});
pixel=screen(roofPoint);
assert.equal(wiring.pickEntityAt({units:[],structures:[building]},pixel.x,pixel.y),building);
wiring.isVisible=()=>false;
assert.equal(wiring.pickEntityAt({units:[],structures:[building]},pixel.x,pixel.y),null,'fogged enemy cannot be picked');
assert.match(source,/clearEntities: function \(\) \{\s*modelPicker\.clear\(\)/);

// Production left/right handlers share one resolver. A roof hit sends attack,
// friendly model hits preserve selection, and no hit sends ordinary movement.
let hit=building;
const commands=[];
const input={roomState:{game:{units:[unit],structures:[building]}},view3d:{pickEntityAt:()=>hit},pointer:{x:100,y:200},
  worldToScreen:(x,y)=>({x,y}),resourceAt:()=>null,selectedUnits:new Set(['u1']),selectedStructureId:null,
  selectedResourceId:null,session:{playerId:'me'},isFriendly:owner=>owner==='me',
  structureRole:kind=>catalog[kind]?.role,selectedUnitIdList:()=>[...input.selectedUnits],
  sendAction:(action,payload)=>{commands.push(payload);return Promise.resolve({});},
  issueGroundCommand:()=>commands.push({command:'move'}),markOrder(){},sound(){},toast(){},renderSelectionInfo(){}};
vm.createContext(input);
vm.runInContext(['entityAt','selectAt','issueContextCommand'].map(n=>sourceFunction(app,n)).join('\n'),input);
input.issueContextCommand(100,200);assert.equal(commands.at(-1).command,'attack');
assert.equal(commands.at(-1).targetId,building.id);assert.deepEqual([...input.selectedUnits],['u1']);
hit=unit;input.issueContextCommand(100,200);assert.equal(commands.at(-1).command,'move');
assert.deepEqual([...input.selectedUnits],['u1']);
hit=building;input.selectAt(100,200,false);assert.equal(input.selectedStructureId,building.id);
hit=unit;input.selectAt(100,200,false);assert.deepEqual([...input.selectedUnits],['u1']);
hit=null;input.issueContextCommand(100,200);assert.equal(commands.at(-1).command,'move');
input.selectAt(100,200,false);assert.equal(input.selectedUnits.size,0);
const turret={id:'s-turret',kind:'turret',owner:'me',active:true};
input.roomState.game.structures.push(turret);input.selectedStructureId=turret.id;hit=building;
input.issueContextCommand(100,200);assert.equal(commands.at(-1).command,'structureAttack');
assert.equal(commands.at(-1).targetId,building.id);

// Click-only cost, not a render FPS benchmark. Exercise real high-detail tank
// geometry with 400 instances, including empty clicks (the tolerance path).
const army=new THREE.InstancedMesh(factories.unitGeometry('tank').body,mat,400);
for(let i=0;i<400;i++) army.setMatrixAt(i,new THREE.Matrix4().makeTranslation((i%20-10)*45,0,(Math.floor(i/20)-10)*45));
const times=[];
for(let i=0;i<20;i++) {
  const start=performance.now();picker.begin();picker.addInstances(army,()=>unit);
  picker.pick(camera,1280,720,i%2?640:40,i%2?360:40);times.push(performance.now()-start);
}
times.sort((a,b)=>a-b);
console.log(`Model picker: ${cases} model/LOD/part cases, roofs, overlap depth, holes, tolerance, fog, lifecycle and actual command handlers passed. 400-unit click median ${times[10].toFixed(2)} ms, p95 ${times[18].toFixed(2)} ms.`);
picker.dispose();mat.dispose();pool.dispose();army.dispose();
