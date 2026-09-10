// Presentation only. Never changes health, orders, collision or weapon ranges.
export const FEEDBACK_LIMITS = Object.freeze({particles:400, wrecks:28, wreckSeconds:12, voices:12, combatVoices:8});
export const TRACK_SPANS = Object.freeze({tank:21.2,harvester:25.2,artillery:23.2,
  tank_destroyer:20.2,v3:27.2,prism:19.2,mcv:31.2,overlord:25.2,overlord_v1:25.2});
export const RECOIL = Object.freeze({tank:2.6,scout:1.0,artillery:4.2,tank_destroyer:3.4,
  overlord:3.4,overlord_v1:3.4});
export const MUZZLE_POINTS = Object.freeze({dragon:[31,14],overlord_v2:[17,36],
  mage:[12,9],frost:[12,9],oracle:[13,11],rifle:[12,9],rocket:[8,11],sniper:[15,10],
  tesla:[12,9],prism:[4,32],v3:[1,52],golem:[8,16],warden:[18,13],colossus:[21,27],comet:[9,27]});

export function recoilDistance(kind, age) {
  if (!Number.isFinite(age) || age < 0 || age >= .34) return 0;
  const envelope = age < .045 ? age/.045 : Math.pow(1-(age-.045)/.295,2);
  return (RECOIL[kind] || 0)*envelope;
}

export function advanceTracks(vis, dx, dy, turn, scale=1) {
  const span = TRACK_SPANS[vis.visualKind || vis.unit.kind];
  if (!span) return;
  // Cumulative local travel: stopped tracks stay still; turning counter-rotates.
  const travel = (dx*Math.cos(vis.dir)+dy*Math.sin(vis.dir))/scale;
  if (Math.abs(travel)>80 || Math.abs(turn)>1.2) return; // reconnect/teleport, not wheel motion
  const wrap = n => ((n%360)+360)%360;
  vis.trackLeft=wrap((vis.trackLeft||0)+travel-turn*span*.5);
  vis.trackRight=wrap((vis.trackRight||0)+travel+turn*span*.5);
}

export function conditionFromHealth(hp,maxHp) {
  return maxHp>0 ? Math.max(0,Math.min(1,(.78-hp/maxHp)/.78)) : 0;
}

export function effectDensity(distance) {
  return distance>1900 ? .28 : distance>1100 ? .55 : 1;
}

export function weaponFamily(kind) {
  if (['arcane','iris','crystal'].includes(kind)) return 'arcane';
  if (['frost'].includes(kind)) return 'ice';
  if (['fireball','meteor','comet','hexling'].includes(kind)) return 'arcaneHeavy';
  if (['tesla','laser','plasma','plasmalance'].includes(kind)) return 'electric';
  if (['siege','missile','boulder'].includes(kind)) return 'heavy';
  if (['shell','ap','rocket'].includes(kind)) return 'cannon';
  if (['bite','claw','dog_arcane'].includes(kind)) return 'melee';
  return 'rifle';
}

// Wrapping the existing shared surface shader preserves atlas/AO/shadow work.
// Only one per-instance vec4 is added; tracks use the existing merged mesh.
export function applyBattleMaterial(material) {
  const previous=material.onBeforeCompile;
  const previousKey=material.customProgramCacheKey.bind(material);
  const condition={value:[0,0]};
  material.userData.battleCondition=condition;
  material.defaultAttributeValues={...material.defaultAttributeValues,aFeedback:[0,0,0,0],aTread:[0,0]};
  material.onBeforeCompile=function(shader,...args) {
    previous.call(this,shader,...args);
    shader.uniforms.uBattleCondition=condition;
    shader.vertexShader='attribute vec2 aTread;\nuniform vec2 uBattleCondition;\nvarying vec2 vTread;\nvarying vec4 vFeedback;\n#ifdef USE_INSTANCING\nattribute vec4 aFeedback;\n#endif\n'+shader.vertexShader;
    shader.vertexShader=shader.vertexShader.replace('#include <begin_vertex>',
      '#include <begin_vertex>\nvTread=aTread;\nvFeedback=vec4(0.0,0.0,uBattleCondition);\n#ifdef USE_INSTANCING\nvFeedback=aFeedback;\n#endif');
    shader.fragmentShader='varying vec2 vTread;\nvarying vec4 vFeedback;\n'+shader.fragmentShader;
    shader.fragmentShader=shader.fragmentShader.replace('#include <normal_fragment_begin>',
      '// Battle surface: narrow animated rubber tread grooves; no geometry displacement.\n'+
      'if(abs(vTread.x)>0.5) {\n'+
      ' float phase=(vTread.y-mix(vFeedback.x,vFeedback.y,step(0.0,vTread.x)))/3.6;\n'+
      ' float aa=max(fwidth(phase),0.035);\n'+
      ' float rib=1.0-smoothstep(0.17-aa,0.17+aa,abs(fract(phase)-0.5));\n'+
      ' diffuseColor.rgb*=mix(0.64,1.9,rib);\n}\n'+
      // Keep owner paint and glowing cores legible even at critical health.
      'float wear=vFeedback.w*(1.0-gEmissive)*(1.0-vTeamMix*0.76);\n'+
      'diffuseColor.rgb*=1.0-wear*(0.22+0.38*(1.0-smoothstep(0.24,0.54,gSurfaceLum)));\n'+
      '#include <normal_fragment_begin>');
    shader.fragmentShader=shader.fragmentShader.replace('#include <opaque_fragment>',
      'outgoingLight+=vec3(1.0,0.66,0.30)*vFeedback.z*0.24*(1.0-gEmissive);\n'+
      'outgoingLight+=gBase*vTeamMix*0.045*(1.0-gEmissive);\n#include <opaque_fragment>');
  };
  material.customProgramCacheKey=()=>previousKey()+'-battle-feedback-1';
  return material;
}
