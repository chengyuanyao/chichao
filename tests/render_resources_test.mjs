import assert from 'node:assert/strict';
import * as THREE from '../public/vendor/three.module.min.js';
import {disposeOwnedRenderGroup, MaterialShaderRegistry} from '../public/render_resources.js';

const world = new THREE.Group();
const owned = new THREE.Group();
world.add(owned);
const sharedTexture = new THREE.Texture();
const geometry = new THREE.BoxGeometry();
const material = new THREE.MeshLambertMaterial({map:sharedTexture});
const unusedTemplate = new THREE.RingGeometry();
const persistentPad = new THREE.MeshLambertMaterial({map:sharedTexture});
const liveRegistry = new MaterialShaderRegistry();
const waterRegistry = new MaterialShaderRegistry();
const shader = {uniforms:{fog:{value:'old'}}};
const alternateShader = {uniforms:{fog:{value:'old'}}};
const padShader = {uniforms:{fog:{value:'old'}}};
liveRegistry.add(material,shader);
liveRegistry.add(material,shader);
liveRegistry.add(material,alternateShader);
liveRegistry.add(persistentPad,padShader);
waterRegistry.add(material,shader);
assert.equal(liveRegistry.size,3,'duplicate compilation reference is only retained once');
assert.equal(liveRegistry.materialCount,2);

const disposed = {geometry:0,material:0,template:0,texture:0,instances:0,pad:0};
geometry.addEventListener('dispose',()=>disposed.geometry++);
material.addEventListener('dispose',()=>disposed.material++);
unusedTemplate.addEventListener('dispose',()=>disposed.template++);
sharedTexture.addEventListener('dispose',()=>disposed.texture++);
persistentPad.addEventListener('dispose',()=>disposed.pad++);
for(let i=0;i<3;i++) {
  const instance=new THREE.InstancedMesh(geometry,material,12);
  instance.addEventListener('dispose',()=>disposed.instances++);
  owned.add(instance);
}
disposeOwnedRenderGroup(owned,[geometry,material,unusedTemplate]);
assert.deepEqual(disposed,{geometry:1,material:1,template:1,texture:0,instances:3,pad:0});
assert.equal(owned.parent,null);
assert.equal(owned.children.length,0);
assert.equal(liveRegistry.materialCount,1,'persistent building-pad material survives map replacement');
assert.equal(liveRegistry.size,1);
assert.equal(waterRegistry.size,0);
liveRegistry.forEach(s=>{s.uniforms.fog.value='new';});
assert.equal(padShader.uniforms.fog.value,'new');
assert.equal(shader.uniforms.fog.value,'old','disposed shader is no longer updated');

// Repeated map replacements must leave the registry at its persistent baseline.
for(let i=0;i<12;i++) {
  const group=new THREE.Group();
  const mat=new THREE.MeshLambertMaterial({map:sharedTexture});
  group.add(new THREE.Mesh(new THREE.BoxGeometry(),mat));
  liveRegistry.add(mat,{uniforms:{}});
  disposeOwnedRenderGroup(group);
  assert.equal(liveRegistry.size,1);
}
liveRegistry.clear();
assert.equal(liveRegistry.size,0);
assert.equal(liveRegistry.materialCount,0);
persistentPad.dispose();
assert.equal(liveRegistry.size,0,'late material disposal after registry clear is harmless');
console.log('render resource lifecycle tests ok');
