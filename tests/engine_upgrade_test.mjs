import assert from 'node:assert/strict';
import vm from 'node:vm';
import {readFileSync} from 'node:fs';
import {createHash} from 'node:crypto';
import * as THREE from '../public/vendor/three.module.min.js';
import {REVISION as coreRevision} from '../public/vendor/three.core.min.js';
import {createPostFX,supportedSceneSamples} from '../public/postfx.js';
import {renderProfile,displayPixelRatio} from '../public/render_profile.js';
import {createMotionClock,pushVisualMotion,sampleVisualMotion} from '../public/visual_motion.js';

assert.equal(THREE.REVISION,'186');assert.equal(coreRevision,THREE.REVISION);
const provenance=JSON.parse(readFileSync(new URL('../public/vendor/THREE_VERSION.json',import.meta.url),'utf8'));
for(const [name,record] of Object.entries(provenance.files)) {
  const hash=createHash('sha256').update(readFileSync(new URL('../public/vendor/'+name,import.meta.url))).digest('hex');
  assert.equal(hash,record.sha256,name+' pinned offline bundle');
}
assert.equal(displayPixelRatio(3,'smooth'),1);
assert.equal(displayPixelRatio(3,'balanced'),1.5);
assert.equal(displayPixelRatio(3,'detailed'),2);
assert.equal(displayPixelRatio(NaN,'balanced'),1);
assert.equal(renderProfile('unknown'),renderProfile('balanced'));

const gl={RENDERBUFFER:1,RGBA16F:2,RGBA8:3,DEPTH_COMPONENT24:4,SAMPLES:5,
  getInternalformatParameter(_,format){return format===2?[4]:[4,2];}};
const renderer={capabilities:{isWebGL2:true,maxSamples:4},getContext:()=>gl,
  extensions:{get:()=>null},info:{render:{calls:1,triangles:1}},setRenderTarget(){},clear(){},render(){}};
assert.equal(supportedSceneSamples(renderer,2),4,'HDR/depth must share a supported sample count');
assert.equal(supportedSceneSamples({...renderer,capabilities:{maxSamples:1}},4),0);
assert.equal(supportedSceneSamples({...renderer,getContext:()=>({...gl,getInternalformatParameter:()=>[]})},4),0);
assert.equal(supportedSceneSamples(renderer,0),0);
const fx=createPostFX(renderer);
fx.setSize(1280,720,1.5);fx.setOptions({msaaSamples:2,resolutionScale:.7});
assert.equal(fx.sceneTarget.samples,4);
assert.equal(fx.sceneTarget.resolveDepthBuffer,false);
assert.deepEqual(fx.resolution,{width:1344,height:756,outputWidth:1920,outputHeight:1080,scale:.7,samples:4});
const draws=[];
renderer.setRenderTarget=t=>draws.push(t);
fx.render({}, {},0);
const post=draws.find(t=>t?.texture.type===THREE.UnsignedByteType&&t.width===1920);
assert.ok(post,'postprocessing stays at native output resolution');
assert.equal(post.samples,0,'fullscreen passes do not allocate MSAA');
assert.equal(draws[1].width,672,'bloom follows scene resolution');
fx.setOptions({resolutionScale:1,msaaSamples:0});
assert.equal(fx.sceneTarget.width,1920);assert.equal(fx.sceneTarget.samples,0);
fx.setOptions({resolutionScale:0});assert.equal(fx.resolution.scale,.5);
fx.dispose();

// 执行真实 resizeCanvas：自动降档保留 HUD 像素密度，保持模型拾取的 CSS 坐标。
const source=readFileSync(new URL('../public/app.js',import.meta.url),'utf8');
const start=source.indexOf('  function resizeCanvas()'),end=source.indexOf('\n  }',start);
const seen=[];
const context={currentScreen:'game',canvas:{getBoundingClientRect:()=>({width:800,height:600})},
  window:{devicePixelRatio:2},settings:{imageQuality:'balanced'},renderScale:.6,displayPixelRatio,
  dpr:0,viewWidth:0,viewHeight:0,lastViewWidth:0,lastViewHeight:0,lastDpr:-1,hudCanvas:{width:0,height:0},
  view3d:{resize:(...args)=>seen.push(args),setQuality:o=>seen.push(o)}};
vm.createContext(context);vm.runInContext(source.slice(start,end+4),context);context.resizeCanvas();
assert.equal(context.hudCanvas.width,1200);assert.equal(context.hudCanvas.height,900);
assert.deepEqual(seen[0],[800,600,1.5]);assert.equal(seen[1].resolutionScale,.6);
context.renderScale=.5;context.lastDpr=-1;context.resizeCanvas();
assert.equal(context.hudCanvas.width,1200,'HUD never follows adaptive scene scaling');

// 8Hz 快照的匀速轨迹在 30/60/144Hz 上相同，替代按帧追赶造成的速度脉冲。
const samples=[];
for(const fps of [30,60,144]) {
  const vis={x:0,y:0,dir:0};let next=0;
  for(let i=0;i<=fps*2;i++) {
    const time=i*1000/fps;
    while(next<=time+1e-6) {
      const u={x:next*.1,y:next*.04,dir:0,size:10};vis.unit=u;
      pushVisualMotion(vis,u,next);next+=125;
    }
    sampleVisualMotion(vis,time,1/fps);
    if(time>=250) assert.ok(Math.abs(vis.x-(time-80)*.1)<.55,'stable velocity across snapshot boundaries');
  }
  samples.push(vis.x);
}
assert.ok(Math.max(...samples)-Math.min(...samples)<1e-6);
const vis={x:0,y:0,dir:Math.PI-.01},a={x:0,y:0,dir:Math.PI-.01,size:10},b={x:12.5,y:5,dir:-Math.PI+.01,size:10};
pushVisualMotion(vis,a,0);pushVisualMotion(vis,b,125);vis.unit=b;
sampleVisualMotion(vis,250,1/60);assert.ok(vis.x<=16.5,'prediction bounded to 40ms');
sampleVisualMotion(vis,900,1/60);assert.equal(vis.x,b.x,'stale stream anchors to last authority');
vis.unit={...b,rooted:true};sampleVisualMotion(vis,200,1/60);assert.equal(vis.x,b.x);
const before=vis.motionPrevious.x;pushVisualMotion(vis,b,125);assert.equal(vis.motionPrevious.x,before);
pushVisualMotion(vis,{x:2000,y:2000,dir:1},250);assert.equal(vis.x,2000,'teleports reset history');
assert.ok(Number.isFinite(vis.dir));
const clock=createMotionClock();clock.push(1000,0);clock.push(1145,125);
assert.ok(Math.abs(clock.time(1145)-145)<=5,'arrival jitter cannot jump the motion clock');
clock.reset();clock.push(100,0);assert.equal(clock.time(200),100);
console.log('Engine upgrade: r186 pair, legal MSAA formats, native HUD/output, adaptive targets and frame-rate-independent motion passed.');
