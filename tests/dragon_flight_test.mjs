import assert from 'node:assert/strict';
import {advanceDragonFlight,dragonPhase,dragonFlightPoint} from '../public/dragon_flight.js';
import * as THREE from '../public/vendor/three.module.min.js';
const idle={unit:{id:'dragon-a'}},moving={unit:{id:'dragon-a'}};
assert.equal(dragonPhase('dragon-a'),dragonPhase('dragon-a'));
assert.notEqual(dragonPhase('dragon-a'),dragonPhase('dragon-b'));
let lo=Infinity,hi=-Infinity;
for(let i=0;i<600;i++) {
  advanceDragonFlight(idle,i*16, .016,0,0,1,true);
  advanceDragonFlight(moving,i*16,.016,1,.02,1,true);
  lo=Math.min(lo,idle.flightWing);hi=Math.max(hi,idle.flightWing);
  for(const key of ['flightWing','flightLift','flightBank','flightPitch']) assert.ok(Number.isFinite(moving[key]));
  assert.ok(moving.flightLift>=6.7&&moving.flightLift<=11.3);
  assert.ok(Math.abs(moving.flightPitch)<.082);
  assert.ok(Math.abs(moving.flightBank)<=.12);
  assert.ok(Math.abs(moving.flightWing)<=.561);
}
assert.ok(hi-lo>.75,'visible full wingbeat, not the previous tiny twitch');
assert.ok(moving.flightMotion>.99&&idle.flightMotion===0);
assert.ok(moving.flightBank>.08,'turn banks smoothly');
advanceDragonFlight(moving,10000,.016,0,0,1,false);
assert.equal(moving.flightWing,0,'distant LOD needs no joint animation');
assert.equal(moving.flightPitch,0);
assert.ok(moving.flightLift>=8,'LOD preserves flight height');
for(let i=0;i<200;i++) advanceDragonFlight(moving,11000+i*16,.016,0,0,1,true);
assert.ok(moving.flightMotion<1e-6&&moving.flightBank<1e-6,'stop settles without locking pose');
console.log('Dragon flight: deterministic phase, bounded hover/flap/bank, motion settling and distant LOD passed.');
const pose={x:71,y:93,groundY:25,dir:1.2,flightLift:9.4,flightPitch:-.06,flightBank:.11};
const matrix=new THREE.Matrix4().makeTranslation(pose.x,pose.groundY,pose.y)
  .multiply(new THREE.Matrix4().makeRotationY(-pose.dir))
  .multiply(new THREE.Matrix4().makeScale(1.34,1.34,1.34))
  .multiply(new THREE.Matrix4().makeTranslation(0,pose.flightLift,0))
  .multiply(new THREE.Matrix4().makeRotationZ(pose.flightPitch))
  .multiply(new THREE.Matrix4().makeRotationX(pose.flightBank));
const composed=new THREE.Matrix4().compose(
  new THREE.Vector3(pose.x,pose.groundY+pose.flightLift*1.34,pose.y),
  new THREE.Quaternion().setFromEuler(new THREE.Euler(pose.flightBank,-pose.dir,pose.flightPitch,'YZX')),
  new THREE.Vector3(1.34,1.34,1.34));
assert.ok(matrix.elements.every((v,i)=>Math.abs(v-composed.elements[i])<1e-10),
  'single-compose optimized flight pose must match the articulated transform');
for(const [x,y] of [[31,14],[29,27]]) {
  const expected=new THREE.Vector3(x,y,0).applyMatrix4(matrix);
  assert.ok(dragonFlightPoint(new THREE.Vector3(),pose,x,y,1.34).distanceTo(expected)<1e-10,
    'both model muzzle/idle effects follow the exact animated body transform');
}
