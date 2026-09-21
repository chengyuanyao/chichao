// The server decides queue membership and progression; these helpers only display it.
export const BUILD_LANES = ['buildQueue','defenseQueue'];
export function buildingQueue(player, kind, buildings) {
  return player?.[buildings[kind]?.role === 'defense' ? 'defenseQueue' : 'buildQueue'] || [];
}
export function readyBuildings(player) {
  return BUILD_LANES.map(key=>player?.[key]?.[0]).filter(item=>item?.ready);
}
export function queueCaption(item, label, buildings, authorized) {
  if(!item)return label+'：空闲';
  return label+'：'+(buildings[item.kind]?.name||item.kind)+' · '+
    (item.ready?(authorized?'待部署':'待展开部署'):(authorized?Math.ceil(item.remaining)+'秒':'已暂停'));
}
