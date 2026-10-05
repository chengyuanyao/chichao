import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import * as THREE from '../public/vendor/three.module.min.js';
const source=readFileSync(new URL('../public/render3d.js',import.meta.url),'utf8');
const block=source.slice(source.indexOf('const INDEXED_RENDER_GEOMETRY='),source.indexOf('function mergeParts('));
const indexed=new Function('THREE',block+';return indexedRenderGeometry;')(THREE);
const original=new THREE.CylinderGeometry(10,12,24,12).toNonIndexed();
const count=original.attributes.position.count;
for(const [name,size] of [['aTeam',1],['aOcc',1],['aSurf',1],['aTread',2],['aBreak',4]]) {
  original.setAttribute(name,new THREE.BufferAttribute(new Float32Array(count*size).fill(.5),size));
}
original.computeBoundingBox();original.computeBoundingSphere();original.setDrawRange(3,count-6);
const before={};for(const [name,a] of Object.entries(original.attributes)) before[name]=a.array.slice();
const render=indexed(original);
assert.notEqual(render,original);assert.equal(indexed(original),render,'cache reused');
assert.ok(render.attributes.position.count<count*.7,'duplicate vertices substantially reduced');
assert.equal(render.index.count,count,'triangle count/order unchanged');
assert.deepEqual(render.groups,original.groups);assert.deepEqual(render.drawRange,original.drawRange);
assert.deepEqual(render.boundingBox,original.boundingBox);assert.deepEqual(render.boundingSphere,original.boundingSphere);
for(const [name,a] of Object.entries(original.attributes)) {
  assert.deepEqual(a.array,before[name],'CPU prototype untouched: '+name);
  const b=render.getAttribute(name);
  for(let i=0;i<count;i++) for(let j=0;j<a.itemSize;j++)
    assert.equal(b.array[render.index.array[i]*a.itemSize+j],a.array[i*a.itemSize+j],name+' exact triangle-corner attribute');
}
const clone=render.clone();clone.setAttribute('aFeedback',new THREE.InstancedBufferAttribute(new Float32Array(40),4));
assert.equal(render.attributes.aFeedback,undefined,'per-pool feedback cannot modify cached render data');
const meshA=new THREE.Mesh(original,new THREE.MeshBasicMaterial()),meshB=new THREE.Mesh(render,meshA.material);
meshA.updateMatrixWorld();meshB.updateMatrixWorld();
const ray=new THREE.Raycaster(new THREE.Vector3(3,2,80),new THREE.Vector3(0,0,-1));
const a=ray.intersectObject(meshA),b=ray.intersectObject(meshB);
assert.equal(a.length,b.length);assert.ok(a.length>0);
assert.equal(a[0].faceIndex,b[0].faceIndex);assert.deepEqual(a[0].point,b[0].point,'picking preserved');
// UV / normal / surface / fracture seams must never be welded by position alone.
const seam=original.clone();seam.attributes.aSurf.setX(0,2);const seamRender=indexed(seam);
assert.equal(seamRender.attributes.aSurf.getX(seamRender.index.getX(0)),2);
assert.equal(seamRender.attributes.aSurf.getX(seamRender.index.getX(1)),.5);
const already=new THREE.BoxGeometry();assert.equal(indexed(already),already,'existing indices preserved');
const half=original.clone();half.setAttribute('position',new THREE.Float16BufferAttribute(new Uint16Array(count*3),3));
assert.equal(indexed(half),half,'special half-float attribute decoding is left unchanged');
console.log(`Indexed render geometry: ${count} -> ${render.attributes.position.count} vertices; exact attributes, triangles, bounds, cache and picking preserved.`);
