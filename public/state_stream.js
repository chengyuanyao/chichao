// Detect a half-open SSE connection even when EventSource never fires onerror.
// One coarse timer per connection, never per rendered frame; reconnect backs off.
export function createStateStream({url, onState, onStatus, onReconnect,
  isActive = () => !document.hidden, makeSource = url => new EventSource(url),
  now = () => performance.now(), schedule = setInterval, unschedule = clearInterval}) {
  let source, closed = false, received = false, last = now(), attempts = 0, healthy = 0;
  let wasActive = isActive();
  function open() {
    if (source) source.close();
    const current = makeSource(url);
    source = current;
    received = false; last = now(); healthy = 0;
    current.addEventListener('state', event => {
      if (closed || source !== current) return;
      if (onState(event) === false) { onStatus(false); return; }
      received = true; last = now(); healthy++;
      // Don't reset the backoff just because one large reconnect frame arrived.
      if (healthy >= 8) attempts = 0;
      onStatus(true);
    });
    current.onerror = () => {
      if (closed || source !== current) return;
      onStatus(false);
      onReconnect();
      // Native EventSource can reconnect first; the watchdog bounds silent gaps.
    };
  }
  open();
  const timer = schedule(() => {
    if (closed) return;
    const active = isActive(), time = now();
    if (!active) { wasActive = false; return; }
    if (!wasActive) { last = time; wasActive = true; return; }
    const limit = Math.min(12000, (received ? 1500 : 5000) * Math.pow(2, attempts));
    if (time - last < limit) return;
    attempts = Math.min(4, attempts + 1);
    onStatus(false); onReconnect(); open();
  }, 250);
  return {close() { closed = true; unschedule(timer); source.close(); }};
}
