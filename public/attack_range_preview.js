import * as THREE from './vendor/three.module.min.js';

// One reusable draw call, only during placement. The outer edge is the catalog
// range in the server's horizontal x/y plane (not sight or projectile splash).
export function createAttackRangePreview(groundHeight) {
  const segments = 128;
  const geometry = new THREE.RingGeometry(0.99, 1, segments).rotateX(-Math.PI / 2);
  const positions = geometry.attributes.position;
  positions.setUsage(THREE.DynamicDrawUsage);
  const material = new THREE.MeshBasicMaterial({
    color: 0xffd166, transparent: true, opacity: 0.9,
    depthWrite: false, depthTest: false, fog: false,
    side: THREE.DoubleSide, toneMapped: false
  });
  const mesh = new THREE.Mesh(geometry, material);
  mesh.visible = false;
  mesh.frustumCulled = false;
  mesh.renderOrder = 5;
  let lastX, lastY, lastRadius, lastTerrain;

  function update(preview, terrainKey) {
    const radius = preview && preview.attackRadius;
    if (!preview || !Number.isFinite(radius) || radius <= 0 ||
        !Number.isFinite(preview.x) || !Number.isFinite(preview.y)) {
      mesh.visible = false;
      lastTerrain = undefined;
      lastRadius = undefined;
      return;
    }
    mesh.visible = true;
    material.color.setHex(preview.valid ? 0xffd166 : 0xff5a5a);
    if (lastX === preview.x && lastY === preview.y &&
        lastRadius === radius && lastTerrain === terrainKey) return;
    lastX = preview.x;
    lastY = preview.y;
    lastRadius = radius;
    lastTerrain = terrainKey;
    mesh.position.set(preview.x, 0, preview.y);
    const width = Math.min(radius * 0.04, Math.max(3, radius * 0.012));
    // Sample both edges: raised terrain and bridge decks must not swallow the
    // circle. No per-frame geometry/material creation or entity scanning.
    for (let row = 0; row < 2; row++) {
      const r = row ? radius : radius - width;
      for (let i = 0; i <= segments; i++) {
        const angle = i / segments * Math.PI * 2;
        const x = Math.cos(angle) * r;
        const z = Math.sin(angle) * r;
        positions.setXYZ(row * (segments + 1) + i, x,
          groundHeight(preview.x + x, preview.y + z) + 3, z);
      }
    }
    positions.needsUpdate = true;
  }

  return {mesh, update};
}
