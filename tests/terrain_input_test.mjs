import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import vm from 'node:vm';
import {performance} from 'node:perf_hooks';
import * as THREE from '../public/vendor/three.module.min.js';
import {prepareTerrainInput,intersectTerrainInput} from '../public/terrain_input.js';
import {createModelPicker} from '../public/model_picker.js';

const render=readFileSync(new URL('../public/render3d.js',import.meta.url),'utf8');
const app=readFileSync(new URL('../public/app.js',import.meta.url),'utf8');
function fn(text,name) {
  const match=text.match(new RegExp('  (?:async )?function '+name+'\\([^]*?\\n  \\}'));
  assert.ok(match,name);return match[0];
}
function fieldFor(height,segX=20,segY=20) {
  const values=new Float32Array((segX+1)*(segY+1));
  for(let z=0;z<=segY;z++) for(let x=0;x<=segX;x++) values[z*(segX+1)+x]=height(x*1000/segX,z*1000/segY);
  return {values,cols:segX+1,segX,segY,width:1000,height:1000};
}
const camera=new THREE.PerspectiveCamera(46,1280/720,12,12000);
const rc=new THREE.Raycaster();
const heightContext={THREE,heightField:null,state:{terrain:{}},riverValleyMode:()=>heightContext.state.terrain.visualStyle==='river_valley'};
vm.createContext(heightContext);
vm.runInContext(fn(render,'baseGroundHeight')+fn(render,'bridgeSurfaceHeightAt')+fn(render,'groundHeight'),heightContext);
function setup(field,terrain={}) {
  heightContext.heightField=field;heightContext.state.terrain=terrain;
  return prepareTerrainInput(field,terrain);
}
function view(pitch=.94,yaw=0,zoom=.78) {
  const dist=620/zoom;
  camera.position.set(500-Math.sin(yaw)*Math.cos(pitch)*dist,Math.sin(pitch)*dist,500+Math.cos(yaw)*Math.cos(pitch)*dist);
  camera.lookAt(500,0,500);camera.updateMatrixWorld();
}
function screen(point) {
  const p=point.clone().project(camera);return {x:(p.x*.5+.5)*1280,y:(.5-p.y*.5)*720};
}
function rayThrough(point) {
  const p=point.clone().project(camera);rc.setFromCamera(new THREE.Vector2(p.x,p.y),camera);return rc.ray;
}
let roundTrips=0;
const fields=[...[-80,0,40,80,180].map(h=>fieldFor(()=>h)),
  fieldFor((x,z)=>.12*x+.04*z-90),fieldFor((x,z)=>x*z*.0002-40)];
for(const field of fields) for(const pitch of [.5,.94,1.3]) for(const yaw of [0,.9,2.4]) {
  const input=setup(field);view(pitch,yaw);
  for(const [x,z] of [[400,420],[500,500],[610,540]]) {
    const height=heightContext.groundHeight(x,z);
    const hit=intersectTerrainInput(rayThrough(new THREE.Vector3(x,height,z)),input,camera.near,camera.far);
    assert.ok(hit,'surface must be hit');
    assert.ok(Math.hypot(hit.x-x,hit.y-z)<.001,JSON.stringify({pitch,yaw,x,z,hit,height}));
    assert.ok(Math.abs(hit.height-height)<.001);roundTrips++;
  }
}
// First visible intersection, not a fixed-point solution on a rear hillside.
let input=setup(fieldFor(x=>Math.max(0,100-Math.abs(x-300)*.5,100-Math.abs(x-700)*.5)));
let hit=intersectTerrainInput(new THREE.Ray(new THREE.Vector3(0,50,500),new THREE.Vector3(1,0,0)),input);
assert.ok(Math.abs(hit.x-200)<.001);
// Bilinear saddle: two crossings occur inside ONE cell, endpoints alone miss it.
input=setup(fieldFor((x,z)=>x*(1000-z)*.001,1,1));
hit=intersectTerrainInput(new THREE.Ray(new THREE.Vector3(0,80,0),new THREE.Vector3(1,0,1).normalize()),input);
assert.ok(Math.abs(hit.x-(1000-Math.sqrt(680000))/2)<.001);

// Bridge deck, both ramps, oblique bridge and terrain above/below the deck.
for(const bridge of [
  {x1:300,y1:500,x2:700,y2:500,width:140,ramp:110,deckHeight:28},
  {x1:300,y1:300,x2:700,y2:700,width:140,ramp:110,deckHeight:28}
]) {
  input=setup(fieldFor(()=>-55),{visualStyle:'river_valley',bridges:[bridge]});
  view(.94,.3);
  const length=Math.hypot(bridge.x2-bridge.x1,bridge.y2-bridge.y1);
  const ux=(bridge.x2-bridge.x1)/length,uz=(bridge.y2-bridge.y1)/length;
  for(const along of [-55,0,length*.5,length,length+55]) {
    const x=bridge.x1+along*ux,z=bridge.y1+along*uz;
    const height=heightContext.groundHeight(x,z);
    hit=intersectTerrainInput(rayThrough(new THREE.Vector3(x,height,z)),input);
    assert.ok(Math.hypot(hit.x-x,hit.y-z)<.001,'bridge/ramp must not fall through to riverbed');
    assert.ok(Math.abs(hit.height-height)<.001);roundTrips++;
  }
  const center=new THREE.Vector3((bridge.x1+bridge.x2)/2,1000,(bridge.y1+bridge.y2)/2);
  input=setup(fieldFor(()=>60),{visualStyle:'river_valley',bridges:[bridge]});
  assert.ok(Math.abs(intersectTerrainInput(new THREE.Ray(center,new THREE.Vector3(0,-1,0)),input).height-60)<.001);
  input=setup(fieldFor(()=>-55),{visualStyle:'forest_barrier',bridges:[bridge]});
  assert.ok(Math.abs(intersectTerrainInput(new THREE.Ray(center,new THREE.Vector3(0,-1,0)),input).height+55)<.001,
    'forest corridors must not invent raised bridges');
}
input=setup(fieldFor(()=>80));
assert.equal(intersectTerrainInput(new THREE.Ray(new THREE.Vector3(500,300,500),new THREE.Vector3(0,1,0)),input),null);
assert.equal(intersectTerrainInput(new THREE.Ray(new THREE.Vector3(-100,300,500),new THREE.Vector3(0,-1,0)),input),null);
assert.equal(intersectTerrainInput(new THREE.Ray(new THREE.Vector3(500,300,500),new THREE.Vector3(0,-1,0)),input,0,10),null);

// Actual renderer input method and actual client routing. Raw screen coordinates
// must survive even when a ground point is high, outside the map or a fallback.
view();
const core={state:{width:1280,height:720,camX:500,camY:500},camera,terrainInput:input,intersectTerrainInput,
  applyCamera(){},ndc:new THREE.Vector2(),raycaster:new THREE.Raycaster(),hitPoint:new THREE.Vector3(),
  groundPlane:new THREE.Plane(new THREE.Vector3(0,1,0),0)};
vm.createContext(core);vm.runInContext(fn(render,'screenToFlatWorld')+fn(render,'screenToWorld'),core);
const surfaceScreen=screen(new THREE.Vector3(500,80,500));
const actual=core.screenToWorld(surfaceScreen.x,surfaceScreen.y);
assert.ok(Math.hypot(actual.x-500,actual.y-500)<.001);
assert.ok(Math.abs(core.screenToFlatWorld(surfaceScreen.x,surfaceScreen.y).y-500)>60,'old bug must still be reproduced');

const picker=createModelPicker(), material=new THREE.MeshBasicMaterial(),geometry=new THREE.BoxGeometry(12,20,12);
const mesh=new THREE.InstancedMesh(geometry,material,1);
mesh.setMatrixAt(0,new THREE.Matrix4().makeTranslation(500,90,500));
const own={id:'u-own',owner:'me',kind:'rifle',hp:100,x:800,y:800}; // Snapshot ahead of displayed position.
const enemy={id:'u-enemy',owner:'enemy',kind:'rifle',hp:100};
mesh.userData.instanceIds=[own.id];
const rendererContext={camera,modelPicker:picker,state:{map:{},width:1280,height:720},
  unitPools:new Map([['rifle',{mesh,simple:null}]]),apocArmMesh:null,dragonOrbitMesh:null,
  apocArmVisuals:[],dragonOrbitVisuals:[],structureNodes:new Map()};
vm.createContext(rendererContext);vm.runInContext(fn(render,'collectPickModels')+fn(render,'unitsInScreenBox'),rendererContext);
const center=screen(new THREE.Vector3(500,90,500));
const game={units:[own,enemy],structures:[]};
const selected=rendererContext.unitsInScreenBox(game,'me',center.x-15,center.y-15,center.x+15,center.y+15);
assert.equal(selected[0],own,'height and displayed interpolation must determine selection');
assert.equal(selected.length,1);
assert.equal(rendererContext.unitsInScreenBox(game,'enemy',center.x-15,center.y-15,center.x+15,center.y+15).length,0);
assert.equal(rendererContext.unitsInScreenBox({units:[{...own,hp:0}],structures:[]},'me',0,0,1280,720).length,0);
mesh.visible=false;assert.equal(rendererContext.unitsInScreenBox(game,'me',0,0,1280,720).length,0);mesh.visible=true;

const client={pointer:{x:surfaceScreen.x,y:surfaceScreen.y},session:{playerId:'me'},roomState:{game},
  selectedUnits:new Set(['old']),selectedStructureId:'old',selectedResourceId:'old',sound(){},renderSelectionInfo(){},
  view3d:{screenToWorld:core.screenToWorld,unitsInScreenBox:rendererContext.unitsInScreenBox,
    pickEntityAt:(g,x,y)=>{assert.equal(x,surfaceScreen.x);assert.equal(y,surfaceScreen.y);return enemy;}}};
vm.createContext(client);vm.runInContext(['screenToWorld','updatePointerWorld','entityAt','selectBoxUnits'].map(n=>fn(app,n)).join('\n'),client);
client.updatePointerWorld();assert.ok(Math.abs(client.pointer.worldY-500)<.001);
assert.equal(client.entityAt(9999,-9999),enemy,'picking never reprojects a terrain point as a flat point');
client.selectBoxUnits(center.x+15,center.y+15,center.x-15,center.y-15,false);
assert.deepEqual([...client.selectedUnits],[own.id]);
client.selectedUnits.add('existing');client.selectBoxUnits(center.x-15,center.y-15,center.x+15,center.y+15,true);
assert.deepEqual([...client.selectedUnits],[own.id,'existing']);
client.selectBoxUnits(0,0,10,10,false);assert.equal(client.selectedUnits.size,0);

// Pointer-to-command wiring stays shared by move, patrol, build, ping and strike;
// model selection uses raw screen coordinates independently.
const pointerDown=app.match(/canvas\.addEventListener\('pointerdown', function \(event\) \{[^]*?\n  \}\);/)[0];
assert.ok(pointerDown.indexOf('pointerPosition(event)')<pointerDown.indexOf('issuePatrolCommand'));
assert.match(pointerDown,/issuePatrolCommand\(pointer.worldX, pointer.worldY\)/);
assert.match(pointerDown,/issueContextCommand\(pointer.worldX, pointer.worldY\)/);
assert.match(fn(app,'placeCurrentBuilding'),/x: pointer.worldX,\s*y: pointer.worldY/);

// Mousemove cost on a 6400-scale dense map (same cell count as real maps).
const dense=fieldFor((x,z)=>60*Math.sin(x*.009)*Math.cos(z*.012),160,160);
dense.width=dense.height=6400;input=prepareTerrainInput(dense);
const started=performance.now();
for(let i=0;i<4000;i++) intersectTerrainInput(new THREE.Ray(new THREE.Vector3(2500+i*.1,800,3000),
  new THREE.Vector3(.1,-.7,.6).normalize()),input);
console.log(`Terrain input: ${roundTrips} height/yaw/bridge round trips, first-hit hills, saddle roots, raw model clicks, interpolated box selection and command wiring passed; ${(performance.now()-started).toFixed(1)} ms / 4000 rays.`);
picker.dispose();mesh.dispose();geometry.dispose();material.dispose();
