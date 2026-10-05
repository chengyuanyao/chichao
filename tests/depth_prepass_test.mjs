import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import * as THREE from '../public/vendor/three.module.min.js';
import {createPostFX} from '../public/postfx.js';
const world=new THREE.Scene(),camera=new THREE.PerspectiveCamera(46,16/9,12,12000);
let target,clears=0,fx;const phases=[];
const renderer={autoClear:true,capabilities:{isWebGL2:true},extensions:{get:()=>null},
  info:{render:{calls:0,triangles:0}},setRenderTarget(t){target=t;},clear(){clears++;},
  render(scene){
    assert.equal(this.autoClear,false,'explicit passes cannot erase preserved depth');
    if(scene===world){phases.push('color');assert.equal(target,fx.sceneTarget);assert.equal(target.resolveColorBuffer,true);
      assert.equal(target.resolveDepthBuffer,true);this.info.render={calls:7,triangles:20};}
    else{phases.push('post');this.info.render={calls:1,triangles:1};}
  }};
fx=createPostFX(renderer);fx.setSize(1280,720,1.5);fx.setOptions({contactAO:.55,bloomEnabled:false});
fx.render(world,camera,0,()=>{
  phases.push('depth');assert.equal(target,fx.sceneTarget);assert.equal(renderer.autoClear,false);
  assert.equal(target.resolveColorBuffer,false);assert.equal(target.resolveDepthBuffer,false);
  assert.equal(target.storeMultisampledColorBuffer,true);assert.equal(target.storeMultisampledDepthBuffer,true);
  renderer.info.render={calls:4,triangles:10};
});
assert.deepEqual(phases,['depth','color','post','post','post']);assert.equal(clears,1,'only scene clear remains');
assert.deepEqual(fx.depthStats,{calls:4,triangles:10});assert.deepEqual(fx.sceneStats,{calls:11,triangles:30});
assert.equal(renderer.autoClear,true);
assert.throws(()=>fx.render(world,camera,1,()=>{throw new Error('depth failed');}),/depth failed/);
assert.equal(renderer.autoClear,true);assert.equal(fx.sceneTarget.resolveColorBuffer,true);assert.equal(fx.sceneTarget.resolveDepthBuffer,true);
fx.render(world,camera,2);assert.deepEqual(fx.depthStats,{calls:0,triangles:0});
fx.dispose();

// Exercise the production layer/override helper with real Three objects.
const source=readFileSync(new URL('../public/render3d.js',import.meta.url),'utf8');
const start=source.indexOf('  function drawUnitDepth()'),end=source.indexOf('\n  }',start);
const scene=new THREE.Scene(),cam=new THREE.PerspectiveCamera();
const unit=new THREE.Mesh(new THREE.BoxGeometry(),new THREE.MeshStandardMaterial());unit.layers.enable(1);scene.add(unit);
const building=new THREE.Mesh(new THREE.BoxGeometry(),unit.material);scene.add(building);
const smoke=new THREE.Mesh(new THREE.PlaneGeometry(),new THREE.MeshBasicMaterial({transparent:true}));scene.add(smoke);
const depth=new THREE.MeshDepthMaterial({colorWrite:false});let fail=false,seen=[];
let masks=0;
const r={shadowMap:{enabled:true},state:{buffers:{color:{setMask(value){assert.equal(value,true);masks++;}}}},render(s,c){
  assert.equal(s.overrideMaterial,depth);assert.equal(this.shadowMap.enabled,false);
  seen=s.children.filter(o=>o.layers.test(c.layers));if(fail) throw new Error('draw failed');
}};
const draw=new Function('renderer','scene','camera','unitDepthMaterial',source.slice(start,end+4)+';return drawUnitDepth;')(r,scene,cam,depth);
draw();assert.deepEqual(seen,[unit],'buildings, collapse and translucent effects excluded');
assert.equal(cam.layers.mask,1);assert.equal(scene.overrideMaterial,null);assert.equal(r.shadowMap.enabled,true);
fail=true;assert.throws(draw,/draw failed/);assert.equal(cam.layers.mask,1);assert.equal(scene.overrideMaterial,null);assert.equal(r.shadowMap.enabled,true);
assert.equal(masks,2,'color writes restored after both successful and failed depth draws');
console.log('Depth prepass: opaque unit layer, one clear, retained MSAA attachments, single resolve, accurate totals and exception-state restoration passed.');
