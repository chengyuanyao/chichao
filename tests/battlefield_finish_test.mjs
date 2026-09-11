import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import vm from 'node:vm';
import * as THREE from '../public/vendor/three.module.min.js';
import {riverStructureDetails} from '../public/river_art_models.js';
import {wreckFamily,collapsePose,suspensionSlope,COLLAPSE_LIMIT,applyBuildingCollapse} from '../public/battlefield_finish.js';
assert.equal(wreckFamily('factory'),'rubble');assert.equal(wreckFamily('dragon'),'arcane');
assert.equal(wreckFamily('tank'),'vehicle');
assert.equal(collapsePose(0).height,1);assert.equal(collapsePose(1).done,true);
for(let t=0;t<1;t+=.01) assert.ok(collapsePose(t).height>0);
assert.equal(suspensionSlope(20,20,40),0);
assert.ok(Math.abs(suspensionSlope(1000,0,40))<=.085);
const source=readFileSync(new URL('../public/render3d.js',import.meta.url),'utf8');
const fn=name=>source.match(new RegExp('  function '+name+'\\([^]*?\\n  }'))[0];
const removed=[];
const context={collapsingStructures:[],COLLAPSE_LIMIT,collapsePose,isVisible:()=>true,
 worldRoot:{remove:g=>removed.push(g)},structureNodes:new Map()};
vm.createContext(context);vm.runInContext(['retireCollapse','startCollapse','updateCollapses'].map(fn).join('\n'),context);
function node(){return {group:new THREE.Group(),structure:{x:10,y:20},
 teamMat:new THREE.MeshPhongMaterial(),breakMat:applyBuildingCollapse(new THREE.MeshPhongMaterial())};}
const n=node();context.startCollapse(n);context.updateCollapses(.4);
assert.equal(n.group.scale.y,1,'rigid pieces, not whole-building squash');
assert.ok(n.breakMat.userData.collapseProgress.value>0);
let disposed=0;n.teamMat.addEventListener('dispose',()=>disposed++);n.breakMat.addEventListener('dispose',()=>disposed++);
context.updateCollapses(.5);assert.equal(context.collapsingStructures.length,0);assert.equal(disposed,2);
for(let i=0;i<20;i++)context.startCollapse(node());assert.equal(context.collapsingStructures.length,COLLAPSE_LIMIT);
assert.match(source,/fx.entityId===id && fx.wreck/,'only confirmed destruction animates');
assert.match(source,/wreckLayers.reduce\(\(n,l\)=>n\+l.list.length,0\)>=FEEDBACK_LIMITS.wrecks/,'one global debris cap');
assert.match(source,/trackLayer.list.length=0/,'tracks clear on restart');
for(const type of ['standard','phong']) {
 const material=applyBuildingCollapse(type==='standard'?new THREE.MeshStandardMaterial():new THREE.MeshPhongMaterial());
 const shader={uniforms:{},vertexShader:THREE.ShaderLib[type].vertexShader};material.onBeforeCompile(shader);
 assert.equal(shader.uniforms.uCollapseProgress.value,0);
 assert.match(shader.vertexShader,/objectNormal=breakRotation/);
 assert.match(shader.vertexShader,/transformed=breakRotation/);
 assert.match(shader.vertexShader,/aBreak.w>=0.0/,'anchored foundations do not fly');
 material.userData.collapseProgress.value=.5;assert.equal(shader.uniforms.uCollapseProgress.value,.5);
 material.dispose();
}
assert.match(source,/warmMaterial\(MAGIC_STRUCTURE_KINDS\[kind\]\?'stone':'metal',sample,true\)/,'fracture program prewarmed for both families');
// Exercise actual cached geometry and attachment groups, not empty mock nodes.
const geometrySource=source.slice(0,source.indexOf('/**\n * 组装一座建筑'))
 .replace(/^import\s[\s\S]*?;$/mg,'').replace(/^export /mg,'');
const groupSource=source.match(/function structureGroup\([^]*?\n}/)[0];
const makeGroup=new Function('THREE','riverStructureDetails',geometrySource+'\n'+groupSource+';return structureGroup;')(THREE,riverStructureDetails);
const catalog=readFileSync(new URL('../catalog.py',import.meta.url),'utf8');
const catalogBlock=catalog.slice(catalog.indexOf('STRUCTURE_TYPES = {'),catalog.indexOf('\nMAGIC_STRUCTURES'));
context.updateCollapses(1);
let checked=0;
for(const sample of [false,true]) for(const match of catalogBlock.matchAll(/^\s{4}"(\w+)": \{[\s\S]*?"size": ([\d.]+)/gm)) {
 const kind=match[1],size=Number(match[2]),n=node();n.teamMat.color.set('#18aee0');
 n.group=makeGroup(kind,size,n.teamMat,sample);
 n.head=n.group.getObjectByName('turretHead');n.spinner=n.group.getObjectByName('spinner');
 let geometries=0;const positions=[];
 n.group.traverse(mesh=>{
   if(!mesh.isMesh)return;geometries++;
   const g=mesh.geometry;assert.equal(g.attributes.aBreak.count,g.attributes.position.count,kind);
   assert.ok(g.attributes.aBreak.array.every(Number.isFinite),kind+' finite anchors');
   positions.push([g,g.attributes.position.array.slice()]);
 });
 assert.ok(geometries>0);
 if(['hq','mhq','factory'].includes(kind)) {
   const a=n.group.children[0].geometry.attributes.aBreak;
   assert.ok(Array.from({length:a.count},(_,i)=>a.getW(i)).some(v=>v<0),kind+' foundation is anchored');
 }
 let released=0;n.teamMat.addEventListener('dispose',()=>released++);n.breakMat.addEventListener('dispose',()=>released++);
 const headY=n.head?.position.y,spinY=n.spinner?.position.y;
 context.startCollapse(n);context.updateCollapses(.45);
 assert.equal(n.breakMat.color.getHex(),n.teamMat.color.getHex(),kind+' ownership preserved');
 n.group.traverse(mesh=>{if(mesh.isMesh){assert.equal(mesh.material,n.breakMat);assert.equal(mesh.frustumCulled,false);}});
 if(n.head) assert.ok(n.head.position.y<headY,kind+' head falls from attachment height');
 if(n.spinner) assert.ok(n.spinner.position.y<spinY,kind+' spinner falls from attachment height');
 context.isVisible=()=>false;context.updateCollapses(.05);assert.equal(n.group.visible,false,kind+' hidden by fog');
 context.isVisible=()=>true;context.updateCollapses(.05);assert.equal(n.group.visible,true);
 context.updateCollapses(.4);assert.equal(released,2,kind+' both materials released');
 for(const [geo,before] of positions) assert.deepEqual(geo.attributes.position.array,before,kind+' cached model is not mutated');
 checked++;
}
assert.equal(checked,30,'all 15 buildings in both model families');
console.log('Battlefield finish passed: debris families, bounded collapse, disposal, confirmed death, suspension clamp and track reset.');
