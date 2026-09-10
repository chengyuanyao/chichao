// Run the actual material hook against the bundled Three.js shaders, and execute
// the quality switches with small render-state fixtures. Browser QA additionally
// compiles these programs on a real WebGL context and measures frame time.
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';
import * as THREE from '../public/vendor/three.module.min.js';
import { createPostFX } from '../public/postfx.js';
import { applyBattleMaterial } from '../public/battle_feedback.js';

const source = readFileSync(new URL('../public/render3d.js', import.meta.url), 'utf8')
  .replace(/\r\n/g, '\n');
function extract(pattern, label) {
  const match = source.match(pattern);
  assert.ok(match, `${label}: source block was not found; update this focused fixture`);
  return match[0];
}
function assertOrder(text, parts, label) {
  let previous = -1;
  for (const part of parts) {
    const position = text.indexOf(part, previous + 1);
    assert.ok(position > previous, `${label}: missing or out-of-order ${part}`);
    previous = position;
  }
}
function expandChunks(shader) {
  return shader.replace(/#include\s+<([\w\d_]+)>/g, (_, name) => {
    assert.equal(typeof THREE.ShaderChunk[name], 'string', `bundled Three chunk ${name}`);
    return expandChunks(THREE.ShaderChunk[name]);
  });
}

const sharedAtlas = new THREE.Texture();
const uniformContext = {
  applyBattleMaterial,
  sunDirViewUniform: { value: new THREE.Vector3(0.4, 0.8, 0.4) },
  armyTimeUniform: { value: 0 },
  makeArmySurfaceTexture: () => sharedAtlas
};
const applySurface = vm.runInNewContext(`(${extract(
  /  function applyEmissiveByVertexColor\(material, surfaceKind\) \{[\s\S]*?\n  }/,
  'army material hook'
)})`, uniformContext);
const programKeys = new Set();
for (const [surface, mode] of [['metal', 0], ['stone', 1], ['cloth', 2], ['hide', 3]]) {
  const material = applySurface(new THREE.MeshPhongMaterial({ vertexColors: true }), surface);
  const shader = {
    uniforms: THREE.UniformsUtils.clone(THREE.ShaderLib.phong.uniforms),
    vertexShader: THREE.ShaderLib.phong.vertexShader,
    fragmentShader: THREE.ShaderLib.phong.fragmentShader
  };
  material.onBeforeCompile(shader);
  assert.equal(shader.uniforms.uArmySurface.value, sharedAtlas, 'all surfaces share one atlas');
  assert.equal(shader.uniforms.uArmySurfaceMode.value, mode);
  assert.equal(shader.uniforms.uArmyTime, uniformContext.armyTimeUniform, 'time uniform is shared');
  programKeys.add(material.customProgramCacheKey());

  assertOrder(shader.vertexShader, [
    '#include <begin_vertex>', 'vArmyLocal = transformed;',
    'armyWorld = instanceMatrix * armyWorld;', 'vArmyWorld = (modelMatrix * armyWorld).xyz;'
  ], 'surface coordinates precede instance motion');
  const localProjection = shader.fragmentShader.match(/vec2 gSurfaceUv = ([^;]+);/);
  assert.ok(localProjection, 'atlas projection exists');
  assert.match(localProjection[1], /vArmyLocal/);
  assert.doesNotMatch(localProjection[1], /vArmyWorld/, 'moving tanks cannot swim through their texture');
  assert.equal((shader.fragmentShader.match(/texture2D\(uArmySurface,/g) || []).length, 1,
    'material detail uses one shared atlas sample');

  assertOrder(shader.fragmentShader, [
    'float gRoughness', '#include <normal_fragment_begin>',
    'float gDetailFade', '#include <lights_phong_fragment>',
    'material.specularColor = gF0', 'material.specularShininess =',
    '#include <lights_fragment_begin>', 'vec3 outgoingLight',
    'outgoingLight +=', 'outgoingLight = mix(outgoingLight, gBase',
    '#include <opaque_fragment>', '#include <fog_fragment>', '#include <dithering_fragment>'
  ], 'material response participates in lighting, shadowing, and output');
  assert.doesNotMatch(shader.fragmentShader, /gl_FragColor\.rgb\s*[+*=]/,
    'injected highlights cannot bypass lighting or fog after the output stage');
  assert.match(shader.fragmentShader, /max\(abs\(gDet\),\s*0\.00001\)/,
    'degenerate derivatives do not normalize a zero normal');

  const expandedVertex = expandChunks(shader.vertexShader);
  const expandedFragment = expandChunks(shader.fragmentShader);
  assert.doesNotMatch(expandedVertex + expandedFragment, /#include\s*</);
  assert.match(expandedFragment, /struct BlinnPhongMaterial/);
  assertOrder(expandedFragment, [
    'BlinnPhongMaterial material;', 'material.specularColor = gF0',
    'getDirectionalLightInfo( directionalLight, directLight );',
    'directLight.color *= ( directLight.visible && receiveShadow ) ? getShadow( directionalShadowMap',
    'RE_Direct( directLight, geometryPosition, geometryNormal, geometryViewDir, geometryClearcoatNormal, material, reflectedLight );',
    'vec3 outgoingLight', 'outgoingLight +=', 'gl_FragColor = vec4( outgoingLight',
    'gl_FragColor.rgb = mix( gl_FragColor.rgb, fogColor'
  ], 'bundled Phong lighting and shadow chunks remain connected');
  for (const [, type, name] of shader.fragmentShader.matchAll(/varying\s+(\w+)\s+(v(?:Army\w+|OwnColor|TeamMix|Occ|Surf));/g)) {
    assert.match(shader.vertexShader, new RegExp(`varying\\s+${type}\\s+${name};`),
      `matching vertex/fragment interface for ${name}`);
  }
  for (const [, lower, upper] of shader.fragmentShader.matchAll(/smoothstep\(\s*(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)/g)) {
    assert.ok(Number(lower) < Number(upper), 'smoothstep requires increasing bounds on every GPU');
  }
  material.dispose();
}
assert.equal(programKeys.size, 4, 'different default surface modes have distinct program keys');
assert.equal((source.match(/applyEmissiveByVertexColor\(\s*new THREE\.MeshPhongMaterial/g) || []).length, 5,
  'four army pools and the building material use the tested Phong hook');
sharedAtlas.dispose();

// Execute the same contact-shadow conditions and placement used by updateUnits.
const shadowSetup = extract(/    let shadowCount = 0;[\s\S]*?if \(shadowMesh\) shadowMesh\.visible[^;]+;/,
  'contact shadow setup');
const shadowPlacement = extract(/        if \(doContactShadows\) \{[\s\S]*?\n        }/,
  'contact shadow placement');
const castAssignment = extract(/      mesh\.castShadow = doShadows[^;]+;/, 'unit shadow casting');
const receiveAssignment = extract(/      mesh\.receiveShadow = doContactShadows[^;]+;/, 'unit shadow receiving');
const shadowFinish = extract(/    if \(shadows\) \{\n      shadows\.count = shadowCount;[\s\S]*?\n    }/,
  'contact shadow update');
for (const quality of ['off', 'structures', 'all']) {
  for (const simpleKind of [false, true]) {
    let shadowRequests = 0;
    const placements = [];
    const shadowMesh = {
      visible: true, count: 99, instanceMatrix: {},
      setMatrixAt(index, matrix) { placements.push({ index, matrix: matrix.clone() }); }
    };
    const mesh = {};
    const context = {
      state: { shadows: quality, renderedUnits: 1 }, shadowMesh, mesh, simpleKind,
      ensureShadowMesh: () => { shadowRequests++; return shadowMesh; },
      vis: { x: 240, y: 130, unit: { size: 20 } }, gy: 6, scale: 1.5,
      matrix: new THREE.Matrix4(), vecAux: new THREE.Vector3(),
      vecPos: new THREE.Vector3(), quatIdentity: new THREE.Quaternion()
    };
    vm.runInNewContext(`${shadowSetup}\n${shadowPlacement}\n${castAssignment}\n${receiveAssignment}\n${shadowFinish}`, context);
    const expectedContact = quality !== 'off';
    assert.equal(shadowRequests, Number(expectedContact), `${quality}: contact shadow allocation`);
    assert.equal(shadowMesh.visible, expectedContact, `${quality}: stale shadows hidden after disabling`);
    assert.equal(placements.length, Number(expectedContact), `${quality}: contact shadow writes`);
    assert.equal(mesh.castShadow, quality === 'all' && !simpleKind,
      `${quality}: expensive casting remains limited to full-detail all-shadow mode`);
    assert.equal(mesh.receiveShadow, expectedContact && !simpleKind,
      `${quality}: near units receive terrain shadows while distant LOD skips shadow sampling`);
    if (expectedContact) {
      assert.equal(shadowMesh.count, 1);
      assert.equal(shadowMesh.instanceMatrix.needsUpdate, true);
      assert.deepEqual(new THREE.Vector3().setFromMatrixPosition(placements[0].matrix).toArray(), [240, 7.2, 130]);
    }
  }
}

// Exercise setQuality against a real postfx instance, not a copied option mapping.
const framePasses = [];
const world = {};
const renderer = {
  capabilities: { isWebGL2: true }, extensions: { get: () => null },
  info: { render: { calls: 1, triangles: 1 } }, shadowMap: { enabled: false },
  setRenderTarget() {}, clear() {},
  render(scene) { framePasses.push(scene === world ? null : scene.children[0].material); }
};
const postfx = createPostFX(renderer);
postfx.setSize(640, 360, 1);
// A map built with shadows disabled already owns these objects. Switching tiers
// must update the same nested casters instead of waiting for a terrain rebuild.
const terrainGroup = new THREE.Group();
const riverGroup = new THREE.Group();
terrainGroup.add(riverGroup);
const terrainObjects = new Map();
for (const [kind, caster] of [
  ['bridge', true], ['cliff', true], ['forest', true], ['mountain', true],
  ['water', false], ['grass', false]
]) {
  const object = new THREE.Object3D();
  object.name = kind;
  object.castShadow = false;
  if (caster) object.userData.shadowCaster = true;
  (kind === 'bridge' || kind === 'water' ? riverGroup : terrainGroup).add(object);
  terrainObjects.set(kind, object);
}
const qualityContext = { state: { shadows: 'off' }, renderer, sun: {}, postfx, terrainGroup,
  EFFECT_MAX: 500, appliedCamX: 0 };
const setQualitySource = extract(/    setQuality: function \(options\) \{[\s\S]*?\n    },/, 'quality setter')
  .replace(/^\s*setQuality:\s*/, '').replace(/,$/, '');
const setQuality = vm.runInNewContext(`(${setQualitySource})`, qualityContext);
for (const [bloom, fastBloom, expectedTotal, expectedBloom] of [
  [false, false, 2, 0], [true, true, 5, 3], [true, false, 7, 5], [false, false, 2, 0]
]) {
  framePasses.length = 0;
  setQuality({ bloom, fastBloom });
  postfx.render(world, {}, 0);
  assert.equal(postfx.enabled, true, 'every graphics tier keeps tone mapping');
  assert.deepEqual(postfx.passStats, { total: expectedTotal, bloom: expectedBloom });
  assert.ok(framePasses.at(-1).uniforms.tSrc, 'FXAA stays active in every standard graphics tier');
  const composite = framePasses.find(material => material?.uniforms.uExposure);
  assert.ok(composite);
  assert.equal(composite.uniforms.uScanline.value, 0);
  assert.equal(composite.uniforms.uBloom.value > 0, bloom);
  assert.match(composite.fragmentShader, /if \(uBloom > 0\.0\)/,
    'zero bloom avoids inactive texture reads as well as blur passes');
  assert.match(composite.fragmentShader, /clamp\(dot\(srgb,/,
    'the contrast power base remains nonnegative for white highlights');
}
for (const shadows of ['off', 'structures', 'all', 'off']) {
  qualityContext.appliedCamX = 120;
  setQuality({ shadows });
  assert.equal(renderer.shadowMap.enabled, shadows !== 'off');
  assert.equal(qualityContext.sun.castShadow, shadows !== 'off');
  assert.ok(Number.isNaN(qualityContext.appliedCamX), 'switching shadows refreshes the sun projection');
  for (const [kind, object] of terrainObjects) {
    assert.strictEqual(terrainGroup.getObjectByName(kind), object,
      `${shadows}/${kind}: quality switches preserve existing terrain objects`);
    assert.equal(object.castShadow, shadows !== 'off' && Boolean(object.userData.shadowCaster),
      `${shadows}/${kind}: only persistent terrain casters change shadow flags`);
  }
}
// Graphics preferences can be applied before a match has created its terrain.
qualityContext.terrainGroup = null;
assert.doesNotThrow(() => setQuality({ shadows: 'all' }));
postfx.dispose();
console.log('render quality tests ok: real Phong shader injection, local atlas, lit specular, ' +
  'unit contact/cast/receive shadows, live off/structures/all terrain switching, all postfx tiers');
