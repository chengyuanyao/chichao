// Input-only work: no frame/tick callbacks, no automatic command replay.
export const ORDERED_UNIT_COMMANDS = new Set([
  'move', 'attackMove', 'patrol', 'attack', 'stop', 'hold', 'scatter', 'harvest', 'repair', 'deploy'
]);

export function createUnitCommandQueue({open, send, isCurrent, timeoutMs = 3000, maxInFlight = 4}) {
  let sequence = 0, active = 0, disposed = false, channel, broken = false;
  const entries = new Set();
  const latest = new Map();
  const cancelled = {cancelled: true};

  async function timed(work, controller) {
    const timer = setTimeout(() => controller.abort('timeout'), timeoutMs);
    try { return await work(controller.signal); }
    finally { clearTimeout(timer); }
  }
  const openingController = new AbortController();
  const ready = timed(open, openingController).then(result => { channel = result.channel; });
  // A failed handshake is surfaced by commands, never an unhandled rejection.
  ready.catch(() => { broken = true; });

  function finish(entry, result, error) {
    if (entry.done) return;
    if (disposed || !isCurrent()) { result = cancelled; error = null; }
    entry.done = true;
    entry.error = error;
    if (entry.running) active--;
    entries.delete(entry);
    entry.ids.forEach(id => { if (latest.get(id) === entry) latest.delete(id); });
    if (error) entry.reject(error); else entry.resolve(result);
  }
  function pump() {
    for (const entry of entries) {
      if (entry.running) continue;
      if (disposed || !isCurrent() || !entry.ids.size) { finish(entry, cancelled); continue; }
      if (entry.dependencies.some(previous => !previous.done)) continue;
      // Don't silently omit a patrol waypoint when its predecessor failed.
      if (entry.dependencies.some(previous => previous.error)) {
        finish(entry, null, new Error('巡逻路径未完整送达，请重新下达命令'));
        continue;
      }
      if (active >= maxInFlight) continue;
      entry.running = true;
      active++;
      timed(signal => send({...entry.payload, unitIds: [...entry.ids],
        input: {channel, sequence: entry.sequence}}, signal), entry.controller)
        .then(result => finish(entry, result), error => finish(entry, null, error))
        .finally(pump);
    }
  }
  function enqueue(payload) {
    if (disposed || !isCurrent()) return Promise.resolve(cancelled);
    const ids = new Set(payload.unitIds || []);
    if (!ids.size) return Promise.resolve(cancelled);
    const dependencies = payload.command === 'patrol'
      ? [...new Set([...ids].map(id => latest.get(id)).filter(Boolean))] : [];
    if (payload.command !== 'patrol') {
      for (const previous of entries) {
        ids.forEach(id => previous.ids.delete(id));
        if (!previous.ids.size) {
          previous.controller.abort('superseded');
          finish(previous, cancelled);
        }
      }
    }
    if (entries.size >= 128) return Promise.reject(new Error('待发指令过多，请等待连接恢复'));
    let entry;
    const result = new Promise((resolve, reject) => {
      entry = {payload, ids, dependencies, sequence: ++sequence, resolve, reject,
        controller: new AbortController(), done: false, running: false};
    });
    entries.add(entry);
    ids.forEach(id => latest.set(id, entry));
    ready.then(pump, error => finish(entry, null, error));
    return result;
  }
  function dispose() {
    disposed = true;
    openingController.abort('superseded');
    for (const entry of entries) {
      entry.controller.abort('superseded');
      finish(entry, cancelled);
    }
    latest.clear();
  }
  return {enqueue, dispose, get broken() { return broken; }};
}
