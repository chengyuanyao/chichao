import * as THREE from './vendor/three.module.min.js';

// Four shared, padded billow silhouettes. Bake once, sample once per fragment;
// no per-frame noise octaves or external texture downloads.
export function bakeBlastSurface(tile=128) {
  const size=tile*2,data=new Uint8Array(size*size*4);
  const fract=x=>x-Math.floor(x),mix=(a,b,t)=>a+(b-a)*t;
  const hash=(x,y,s)=>fract(Math.sin(x*127.1+y*311.7+s*73.9)*43758.5453);
  function noise(x,y,s) {
    const ix=Math.floor(x),iy=Math.floor(y);let u=fract(x),v=fract(y);
    u=u*u*(3-2*u);v=v*v*(3-2*v);
    return mix(mix(hash(ix,iy,s),hash(ix+1,iy,s),u),mix(hash(ix,iy+1,s),hash(ix+1,iy+1,s),u),v);
  }
  function field(u,v,s) {
    const x=(u-.5)*2,y=(v-.5)*2,r=Math.hypot(x,y);
    const n=noise(u*6,v*6,s)*.58+noise(u*15,v*15,s)*.29+noise(u*37,v*37,s)*.13;
    const lobes=.10*Math.sin(Math.atan2(y,x)*5+s)+.06*Math.cos(Math.atan2(y,x)*9-s);
    const edge=Math.max(0,Math.min(1,(.80+lobes-r)*5));
    return edge*Math.max(0,Math.min(1,(n-.22)*1.75));
  }
  for(let s=0;s<4;s++) for(let y=0;y<tile;y++) for(let x=0;x<tile;x++) {
    const u=x/(tile-1),v=y/(tile-1),d=field(u,v,s);
    const slope=field(u-.012,v-.016,s)-field(u+.012,v+.016,s);
    const light=Math.max(.1,Math.min(1,.48+slope*2.4));
    const i=((y+Math.floor(s/2)*tile)*size+x+(s%2)*tile)*4;
    data.set([Math.round(d*255),Math.round(light*255),0,255],i);
  }
  return {size,data};
}

export function createBlastSurface() {
  const {size,data}=bakeBlastSurface();
  const texture=new THREE.DataTexture(data,size,size,THREE.RGBAFormat);
  texture.colorSpace=THREE.NoColorSpace;
  texture.magFilter=THREE.LinearFilter;texture.minFilter=THREE.LinearMipmapLinearFilter;
  texture.generateMipmaps=true;texture.needsUpdate=true;return texture;
}

export const BLAST_FRAGMENT = `
varying vec3 vColor;
varying float vAlpha;
varying float vSeed;
varying float vAge;
varying float vSize;
varying vec4 vFlowRotation;
varying vec2 vTileOffset;
uniform float uHot;
uniform sampler2D uBlastSurface;
void main() {
  vec2 p=gl_PointCoord-0.5;
  // Small sparks and muzzle transients need no billow atlas work. Reserve it
  // for the large fireballs where the silhouette detail is actually readable.
  if(uHot>0.5 && vSize<=18.0) {
    float shape=exp(-dot(p,p)*40.0),alpha=shape*vAlpha*1.5;
    if(alpha<0.012) discard;
    float heat=(1.0-smoothstep(0.05,0.8,vAge))*shape;
    float energy=step(vColor.r*1.05,max(vColor.g,vColor.b));
    vec3 cool=mix(vec3(.70,.20,.055),vec3(.45),energy);
    gl_FragColor=vec4(vColor*mix(cool,vec3(1.15,1.0,.85),heat)*(mix(.35,1.4,heat)+1.0),alpha);
    return;
  }
  mat2 turn=mat2(vFlowRotation.x,-vFlowRotation.y,vFlowRotation.y,vFlowRotation.x);
  vec2 uv=turn*p+0.5;
  vec2 flow=vFlowRotation.zw;
  vec2 sampleUv=clamp(uv+flow,vec2(0.015),vec2(0.985));
  vec2 billow=texture2D(uBlastSurface,(vTileOffset+sampleUv)*0.5).rg;
  float shape=billow.r*mix(0.65,1.35,billow.r);
  float small=1.0-smoothstep(7.0,12.0,vSize);
  float spark=exp(-dot(p,p)*40.0);
  shape=mix(shape,spark,small*uHot);
  float alpha=shape*vAlpha*(uHot>0.5?1.5:1.8);
  if(alpha<0.012) discard;
  vec3 smoke=vColor*mix(0.48,1.55,billow.g);
  // White/yellow heat collapses into orange embers; smoke is a separate,
  // normally blended layer, never an additive grey ball.
  float heat=(1.0-smoothstep(0.05,0.8,vAge))*shape;
  float energy=step(vColor.r*1.05,max(vColor.g,vColor.b));
  vec3 coolTint=mix(vec3(0.70,0.20,0.055),vec3(0.45),energy);
  vec3 fire=vColor*mix(coolTint,vec3(1.15,1.0,0.85),heat);
  fire*=mix(0.35,1.4,heat)+small;
  gl_FragColor=vec4(mix(smoke,fire,uHot),alpha);
}`;
