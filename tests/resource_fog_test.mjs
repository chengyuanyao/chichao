import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import vm from 'node:vm';
import * as THREE from '../public/vendor/three.module.min.js';
import {oreReserveTier} from '../public/render3d.js';

const app = readFileSync(new URL('../public/app.js',import.meta.url),'utf8');
const render = readFileSync(new URL('../public/render3d.js',import.meta.url),'utf8');
function sourceFunction(source,name) {
  const match=source.match(new RegExp('  function '+name+'\\([^]*?\\n  \\}'));
  assert.ok(match, name); return match[0];
}
let visible=false;
const arcs=[];
const ctx=new Proxy({}, {get(target,key) {
  if(key==='arc') return (...args)=>arcs.push(args);
  return target[key] || (()=>{});
},set(target,key,value){target[key]=value;return true;}});
const resource={id:'ore-private',x:2000,y:2000,radius:48,amount:230000,maxAmount:230000};
const env={roomState:{game:{map:{width:4000,height:4000},terrain:{},resources:[resource],
  structures:[],units:[],crates:[],pings:[],strikes:[]}},
  minimap:{width:400,height:400},miniCtx:ctx,minimapStaticCanvas:{},buildMinimapStatic(){},
  view3d:{isVisible:()=>visible,getFogCanvas:()=>({}),screenToWorld:()=>({x:0,y:0})},
  oreReserveTier,selectedResourceId:resource.id,cellHash:()=>.5,paintTerrainFeatures(){},
  activeAttackAlerts:()=>[],ownIntent:()=>null,performance:{now:()=>1000},viewWidth:1000,viewHeight:600};
vm.createContext(env);
vm.runInContext(sourceFunction(app,'drawMinimap'),env);
for(const [width,height] of [[4000,4000],[6400,6400],[4800,3200]]) {
  env.roomState.game.map={width,height};
  visible=false;arcs.length=0;env.drawMinimap();assert.equal(arcs.length,0,'unscouted selected ore is hidden');
  visible=true;env.drawMinimap();assert.ok(arcs.length>0,'friendly sight reveals marker');
  visible=false;arcs.length=0;env.drawMinimap();assert.equal(arcs.length,0,'no permanent discovery bypass');
  visible=true;resource.amount=0;env.drawMinimap();assert.equal(arcs.length,0,'depleted ore is hidden');
  resource.amount=230000;
}

// Exercise the actual 3D updater, including invisible entries omitted by the server.
const mesh={visible:true,userData:{}};
const oreEnv={oreMeshes:new Map([[resource.id,mesh]]),state:{resourceById:new Map([[resource.id,resource]])},
  oreReserveTier,isVisible:()=>visible};
vm.createContext(oreEnv);
vm.runInContext(sourceFunction(render,'updateOre'),oreEnv);
visible=false;oreEnv.updateOre([[resource.id,230000,0]],1000);assert.equal(mesh.visible,false);
visible=true;oreEnv.updateOre([[resource.id,230000,0]],1100);assert.equal(mesh.visible,true);
visible=false;oreEnv.updateOre([],1200);assert.equal(mesh.visible,false,'missing delta hides old mesh');
visible=true;oreEnv.updateOre([[resource.id,0,0]],1300);assert.equal(mesh.visible,false);

const rockGeo=new THREE.BoxGeometry(), rockMat=new THREE.MeshBasicMaterial();
const rockMesh=new THREE.InstancedMesh(rockGeo,rockMat,1);
rockMesh.setMatrixAt(0,new THREE.Matrix4().makeTranslation(40,10,10));
mesh.position={y:300};
Object.assign(mesh.userData,{crystalMesh:rockMesh,crystalCapacity:1,
  maxTier:oreReserveTier(230000),groundSamples:[{x:40,y:10,lift:7}]});
oreEnv.THREE=THREE;oreEnv.groundHeight=(x,y)=>x*.05+y*.1;
for(const amount of [230000,10000,1000]) {
  oreEnv.updateOre([[resource.id,amount,0]],1400);
  const pose=new THREE.Matrix4();rockMesh.getMatrixAt(0,pose);
  const actualBase=mesh.position.y+pose.elements[13]*rockMesh.scale.y-7*rockMesh.scale.y;
  const expected=oreEnv.groundHeight(resource.x+40*rockMesh.scale.x,resource.y+10*rockMesh.scale.z);
  assert.ok(Math.abs(actualBase-expected)<.001,'shrinking reserve tiers stay seated on slopes');
}
rockGeo.dispose();rockMat.dispose();rockMesh.dispose();

// Late mineral discovery must hydrate coordinates and reserves without rebuilding terrain.
let oreBuilds=0;
const hydration={matchStatic:null,minimapStaticKey:'',applyCatalog(){},view3d:{
  setMatch(){return true;},setResources(resources){oreBuilds++;assert.equal(resources.length,1);}}};
vm.createContext(hydration);
vm.runInContext(sourceFunction(app,'hydrateGame'),hydration);
assert.equal(hydration.hydrateGame({ore:[]}),false,'delta before static metadata is ignored');
hydration.hydrateGame({full:true,map:{id:'central_scramble',seed:1},terrain:{},resources:[],sight:{},resourceIntel:[],ore:[]});
const learned={resourceIntel:[{...resource,amount:230000}],ore:[[resource.id,229000,0]]};
hydration.hydrateGame(learned);
assert.equal(learned.resources.length,1);assert.equal(learned.resources[0].amount,229000);assert.equal(oreBuilds,1);
const hidden={resourceIntel:[],ore:[]};hydration.hydrateGame(hidden);
assert.equal(hidden.resources[0].amount,229000,'no blind reserve updates');assert.equal(oreBuilds,1);
hydration.hydrateGame({resourceIntel:[{...resource,amount:200000}],ore:[[resource.id,200000,0]]});
assert.equal(oreBuilds,1,'rediscovery reuses existing geometry');
hydration.hydrateGame({full:true,map:{id:'central_scramble',seed:2},terrain:{},resources:[],sight:{},resourceIntel:[],ore:[]});
assert.equal(hydration.matchStatic.resources.length,0,'new match does not inherit mineral intel');
assert.ok(render.includes('cluster.visible = false; // No one-frame flash'));
assert.ok(render.includes('visionSources.length = 0;'));
assert.ok(render.includes('resetFogState();'));
assert.ok(app.includes("':' + roomState.game.map.seed"));
console.log('Resource fog: actual minimap/3D/hydration paths passed; live sight only, no stale markers, no blind reserve deltas, late discoveries and new-match reset.');
