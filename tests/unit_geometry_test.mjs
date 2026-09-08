// Exercise real Three geometry builders without creating a DOM/WebGL renderer.
// Timings describe one-time CPU cache creation, not GPU frame rate.
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { performance } from 'node:perf_hooks';
import * as THREE from '../public/vendor/three.module.min.js';

const source = readFileSync(new URL('../public/render3d.js', import.meta.url), 'utf8');
const modelEnd = source.indexOf('/**\n * 组装一座建筑');
assert.ok(modelEnd > 0, 'cached geometry boundary must be present');
const modelSource = source.slice(0, modelEnd)
  .replace(/^import\s[\s\S]*?;$/mg, '').replace(/^export /mg, '');

// These factories are private inside createRenderer. Extract their actual source
// so cache/AO regressions exercise production code without a test-only API.
function privateFactory(name) {
  const start = source.indexOf(`  function ${name}(`);
  assert.ok(start >= 0, `missing ${name}`);
  const end = source.indexOf('\n  }', start);
  assert.ok(end > start, `missing closing brace for ${name}`);
  return source.slice(start, end + 4);
}
const { builders, geometryFor, structureFor } = new Function('THREE', `${modelSource}
  const UNIT_GEOMETRY_CACHE = new Map();
  ${privateFactory('simpleUnitParts')}
  ${privateFactory('unitGeometry')}
  return { builders: UNIT_BUILDERS, geometryFor: unitGeometry, structureFor: structureGeometries };
`)(THREE);

const rows = [];
for (const kind of Object.keys(builders)) {
  const build = builders[kind];
  let calls = 0;
  builders[kind] = () => { calls++; return build(); };
  const started = performance.now();
  const entry = geometryFor(kind);
  const firstMs = performance.now() - started;
  assert.strictEqual(geometryFor(kind), entry, `${kind}: cache must reuse entry`);
  assert.equal(calls, 1, `${kind}: all instances must share one model build`);

  for (const [lod, geo] of Object.entries(entry)) {
    assert.ok(geo.attributes.position.count > 0, `${kind}/${lod}: empty model`);
    for (const attr of ['position', 'normal', 'color', 'aOcc', 'aSurf', 'aTeam']) {
      assert.ok(geo.attributes[attr].array.every(Number.isFinite),
        `${kind}/${lod}: ${attr} contains invalid numbers`);
    }
    const occ = geo.attributes.aOcc.array;
    assert.ok(occ.every(value => value >= 0.45 && value <= 1), `${kind}/${lod}: invalid AO`);
    if (lod === 'simple') {
      assert.ok(occ.every(value => value === 1), `${kind}: distant LOD must skip AO baking`);
    } else {
      assert.ok(occ.some(value => value < 0.99), `${kind}: near model must bake occlusion`);
      const color = geo.attributes.color;
      for (let i = 0; i < color.count; i++) {
        if (Math.max(color.getX(i), color.getY(i), color.getZ(i)) > 1.05) {
          assert.equal(occ[i], 1, `${kind}: glow must stay unoccluded`);
        }
      }
    }
    geo.computeBoundingBox();
    assert.ok(geo.boundingBox.min.toArray().every(Number.isFinite));
    assert.ok(geo.boundingBox.max.toArray().every(Number.isFinite));
  }
  rows.push({ kind, firstMs: Number(firstMs.toFixed(2)),
    nearTriangles: entry.body.attributes.position.count / 3,
    distantTriangles: entry.simple.attributes.position.count / 3 });
}
console.table(rows);
console.log(`unit geometry tests ok: ${rows.length} cached kinds; finite geometry, near AO, ` +
  `unoccluded glow and distant LOD; total first construction ${rows.reduce((sum, row) => sum + row.firstMs, 0).toFixed(2)} ms`);

const catalog = readFileSync(new URL('../catalog.py', import.meta.url), 'utf8');
const structures = catalog.slice(catalog.indexOf('STRUCTURE_TYPES = {'), catalog.indexOf('\nMAGIC_STRUCTURES'));
const structureRows = [];
for (const match of structures.matchAll(/^\s{4}"(\w+)": \{[\s\S]*?"size": ([\d.]+)/gm)) {
  const kind = match[1], size = Number(match[2]);
  const started = performance.now();
  const entry = structureFor(kind, size);
  const firstMs = performance.now() - started;
  assert.strictEqual(structureFor(kind, size), entry, `${kind}: building must reuse cached entry`);
  const meshes = { body: entry.team, head: entry.head?.team, spin: entry.spin?.team };
  for (const [part, geo] of Object.entries(meshes)) {
    if (!geo) continue;
    for (const attr of ['position', 'normal', 'color', 'aOcc', 'aTeam']) {
      assert.ok(geo.attributes[attr].array.every(Number.isFinite), `${kind}/${part}: invalid ${attr}`);
    }
    const occ = geo.attributes.aOcc.array;
    assert.ok(occ.every(value => value >= 0.45 && value <= 1), `${kind}/${part}: invalid AO`);
    assert.ok(part === 'body' ? occ.some(value => value < 0.99) : occ.every(value => value === 1),
      `${kind}/${part}: only the ground-based body must bake AO`);
    const color = geo.attributes.color;
    for (let i = 0; i < color.count; i++) {
      if (Math.max(color.getX(i), color.getY(i), color.getZ(i)) > 1.05) {
        assert.equal(occ[i], 1, `${kind}/${part}: glow must stay unoccluded`);
      }
    }
  }
  structureRows.push({ kind, size, firstMs: Number(firstMs.toFixed(2)),
    bodyTriangles: entry.team.attributes.position.count / 3 });
}
assert.ok(structureRows.length >= 15, 'both factions must have building coverage');
console.table(structureRows);
console.log(`structure geometry tests ok: ${structureRows.length} cached kinds; finite geometry, body AO, ` +
  `unoccluded glow and local-axis attachments; total first construction ${structureRows.reduce((sum, row) => sum + row.firstMs, 0).toFixed(2)} ms`);
