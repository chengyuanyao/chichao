import { FEEDBACK_LIMITS, weaponFamily } from './battle_feedback.js';
import { warmAssetTasks } from './asset_warmup.js';

// Cached, locally synthesized samples: no downloads, microphone or audio assets.
const PROFILES={
  rifle:[.13,150,.82,42],cannon:[.32,92,.68,29],heavy:[.60,63,.78,22],
  electric:[.26,710,.19,140],arcane:[.38,440,.10,880],ice:[.30,1680,.33,940],
  arcaneHeavy:[.65,170,.30,510],melee:[.14,220,.68,74],
  explosion:[.70,70,.90,24],magicExplosion:[.75,125,.48,370],
  select:[.055,520,0,510],move:[.08,260,0,320],attack:[.11,160,.12,68],
  confirm:[.12,680,0,880],repair:[.14,740,.04,990],cancel:[.13,330,0,150],
  error:[.18,110,.08,88],start:[.38,380,0,760],complete:[.30,600,0,1200],promote:[.46,523,0,1046]
};

export function createBattleAudio(context) {
  const cache=new Map(),voices=[],cooldowns=new Map();
  let disposed=false,warmPromise=null;
  const master=context.createGain(),limiter=context.createDynamicsCompressor();
  master.gain.value=.26;
  limiter.threshold.value=-14;limiter.knee.value=12;limiter.ratio.value=5;
  limiter.attack.value=.004;limiter.release.value=.14;
  master.connect(limiter);limiter.connect(context.destination);
  function sample(key) {
    if(cache.has(key)) return cache.get(key);
    const [duration,start,noise,end]=PROFILES[key]||PROFILES.rifle;
    const buffer=context.createBuffer(1,Math.ceil(duration*context.sampleRate),context.sampleRate);
    const values=buffer.getChannelData(0);
    let phase=0,low=0,seed=73421;
    for(let i=0;i<values.length;i++) {
      const t=i/context.sampleRate,p=t/duration;
      seed=(Math.imul(seed,1664525)+1013904223)>>>0;
      const white=seed/2147483648-1;low+=.14*(white-low);
      const frequency=start*Math.pow(end/start,p);
      phase+=frequency*2*Math.PI/context.sampleRate;
      const harmonic=Math.sin(phase)+.28*Math.sin(phase*2.013)+.12*Math.sin(phase*3.97);
      const attack=Math.min(1,t/.003),envelope=Math.exp(-p*(noise>.5?7:5))*(1-p);
      const texture=key==='ice'?white-low:low*2.8+white*.12;
      values[i]=Math.tanh(((1-noise)*harmonic+noise*texture)*attack*envelope)*.72;
    }
    cache.set(key,buffer);return buffer;
  }
  function stopVoice(voice) {
    if(voice.closed) return;
    voice.closed=true;
    const i=voices.indexOf(voice);if(i>=0) voices.splice(i,1);
    try {voice.source.stop();} catch (_) {}
    voice.source.disconnect();voice.gain.disconnect();if(voice.pan) voice.pan.disconnect();
  }
  function play(key,volume,pan=0,priority=1,combat=true) {
    if(context.state!=='running'||volume<.001) return false;
    const now=context.currentTime;
    const cooldown=combat?(priority>=3?.16:.095):.04;
    if(now-(cooldowns.get(key)??-Infinity)<cooldown) return false;
    const pool=combat?voices.filter(v=>v.combat):voices;
    const full=voices.length>=FEEDBACK_LIMITS.voices || (combat&&pool.length>=FEEDBACK_LIMITS.combatVoices);
    if(full) {
      const candidate=pool.filter(v=>v.priority<priority).sort((a,b)=>a.priority-b.priority||a.at-b.at)[0];
      if(!candidate) return false;
      stopVoice(candidate);
    }
    const source=context.createBufferSource(),gain=context.createGain();
    const stereo=context.createStereoPanner?context.createStereoPanner():null;
    source.buffer=sample(key);source.playbackRate.value=combat?.97+Math.random()*.06:1;
    gain.gain.value=Math.min(1,volume);
    source.connect(gain);if(stereo) {gain.connect(stereo);stereo.pan.value=pan;stereo.connect(master);} else gain.connect(master);
    const voice={source,gain,pan:stereo,combat,priority,at:now};voices.push(voice);
    source.onended=()=>stopVoice(voice);cooldowns.set(key,now);source.start(now);return true;
  }
  return {
    prewarm() {
      if(disposed) return Promise.resolve(false);
      if(!warmPromise) warmPromise=warmAssetTasks(Object.keys(PROFILES).map(key=>()=>sample(key)),()=>disposed);
      return warmPromise;
    },
    ui(type,volume=1) {return PROFILES[type]?play(type,volume,0,5,false):false;},
    events(events,view,volume=1) {
      const radius=Math.max(600,(view.width||1280)/Math.max(.2,view.zoom||1)*.9);
      const cues=[];
      for(const fx of events) {
        if(!['muzzle','impact','explosion','blast'].includes(fx.type)) continue;
        const distance=Math.hypot(fx.x-view.x,fx.y-view.y);
        if(distance>radius) continue;
        const family=weaponFamily(fx.kind),death=fx.type==='explosion'||fx.type==='blast';
        const magic=fx.faction==='magic'||fx.kind==='hexling';
        const key=death?(magic?'magicExplosion':'explosion'):family;
        const priority=death?3:(['heavy','arcaneHeavy'].includes(family)?2:1);
        const yaw=view.yaw||0,side=(fx.x-view.x)*Math.cos(yaw)+(fx.y-view.y)*Math.sin(yaw);
        cues.push({key,priority,distance,pan:Math.max(-.85,Math.min(.85,side/radius)),
          gain:volume*(1-distance/radius)**2*(fx.type==='impact'?.42:.8)});
      }
      cues.sort((a,b)=>b.priority-a.priority||a.distance-b.distance);
      let count=0;for(const cue of cues) {
        if(play(cue.key,cue.gain,cue.pan,cue.priority)&&++count>=5) break;
      }
      return count;
    },
    clear() {for(const voice of [...voices]) stopVoice(voice);cooldowns.clear();},
    stats() {return {voices:voices.length,combatVoices:voices.filter(v=>v.combat).length,cachedSamples:cache.size};},
    dispose() {disposed=true;this.clear();master.disconnect();limiter.disconnect();cache.clear();}
  };
}
