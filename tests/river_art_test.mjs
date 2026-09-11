import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import * as THREE from '../public/vendor/three.module.min.js';
import {createRiverSurfaceMaps,applyRiverPBR,applyRiverGround} from '../public/river_art_materials.js';
import {applyBattleMaterial} from '../public/battle_feedback.js';
import {createModelPicker} from '../public/model_picker.js';
import {riverUnitModel,riverStructureDetails,artJointAngle,RIVER_ART_KINDS,armorShell,organicShell} from '../public/river_art_models.js';
const source=readFileSync(new URL('../public/render3d.js',import.meta.url),'utf8');
const modelSource=source.slice(0,source.indexOf('/**\n * 组装一座建筑'))
 .replace(/^import\s[\s\S]*?;$/mg,'').replace(/^export /mg,'');
function factory(name) {const s=source.indexOf(`  function ${name}(`),e=source.indexOf('\n  }',s);return source.slice(s,e+4);}
const {unit,structure}=new Function('THREE','riverUnitModel','riverStructureDetails',`${modelSource}
 const UNIT_GEOMETRY_CACHE=new Map();${factory('simpleUnitParts')} ${factory('unitGeometry')}
 return {unit:unitGeometry,structure:structureGeometries};`)(THREE,riverUnitModel,riverStructureDetails);
const picker=createModelPicker(),pickMat=new THREE.MeshBasicMaterial();
const makeBevel=new Function('THREE',`${modelSource};return chamferedBoxGeometry;`)(THREE);
for(const dims of [[10,4,8],[40,.5,2],[.4,20,12]]) {
 const geo=makeBevel(...dims);geo.computeBoundingBox();
 const measured=geo.boundingBox.getSize(new THREE.Vector3());
 for(let i=0;i<3;i++) assert.ok(Math.abs(measured.getComponent(i)-dims[i])<1e-5,'bevel keeps footprint');
 assert.equal(geo.attributes.position.count/3,28,'true narrow bevel is cheaper than old 32-face cylinder');
 assert.ok(geo.attributes.normal.array.every(Number.isFinite));geo.dispose();
}
const pickCamera=new THREE.PerspectiveCamera(46,1280/720,12,12000);
pickCamera.position.set(0,440,440);pickCamera.lookAt(0,40,0);pickCamera.updateMatrixWorld();
for(const kind of RIVER_ART_KINDS) {
 const original=unit(kind),sample=unit(kind,true);
 assert.notEqual(original,sample);assert.equal(unit(kind,true),sample);
 assert.deepEqual(original.simple.attributes.position.array,sample.simple.attributes.position.array);
 const pieces=[sample.body,sample.barrel,...(sample.rigs||[]).map(r=>r.geometry)].filter(Boolean);
 let triangles=0;
 for(const geo of pieces) {
  for(const key of ['position','normal','uv','aTeam','aOcc','aSurf']) assert.ok(geo.attributes[key].array.every(Number.isFinite),kind+'/'+key);
  geo.computeBoundingBox();assert.ok(geo.boundingBox.min.y>=-1||sample.rigs?.some(r=>r.geometry===geo));
  triangles+=geo.attributes.position.count/3;
  const mesh=new THREE.InstancedMesh(geo,pickMat,1),entity={id:'sample',owner:'me',kind,hp:100};
  const transform=new THREE.Matrix4().makeTranslation(10,35,10);
  mesh.setMatrixAt(0,transform);mesh.count=1;
  picker.begin();picker.addInstances(mesh,()=>entity);
  const p=geo.attributes.position,a=new THREE.Vector3(),b=new THREE.Vector3(),c=new THREE.Vector3();
  let hit=false;
  for(let i=0;i<p.count;i+=3) {
    a.fromBufferAttribute(p,i);b.fromBufferAttribute(p,i+1);c.fromBufferAttribute(p,i+2);
    if(new THREE.Triangle(a,b,c).getArea()<.01) continue;
    a.add(b).add(c).divideScalar(3).applyMatrix4(transform).project(pickCamera);
    hit=picker.pick(pickCamera,1280,720,(a.x*.5+.5)*1280,(.5-a.y*.5)*720)===entity;
    if(hit) break;
  }
  assert.ok(hit,kind+' articulated model is pickable');mesh.dispose();
 }
 assert.ok(triangles<10000,kind+' geometry budget');
 if(kind==='dragon') assert.ok(triangles<=3320,'head silhouette detail funded by membrane tessellation');
 if(kind==='overlord_v2') {
   const p=sample.body.attributes.position;let shoulderVertices=0;
   for(let i=0;i<p.count;i++) if(p.getY(i)>32&&p.getY(i)<42&&Math.abs(p.getZ(i))>14) shoulderVertices++;
   assert.ok(shoulderVertices>=24,'retain both shoulder armor housings around existing arm pivots');
   assert.ok(triangles<=2600,'shoulder fix stays within core robot geometry budget');
 }
 console.log(kind,triangles,'triangles',sample.rigs?.length||0,'rig batches');
}
for(const kind of ['hq','mhq','factory']) {
 const sample=structure(kind,58,true);assert.equal(sample,structure(kind,58,true));
 assert.notEqual(sample,structure(kind,58));assert.ok(sample.team.attributes.position.array.every(Number.isFinite));
 assert.equal(sample.team.attributes.aBreak.count,sample.team.attributes.position.count);
 assert.ok(sample.team.attributes.aBreak.array.every(Number.isFinite),'prebaked rigid-piece anchors');
 assert.ok(sample.team.attributes.position.count/3<10000,kind+' merged architecture budget');
 console.log(kind,sample.team.attributes.position.count/3,'architecture triangles');
}
const shell=armorShell([[-2,1,0,1],[2,1,0,1]],1).geo;
const anatomy=organicShell([[-2,1,2,1],[0,2,3,2],[2,1,4,1]],1).geo;
for(const name of ['position','normal','uv']) assert.ok(anatomy.attributes[name].array.every(Number.isFinite));
for(let i=0;i<3;i++) {
 const a=i*11,b=a+10;
 for(let axis=0;axis<3;axis++) assert.ok(Math.abs(anatomy.attributes.normal.array[a*3+axis]-anatomy.attributes.normal.array[b*3+axis])<1e-6,'loft seam is smooth');
 assert.ok(anatomy.attributes.normal.getZ(a)>.7,'loft sides face outward');
}
assert.ok(unit('overlord',true).body.attributes.aSurf.array.some(v=>v===.25),'bare-metal hardware is explicitly tagged');
assert.ok(structure('factory',58,true).team.attributes.aSurf.array.some(v=>v===.25),'factory hardware uses same material convention');
anatomy.dispose();
for(let i=0;i<shell.attributes.position.count;i++) if(shell.attributes.position.getY(i)>.99)
 assert.ok(shell.attributes.normal.getY(i)>=0,'armor upper faces point outward');
assert.equal(artJointAngle({mode:'walk',side:1},100,10,0),0);
assert.equal(artJointAngle({mode:'walk',side:1},100,10,1),-artJointAngle({mode:'walk',side:-1},100,10,1));
assert.match(source,/pool\.rigs/);assert.match(source,/state.artSample = state.artSampleOption !== false/);
const maps=createRiverSurfaceMaps(new THREE.Texture());
assert.equal(maps.normal.colorSpace,THREE.NoColorSpace);
assert.equal(maps.orm.colorSpace,THREE.NoColorSpace);
assert.equal(maps.normal.image.width,512);
for(const data of [maps.normal.image.data,maps.orm.image.data]) assert.ok(data.every(Number.isFinite));
const {solidSurface}=await import('../public/asset_warmup.js');
const decorate=new Function('sunDirViewUniform','armyTimeUniform','makeArmySurfaceTexture','applyBattleMaterial','solidSurface',
 `${factory('applyEmissiveByVertexColor')};return applyEmissiveByVertexColor;`)({}, {},()=>new THREE.Texture(),applyBattleMaterial,solidSurface);
const material=applyRiverPBR(decorate(new THREE.MeshStandardMaterial(),'metal'),maps);
const shader={uniforms:{},vertexShader:THREE.ShaderLib.standard.vertexShader,fragmentShader:THREE.ShaderLib.standard.fragmentShader};
material.onBeforeCompile(shader);
assert.equal(shader.uniforms.uArmySurface.value,maps.color);
assert.match(shader.fragmentShader,/vec2 gAtlasUv = riverUV/);
assert.match(shader.fragmentShader,/roughnessFactor=gMode/);
assert.match(shader.fragmentShader,/metalnessFactor=gMode/);
assert.match(shader.fragmentShader,/gMode>0.2\?1.0/,'bare metal is independent of brightness');
assert.match(shader.fragmentShader,/normal=normalize\(riverTBN\*normalize\(riverN\)\)/);
assert.match(shader.fragmentShader,/pow\(max\(vOwnColor/,'sRGB own colors decoded only once');
assert.match(shader.fragmentShader,/riverSurfaceUv\*=gMode/,'physical texel density independent of primitive size');
assert.doesNotMatch(shader.fragmentShader,/gBumpScale \* gDetailFade \* gGrad/);
assert.match(shader.vertexShader,/vRiverUv=uv/);
const ground=applyRiverGround(new THREE.MeshLambertMaterial());
const gs={fragmentShader:'diffuseColor.rgb *= tdSurface;'};ground.onBeforeCompile(gs);
assert.match(gs.fragmentShader,/riverWet/);
maps.normal.dispose();maps.orm.dispose();maps.color.dispose();material.dispose();ground.dispose();
pickMat.dispose();
console.log('River art: cached variants, unchanged distant models, finite authored UV/geometry, outward armor normals, picking rigs and bounded motion passed.');
