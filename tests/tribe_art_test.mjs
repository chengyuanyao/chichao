import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import * as THREE from '../public/vendor/three.module.min.js';
import {riverUnitModel,riverStructureDetails,artJointAngle} from '../public/river_art_models.js';
import {TRIBE_ART_KINDS,TRIBE_ART_STRUCTURES} from '../public/tribe_art_models.js';
import {createModelPicker} from '../public/model_picker.js';
import {applyRiverPBR,createRiverSurfaceMaps} from '../public/river_art_materials.js';
import {weaponFamily,MUZZLE_POINTS} from '../public/battle_feedback.js';

const source=readFileSync(new URL('../public/render3d.js',import.meta.url),'utf8');
const modelSource=source.slice(0,source.indexOf('/**\n * 组装一座建筑'))
  .replace(/^import\s[\s\S]*?;$/mg,'').replace(/^export /mg,'');
function factory(name) {const s=source.indexOf(`  function ${name}(`),e=source.indexOf('\n  }',s);return source.slice(s,e+4);}
const {unit,structure}=new Function('THREE','riverUnitModel','riverStructureDetails',`${modelSource}
  const UNIT_GEOMETRY_CACHE=new Map();${factory('simpleUnitParts')} ${factory('unitGeometry')}
  return {unit:unitGeometry,structure:structureGeometries};`)(THREE,riverUnitModel,riverStructureDetails);
const budgets={spear:1600,javelin:1600,slinger:1600,tamer:1600,wolf:2600,spider:3200,
  scorpion:3200,panda:3000,mammoth:4800,tharvester:3000,tmcv:3500,catapult:3500};
const picker=createModelPicker(),material=new THREE.MeshBasicMaterial();
const camera=new THREE.PerspectiveCamera(46,1280/720,12,12000);
camera.position.set(0,440,440);camera.lookAt(0,40,0);camera.updateMatrixWorld();
function pickable(geo,label) {
  const mesh=new THREE.InstancedMesh(geo,material,1),entity={id:label,owner:'me',kind:label,hp:100};
  const transform=new THREE.Matrix4().makeTranslation(10,35,10);
  mesh.setMatrixAt(0,transform);mesh.count=1;picker.begin();picker.addInstances(mesh,()=>entity);
  const p=geo.attributes.position,a=new THREE.Vector3(),b=new THREE.Vector3(),c=new THREE.Vector3();
  let hit=false;
  for(let i=0;i<p.count;i+=3) {
    a.fromBufferAttribute(p,i);b.fromBufferAttribute(p,i+1);c.fromBufferAttribute(p,i+2);
    if(new THREE.Triangle(a,b,c).getArea()<.01) continue;
    a.add(b).add(c).divideScalar(3).applyMatrix4(transform).project(camera);
    hit=picker.pick(camera,1280,720,(a.x*.5+.5)*1280,(.5-a.y*.5)*720)===entity;
    if(hit) break;
  }
  assert.ok(hit,label+' pickable');mesh.dispose();
}
console.log('Feature: tribe-faction-redesign, Property 11: 近景几何、队色、拾取与远景一致');
let batches=0;
for(const kind of TRIBE_ART_KINDS) {
  const near=unit(kind,true),base=unit(kind),pieces=[near.body,...(near.rigs||[]).map(r=>r.geometry)];
  assert.ok(near.staticBody,kind+' middle-distance body');
  const staticCount=near.body.attributes.position.count+near.rigs
    .filter(r=>r.mode!=='strike').reduce((sum,r)=>sum+r.geometry.attributes.position.count,0);
  assert.equal(near.staticBody.attributes.position.count,staticCount,kind+' static joints retain geometry');
  pickable(near.staticBody,kind+'/static');
  const triangles=pieces.reduce((sum,g)=>sum+g.attributes.position.count/3,0);
  assert.ok(triangles<=budgets[kind],kind+': '+triangles+' triangles');
  assert.ok((near.rigs||[]).length<=4);batches+=(near.rigs||[]).length;
  for(const piece of pieces) {
    for(const field of ['position','normal','uv','aTeam','aOcc','aSurf']) {
      assert.ok(piece.attributes[field].array.every(Number.isFinite),kind+'/'+field);
    }
    pickable(piece,kind);
  }
  assert.ok(pieces.some(g=>g.attributes.aTeam.array.some(v=>v===1)),kind+' team paint');
  if(['wolf','mammoth','panda','tharvester','tmcv'].includes(kind)) {
    assert.ok(pieces.some(g=>g.attributes.aSurf.array.some(v=>v===3.25)),kind+' fur');
  }
  assert.deepEqual(base.simple.attributes.position.array,near.simple.attributes.position.array);
  for(const r of near.rigs||[]) {
    assert.ok(['x','y','z'].includes(r.axis));
    assert.ok(['walk','strike','roll'].includes(r.mode));
    if(r.mode==='walk') assert.equal((r.rate??.25)*4%1,0);
    if(r.mode==='roll') assert.ok(Math.abs(4/r.radius-Math.round(4/r.radius))<1e-9);
  }
  if(kind==='javelin'||kind==='catapult') assert.ok(base.simple.attributes.position.count/3<=200);
  if(['wolf','mammoth','tharvester','tmcv'].includes(kind)) {
    assert.deepEqual(near.rigs.map(r=>r.side),[-1,1,1,-1],kind+' diagonal gait');
  }
  console.log(kind,triangles,'triangles',(near.rigs||[]).length,'rigs');
}
assert.equal(batches,34);
// 真正的池构造器：隐藏的近景/中景/关节也必须带实例颜色，否则预热会多编译变体。
const ensurePool=new Function('THREE','riverUnitModel',`${modelSource}
  const state={artSample:true,shadows:'structures'},worldRoot=new THREE.Group();
  const unitPools=new Map(),UNIT_GEOMETRY_CACHE=new Map(),riverUnitMaterials=new Map();
  const unitMetalMaterial=new THREE.MeshBasicMaterial({vertexColors:true});
  const unitClothMaterial=unitMetalMaterial,unitHideMaterial=unitMetalMaterial,unitStoneMaterial=unitMetalMaterial;
  const makeRiverMaterial=()=>new THREE.MeshBasicMaterial({vertexColors:true});
  ${factory('simpleUnitParts')} ${factory('unitGeometry')} ${factory('ensurePool')}
  return ensurePool;`)(THREE,riverUnitModel);
for(const kind of TRIBE_ART_KINDS) {
  const pool=ensurePool(kind,1);
  for(const mesh of Object.values(pool).filter(v=>v?.isInstancedMesh)) {
    assert.ok(mesh.instanceColor,kind+' unused pools share color shader variant');
    assert.equal(mesh.count,0);
  }
}

console.log('Feature: tribe-faction-redesign, Property 12: 关节有界、静止归位与连续性');
let seed=1201;const rand=()=>((seed=(Math.imul(seed,1664525)+1013904223)>>>0)/4294967296);
for(let i=0;i<1000;i++) {
  const travel=rand()*8*Math.PI,motion=rand(),time=rand()*1e6;
  const r={axis:'z',mode:'walk',side:rand()<.5?-1:1,rate:(1+Math.floor(rand()*8))*.25,
    amp:.1+rand()*.8,gain:.1+rand(),phase:rand()*Math.PI*2};
  const angle=artJointAngle(r,time,travel,motion);
  assert.ok(Number.isFinite(angle)&&Math.abs(angle)<=r.amp+1e-9);
  assert.ok(Math.abs(angle+artJointAngle({...r,side:-r.side},time,travel,motion))<1e-9);
  assert.ok(artJointAngle(r,time,travel,0)===0);
  assert.ok(Math.abs(artJointAngle(r,time,0,motion)-artJointAngle(r,time,8*Math.PI-1e-9,motion))<1e-8);
  const strike={axis:'z',mode:'strike',rest:rand()-.5,swing:rand()*2-1,attack:.08+rand()*.2,duration:.6+rand()};
  const since=rand()<.2?Infinity:rand()*6-1;
  const a=artJointAngle(strike,time,travel,motion,since);
  assert.ok(Number.isFinite(a));
  assert.ok(a>=Math.min(strike.rest,strike.rest+strike.swing)-1e-9&&a<=Math.max(strike.rest,strike.rest+strike.swing)+1e-9);
  if(!(since>=0)||since>=strike.duration) assert.equal(a,strike.rest);
  assert.ok(Math.abs(artJointAngle(strike,time,travel,0,strike.attack)-(strike.rest+strike.swing))<1e-9);
  assert.equal(artJointAngle({mode:'roll',radius:4},time,travel,motion),-travel/4);
  assert.equal(artJointAngle({mode:'unknown'},time,travel,motion),0);
  assert.equal(artJointAngle({...r,axis:'unknown'},time,travel,motion),0);
}
console.log('Feature: tribe-faction-redesign, Property 13: 建筑队色、锚定与破拆预算');
for(const [kind,size,budget] of [['thq',58,6000],['tspiketower',28,3000],['ttoxtower',32,3200]]) {
  assert.ok(TRIBE_ART_STRUCTURES.has(kind));
  const near=structure(kind,size,true),base=structure(kind,size);
  assert.notEqual(near,base);
  const g=near.team,count=g.attributes.position.count;
  assert.ok(count/3<=budget);
  assert.equal(g.attributes.aBreak.count,count);
  assert.ok(g.attributes.aBreak.array.every(Number.isFinite));
  assert.ok(g.attributes.aBreak.array.some((v,i)=>i%4===3&&v<0),'ground anchoring');
  assert.ok(g.attributes.aTeam.array.some(v=>v===1));
  for(let i=0;i<count;i++) {
    if(Math.max(g.attributes.color.getX(i),g.attributes.color.getY(i),g.attributes.color.getZ(i))>1.05) {
      assert.equal(g.attributes.aOcc.getX(i),1,'glow skips AO');
    }
  }
}
assert.match(source,/fur: 3\.25/);
assert.match(source,/previous\.version!==version/);
assert.match(source,/if\(rigMatrixDirty\) rigMesh\.instanceMatrix\.needsUpdate=true/);
const detailLevel=new Function(source.match(/function unitDetailLevel\([^]*?\n}/)[0]+';return unitDetailLevel;')();
assert.equal(detailLevel({staticBody:{}},false,600),'mesh');
assert.equal(detailLevel({staticBody:{}},false,601),'staticBody');
assert.equal(detailLevel({staticBody:{}},true,1000),'simple');
assert.equal(detailLevel({},false,800),'mesh');
assert.match(source,/if\(staticKind && rig.mode!=='strike'\) return/);
assert.match(source,/markedCount<128/);assert.match(source,/auraCount<32/);
assert.match(source,/huntMarks=markerMesh\(huntMarks,huntMarkGeo,128,128\)/);
assert.match(source,/commandAuras=markerMesh\(commandAuras,commandAuraGeo,32,32\)/);
assert.match(source,/commandAuraRadius/);assert.doesNotMatch(source,/auraRadius=220/);
assert.equal(weaponFamily('javelin'),'sting');assert.equal(weaponFamily('megalith'),'heavy');
assert.deepEqual(MUZZLE_POINTS.javelin,[10,14]);assert.deepEqual(MUZZLE_POINTS.catapult,[-4,34]);
for(const look of ['javelin','megalith']) {
  const section=source.slice(source.indexOf("} else if (look === '"+look+"')"));
  const branch=section.slice(0,section.indexOf('} else if',5));
  assert.ok((branch.match(/writeTracer\(tracers/g)||[]).length<=4);
  assert.ok((branch.match(/writeTracer\(orbs/g)||[]).length<=2);
  assert.ok((branch.match(/writeTracer\(shards/g)||[]).length<=2);
}
const maps=createRiverSurfaceMaps(),pbr=new THREE.MeshStandardMaterial();
pbr.onBeforeCompile=shader=>{shader.uniforms.uArmySurface={value:null};};
applyRiverPBR(pbr,maps);
const shader={uniforms:{},vertexShader:'#include <begin_vertex>',fragmentShader:
  'float gSurfaceLum = 0.5;\n#include <roughnessmap_fragment>\n#include <normal_fragment_maps>'};
pbr.onBeforeCompile(shader);
assert.match(shader.fragmentShader,/riverFur/);
assert.match(shader.fragmentShader,/roughnessFactor=0\.9/);
assert.match(pbr.customProgramCacheKey(),/river-pbr-v4/);
assert.equal(maps.normal.image.width,512);
maps.normal.dispose();maps.orm.dispose();maps.color?.dispose();pbr.dispose();material.dispose();
console.log('部落近景几何、关节、材质、破拆锚定与特效容量测试通过。');
