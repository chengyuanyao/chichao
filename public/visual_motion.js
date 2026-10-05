// 服务器仍决定位置；这里用两帧权威快照和短缓冲构造稳定的显示轨迹。
export function createMotionClock() {
  let offset=null,lastSource=-Infinity,lastNow=-Infinity;
  return {
    push(now,source) {
      if(!Number.isFinite(source)) source=now;
      const observed=now-source;
      if(offset==null||source<lastSource||now<lastNow||now-lastNow>1000) offset=observed;
      else offset+=Math.max(-5,Math.min(5,(observed-offset)*.1));
      lastSource=source;lastNow=now;
    },
    time(now) {return now-(offset??0);},
    reset() {offset=null;lastSource=-Infinity;lastNow=-Infinity;}
  };
}
const shortAngle=value=>Math.atan2(Math.sin(value),Math.cos(value));
export function pushVisualMotion(vis,unit,time) {
  const current=vis.motionCurrent;
  if(current&&time===current.time&&unit.x===current.x&&unit.y===current.y) {
    current.dir=unit.dir||0;
    return;
  }
  const teleport=Math.max(160,(unit.size||12)*10);
  if(!current||time<=current.time||time-current.time>1000||
    Math.hypot(unit.x-current.x,unit.y-current.y)>teleport) {
    vis.motionPrevious={x:unit.x,y:unit.y,dir:unit.dir||0,time};
    vis.motionCurrent={...vis.motionPrevious};
    vis.x=unit.x;vis.y=unit.y;vis.dir=unit.dir||0;
    return;
  }
  Object.assign(vis.motionPrevious,current);
  current.x=unit.x;current.y=unit.y;current.dir=unit.dir||0;current.time=time;
}
export function sampleVisualMotion(vis,time,dt=1/60) {
  const a=vis.motionPrevious,b=vis.motionCurrent;
  if(!a||!b) return;
  const span=b.time-a.time;
  const moving=span>0&&Math.hypot(b.x-a.x,b.y-a.y)>.01;
  // 80ms 缓冲消除 8Hz 追赶式速度脉冲；最多短推 40ms，断流则回到最后权威位置。
  const sample=time-80,ratio=moving&&time-b.time<=500?Math.max(0,Math.min(1+40/span,(sample-a.time)/span)):1;
  const x=a.x+(b.x-a.x)*ratio,y=a.y+(b.y-a.y)*ratio;
  if(vis.unit?.rooted) {vis.x=b.x;vis.y=b.y;}
  else {vis.x=x;vis.y=y;}
  const angle=a.dir+shortAngle(b.dir-a.dir)*Math.min(1,ratio);
  const turn=shortAngle(angle-vis.dir)*(1-Math.exp(-Math.max(0,dt)*14));
  vis.dir+=turn;
  return turn;
}
