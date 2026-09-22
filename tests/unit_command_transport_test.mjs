import assert from 'node:assert/strict';
import {createUnitCommandQueue} from '../public/unit_commands.js';

const drain = () => new Promise(resolve => setImmediate(resolve));
function harness(options = {}) {
  const sent = [];
  let current = true;
  const queue = createUnitCommandQueue({
    open: async () => ({channel: 'test'}), isCurrent: () => current,
    send(payload, signal) {
      return new Promise((resolve, reject) => {
        const item = {payload, resolve, reject, signal};
        sent.push(item);
        signal.addEventListener('abort', () => reject(new Error(signal.reason)), {once: true});
      });
    }, ...options
  });
  return {queue, sent, stale: () => {current = false;}};
}
const move = (ids, x = 100) => ({command: 'move', unitIds: ids, x, y: 100});
const patrol = x => ({command: 'patrol', unitIds: ['dog'], x, y: 100});

// Exact incident reproduction: never answer the first mass-tank move. H and an
// unrelated scouting order must both reach HTTP without waiting for that reply.
{
  const {queue, sent} = harness();
  const ids = Array.from({length: 53}, (_, i) => 'overlord' + i);
  const blocked = queue.enqueue(move(ids));
  await drain();
  const stop = queue.enqueue({command: 'stop', unitIds: ids});
  const scout = queue.enqueue(move(['dog']));
  await drain();
  assert.deepEqual(sent.map(item => item.payload.command), ['move', 'stop', 'move']);
  assert.equal((await blocked).cancelled, true);
  assert.equal(sent[0].signal.aborted, true);
  assert.equal(sent[1].payload.unitIds.length, 53);
  sent[1].resolve({}); sent[2].resolve({}); await Promise.all([stop, scout]);
  queue.dispose();
}
// Same-unit patrol is ordered, other units independent. Replacement cancels
// unsent nodes and in-flight stale waypoints without waiting for their ACK.
{
  const {queue, sent} = harness();
  const first = queue.enqueue(patrol(100)), second = queue.enqueue(patrol(200));
  const third = queue.enqueue(patrol(300));
  await drain(); assert.equal(sent.length, 1);
  sent[0].resolve({}); await first; await drain();
  assert.equal(sent[1].payload.x, 200);
  const stop = queue.enqueue({command: 'stop', unitIds: ['dog']});
  await drain();
  assert.equal((await second).cancelled, true);
  assert.equal((await third).cancelled, true);
  assert.equal(sent[2].payload.command, 'stop');
  sent[2].resolve({}); await stop; queue.dispose();
}
// Partial overlap: preserve the old request for B; server will filter its A.
{
  const {queue, sent} = harness();
  const old = queue.enqueue(move(['a', 'b'])); await drain();
  const recent = queue.enqueue(move(['a'], 200)); await drain();
  assert.equal(sent.length, 2); assert.equal(sent[0].signal.aborted, false);
  assert.ok(sent[1].payload.input.sequence > sent[0].payload.input.sequence);
  sent[1].resolve({}); sent[0].resolve({}); await Promise.all([old, recent]); queue.dispose();
}
// No automatic replay of deploy/harvest/etc on timeout. Failed patrol tails do
// not drop a waypoint then silently carry on; a fresh explicit move recovers.
{
  const {queue, sent} = harness({timeoutMs: 25});
  const first = assert.rejects(queue.enqueue(patrol(100)), /timeout/);
  const second = assert.rejects(queue.enqueue(patrol(200)), /巡逻/);
  await Promise.all([first, second]); assert.equal(sent.length, 1);
  const recover = queue.enqueue(move(['dog'])); await drain();
  sent[1].resolve({}); await recover; queue.dispose();
}
// Bounded connections and stale-match cancellation.
{
  const {queue, sent, stale} = harness({maxInFlight: 2});
  const results = ['a','b','c'].map(id => queue.enqueue(move([id])));
  await drain(); assert.equal(sent.length, 2);
  stale(); sent[0].resolve({}); sent[1].resolve({});
  assert.ok((await Promise.all(results)).every(result => result.cancelled));
  queue.dispose();
}
// Failed initial handshakes are visible and can be replaced by the app.
{
  const {queue} = harness({open: async () => {throw new Error('offline');}});
  await assert.rejects(queue.enqueue(move(['a'])), /offline/);
  assert.equal(queue.broken, true);
  queue.dispose();
}
console.log('Unit transport: hung 53-tank move, H, independent groups, patrol order, partial overlap, timeout and match isolation passed.');
