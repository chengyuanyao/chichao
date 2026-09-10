import * as THREE from './vendor/three.module.min.js';

// Deterministic, authored micro-relief. These are non-color data maps, not a
// brightness-to-normal conversion of the albedo photograph. Baked once per renderer.
export function surfaceHeight(kind,u,v) {
  const wave=(x)=>Math.sin(x*Math.PI*2);
  if(kind===0) return .018*wave(u*31)*wave(v*27)+.035*Math.exp(-Math.pow(wave(v*5+u*.1)*18,2));
  if(kind===1) return .10*wave(u*7)*wave(v*9)+.025*wave(u*29+v*23);
  if(kind===2) return .065*wave(u*36)+.065*wave(v*36)+.018*wave(u*18)*wave(v*18);
  const row=Math.floor(v*15),x=((u*18+(row%2)*.5)%1)-.5,y=(v*15)%1-.5;
  return .24*Math.max(0,1-x*x*3.7-y*y*3.5);
}
export function bakeRiverSurfaceData(tile=256) {
  const size=tile*2,normal=new Uint8Array(size*size*4),orm=new Uint8Array(size*size*4);
  const wrap=v=>((v%1)+1)%1;
  for(let kind=0;kind<4;kind++) for(let y=0;y<tile;y++) for(let x=0;x<tile;x++) {
    const u=x/tile,v=y/tile,d=1/tile,h=surfaceHeight(kind,u,v);
    const dx=(surfaceHeight(kind,wrap(u+d),v)-surfaceHeight(kind,wrap(u-d),v))*1.2;
    const dy=(surfaceHeight(kind,u,wrap(v+d))-surfaceHeight(kind,u,wrap(v-d)))*1.2;
    const len=Math.hypot(dx,dy,1),i=((y+Math.floor(kind/2)*tile)*size+x+(kind%2)*tile)*4;
    normal.set([Math.round((-dx/len*.5+.5)*255),Math.round((-dy/len*.5+.5)*255),Math.round((1/len*.5+.5)*255),255],i);
    const rough=[.49,.88,.93,.66][kind]+h*.22;
    orm.set([Math.round((.91+Math.min(.09,Math.max(-.1,h)*.3))*255),Math.round(Math.min(1,rough)*255),kind===0?220:0,255],i);
  }
  return {size,normal,orm};
}
export function createRiverSurfaceMaps(color) {
  const data=bakeRiverSurfaceData();
  const make=(bytes)=>{
    const t=new THREE.DataTexture(bytes,data.size,data.size,THREE.RGBAFormat);
    t.colorSpace=THREE.NoColorSpace;t.magFilter=THREE.LinearFilter;t.minFilter=THREE.LinearMipmapLinearFilter;
    t.generateMipmaps=true;t.needsUpdate=true;return t;
  };
  return {color,normal:make(data.normal),orm:make(data.orm)};
}

export function createRiverEnvironment(renderer) {
  // Static overcast sky/earth light probe. PMREM is generated once, not each frame.
  const width=128,height=64,pixels=new Float32Array(width*height*4);
  for(let y=0;y<height;y++) for(let x=0;x<width;x++) {
    const v=y/(height-1),sky=v<.5,k=sky?v*2:(v-.5)*2;
    const zenith=[.29,.43,.61],horizon=[.72,.77,.78],earth=[.12,.14,.09];
    const a=sky?zenith:horizon,b=sky?horizon:earth,i=(y*width+x)*4;
    for(let c=0;c<3;c++) pixels[i+c]=a[c]*(1-k)+b[c]*k;
    pixels[i+3]=1;
  }
  const texture=new THREE.DataTexture(pixels,width,height,THREE.RGBAFormat,THREE.FloatType);
  texture.mapping=THREE.EquirectangularReflectionMapping;texture.needsUpdate=true;
  const pmrem=new THREE.PMREMGenerator(renderer),target=pmrem.fromEquirectangular(texture);
  pmrem.dispose();texture.dispose();return target;
}

export function applyRiverPBR(material,maps) {
  material.normalMap=maps.normal;material.normalScale.set(.72,.72);
  const before=material.onBeforeCompile,key=material.customProgramCacheKey.bind(material);
  material.onBeforeCompile=function(shader,...args) {
    before.call(this,shader,...args);
    shader.uniforms.uArmySurface.value=maps.color;
    shader.uniforms.uRiverORM={value:maps.orm};
    shader.vertexShader='varying vec2 vRiverUv;\nvarying vec3 vRiverLocalNormal;\n'+shader.vertexShader;
    shader.vertexShader=shader.vertexShader.replace('#include <begin_vertex>','#include <begin_vertex>\nvRiverUv=uv;vRiverLocalNormal=normal;');
    shader.fragmentShader='varying vec2 vRiverUv;\nvarying vec3 vRiverLocalNormal;\nuniform sampler2D uRiverORM;\n'+shader.fragmentShader;
    shader.fragmentShader=shader.fragmentShader
      // Authored RGB swatches are display/sRGB colors; Three's light transport is
      // linear. Team instance colors have already been decoded by THREE.Color.
      .replace('diffuseColor.rgb = mix(vOwnColor, diffuseColor.rgb, vTeamMix);',
        'vec3 riverOwn=max(max(vOwnColor.r,vOwnColor.g),vOwnColor.b)>1.0?vOwnColor:pow(max(vOwnColor,vec3(0.0)),vec3(2.2));\n diffuseColor.rgb = mix(riverOwn, diffuseColor.rgb, vTeamMix);')
      .replace('float gSurfaceLum = 0.5;',`float gSurfaceLum = 0.5;
        float riverKind=clamp(floor(gMode+0.01),0.0,3.0);
        vec2 riverTile=vec2(mod(riverKind,2.0),1.0-floor(riverKind/2.0));
        vec3 riverAxis=abs(normalize(vRiverLocalNormal));
        vec2 riverSurfaceUv=riverAxis.y>max(riverAxis.x,riverAxis.z)?vArmyLocal.xz:
          (riverAxis.x>riverAxis.z?vArmyLocal.zy:vArmyLocal.xy);
        riverSurfaceUv*=gMode>1.5?0.055:0.028;
        vec2 riverUV=(riverTile+0.02+fract(riverSurfaceUv)*0.96)*0.5;
        vec4 riverORM=texture2D(uRiverORM,vec2(riverUV.x,1.0-riverUV.y));`)
      .replace('vec2 gAtlasUv = vec2(mix(0.01, 0.51, gAtlasSide) + gMirror.x * 0.48, 0.01 + gMirror.y * 0.98);','vec2 gAtlasUv = riverUV;')
      .replace('float gRelief = mix(0.62, 1.42, smoothstep(0.17, 0.60, gSurfaceLum));','float gRelief = mix(0.48, 1.24, smoothstep(0.22, 0.78, gSurfaceLum));')
      .replace('#include <roughnessmap_fragment>','#include <roughnessmap_fragment>\nroughnessFactor=gMode>3.5?0.26:clamp(riverORM.g,0.24,0.96);')
      .replace('#include <metalnessmap_fragment>','#include <metalnessmap_fragment>\nmetalnessFactor=gMode<0.5?riverORM.b*smoothstep(0.30,0.62,max(max(vOwnColor.r,vOwnColor.g),vOwnColor.b))*(1.0-vTeamMix*0.96):0.0;')
      // Disable the previous albedo-derived micro-normal for sample PBR only.
      .replace('gBumpScale * gDetailFade * gGrad','0.0 * gDetailFade * gGrad')
      .replace('#include <normal_fragment_maps>',`vec3 riverN=texture2D(normalMap,vec2(riverUV.x,1.0-riverUV.y)).xyz*2.0-1.0;
        riverN.xy*=normalScale*(1.0-smoothstep(800.0,1800.0,length(vViewPosition)));
        mat3 riverTBN=getTangentFrame(-vViewPosition,normal,riverSurfaceUv);
        normal=normalize(riverTBN*normalize(riverN));
        float riverDirt=(1.0-smoothstep(1.0,12.0,vArmyLocal.y))*(0.10+0.08*sin(vArmyLocal.x*0.47+vArmyLocal.z*0.73));
        diffuseColor.rgb*=riverORM.r*mix(vec3(1.0),vec3(0.46,0.38,0.28),riverDirt);`);
  };
  material.customProgramCacheKey=()=>key()+'-river-pbr-v2';return material;
}

export function applyRiverGround(material) {
  const before=material.onBeforeCompile,key=material.customProgramCacheKey.bind(material);
  material.onBeforeCompile=function(shader,...args) {
    before.call(this,shader,...args);
    shader.fragmentShader=shader.fragmentShader.replace('diffuseColor.rgb *= tdSurface;',`
      float riverWet=(1.0-smoothstep(-22.0,6.0,vFogWorld.y))*(1.0-tdStone*0.5);
      float riverGravel=smoothstep(0.40,0.64,fmNoise(tdWorld*0.095));
      tdSurface=mix(tdSurface,tdSoil*vec3(0.79,0.87,0.92),riverWet*0.68);
      tdSurface=mix(tdSurface,tdRock*vec3(0.94,0.93,0.88),riverWet*riverGravel*0.27);
      diffuseColor.rgb*=tdSurface;
    `);
  };
  material.customProgramCacheKey=()=>key()+'-river-wet-bank-v1';return material;
}
