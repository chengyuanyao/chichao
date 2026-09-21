// 纯表现层：复用 vis 存姿态，不创建骨骼、粒子或逐帧临时对象。
export function dragonPhase(id) {
  let hash=2166136261;
  for(let i=0;i<id.length;i++) hash=Math.imul(hash^id.charCodeAt(i),16777619);
  hash=Math.imul(hash^(hash>>>16),0x85ebca6b);
  hash=Math.imul(hash^(hash>>>13),0xc2b2ae35);hash^=hash>>>16;
  return (hash>>>0)/4294967296*Math.PI*2;
}

export function advanceDragonFlight(vis,time,dt,distance,turn,scale,detailed) {
  if(vis.flightPhase==null) vis.flightPhase=dragonPhase(String(vis.unit.id));
  const blend=1-Math.exp(-Math.max(0,dt)*6);
  const target=Math.min(1,distance/Math.max(.001,dt)/scale/35);
  vis.flightMotion=(vis.flightMotion||0)+(target-(vis.flightMotion||0))*blend;
  const bankTarget=Math.max(-.12,Math.min(.12,turn/Math.max(.001,dt)*.07));
  vis.flightBank=(vis.flightBank||0)+(bankTarget-(vis.flightBank||0))*blend;
  // 远景不更新翼关节，仍保持相同悬浮高度，避免切 LOD 时突然落地。
  const cycle=time*.0048+vis.flightPhase;
  const beat=detailed?Math.sin(cycle):0;
  vis.flightLift=8+vis.flightMotion*2+beat*1.3;
  vis.flightPitch=detailed?-.065*vis.flightMotion+Math.cos(cycle)*.016:0;
  vis.flightWing=detailed?.06+beat*(.38+vis.flightMotion*.12):0;
  vis.flightDetailed=detailed;
}

// 与 T(地面)·Ry(朝向)·S·T(悬浮)·Rz(俯仰)·Rx(侧倾) 完全同序。
// 炮口/余焰共用，不从旧地面坐标发射，也不必另算一套临时矩阵。
export function dragonFlightPoint(out,vis,x,y,scale) {
  const bank=vis.flightDetailed===false?0:(vis.flightBank||0),pitch=vis.flightPitch||0;
  const by=y*Math.cos(bank),bz=y*Math.sin(bank);
  const px=(x*Math.cos(pitch)-by*Math.sin(pitch))*scale;
  const py=((vis.flightLift||0)+x*Math.sin(pitch)+by*Math.cos(pitch))*scale;
  const pz=bz*scale,c=Math.cos(vis.dir),s=Math.sin(vis.dir);
  return out.set(vis.x+c*px-s*pz,vis.groundY+py,vis.y+s*px+c*pz);
}
