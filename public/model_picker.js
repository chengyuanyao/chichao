import * as THREE from './vendor/three.module.min.js';

// Read the same geometry/instance matrices as the displayed frame. Bounds are
// only a broad-phase test inside Mesh.raycast; a triangle must actually be hit.
// This helper never clones models, changes the scene, or runs on animation ticks.
export function createModelPicker() {
  const raycaster = new THREE.Raycaster();
  const ndc = new THREE.Vector2();
  const instanceMatrix = new THREE.Matrix4();
  const worldMatrix = new THREE.Matrix4();
  const probeMaterial = new THREE.MeshBasicMaterial({side: THREE.DoubleSide});
  const emptyGeometry = new THREE.BufferGeometry();
  const probe = new THREE.Mesh(emptyGeometry, probeMaterial);
  const records = [];
  const intersections = [];
  let count = 0;

  function begin() {
    for (let i = 0; i < count; i++) {
      records[i].entity = null;
      records[i].geometry = null;
    }
    count = 0;
  }

  function add(entity, geometry, matrixWorld) {
    if (!entity || !geometry) return;
    if (!geometry.boundingBox) geometry.computeBoundingBox();
    if (!geometry.boundingSphere) geometry.computeBoundingSphere();
    const record = records[count] || (records[count] = {matrix: new THREE.Matrix4()});
    record.entity = entity;
    record.geometry = geometry;
    record.matrix.copy(matrixWorld);
    count++;
  }

  function addInstances(mesh, entityAtIndex) {
    if (!mesh || !mesh.visible || !mesh.count) return;
    mesh.updateWorldMatrix(true, false);
    for (let i = 0; i < mesh.count; i++) {
      const entity = entityAtIndex(i);
      if (!entity) continue;
      mesh.getMatrixAt(i, instanceMatrix);
      worldMatrix.multiplyMatrices(mesh.matrixWorld, instanceMatrix);
      add(entity, mesh.geometry, worldMatrix);
    }
  }

  function addObject(root, entity) {
    if (!root || !root.visible || !entity) return;
    root.updateWorldMatrix(true, true);
    root.traverseVisible(object => {
      // Dirt aprons, selection rings and effects are not the building model.
      if (object.isMesh && !object.userData.pickIgnore) {
        add(entity, object.geometry, object.matrixWorld);
      }
    });
  }

  function cast(camera, width, height, sx, sy, acceptHit) {
    ndc.set(sx / width * 2 - 1, 1 - sy / height * 2);
    raycaster.setFromCamera(ndc, camera);
    raycaster.near = camera.near;
    raycaster.far = camera.far;
    let best = null;
    for (let i = 0; i < count; i++) {
      const record = records[i];
      probe.geometry = record.geometry;
      probe.matrixWorld.copy(record.matrix);
      intersections.length = 0;
      probe.raycast(raycaster, intersections);
      for (const hit of intersections) {
        if ((!best || hit.distance < best.distance) &&
            (!acceptHit || acceptHit(record.entity, hit.point))) {
          best = {entity: record.entity, distance: hit.distance};
        }
      }
    }
    probe.geometry = emptyGeometry;
    intersections.length = 0;
    return best;
  }

  function pick(camera, width, height, sx, sy, acceptHit) {
    if (!count || ![width, height, sx, sy].every(Number.isFinite) ||
        width <= 0 || height <= 0 || sx < 0 || sy < 0 || sx > width || sy > height) return null;
    const exact = cast(camera, width, height, sx, sy, acceptHit);
    if (exact) return exact.entity;
    // A small CSS-pixel halo helps thin limbs and distant infantry. It is tried
    // only after ALL exact unit/building hits, so a nearby bounding box cannot
    // steal an enemy roof click. Empty space > 4 px from the model stays empty.
    for (const radius of [1, 2, 3, 4]) {
      let nearest = null;
      for (let i = 0; i < 8; i++) {
        const angle = i * Math.PI / 4;
        const hit = cast(camera, width, height,
          sx + Math.cos(angle) * radius, sy + Math.sin(angle) * radius, acceptHit);
        if (hit && (!nearest || hit.distance < nearest.distance)) nearest = hit;
      }
      if (nearest) return nearest.entity;
    }
    return null;
  }

  function clear() { begin(); records.length = 0; }
  return {begin, add, addInstances, addObject, pick, clear,
    dispose() { clear(); probeMaterial.dispose(); emptyGeometry.dispose(); }};
}
