/** Resources owned by one generated map, separate from shared texture/model caches. */
export function disposeOwnedRenderGroup(group, extraResources = []) {
  if (!group) return;
  const geometries = new Set();
  const materials = new Set();
  function collect(resource) {
    if (!resource) return;
    if (resource.isBufferGeometry) geometries.add(resource);
    if (resource.isMaterial) materials.add(resource);
  }
  group.traverse(function (object) {
    // Instance matrices/colors have their own GPU allocations; geometry disposal
    // alone does not release them. This does not dispose the shared geometry.
    if (object.isInstancedMesh) object.dispose();
    collect(object.geometry);
    if (Array.isArray(object.material)) object.material.forEach(collect);
    else collect(object.material);
  });
  extraResources.forEach(collect);
  geometries.forEach(function (geometry) { geometry.dispose(); });
  // Material.dispose releases shader programs, not its texture maps. Ground,
  // foliage, army and ore textures belong to the renderer's shared texture cache.
  materials.forEach(function (material) { material.dispose(); });
  group.removeFromParent();
  group.clear();
}

/** Keep live shader variants only; material disposal removes every owned variant. */
export class MaterialShaderRegistry {
  constructor() {
    this.entries = new Map();
    this.size = 0;
  }

  get materialCount() { return this.entries.size; }

  add(material, shader) {
    let entry = this.entries.get(material);
    if (!entry) {
      const release = () => {
        const owned = this.entries.get(material);
        if (!owned) return;
        this.size -= owned.shaders.size;
        this.entries.delete(material);
        material.removeEventListener('dispose', release);
      };
      entry = {shaders: new Set(), release};
      this.entries.set(material, entry);
      material.addEventListener('dispose', release);
    }
    if (!entry.shaders.has(shader)) {
      entry.shaders.add(shader);
      this.size++;
    }
  }

  forEach(callback) {
    this.entries.forEach(function (entry) { entry.shaders.forEach(callback); });
  }

  clear() {
    this.entries.forEach(function (entry, material) {
      material.removeEventListener('dispose', entry.release);
    });
    this.entries.clear();
    this.size = 0;
  }
}
