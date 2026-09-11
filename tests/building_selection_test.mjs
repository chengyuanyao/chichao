import assert from 'node:assert/strict';
import vm from 'node:vm';
import {readFileSync} from 'node:fs';
import * as THREE from '../public/vendor/three.module.min.js';

const source=readFileSync(new URL('../public/render3d.js',import.meta.url),'utf8');
const update=source.match(/  function updateReadability\(game,time\) \{[\s\S]*?\n  }/)[0];
const mesh=()=>({count:99,visible:true,instanceMatrix:{},instanceColor:{},setMatrixAt(){},setColorAt(){}});
const building={id:'hq1',owner:'blue',size:58,x:150,y:200};
const node={structure:building,group:{visible:true},groundY:25};
const context={state:{renderedUnits:0,renderedStructures:1,artSample:false},
  ownerMarks:mesh(),dangerMarks:mesh(),markerMesh:existing=>existing,
  ownerMarkGeo:{},dangerMarkGeo:{},markerMaterial:{},riverOwnerMaterial:{},snapshotVisuals:[],
  matrix:new THREE.Matrix4(),vecPos:new THREE.Vector3(),vecScale:new THREE.Vector3(),
  quatIdentity:new THREE.Quaternion(),tmpColor:new THREE.Color(),colorOf:()=> '#44bbff',groundHeight:()=>25,
  structureNodes:new Map([[building.id,node]]),payload:{selectedStructureId:null},
  rings:mesh(),ringSpin:new THREE.Quaternion(),ringCount:0};
vm.createContext(context);vm.runInContext(update,context);
for(const sample of [false,true]) {
  context.state.artSample=sample;
  context.updateReadability({structures:[building]},0);
  assert.equal(context.ownerMarks.count,0,'unselected buildings have no owner arcs in either art mode');
  assert.equal(context.ownerMarks.visible,false,'stale owner marks are hidden');
}
const start=source.indexOf('    if (payload.selectedStructureId) {');
const end=source.indexOf('    if (payload.selectedResourceId)',start);
const selection=source.slice(start,end);
assert.ok(start>0&&end>start);
for(const [selected,visible,expected] of [[null,true,0],['hq1',true,1],['hq1',false,0],['missing',true,0]]) {
  context.payload.selectedStructureId=selected;node.group.visible=visible;context.ringCount=0;
  vm.runInContext(selection,context);
  assert.equal(context.ringCount,expected,'only the selected visible building gets one selection ring');
}
console.log('Building selection passed: no permanent owner arcs, stale marks cleared, selected/hidden/missing buildings handled.');
