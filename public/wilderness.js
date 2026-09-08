import * as THREE from './vendor/three.module.min.js';

// Build-time ecology, not a per-frame simulation. All maps use the same physical
// materials; moisture, exposed stone and woodland coverage choose their mixture.
const clamp = (v) => Math.max(0, Math.min(1, v));
const smooth = (a, b, v) => { const t = clamp((v - a) / (b - a)); return t * t * (3 - 2 * t); };
const hash = (x, y) => { const n = Math.sin(x * 127.1 + y * 311.7) * 43758.5453; return n - Math.floor(n); };
export function wildernessNoise(x, y) {
  const ix = Math.floor(x), iy = Math.floor(y);
  const fx = smooth(0, 1, x - ix), fy = smooth(0, 1, y - iy);
  const a = hash(ix, iy) * (1 - fx) + hash(ix + 1, iy) * fx;
  const b = hash(ix, iy + 1) * (1 - fx) + hash(ix + 1, iy + 1) * fx;
  return a * (1 - fy) + b * fy;
}

export function wildernessBiome(x, y, { depth = 0, rock = 0, trail = 0, wear = 0, style = '' } = {}) {
  const broad = wildernessNoise(x * 0.004, y * 0.004);
  const detail = wildernessNoise(x * 0.013 + 37, y * 0.013 - 19);
  const dry = style === 'arid_wilderness' || style === 'crater_wilderness';
  const river = style === 'river_valley';
  const forest = river ? 0 : smooth(0.01, 0.35, depth) * (1 - trail);
  const shore = river ? smooth(0.012, 0.16, depth) : 0;
  const soil = clamp(smooth(dry ? 0.26 : 0.45, dry ? 0.64 : 0.76,
    broad * 0.75 + detail * 0.25) * 0.91 + wear * 0.28 + shore * 0.6 + trail * 0.85);
  const stone = clamp(smooth(9, 85, rock) * (0.78 + detail * 0.22) + shore * 0.20);
  const litter = clamp(forest * 0.94 + (!dry && !river ? smooth(20, 100, rock) * 0.24 : 0));
  const wet = clamp(shore * 0.7 + forest * 0.28);
  return [soil, stone, litter, wet];
}

// Mirrored quadrants with an eight-pixel inset keep neighbouring atlas surfaces
// out of the mip footprint. World projection preserves texel density on all maps.
const ATLAS_GLSL = `
vec2 wildUv(vec2 p, vec2 tile) {
  vec2 uv = 1.0 - abs(mod(p, 2.0) - 1.0);
  return tile * 0.5 + vec2(0.008) + uv * 0.484;
}
vec2 wildHash2(vec2 p) {
  return fract(sin(vec2(dot(p, vec2(127.1, 311.7)), dot(p, vec2(269.5, 183.3)))) * 43758.5453);
}
vec3 wildGrass(sampler2D atlas, vec2 p) {
  // Triangular stochastic tiling: three overlapping, independently offset
  // patches remove the visible mirrored checkerboard from photographic grass.
  vec2 skew = mat2(1.0, 0.0, -0.57735027, 1.15470054) * p;
  vec2 base = floor(skew), f = fract(skew);
  vec2 a, b, c; vec3 w;
  if (f.x + f.y < 1.0) {
    a = base; b = base + vec2(1.0, 0.0); c = base + vec2(0.0, 1.0);
    w = vec3(1.0 - f.x - f.y, f.x, f.y);
  } else {
    a = base + vec2(1.0); b = base + vec2(0.0, 1.0); c = base + vec2(1.0, 0.0);
    w = vec3(f.x + f.y - 1.0, 1.0 - f.x, 1.0 - f.y);
  }
  w = w * w; w /= dot(w, vec3(1.0));
  return texture2D(atlas, wildUv(p + wildHash2(a) * 7.0, vec2(0.0, 1.0))).rgb * w.x
    + texture2D(atlas, wildUv(p + wildHash2(b) * 7.0, vec2(0.0, 1.0))).rgb * w.y
    + texture2D(atlas, wildUv(p + wildHash2(c) * 7.0, vec2(0.0, 1.0))).rgb * w.z;
}
`;

function extendKey(material, suffix) {
  const previous = material.customProgramCacheKey;
  material.customProgramCacheKey = function () {
    return (previous ? previous.call(this) : '') + suffix;
  };
}

export function applyWildernessGround(material) {
  const previous = material.onBeforeCompile;
  material.onBeforeCompile = function (shader) {
    if (previous) previous(shader);
    shader.vertexShader = 'attribute vec4 aBiome;\nvarying vec4 vBiome;\n' + shader.vertexShader
      .replace('#include <begin_vertex>', '#include <begin_vertex>\nvBiome = aBiome;');
    shader.fragmentShader = 'varying vec4 vBiome;\n' + ATLAS_GLSL + shader.fragmentShader
      .replace('#include <map_fragment>', `
        vec2 tdWorld = vFogWorld.xz;
        vec3 tdGrass = wildGrass(map, tdWorld / 112.0) * vec3(0.95, 1.12, 0.88);
        vec3 tdSoil = texture2D(map, wildUv(tdWorld.yx / 104.0 + 0.37, vec2(1.0, 1.0))).rgb;
        vec3 tdRock = texture2D(map, wildUv(tdWorld / 125.0 + 0.71, vec2(0.0, 0.0))).rgb;
        vec3 tdLitter = texture2D(map, wildUv(tdWorld / 95.0, vec2(1.0, 0.0))).rgb;
        // Height-modulated blend breaks the coarse splat triangles into grass
        // islands and gritty edges, instead of painting blurred green/brown bands.
        float tdGrain = dot(tdGrass, vec3(0.30, 0.50, 0.20));
        float tdEdgeNoise = fmNoise(tdWorld * 0.048 + vec2(3.1, 7.2)) - 0.5;
        float tdDirt = smoothstep(0.23, 0.70, vBiome.x + tdEdgeNoise * 0.38 + (0.10 - tdGrain) * 4.2);
        float tdStone = smoothstep(0.08, 0.92, vBiome.y);
        vec3 tdSurface = mix(tdGrass, tdSoil, tdDirt);
        tdSurface = mix(tdSurface, tdRock, tdStone);
        tdSurface = mix(tdSurface, tdLitter, vBiome.z * (1.0 - tdStone * 0.6));
        tdSurface *= 1.18 - vBiome.w * 0.34;
        float tdLum = dot(tdSurface, vec3(0.30, 0.50, 0.20));
        diffuseColor.rgb *= tdSurface;
      `)
      .replace('#include <normal_fragment_begin>', `
        #include <normal_fragment_begin>
        vec3 tdDx = dFdx(vViewPosition), tdDy = dFdy(vViewPosition);
        vec3 tdR1 = cross(tdDy, normal), tdR2 = cross(normal, tdDx);
        float tdDet = dot(tdDx, tdR1);
        float tdFade = 1.0 - smoothstep(650.0, 1900.0, length(vViewPosition));
        vec3 tdGradient = sign(tdDet) * (dFdx(tdLum) * tdR1 + dFdy(tdLum) * tdR2);
        normal = normalize(max(abs(tdDet), 0.00001) * normal - tdGradient * 2.8 * tdFade);
      `);
  };
  extendKey(material, '+wilderness-ground2');
  return material;
}

export function applyWildernessRock(material) {
  const previous = material.onBeforeCompile;
  material.onBeforeCompile = function (shader) {
    if (previous) previous(shader);
    shader.fragmentShader = ATLAS_GLSL + shader.fragmentShader
      .replace('#include <map_fragment>', `
        // Slanted world projection avoids stretched cliff UVs without three
        // triplanar samples. The same strata pass continuously through boulders.
        vec2 wrUV = vec2(vFogWorld.x + vFogWorld.z * 0.36,
          vFogWorld.y * 1.5 + vFogWorld.z * 0.45) / 85.0;
        vec3 wrSurface = texture2D(map, wildUv(wrUV, vec2(0.0))).rgb;
        float wrLum = dot(wrSurface, vec3(0.30, 0.50, 0.20));
        diffuseColor.rgb *= wrSurface * 1.6;
      `)
      .replace('#include <normal_fragment_begin>', `
        #include <normal_fragment_begin>
        vec3 wrDx = dFdx(vViewPosition), wrDy = dFdy(vViewPosition);
        vec3 wrR1 = cross(wrDy, normal), wrR2 = cross(normal, wrDx);
        float wrDet = dot(wrDx, wrR1);
        float wrFade = 1.0 - smoothstep(650.0, 1600.0, length(vViewPosition));
        vec3 wrGradient = sign(wrDet) * (dFdx(wrLum) * wrR1 + dFdy(wrLum) * wrR2);
        normal = normalize(max(abs(wrDet), 0.00001) * normal - wrGradient * 3.6 * wrFade);
      `);
  };
  extendKey(material, '+wilderness-rock2');
  return material;
}

export function applyWildernessTrail(material, rut = false) {
  const previous = material.onBeforeCompile;
  material.onBeforeCompile = function (shader) {
    if (previous) previous(shader);
    shader.fragmentShader = ATLAS_GLSL + shader.fragmentShader
      .replace('#include <map_fragment>', `
        vec3 trSoil = texture2D(map, wildUv(vFogWorld.xz / 104.0, vec2(1.0))).rgb;
        float trGrit = dot(trSoil, vec3(0.30, 0.50, 0.20));
        float trEdge = abs(vMapUv.y - 0.5) * 2.0;
        float trFade = 1.0 - smoothstep(0.18, 0.96, trEdge + (trGrit - 0.16) * 1.3);
        diffuseColor.rgb *= trSoil * ${rut ? '0.62' : '1.05'};
        diffuseColor.a *= trFade;
      `);
  };
  extendKey(material, '+wilderness-trail2-' + Number(rut));
  return material;
}

export function applyBridgeWeathering(material) {
  const previous = material.onBeforeCompile;
  material.onBeforeCompile = function (shader) {
    if (previous) previous(shader);
    shader.fragmentShader = ATLAS_GLSL + shader.fragmentShader
      .replace('#include <map_fragment>', `
        vec2 bwUv = vec2(vFogWorld.x + vFogWorld.z * 0.31,
          vFogWorld.z + vFogWorld.y) / 76.0;
        vec3 bwStone = texture2D(map, wildUv(bwUv, vec2(0.0))).rgb;
        float bwLum = dot(bwStone, vec3(0.30, 0.50, 0.20));
        diffuseColor.rgb *= 0.58 + bwLum * 2.3;
      `);
  };
  extendKey(material, '+bridge-weathered2');
  return material;
}

// Weathered asymmetric ledges, not identical faceted gemstones. Shared templates
// have 108 triangles each and are merged by hill; no object is created per frame.
export function makeWeatheredRockGeometry(variant = 0) {
  const positions = [], uvs = [], indices = [];
  const segments = 12;
  const profile = [[-0.65, 0.68], [-0.20, 1], [0.22, 0.92], [0.62, 0.63], [0.88, 0.12]];
  for (let row = 0; row < profile.length; row++) {
    for (let i = 0; i <= segments; i++) {
      const angle = (i % segments) / segments * Math.PI * 2;
      const angular = hash(i % segments, variant + 13);
      const radial = profile[row][1] * (0.77 + angular * 0.38);
      const offset = (row - 2) * 0.085;
      positions.push(Math.cos(angle) * radial + offset,
        profile[row][0] + (hash(i % segments, row + variant * 7) - 0.5) * 0.17,
        Math.sin(angle) * radial + offset * 0.4);
      uvs.push(i / segments, row / (profile.length - 1));
      if (row < profile.length - 1 && i < segments) {
        const a = row * (segments + 1) + i, b = a + segments + 1;
        indices.push(a, b, a + 1, b, b + 1, a + 1);
      }
    }
  }
  // Close the exposed top. The underside stays buried, so it needs no cap.
  const top = positions.length / 3;
  positions.push(0.17, 0.86, 0.068);
  uvs.push(0.5, 1);
  for (let i = 0; i < segments; i++) {
    const edge = (profile.length - 1) * (segments + 1) + i;
    indices.push(edge, top, edge + 1);
  }
  const indexed = new THREE.BufferGeometry();
  indexed.setAttribute('position', new THREE.Float32BufferAttribute(positions, 3));
  indexed.setAttribute('uv', new THREE.Float32BufferAttribute(uvs, 2));
  indexed.setIndex(indices);
  indexed.computeVertexNormals();
  const geometry = indexed.toNonIndexed();
  indexed.dispose();
  return geometry;
}

export const FOREST_CHUNK_SIZE = 640;
export function forestChunkKey(x, z) {
  return Math.floor(x / FOREST_CHUNK_SIZE) + ':' + Math.floor(z / FOREST_CHUNK_SIZE);
}
