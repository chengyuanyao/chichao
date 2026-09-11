// Presentation policies shared by rendering and regression tests.
export const DEBRIS_LIMIT=28, COLLAPSE_LIMIT=6, COLLAPSE_SECONDS=.85;
const buildings=new Set(['hq','power','refinery','barracks','factory','repair','turret','missile',
  'mhq','mpower','mrefinery','mtemple','mcircle','mspring','mtower']);
export function wreckFamily(kind) {
  if(buildings.has(kind)) return 'rubble';
  if(['dragon','golem','warden','colossus','comet','mharvester','mmcv'].includes(kind)) return 'arcane';
  return 'vehicle';
}
export function collapsePose(age) {
  const t=Math.max(0,Math.min(1,age/COLLAPSE_SECONDS));
  return {height:1,progress:t,done:t>=1};
}
// All pieces stay in the original merged draw. Uniform zero is the intact path;
// the same prewarmed program handles death without shader compilation or cloning.
export function applyBuildingCollapse(material) {
  const before=material.onBeforeCompile,key=material.customProgramCacheKey.bind(material);
  const progress={value:0};material.userData.collapseProgress=progress;
  material.onBeforeCompile=function(shader,...args) {
    before.call(this,shader,...args);
    shader.uniforms.uCollapseProgress=progress;
    shader.vertexShader=`attribute vec4 aBreak;
      uniform float uCollapseProgress;
      mat3 breakRotation() {
        float seed=fract(dot(aBreak.xyz,vec3(.173,.317,.231)));
        float t=max(0.0,uCollapseProgress-seed*.14);
        float angle=t*t*(seed<.5?-1.0:1.0)*1.8;
        float c=cos(angle),s=sin(angle);
        return mat3(c,s,0.0,-s,c,0.0,0.0,0.0,1.0);
      }
    `+shader.vertexShader;
    shader.vertexShader=shader.vertexShader
      .replace('#include <beginnormal_vertex>',`#include <beginnormal_vertex>
        if(uCollapseProgress>0.0 && aBreak.w>=0.0) objectNormal=breakRotation()*objectNormal;`)
      .replace('#include <begin_vertex>',`#include <begin_vertex>
        if(uCollapseProgress>0.0 && aBreak.w>=0.0) {
          float seed=fract(dot(aBreak.xyz,vec3(.173,.317,.231)));
          float t=max(0.0,uCollapseProgress-seed*.14);
          vec3 origin=aBreak.xyz;
          transformed=breakRotation()*(transformed-origin)+origin;
          vec2 outward=normalize(origin.xz+vec2(.31,.73));
          transformed.xz+=outward*t*t*(3.0+aBreak.w*.3);
          // Gravity accelerates; pieces retain thickness instead of scaling flat.
          transformed.y-=min(max(0.0,origin.y-aBreak.w*.2),180.0*t*t);
          transformed.y-=max(0.0,t-.72)*aBreak.w;
        }`);
  };
  material.customProgramCacheKey=()=>key()+'-building-break-v1';
  return material;
}
export function suspensionSlope(front,back,size) {
  return Math.max(-.085,Math.min(.085,Math.atan2(front-back,Math.max(12,size))));
}
