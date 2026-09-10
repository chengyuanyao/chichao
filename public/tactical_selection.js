// Filtering changes only the local selection, never a unit's current order.
export function createTacticalSelection() {
  let source = new Set(), expected = new Set(), activeKind = null;
  let live = new Map();
  const same = (a,b) => a.size === b.size && [...a].every(id => b.has(id));
  function sync(units, selected, owner) {
    live = new Map(units.filter(u => u.owner === owner && u.hp > 0).map(u => [u.id,u]));
    const current = new Set([...selected].filter(id => live.has(id)));
    expected = new Set([...expected].filter(id => live.has(id)));
    if (!same(current,expected)) { source = new Set(current); activeKind = null; }
    source = new Set([...source].filter(id => live.has(id)));
    expected = current;
    const counts = new Map();
    for (const id of source) {
      const kind = live.get(id).kind;
      counts.set(kind,(counts.get(kind)||0)+1);
    }
    return {groups:[...counts].map(([kind,count]) => ({kind,count})),activeKind,total:source.size};
  }
  function filter(kind) {
    activeKind = kind || null;
    expected = new Set([...source].filter(id => live.has(id) && (!activeKind || live.get(id).kind === activeKind)));
    return [...expected];
  }
  return {sync,filter};
}
