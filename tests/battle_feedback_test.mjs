import assert from 'node:assert/strict';
import vm from 'node:vm';
import {readFileSync} from 'node:fs';
import * as THREE from '../public/vendor/three.module.min.js';
import {FEEDBACK_LIMITS,advanceTracks,recoilDistance,conditionFromHealth,effectDensity,applyBattleMaterial} from '../public/battle_feedback.js';
import {createBattleAudio} from '../public/battle_audio.js';
const vis={unit:{kind:'tank'},dir:0};
advanceTracks(vis,10,0,0);assert.equal(vis.trackLeft,10);assert.equal(vis.trackRight,10);
advanceTracks(vis,0,0,0);assert.equal(vis.trackLeft,10,'stopped treads cannot drift');
advanceTracks(vis,0,0,.3);assert.ok(vis.trackLeft<10&&vis.trackRight>10,'counter-rotating inside/outside tracks');
assert.equal(recoilDistance('tank',.34),0);assert.equal(recoilDistance('tank',Infinity),0);
assert.ok(recoilDistance('artillery',.045)>recoilDistance('tank',.045));
assert.equal(conditionFromHealth(100,100),0);assert.equal(conditionFromHealth(0,100),1);
assert.ok(effectDensity(2500)<effectDensity(900));

// Real material injection must not deform model-picking surfaces.
const material=applyBattleMaterial(new THREE.MeshPhongMaterial());
const shader={uniforms:{},vertexShader:THREE.ShaderLib.phong.vertexShader,fragmentShader:THREE.ShaderLib.phong.fragmentShader};
material.onBeforeCompile(shader);
assert.doesNotMatch(shader.vertexShader,/transformed\s*[-+]=/);
assert.match(shader.fragmentShader,/vTeamMix\*0.76/,'damage preserves owner paint');
assert.match(shader.fragmentShader,/fwidth\(phase\)/,'tread grooves antialias at distance');

// Execute actual bounded particle and decal code with tiny renderer stand-ins.
const source=readFileSync(new URL('../public/render3d.js',import.meta.url),'utf8');
function fn(name){const start=source.indexOf(`  function ${name}(`),end=source.indexOf('\n  }',start);assert.ok(start>=0&&end>start);return source.slice(start,end+4);}
const layer=()=>({list:[],geo:{attributes:Object.fromEntries(['position','color','size','alpha','seed'].map(k=>[k,{array:new Float32Array(1200)}])),setDrawRange(){}}});
const fireLayer=layer(),smokeLayer=layer();
const ctx={Math,TAU:Math.PI*2,FEEDBACK_LIMITS,EFFECT_MAX:400,state:{particleBudget:150,feedbackDensity:1},fireLayer,smokeLayer,
  groundHeight:()=>84,inViewportBounds:()=>true,flashAt(){},shockLayer:{spawn(){}},scorchLayer:{spawn(){}},
  wreckLayer:{list:[],spawn(item){if(this.list.length>=28)this.list.shift();this.list.push(item);}}};
vm.createContext(ctx);vm.runInContext(fn('emit')+'\nconst emitAbsoluteParticle=emit;\n'+fn('spawnEffect')+'\n'+fn('updateParticleLayer'),ctx);
ctx.spawnEffect('impact',100,200,'shell');
assert.ok(fireLayer.list.every(p=>p.y>=84),'high-ground sparks start above ground');
for(let i=0;i<200;i++)ctx.spawnEffect('explosion',100,200,null,{wreck:true,entityKind:'tank'});
assert.ok(fireLayer.list.length+smokeLayer.list.length<=150);
assert.ok(smokeLayer.list.length<=42);assert.equal(ctx.wreckLayer.list.length,28);
for(let i=0;i<80;i++) {ctx.updateParticleLayer(fireLayer,.05,.90,190);ctx.updateParticleLayer(smokeLayer,.05,.955,190);}
assert.equal(fireLayer.list.length+smokeLayer.list.length,0,'all particles expire');
ctx.inViewportBounds=()=>false;ctx.spawnEffect('explosion',100,200);assert.equal(fireLayer.list.length,0);
assert.doesNotMatch(source,/if \(isVisible\(vis.x, vis.y\)\) spawnEffect\('explosion'/,'vision loss is not a death');
assert.match(source,/pool.mesh, pool.simple, pool.barrel/,'recoiling barrels participate in real picking');

// WebAudio node graph fixture: limits, priorities, cached samples, teardown.
const samples=[],nodes=[];
function node(){const n={connect(){},disconnect(){this.disconnected=true;}};nodes.push(n);return n;}
const context={currentTime:0,state:'running',sampleRate:8000,destination:{},
  createGain(){return {...node(),gain:{value:1}};},
  createDynamicsCompressor(){return {...node(),threshold:{},knee:{},ratio:{},attack:{},release:{}};},
  createStereoPanner(){return {...node(),pan:{}};},
  createBuffer(_channels,n){const data=new Float32Array(n);samples.push(data);return {getChannelData:()=>data};},
  createBufferSource(){return {...node(),playbackRate:{},start(){},stop(){}};}};
const audio=createBattleAudio(context),view={x:0,y:0,width:1280,zoom:1};
const events=['bullet','shell','siege','tesla','arcane','frost','meteor','bite'].map((kind,i)=>({type:'muzzle',kind,x:i*10,y:0}));
for(let i=0;i<50;i++){context.currentTime+=.2;audio.events(events,view);audio.ui('select');}
assert.ok(audio.stats().voices<=12);assert.ok(audio.stats().combatVoices<=8);
assert.equal(audio.events([{type:'explosion',x:90000,y:90000}],view),0);
assert.ok(samples.every(a=>a.every(Number.isFinite)&&a.every(v=>Math.abs(v)<=1)));
audio.clear();assert.equal(audio.stats().voices,0);const cached=audio.stats().cachedSamples;
context.currentTime+=1;audio.ui('select');assert.equal(audio.stats().cachedSamples,cached);
audio.dispose();assert.equal(audio.stats().cachedSamples,0);
console.log('Battle feedback passed: motion, recoil, team-preserving wear, terrain-relative particles, combined/smoke/wreck/audio caps, expiry, fog disappearance, barrel picking and audio teardown.');
