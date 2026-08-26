/**
 * 后处理链：亮度提取 → 两级模糊 → 合成（辉光 + 调色 + 暗角）→ FXAA。
 *
 * 没有用 three.js 的 postprocessing 附加包：UnrealBloomPass 要额外内置约十个
 * 文件、跑五级 mip 的可分离模糊，对一个局域网小游戏太重。这里只做两级半分辨
 * 率模糊，加上合成与 FXAA 共七个 pass，画面收益几乎一样但便宜得多。
 *
 * 色彩管线：场景渲染到 HalfFloat 的线性目标（保留 >1 的高光，辉光才有东西可
 * 提取），全部中间 pass 都在线性空间。合成 pass 做「曝光 → 白平衡 → 电影
 * 色调映射（AgX / ACES）→ 饱和度与对比 → 暗角」，然后**手动**做线性→sRGB
 * 编码写进一个 RGBA8 目标，把感知亮度塞进 alpha 通道；最后 FXAA 以该亮度
 * 找边，抗锯齿后直写画布。
 *
 * 为什么不用 three.js 自带的 <colorspace_fragment>：它在渲染到离屏目标时
 * 会自动变成空操作（离屏目标一律按线性对待），合成 pass 的输出现在正是
 * 离屏的 FXAA 输入，所以 sRGB 编码必须自己写。FXAA 收到的已经是 sRGB 数据，
 * 直接输出即可，不能再转换一次。
 *
 * 为什么需要 FXAA：画布的 antialias:true 只对直接渲染到画布生效；场景一旦
 * 先渲染进 FBO（辉光开启时的路径），MSAA 就不存在了 —— 之前辉光开着其实
 * 一直没有抗锯齿。
 */

import * as THREE from './vendor/three.module.min.js';

const FULLSCREEN_VERT = `
varying vec2 vUv;
void main() {
  vUv = uv;
  gl_Position = vec4(position.xy, 0.0, 1.0);
}
`;

const BRIGHT_FRAG = `
uniform sampler2D tScene;
uniform float uThreshold;
uniform float uKnee;
varying vec2 vUv;
void main() {
  vec3 c = texture2D(tScene, vUv).rgb;
  float luma = dot(c, vec3(0.2126, 0.7152, 0.0722));
  // 软阈值：阈值附近平滑过渡，避免出现硬边光斑
  float soft = clamp(luma - uThreshold + uKnee, 0.0, 2.0 * uKnee);
  soft = soft * soft / (4.0 * uKnee + 0.0001);
  float contribution = max(soft, luma - uThreshold) / max(luma, 0.0001);
  gl_FragColor = vec4(c * contribution, 1.0);
}
`;

const BLUR_FRAG = `
uniform sampler2D tSource;
uniform vec2 uDirection;   // 像素步长，已经含方向
varying vec2 vUv;
void main() {
  // 9 抽样高斯，权重来自 sigma≈2 的归一化核
  vec4 sum = texture2D(tSource, vUv) * 0.2270270270;
  sum += texture2D(tSource, vUv + uDirection * 1.3846153846) * 0.3162162162;
  sum += texture2D(tSource, vUv - uDirection * 1.3846153846) * 0.3162162162;
  sum += texture2D(tSource, vUv + uDirection * 3.2307692308) * 0.0702702703;
  sum += texture2D(tSource, vUv - uDirection * 3.2307692308) * 0.0702702703;
  gl_FragColor = sum;
}
`;

const COMPOSITE_FRAG = `
uniform sampler2D tScene;
uniform sampler2D tBloomNear;
uniform sampler2D tBloomFar;
uniform float uBloom;
uniform float uVignette;
uniform float uScanline;
uniform float uExposure;
uniform float uWarmth;
uniform float uSaturation;
uniform float uContrast;
uniform float uTonemap;    // 0 = AgX punchy, 1 = ACES fitted
uniform float uTime;
uniform vec2 uResolution;
varying vec2 vUv;

/* ---- ACES fitted（Stephen Hill / BakingLab）。GLSL 列主序 = HLSL 行的转置 ---- */
const mat3 ACESInputMat = mat3(
  0.59719, 0.07600, 0.02840,
  0.35458, 0.90834, 0.13383,
  0.04823, 0.01566, 0.83777);
const mat3 ACESOutputMat = mat3(
  1.60475, -0.10208, -0.00327,
 -0.53108,  1.10813, -0.07276,
 -0.07367, -0.00605,  1.07602);
vec3 RRTAndODTFit(vec3 v) {
  vec3 a = v * (v + 0.0245786) - 0.000090537;
  vec3 b = v * (0.983729 * v + 0.4329510) + 0.238081;
  return a / b;
}
vec3 acesFitted(vec3 c) {
  c = ACESInputMat * c;
  c = RRTAndODTFit(c);
  return clamp(ACESOutputMat * c, 0.0, 1.0);
}

/* ---- AgX（Benjamin Wrensch 的最小近似，three r160+ 采用的同族曲线）。
 *      对高饱和的队伍色 / 爆炸橙比 ACES 的色相偏移更小。 ---- */
vec3 agxDefaultContrastApprox(vec3 x) {
  vec3 x2 = x * x;
  vec3 x4 = x2 * x2;
  return + 15.5   * x4 * x2 - 40.14 * x4 * x + 31.96 * x4
         - 6.868  * x2 * x + 0.4298 * x2 + 0.1191 * x - 0.00232;
}
vec3 agx(vec3 val) {
  const mat3 agx_mat = mat3(
    0.842479062253094, 0.0423282422610123, 0.0423756549057051,
    0.0784335999999992, 0.878468636469772,  0.0784336,
    0.0792237451477643, 0.0791661274605434, 0.879142973793104);
  const float min_ev = -12.47393;
  const float max_ev = 4.026069;
  val = agx_mat * val;
  val = clamp(log2(max(val, vec3(1e-10))), min_ev, max_ev);
  val = (val - min_ev) / (max_ev - min_ev);
  return agxDefaultContrastApprox(val);
}
vec3 agxEotf(vec3 val) {
  const mat3 agx_mat_inv = mat3(
     1.19687900512017,  -0.0528968517574562, -0.0529716355144438,
    -0.0980208811401368, 1.15190312990417,   -0.0980434501171241,
    -0.0990297440797205,-0.0989611768448433,  1.15107367264116);
  val = agx_mat_inv * val;
  // 回到线性；最终的 sRGB 编码在输出前统一做
  return pow(max(val, vec3(0.0)), vec3(2.2));
}
// 收敛 punchy：饱和提升 1.4→1.18、对比曲线 1.35→1.22。色相分离保留（RTS 靠它
// 分队/辨兵种），但去掉那股「冲」劲，画面更平、更中性，贴近 Apple/Google 的干净。
vec3 agxLookPunchy(vec3 val) {
  float luma = dot(val, vec3(0.2126, 0.7152, 0.0722));
  val = pow(max(val, vec3(0.0)), vec3(1.22));
  return luma + 1.18 * (val - luma);
}

/* 手动 sRGB 编码：见文件头，离屏目标上 three 的自动转换是空操作 */
vec3 OETFsRGB(vec3 c) {
  c = clamp(c, 0.0, 1.0);
  return mix(c * 12.92, 1.055 * pow(c, vec3(1.0 / 2.4)) - 0.055,
             step(vec3(0.0031308), c));
}

void main() {
  vec3 scene = texture2D(tScene, vUv).rgb;
  vec3 bloom = texture2D(tBloomNear, vUv).rgb * 0.62
             + texture2D(tBloomFar, vUv).rgb * 0.38;
  vec3 color = scene + bloom * uBloom;

  // 线性空间：曝光 + 白平衡（暖阳基调 —— 参考画面是高对比的晴天午后）
  color *= uExposure * mix(vec3(1.0), vec3(1.06, 1.00, 0.90), uWarmth);

  // 电影色调映射：AgX 输出回线性再统一编码，ACES 输出当作显示线性用
  vec3 mapped = uTonemap < 0.5
    ? agxEotf(agxLookPunchy(agx(color)))
    : acesFitted(color);
  color = mapped;

  // 显示空间的最后修饰：饱和度（RTS 的可读性靠色相区分）+ 对比
  float luma = dot(color, vec3(0.2126, 0.7152, 0.0722));
  color = mix(vec3(luma), color, uSaturation);
  color = (color - 0.5) * uContrast + 0.5;

  // 暗角：把注意力压回战场中心
  vec2 centered = vUv - 0.5;
  float vig = 1.0 - dot(centered, centered) * uVignette;
  color *= clamp(vig, 0.0, 1.0);

  // 极轻的扫描线，给一点显示器质感；太强会显得廉价
  if (uScanline > 0.0) {
    float line = sin(vUv.y * uResolution.y * 1.5708) * 0.5 + 0.5;
    color *= 1.0 - uScanline * line;
  }

  // sRGB 编码进 RGBA8，感知亮度进 alpha 供 FXAA 找边
  vec3 srgb = OETFsRGB(color);
  gl_FragColor = vec4(srgb, dot(srgb, vec3(0.299, 0.587, 0.114)));
}
`;

/* FXAA 3.11（Simon Rodriguez 的忠实移植版）。输入的 alpha 已存好感知亮度。 */
const FXAA_FRAG = `
uniform sampler2D tSrc;
uniform vec2 uInvRes;
varying vec2 vUv;
#define EDGE_MIN 0.0312
#define EDGE_MAX 0.125
#define SUBPIX 0.75
#define ITER 12
float Q(int i) { return i < 5 ? 1.0 : (i == 5 ? 1.5 : (i < 10 ? 2.0 : (i == 10 ? 4.0 : 8.0))); }
float L(vec2 uv) { return texture2D(tSrc, uv).a; }
void main() {
  vec3 rgbC = texture2D(tSrc, vUv).rgb;
  float lC = L(vUv);
  float lD = L(vUv + vec2(0.0, -uInvRes.y));
  float lU = L(vUv + vec2(0.0,  uInvRes.y));
  float lL = L(vUv + vec2(-uInvRes.x, 0.0));
  float lR = L(vUv + vec2( uInvRes.x, 0.0));
  float lMin = min(lC, min(min(lD, lU), min(lL, lR)));
  float lMax = max(lC, max(max(lD, lU), max(lL, lR)));
  float range = lMax - lMin;
  if (range < max(EDGE_MIN, lMax * EDGE_MAX)) { gl_FragColor = vec4(rgbC, 1.0); return; }
  float lDL = L(vUv + vec2(-uInvRes.x, -uInvRes.y));
  float lUR = L(vUv + uInvRes);
  float lUL = L(vUv + vec2(-uInvRes.x,  uInvRes.y));
  float lDR = L(vUv + vec2( uInvRes.x, -uInvRes.y));
  float lDU = lD + lU;
  float lLR = lL + lR;
  float lLC = lDL + lUL;
  float lDC = lDL + lDR;
  float lRC = lDR + lUR;
  float lUC = lUR + lUL;
  float eH = abs(-2.0 * lL + lLC) + abs(-2.0 * lC + lDU) * 2.0 + abs(-2.0 * lR + lRC);
  float eV = abs(-2.0 * lU + lUC) + abs(-2.0 * lC + lLR) * 2.0 + abs(-2.0 * lD + lDC);
  bool horiz = (eH >= eV);
  float l1 = horiz ? lD : lL;
  float l2 = horiz ? lU : lR;
  float g1 = l1 - lC;
  float g2 = l2 - lC;
  bool steep1 = abs(g1) >= abs(g2);
  float gScaled = 0.25 * max(abs(g1), abs(g2));
  float stepLen = horiz ? uInvRes.y : uInvRes.x;
  float lAvg = 0.0;
  if (steep1) { stepLen = -stepLen; lAvg = 0.5 * (l1 + lC); }
  else { lAvg = 0.5 * (l2 + lC); }
  vec2 cur = vUv;
  if (horiz) cur.y += stepLen * 0.5; else cur.x += stepLen * 0.5;
  vec2 off = horiz ? vec2(uInvRes.x, 0.0) : vec2(0.0, uInvRes.y);
  vec2 uv1 = cur - off;
  vec2 uv2 = cur + off;
  float e1 = L(uv1) - lAvg;
  float e2 = L(uv2) - lAvg;
  bool r1 = abs(e1) >= gScaled;
  bool r2 = abs(e2) >= gScaled;
  if (!r1) uv1 -= off;
  if (!r2) uv2 += off;
  if (!(r1 && r2)) {
    for (int i = 2; i < ITER; i++) {
      if (!r1) e1 = L(uv1) - lAvg;
      if (!r2) e2 = L(uv2) - lAvg;
      r1 = abs(e1) >= gScaled;
      r2 = abs(e2) >= gScaled;
      if (!r1) uv1 -= off * Q(i);
      if (!r2) uv2 += off * Q(i);
      if (r1 && r2) break;
    }
  }
  float d1 = horiz ? (vUv.x - uv1.x) : (vUv.y - uv1.y);
  float d2 = horiz ? (uv2.x - vUv.x) : (uv2.y - vUv.y);
  bool dir1 = d1 < d2;
  float dFinal = min(d1, d2);
  float thick = d1 + d2;
  bool smaller = lC < lAvg;
  bool var1 = (e1 < 0.0) != smaller;
  bool var2 = (e2 < 0.0) != smaller;
  float po = ((dir1 ? var1 : var2) ? (-dFinal / thick + 0.5) : 0.0);
  float la = (1.0 / 12.0) * (2.0 * (lDU + lLR) + lLC + lRC);
  float sp1 = clamp(abs(la - lC) / range, 0.0, 1.0);
  float sp2 = (-2.0 * sp1 + 3.0) * sp1 * sp1;
  po = max(po, sp2 * sp2 * SUBPIX);
  vec2 fUv = vUv;
  if (horiz) fUv.y += po * stepLen; else fUv.x += po * stepLen;
  gl_FragColor = vec4(texture2D(tSrc, fUv).rgb, 1.0);
}
`;

function fullscreenGeometry() {
  // 一个覆盖屏幕的大三角形，比两个三角形的 quad 少一条对角接缝
  const geo = new THREE.BufferGeometry();
  geo.setAttribute('position', new THREE.BufferAttribute(
    new Float32Array([-1, -1, 0, 3, -1, 0, -1, 3, 0]), 3));
  geo.setAttribute('uv', new THREE.BufferAttribute(
    new Float32Array([0, 0, 2, 0, 0, 2]), 2));
  return geo;
}

export function createPostFX(renderer) {
  const quadGeo = fullscreenGeometry();
  const quadCamera = new THREE.OrthographicCamera(-1, 1, 1, -1, 0, 1);
  const quadScene = new THREE.Scene();
  const quad = new THREE.Mesh(quadGeo, null);
  quad.frustumCulled = false;
  quadScene.add(quad);

  const supportsHalfFloat = renderer.capabilities.isWebGL2 ||
    !!renderer.extensions.get('OES_texture_half_float');

  const targetOptions = {
    minFilter: THREE.LinearFilter,
    magFilter: THREE.LinearFilter,
    type: supportsHalfFloat ? THREE.HalfFloatType : THREE.UnsignedByteType,
    depthBuffer: true,
    stencilBuffer: false
  };

  const sceneTarget = new THREE.WebGLRenderTarget(1, 1, targetOptions);
  const blurOptions = Object.assign({}, targetOptions, { depthBuffer: false });
  const nearA = new THREE.WebGLRenderTarget(1, 1, blurOptions);
  const nearB = new THREE.WebGLRenderTarget(1, 1, blurOptions);
  const farA = new THREE.WebGLRenderTarget(1, 1, blurOptions);
  const farB = new THREE.WebGLRenderTarget(1, 1, blurOptions);
  // FXAA 的输入：合成后的 sRGB 图，8 位足够（不再有 >1 的值）
  const postTarget = new THREE.WebGLRenderTarget(1, 1, {
    minFilter: THREE.LinearFilter,
    magFilter: THREE.LinearFilter,
    type: THREE.UnsignedByteType,
    depthBuffer: false,
    stencilBuffer: false
  });

  const brightMat = new THREE.ShaderMaterial({
    uniforms: {
      tScene: { value: null },
      uThreshold: { value: 1.0 },
      uKnee: { value: 0.4 }
    },
    vertexShader: FULLSCREEN_VERT,
    fragmentShader: BRIGHT_FRAG,
    depthTest: false,
    depthWrite: false
  });

  const blurMat = new THREE.ShaderMaterial({
    uniforms: {
      tSource: { value: null },
      uDirection: { value: new THREE.Vector2() }
    },
    vertexShader: FULLSCREEN_VERT,
    fragmentShader: BLUR_FRAG,
    depthTest: false,
    depthWrite: false
  });

  const compositeMat = new THREE.ShaderMaterial({
    uniforms: {
      tScene: { value: null },
      tBloomNear: { value: null },
      tBloomFar: { value: null },
      // 写实材质需要看得见粗糙表面，辉光/曝光太高会把它们重新洗成塑料。
      // 队伍辨识主要交给哑光识别色，小灯和爆炸仍能正常进 bloom。
      uBloom: { value: 0.46 },
      uVignette: { value: 0.20 },
      uScanline: { value: 0.0 },
      uExposure: { value: 1.46 },
      uWarmth: { value: 0.20 },
      uSaturation: { value: 1.02 },
      uContrast: { value: 1.03 },
      uTonemap: { value: 0.0 },
      uTime: { value: 0 },
      uResolution: { value: new THREE.Vector2(1, 1) }
    },
    vertexShader: FULLSCREEN_VERT,
    fragmentShader: COMPOSITE_FRAG,
    depthTest: false,
    depthWrite: false
  });

  const fxaaMat = new THREE.ShaderMaterial({
    uniforms: {
      tSrc: { value: null },
      uInvRes: { value: new THREE.Vector2(1, 1) }
    },
    vertexShader: FULLSCREEN_VERT,
    fragmentShader: FXAA_FRAG,
    depthTest: false,
    depthWrite: false
  });

  // 后处理会多次调用 renderer.render，而 renderer.info.render 每次都会重置，
  // 所以在场景 pass 之后立刻把统计抄下来，供外部读取。
  const state = { width: 1, height: 1, enabled: true, fxaa: true, fastBloom: false, calls: 0, triangles: 0 };

  function blit(material, target) {
    quad.material = material;
    renderer.setRenderTarget(target);
    renderer.clear(true, false, false);
    renderer.render(quadScene, quadCamera);
  }

  return {
    get sceneTarget() { return sceneTarget; },
    get enabled() { return state.enabled; },

    setSize: function (width, height, pixelRatio) {
      const w = Math.max(1, Math.floor(width * pixelRatio));
      const h = Math.max(1, Math.floor(height * pixelRatio));
      state.width = w;
      state.height = h;
      sceneTarget.setSize(w, h);
      postTarget.setSize(w, h);
      const nearW = Math.max(1, w >> 1);
      const nearH = Math.max(1, h >> 1);
      const farW = Math.max(1, w >> 2);
      const farH = Math.max(1, h >> 2);
      nearA.setSize(nearW, nearH);
      nearB.setSize(nearW, nearH);
      farA.setSize(farW, farH);
      farB.setSize(farW, farH);
      compositeMat.uniforms.uResolution.value.set(w, h);
      fxaaMat.uniforms.uInvRes.value.set(1 / w, 1 / h);
    },

    setOptions: function (options) {
      if (options.enabled != null) state.enabled = !!options.enabled;
      if (options.fxaa != null) state.fxaa = !!options.fxaa;
      if (options.fastBloom != null) state.fastBloom = !!options.fastBloom;
      if (options.bloom != null) compositeMat.uniforms.uBloom.value = options.bloom;
      if (options.threshold != null) brightMat.uniforms.uThreshold.value = options.threshold;
      if (options.vignette != null) compositeMat.uniforms.uVignette.value = options.vignette;
      if (options.scanline != null) compositeMat.uniforms.uScanline.value = options.scanline;
      if (options.exposure != null) compositeMat.uniforms.uExposure.value = options.exposure;
      if (options.warmth != null) compositeMat.uniforms.uWarmth.value = options.warmth;
      if (options.saturation != null) compositeMat.uniforms.uSaturation.value = options.saturation;
      if (options.contrast != null) compositeMat.uniforms.uContrast.value = options.contrast;
      if (options.tonemap != null) {
        compositeMat.uniforms.uTonemap.value = options.tonemap === 'aces' ? 1 : 0;
      }
    },

    get sceneStats() { return { calls: state.calls, triangles: state.triangles }; },

    /** 渲染一帧：关闭后处理时直接画到画布。 */
    render: function (scene, camera, time) {
      if (!state.enabled) {
        renderer.setRenderTarget(null);
        renderer.render(scene, camera);
        state.calls = renderer.info.render.calls;
        state.triangles = renderer.info.render.triangles;
        return;
      }
      renderer.setRenderTarget(sceneTarget);
      renderer.clear();
      renderer.render(scene, camera);
      state.calls = renderer.info.render.calls;
      state.triangles = renderer.info.render.triangles;

      brightMat.uniforms.tScene.value = sceneTarget.texture;
      blit(brightMat, nearA);

      const nearStep = blurMat.uniforms.uDirection.value;
      blurMat.uniforms.tSource.value = nearA.texture;
      nearStep.set(1 / nearA.width, 0);
      blit(blurMat, nearB);
      blurMat.uniforms.tSource.value = nearB.texture;
      nearStep.set(0, 1 / nearA.height);
      blit(blurMat, nearA);

      // 快速泛光：只做一级模糊就合成，省略第二级 + FXAA
      if (state.fastBloom) {
        compositeMat.uniforms.tScene.value = sceneTarget.texture;
        compositeMat.uniforms.tBloomNear.value = nearA.texture;
        compositeMat.uniforms.tBloomFar.value = nearA.texture;
        compositeMat.uniforms.uTime.value = time * 0.001;
        quad.material = compositeMat;
        renderer.setRenderTarget(null);
        renderer.render(quadScene, quadCamera);
        return;
      }

      // 第二级：在半分辨率结果上再模糊一次，得到范围更大的柔光
      blurMat.uniforms.tSource.value = nearA.texture;
      nearStep.set(1 / farA.width, 0);
      blit(blurMat, farB);
      blurMat.uniforms.tSource.value = farB.texture;
      nearStep.set(0, 1 / farA.height);
      blit(blurMat, farA);

      compositeMat.uniforms.tScene.value = sceneTarget.texture;
      compositeMat.uniforms.tBloomNear.value = nearA.texture;
      compositeMat.uniforms.tBloomFar.value = farA.texture;
      compositeMat.uniforms.uTime.value = time * 0.001;

      if (state.fxaa) {
        blit(compositeMat, postTarget);
        fxaaMat.uniforms.tSrc.value = postTarget.texture;
        quad.material = fxaaMat;
        renderer.setRenderTarget(null);
        renderer.render(quadScene, quadCamera);
      } else {
        // 无 FXAA 时合成直写画布：数据已经手动编码为 sRGB，直接输出
        quad.material = compositeMat;
        renderer.setRenderTarget(null);
        renderer.render(quadScene, quadCamera);
      }
    },

    dispose: function () {
      [sceneTarget, nearA, nearB, farA, farB, postTarget].forEach(function (t) { t.dispose(); });
      [brightMat, blurMat, compositeMat, fxaaMat].forEach(function (m) { m.dispose(); });
      quadGeo.dispose();
    }
  };
}
