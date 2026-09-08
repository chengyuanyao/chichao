import assert from 'node:assert/strict';
import { readFileSync, statSync } from 'node:fs';
import * as THREE from '../public/vendor/three.module.min.js';
import { wildernessNoise, wildernessBiome, applyWildernessGround, applyWildernessRock,
  applyWildernessTrail, applyBridgeWeathering, makeWeatheredRockGeometry,
  forestChunkKey, FOREST_CHUNK_SIZE, prepareWildernessLandforms,
  wildernessLandformAt, makeTerrainApronGeometry } from '../public/wilderness.js';

const render = readFileSync(new URL('../public/render3d.js', import.meta.url), 'utf8');
let soilTemperate = 0, soilArid = 0, lo = 1, hi = 0;
for (let x = -700; x < 4000; x += 97) for (let y = -300; y < 4000; y += 131) {
  const n = wildernessNoise(x * 0.004, y * 0.004);
  assert.ok(n >= 0 && n <= 1);
  assert.equal(n, wildernessNoise(x * 0.004, y * 0.004));
  const meadow = wildernessBiome(x, y, {style:'river_valley'});
  const arid = wildernessBiome(x, y, {style:'crater_wilderness'});
  for (const value of [...meadow, ...arid]) assert.ok(Number.isFinite(value) && value >= 0 && value <= 1);
  soilTemperate += meadow[0]; soilArid += arid[0];
  lo = Math.min(lo, meadow[0]); hi = Math.max(hi, meadow[0]);
  const path = wildernessBiome(x, y, {style:'river_valley',trail:1});
  assert.ok(path[0] >= 0.85, 'forest corridors expose walkable soil');
}
assert.ok(hi - lo > 0.75, 'different ecologies, not a uniform ground tint');
assert.ok(soilArid > soilTemperate * 1.5, 'crater retains a drier identity');
for (let i = -10; i < 10; i++) {
  assert.ok(Math.abs(wildernessNoise(i - 0.00001, 2.3) - wildernessNoise(i + 0.00001, 2.3)) < 0.0001);
}
const shore = wildernessBiome(400,500,{style:'river_valley',depth:0.5});
const forest = wildernessBiome(400,500,{style:'crater_wilderness',depth:0.5});
assert.ok(shore[3] > 0.6 && shore[2] === 0, 'waterbank, not forest floor');
assert.ok(forest[2] > 0.9, 'dense forest has shaded litter');
assert.equal(wildernessBiome(400,500,{depth:0.5,trail:1})[2], 0, 'corridors remain clear');
assert.ok(wildernessBiome(400,500,{rock:120})[1] > 0.75, 'exposed hills use bedrock');

const ridge = prepareWildernessLandforms([
  {x:0,y:0,angle:0,length:620,width:280,height:66,bend:65,kind:'ridge'}]);
const swale = prepareWildernessLandforms([
  {x:0,y:0,angle:90,length:560,width:125,height:-18,bend:80,kind:'swale'}]);
assert.equal(wildernessLandformAt(0,0,ridge).height,66);
assert.equal(wildernessLandformAt(0,0,swale).height,-18);
assert.equal(wildernessLandformAt(621,0,ridge).height,0);
assert.equal(wildernessLandformAt(0,281,ridge).height,0);
assert.deepEqual(wildernessLandformAt(500,500), {height:0,erosion:0,bedrock:0,level:0},
  'old maps have exactly zero authored relief');
assert.equal(prepareWildernessLandforms([{width:0},{x:NaN}]).length,0);
for(let x=-800;x<800;x+=19) for(let y=-400;y<400;y+=17) {
  const a = wildernessLandformAt(x,y,ridge);
  const b = wildernessLandformAt(x+0.1,y,ridge);
  const c = wildernessLandformAt(x,y+0.1,ridge);
  assert.ok(a.height >= 0 && a.height <= 66);
  assert.ok(Math.abs(b.height-a.height) < 0.06 && Math.abs(c.height-a.height) < 0.06,
    'walkable shoulders are smooth, not sheer walls');
}
const hollow = wildernessLandformAt(0,0,swale);
const dryBed = wildernessBiome(0,0,hollow);
assert.ok(dryBed[0] >= .78 && dryBed[3] === 0, 'dry gullies expose soil without fake water');
assert.ok(render.includes('state.landforms = prepareWildernessLandforms(state.terrain.landforms)'));
assert.ok(render.includes('rollingHeight(wx, wz, landform)'), 'ground and entities share relief');
assert.ok(render.includes('JSON.stringify(t.landforms || [])'), 'same-count geometry edits invalidate cache');
const plateau = prepareWildernessLandforms([
  {x:0,y:0,angle:0,length:700,width:720,height:100,bend:0,kind:'plateau'}]);
for(const [x,y] of [[0,0],[200,0],[0,300],[200,200]]) {
  assert.equal(wildernessLandformAt(x,y,plateau).height,100,'level base interior');
  assert.equal(wildernessLandformAt(x,y,plateau).level,1,'suppress micro hills under base');
}
assert.equal(wildernessLandformAt(701,0,plateau).height,0);
assert.ok(wildernessLandformAt(520,0,plateau).bedrock>.35,'exposed terrace shoulder reads as a slope');
let previous=100;
for(let x=350;x<=700;x++) {
  const h=wildernessLandformAt(x,0,plateau).height;
  assert.ok(h <= previous && previous-h < .5,'broad, continuous drivable ramp');
  previous=h;
}

const variants = [];
const apron = makeTerrainApronGeometry(4000,4000,100,100,(x,y)=>x*.02+y*.01);
assert.equal(apron.index.count/3,800,'bounded static edge geometry');
const apronPosition=apron.attributes.position;
for(let i=0;i<apronPosition.count;i+=2) {
  const x=apronPosition.getX(i),z=apronPosition.getZ(i);
  assert.ok(Math.abs(apronPosition.getY(i)-(x*.02+z*.01-.25))<.001,'no gap below raised boundary');
}
apron.dispose();
for (let variant = 0; variant < 3; variant++) {
  const geometry = makeWeatheredRockGeometry(variant);
  assert.equal(geometry.index, null);
  assert.equal(geometry.attributes.position.count / 3, 108, 'bounded template cost');
  geometry.computeBoundingSphere();
  assert.ok(geometry.boundingSphere.radius < 2);
  for (const name of ['position','normal','uv']) {
    assert.ok(Array.from(geometry.attributes[name].array).every(Number.isFinite));
  }
  const again = makeWeatheredRockGeometry(variant);
  assert.deepEqual(geometry.attributes.position.array, again.attributes.position.array);
  variants.push(Array.from(geometry.attributes.position.array));
  geometry.dispose(); again.dispose();
}
assert.notDeepEqual(variants[0], variants[1], 'weathered forms vary deterministically');
assert.equal(FOREST_CHUNK_SIZE, 640);
assert.equal(forestChunkKey(0,0), forestChunkKey(639,639));
assert.notEqual(forestChunkKey(639,639), forestChunkKey(640,639));
assert.equal(forestChunkKey(-1,-1), '-1:-1');

function expandChunks(source) {
  return source.replace(/#include\s+<([\w\d_]+)>/g, (_, name) => {
    assert.equal(typeof THREE.ShaderChunk[name], 'string');
    return expandChunks(THREE.ShaderChunk[name]);
  });
}
const keys = new Set();
for (const [apply, marker, mapSamples] of [
  [applyWildernessGround, 'vBiome', 3], [applyWildernessRock, 'wrSurface', 1],
  [applyWildernessTrail, 'trFade', 1], [applyBridgeWeathering, 'bwStone', 1]
]) {
  const material = new THREE.MeshLambertMaterial({map:new THREE.Texture(),vertexColors:true});
  let parentRan = false;
  material.onBeforeCompile = () => { parentRan = true; };
  apply(material);
  const shader = {uniforms:{},vertexShader:THREE.ShaderLib.lambert.vertexShader,
    fragmentShader:THREE.ShaderLib.lambert.fragmentShader};
  material.onBeforeCompile(shader);
  assert.ok(parentRan, 'fog hook is chained, not overwritten');
  assert.ok(shader.fragmentShader.includes(marker));
  assert.equal((shader.fragmentShader.match(/texture2D\(map,/g)||[]).length,mapSamples);
  for (const chunk of ['color_fragment','alphatest_fragment','lights_fragment_begin','fog_fragment','dithering_fragment']) {
    assert.ok(shader.fragmentShader.includes('#include <'+chunk+'>'), 'preserve '+chunk);
  }
  assert.ok(expandChunks(shader.fragmentShader).includes('void main()'));
  keys.add(material.customProgramCacheKey());
  material.dispose();
}
assert.equal(keys.size, 4, 'each material has its own shader cache key');
assert.ok(readFileSync(new URL('../public/wilderness.js', import.meta.url), 'utf8')
  .includes('wildGrass(map, tdWorld / 112.0)'), 'stochastic grass sampling is actually used');
assert.ok(render.includes('applyTerrainDetail(applyFogMask'), 'ground shader is actually used');
assert.ok(render.includes("geo.setAttribute('aBiome'"));
assert.ok(render.includes("map: loadSharedTexture('/assets/textures/woodland-leaves-v2.webp'"));
assert.ok(render.includes('alphaTest: 0.42'), 'leaf cards write cutout depth, no transparent sorting');
assert.ok(render.includes('const key = forestChunkKey(tx, ty)'));
assert.ok(render.includes('mesh.frustumCulled = true'));
assert.ok(render.includes("const lift = geo === grassGeo ? 0 : geo === logGeo ? Math.max(sx, sz) * 0.62"),
  'grass and sideways logs must touch the ground');
for (const file of ['wilderness-atlas-v2.webp','woodland-leaves-v2.webp']) {
  assert.ok(statSync(new URL('../public/assets/textures/'+file,import.meta.url)).size < 650000);
}
console.log('Wilderness: deterministic ecology, continuous noise, 108-face weathered rock templates, four shader hooks, cutout/chunk integration and texture budgets passed.');
