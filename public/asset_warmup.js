// Yield between assets: never turn first-use work into one long startup task.
export const yieldAssetTask = () => new Promise(resolve => setTimeout(resolve, 8));

export async function warmAssetTasks(tasks, cancelled = () => false) {
  for (const task of tasks) {
    await yieldAssetTask();
    if (cancelled()) return false;
    await task();
  }
  return !cancelled();
}

// Solid armor/stone/cloth must occlude the scene. Ghost placement previews and
// particles have their own materials and deliberately do not use this helper.
export function solidSurface(material) {
  material.transparent = false;
  material.opacity = 1;
  material.depthTest = true;
  material.depthWrite = true;
  return material;
}
