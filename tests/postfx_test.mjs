// Exercise the real postprocessing pipeline with a render recorder: no browser,
// GPU timing, or WebGL mock needed. Shader compilation is covered by browser QA.
import assert from 'node:assert/strict';
import { createPostFX } from '../public/postfx.js';

const world = { name: 'world' };
let renderTarget = null;
let draws = [];
const renderer = {
  capabilities: { isWebGL2: true },
  extensions: { get: () => null },
  info: { render: { calls: 0, triangles: 0 } },
  setRenderTarget(target) { renderTarget = target; },
  clear() {},
  render(scene) {
    const isWorld = scene === world;
    const uniforms = isWorld ? null : scene.children[0].material.uniforms;
    draws.push({
      isWorld, target: renderTarget,
      pass: isWorld ? 'scene' : uniforms.tScene
        ? (uniforms.uExposure ? 'composite' : 'bright')
        : uniforms.tSource ? 'blur' : 'fxaa',
      bloom: uniforms?.uBloom?.value
    });
    this.info.render.calls = isWorld ? 127 : 1;
    this.info.render.triangles = isWorld ? 43210 : 1;
  }
};
const postfx = createPostFX(renderer);
postfx.setSize(1280, 720, 1.5);
assert.equal(postfx.sceneTarget.width, 1920);
assert.equal(postfx.sceneTarget.height, 1080);

function checkFrame(options, passes, bloomPasses) {
  draws = [];
  postfx.setOptions(options);
  postfx.render(world, {}, 500);
  assert.deepEqual(draws.map(draw => draw.pass), ['scene', ...passes]);
  assert.deepEqual(postfx.passStats, { total: passes.length, bloom: bloomPasses });
  assert.deepEqual(postfx.sceneStats, { calls: 127, triangles: 43210 });
  assert.equal(draws.at(-1).target, null, 'last pass must reach the canvas');
  return draws;
}

checkFrame({}, ['bright', 'blur', 'blur', 'blur', 'blur', 'composite', 'fxaa'], 5);
checkFrame({ fastBloom: true }, ['bright', 'blur', 'blur', 'composite', 'fxaa'], 3);
checkFrame({ bloomEnabled: false }, ['composite', 'fxaa'], 0);
assert.equal(draws.at(-2).bloom, 0, 'disabled bloom cannot leak an old frame');
checkFrame({ bloomEnabled: true }, ['bright', 'blur', 'blur', 'composite', 'fxaa'], 3);
assert.equal(draws.at(-2).bloom, 0.30, 're-enabling keeps the configured strength');
checkFrame({ bloom: 0, fastBloom: false }, ['composite', 'fxaa'], 0);
checkFrame({ bloom: 0.17, fxaa: false }, ['bright', 'blur', 'blur', 'blur', 'blur', 'composite'], 5);
assert.equal(draws.at(-1).bloom, 0.17);
checkFrame({ bloomEnabled: false }, ['composite'], 0);
checkFrame({ enabled: false }, [], 0);
checkFrame({ enabled: true, fxaa: true }, ['composite', 'fxaa'], 0);

postfx.setSize(801, 603);
assert.equal(postfx.sceneTarget.width, 801, 'omitted DPR defaults to 1');
assert.equal(postfx.sceneTarget.height, 603);
checkFrame({ bloomEnabled: true, fastBloom: true }, ['bright', 'blur', 'blur', 'composite', 'fxaa'], 3);
assert.equal(draws[1].target.width, 400, 'lazy bloom resize follows the scene');
assert.equal(draws[1].target.height, 301);
postfx.dispose();
console.log('postfx tests ok: full / fast / disabled bloom, FXAA, resize, scene statistics');
