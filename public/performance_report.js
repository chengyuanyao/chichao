// Bounded frame/network counters. Transport is handled separately at low frequency.
const LIMIT = 120;
const sums=['frames','ms','over50','over100','loadSamples','netMessages','netGapSamples','netGapMs','netOver500',
  'stateBytes','parseMs','commandSamples','commandMs','commandFailures','probeSamples','probeMs','probeFailures','reconnects'];
const maxima=['maxMs','maxUnits','maxDrawCalls','maxTriangles','maxParticles','maxGeometries','maxTextures',
  'netMaxGapMs','parseMaxMs','commandMaxMs','probeMaxMs'];
const histogram = () => new Uint32Array(1002);
const fresh = time => Object.assign({time,minScale:1},Object.fromEntries([...sums,...maxima].map(k=>[k,0])));
export function createPerformanceRecorder() {
  let matchId=null,viewerId=null,settings={},last=null,lastLoad=-Infinity,width=30,periods=[],total=fresh(0),hist=histogram();
  let lastState=null,clientRunId='',sequence=0;
  function period(elapsed) {
    const time=Math.max(0,Number(elapsed)||0);
    while(time>=width*LIMIT) {
      const merged=[];
      for(let i=0;i<periods.length;i++) {
        if(i%2===0) merged.push({...periods[i]});
        else {
          const dest=merged[merged.length-1],src=periods[i];
          for(const key of sums) dest[key]+=src[key];
          for(const key of maxima) dest[key]=Math.max(dest[key],src[key]);
          dest.minScale=Math.min(dest.minScale,src.minScale);
        }
      }
      periods=merged;width*=2;
    }
    const index=Math.floor(time/width);
    while(periods.length<=index)periods.push(fresh(periods.length*width));
    return periods[index];
  }
  return {
    pause() {last=null;lastState=null;},
    start(id,viewer,quality={}) {matchId=id;viewerId=viewer;settings={...quality};last=null;lastState=null;lastLoad=-Infinity;width=30;periods=[];total=fresh(0);hist=histogram();sequence=0;
      clientRunId=globalThis.crypto?.randomUUID?.() || Date.now().toString(36)+'-'+Math.random().toString(36).slice(2);},
    received(timestamp,elapsed,parseMs) {
      if(!matchId)return;
      for(const row of [total,period(elapsed)]) {
        row.netMessages++;row.parseMs+=Math.max(0,parseMs);row.parseMaxMs=Math.max(row.parseMaxMs,parseMs);
        if(lastState!==null) {const gap=Math.max(0,timestamp-lastState);row.netGapSamples++;row.netGapMs+=gap;row.netMaxGapMs=Math.max(row.netMaxGapMs,gap);if(gap>500)row.netOver500++;}
      }
      lastState=timestamp;
    },
    network(kind,ms,ok,elapsed) {
      if(!matchId||!['command','probe','reconnect'].includes(kind))return;
      for(const row of [total,period(elapsed)]) {
        if(kind==='reconnect') {row.reconnects++;continue;}
        if(!ok) {row[kind+'Failures']++;continue;}
        row[kind+'Samples']++;row[kind+'Ms']+=Math.max(0,ms);row[kind+'MaxMs']=Math.max(row[kind+'MaxMs'],ms);
      }
    },
    frame(timestamp,active,elapsed) {
      if(!matchId||!active) {last=null;return;}
      const previous=last;last=timestamp;
      if(previous===null||timestamp<=previous)return;
      const ms=timestamp-previous;
      hist[Math.min(1001,Math.ceil(ms))]++;
      for(const row of [total,period(elapsed)]) {
        row.frames++;row.ms+=ms;row.maxMs=Math.max(row.maxMs,ms);
        if(ms>50)row.over50++;
        if(ms>100)row.over100++;
      }
    },
    load(timestamp,elapsed,stats,scale) {
      if(!matchId||timestamp-lastLoad<1000)return;
      lastLoad=timestamp;
      for(const row of [total,period(elapsed)]) {
        row.loadSamples++;
        for(const [key,source] of [['maxUnits','renderedUnits'],['maxDrawCalls','drawCalls'],['maxTriangles','triangles'],
          ['maxParticles','particles'],['maxGeometries','geometries'],['maxTextures','textures']]) row[key]=Math.max(row[key],Number(stats[source])||0);
        row.minScale=Math.min(row.minScale,scale);
      }
    },
    snapshot(id,viewer,detail=true) {
      if(id!==matchId||viewer!==viewerId||!total.frames)return null;
      let sum=0,p95=0;
      for(let i=0;i<hist.length;i++){sum+=hist[i];if(sum>=Math.ceil(total.frames*.95)){p95=i;break;}}
      return {version:1,matchId,viewerId,clientRunId,sequence:++sequence,settings:{...settings},interval:width,
        ...total,averageFps:1000*total.frames/total.ms,p95Ms:p95,p95Overflow:p95===1001,
        full:detail,periods:detail?periods.map(p=>({...p,averageFps:p.ms?1000*p.frames/p.ms:0})):[]};
    }
  };
}
