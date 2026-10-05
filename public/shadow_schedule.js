// 静止镜头复用阴影。快照/镜头变化即时更新，旋转与移动投影最多 30Hz。
export function createShadowSchedule() {
  let last=-Infinity,dirty=true,refreshed=0,cached=0;
  return {
    update(time,changed,animated) {
      const refresh=dirty||changed||time<last||(animated&&time-last>=1000/30-.01);
      if(refresh) {last=time;dirty=false;refreshed++;} else cached++;
      return refresh;
    },
    reset() {last=-Infinity;dirty=true;refreshed=0;cached=0;},
    get stats() {return {refreshed,cached};}
  };
}
