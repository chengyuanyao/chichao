import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {execFileSync} from 'node:child_process';
import vm from 'node:vm';
import {createAttackRangePreview} from '../public/attack_range_preview.js';

// Test against the authoritative catalog, so balance changes cannot leave a
// hard-coded UI radius behind.
const catalog = JSON.parse(execFileSync(process.platform === 'win32' ? 'py' : 'python3',
  ['-c', 'import json,catalog; print(json.dumps(catalog.STRUCTURE_TYPES))'],
  {cwd:new URL('..', import.meta.url), encoding:'utf8'}));
const app = readFileSync(new URL('../public/app.js', import.meta.url), 'utf8');
function sourceFunction(name) {
  const match = app.match(new RegExp('  function ' + name + '\\([^]*?\\n  \\}'));
  assert.ok(match, name);
  return match[0];
}
const context = {
  buildMode:null, BUILDINGS:catalog, pointer:{worldX:800, worldY:900},
  structureRole:kind=>catalog[kind]?.role,
  nearestBuildAnchor:()=>({x:650,y:710,radius:620}),
  positionValidClient:()=>true,
  canvas:{classList:{add(){}}}, buildCursorLabel:{classList:{remove(){}}},
  sound(){}, toast(){}
};
vm.createContext(context);
vm.runInContext(sourceFunction('buildPreviewState') + sourceFunction('activateBuildMode'), context);
assert.equal(context.buildPreviewState(), null);
let calls = 0;
const height = (x,y)=>x * .05 + y * .03;
const overlay = createAttackRangePreview((x,y)=>{calls++;return height(x,y);});
const terrain = {};
const {mesh} = overlay;
const geometry = mesh.geometry, material = mesh.material;
for (const [kind, definition] of Object.entries(catalog)) {
  context.activateBuildMode(kind, true);
  const preview = context.buildPreviewState();
  const defense = definition.role === 'defense';
  assert.equal(preview.attackRadius, defense ? definition.range : 0);
  assert.equal(preview.anchorRadius, 620, 'build radius remains independent');
  overlay.update(preview, terrain);
  assert.equal(mesh.visible, defense);
  if (!defense) continue;
  assert.ok(context.buildCursorLabel.textContent.includes('基础射程 ' + definition.range));
  assert.equal(mesh.material.color.getHex(), 0xffd166);
  const positions = geometry.attributes.position;
  for (let i = 129; i < positions.count; i++) {
    const x = positions.getX(i), z = positions.getZ(i);
    assert.ok(Math.abs(Math.hypot(x,z) - definition.range) < 0.0001);
    assert.ok(Math.abs(positions.getY(i) - height(preview.x+x,preview.y+z) - 3) < 0.0001);
  }
  assert.equal(mesh.position.x, preview.x);
  assert.equal(mesh.position.z, preview.y);
  const version = positions.version, before = calls;
  for (let frame = 0; frame < 120; frame++) overlay.update(preview, terrain);
  assert.equal(calls, before, 'stationary cursor does not resample terrain');
  assert.equal(positions.version, version, 'stationary cursor does not upload vertices');
  overlay.update({...preview,valid:false}, terrain);
  assert.equal(mesh.visible, true, 'invalid sites still show coverage');
  assert.equal(material.color.getHex(), 0xff5a5a);
  overlay.update({...preview,x:preview.x+100}, terrain);
  assert.equal(mesh.position.x, preview.x+100);
  overlay.update(preview, {});
  assert.ok(positions.version > version, 'changed map refreshes height samples');
  overlay.update(null, terrain);
  assert.equal(mesh.visible, false);
  overlay.update(preview, terrain);
  assert.equal(mesh.visible, true);
  assert.equal(mesh.geometry, geometry);
  assert.equal(mesh.material, material);
}
for (const attackRadius of [0,-1,NaN,Infinity,undefined]) {
  overlay.update({x:1,y:2,attackRadius}, terrain);
  assert.equal(mesh.visible,false);
}
const render = readFileSync(new URL('../public/render3d.js', import.meta.url), 'utf8');
assert.match(render, /function updatePreview\(preview\) \{\s*attackRangePreview\.update\(preview, heightField \|\| state\.map\);/);
assert.equal(material.depthTest, false, 'terrain, forests and fog cannot hide the guide');
geometry.dispose(); material.dispose();
console.log('Attack range preview: live catalog, all defenses, terrain following, validity, cancellation and buffer reuse passed.');
