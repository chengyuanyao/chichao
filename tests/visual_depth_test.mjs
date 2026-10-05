import assert from 'node:assert/strict';
import * as THREE from '../public/vendor/three.module.min.js';
import {createPostFX} from '../public/postfx.js';
import {createShadowSchedule} from '../public/shadow_schedule.js';
import {renderProfile} from '../public/render_profile.js';

// 阴影可复用，但镜头、建筑/迷雾快照和换局必须立即失效。
for(const fps of [30,60,144]) {
  const schedule=createShadowSchedule();let count=0;
  for(let i=0;i<fps;i++) count+=Number(schedule.update(i*1000/fps,false,true));
  assert.ok(count>=29&&count<=30,`animated shadows stay near 30Hz without exceeding it at ${fps}Hz`);
  assert.equal(schedule.update(1001,true,false),true,'camera/snapshot changes render immediately');
  assert.equal(schedule.update(1002,false,false),false,'static scene reuses the map');
  assert.equal(schedule.update(1003,true,true),true,'invalidation overrides animation throttling');
  assert.equal(schedule.update(0,false,false),true,'clock rewind cannot retain stale shadows');
  schedule.reset();assert.equal(schedule.update(0,false,false),true,'new match starts fresh');
}
assert.equal(renderProfile('smooth').contactAO,0);
assert.equal(renderProfile('detailed').shadowMapSize,2048);

const world=new THREE.Scene(),camera=new THREE.PerspectiveCamera(46,16/9,12,12000);
let target=null;const passes=[];
const gl={RENDERBUFFER:1,RGBA16F:2,DEPTH_COMPONENT24:3,SAMPLES:4,getInternalformatParameter:()=>[4,2]};
const renderer={capabilities:{isWebGL2:true,maxSamples:4},extensions:{get:()=>null},getContext:()=>gl,
  info:{render:{calls:40,triangles:5000}},setRenderTarget(value){target=value;},clear(){},
  render(scene){if(scene!==world) passes.push({target,material:scene.children[0].material});}};
const fx=createPostFX(renderer);
fx.setSize(1280,720,1.5);fx.setOptions({bloomEnabled:false,msaaSamples:2,contactAO:.35});
assert.equal(fx.sceneTarget.depthTexture.type,THREE.UnsignedIntType);
assert.equal(fx.sceneTarget.resolveDepthBuffer,true,'MSAA must resolve the sampled depth');
fx.render(world,camera,0);
assert.equal(passes.length,3,'AO uses one fullscreen pass; no duplicate geometry pass');
const [ao,composite,fxaa]=passes;
assert.equal(ao.target.width,960);assert.equal(ao.target.height,540);
assert.equal(ao.target.samples,0);assert.equal(ao.target.depthBuffer,false);
assert.equal(composite.target.width,1920,'AO never reduces final clarity');
assert.equal(fxaa.target,null);
assert.equal(ao.material.uniforms.tDepth.value,fx.sceneTarget.depthTexture);
assert.deepEqual(ao.material.uniforms.uProjectionInverse.value.elements,camera.projectionMatrixInverse.elements);
assert.equal(composite.material.uniforms.tContactAO.value,ao.target.texture);
assert.equal(composite.material.uniforms.uContactAO.value,.35);
camera.near=20;camera.far=8000;camera.updateProjectionMatrix();
fx.setOptions({resolutionScale:.5});passes.length=0;fx.render(world,camera,1);
assert.equal(ao.target.width,480);assert.equal(ao.target.height,270);
assert.deepEqual(composite.material.uniforms.uCameraRange.value.toArray(),[20,8000]);
// Disabling must remove the readback, pass, stale darkening and allocated AO image.
let released=0;const depth=fx.sceneTarget.depthTexture;depth.addEventListener('dispose',()=>released++);
fx.setOptions({contactAO:0});passes.length=0;fx.render(world,camera,2);
assert.equal(released,1);assert.equal(fx.sceneTarget.depthTexture,null);
assert.equal(fx.sceneTarget.resolveDepthBuffer,false);assert.equal(passes.length,2);
assert.equal(composite.material.uniforms.uContactAO.value,0);
assert.equal(ao.target.width,1);assert.equal(ao.target.height,1);
assert.equal(fx.contactStats.passes,0);
fx.setOptions({contactAO:NaN});assert.equal(fx.contactStats.strength,0);
fx.setOptions({contactAO:.55});passes.length=0;fx.render(world,camera,3);
assert.notEqual(fx.sceneTarget.depthTexture,depth,'live re-enabling gets a fresh depth attachment');
assert.equal(passes.length,3);assert.equal(composite.material.uniforms.uContactAO.value,.55);
fx.dispose();
const legacy=createPostFX({...renderer,capabilities:{isWebGL2:false},extensions:{get:()=>null}});
legacy.setOptions({contactAO:1});assert.equal(legacy.contactStats.strength,0,'unsupported depth pipeline falls back');legacy.dispose();
console.log('Visual depth: shadow reuse/invalidation, 30Hz cadence, depth resolve, half-resolution AO, native output and live disposal passed.');
