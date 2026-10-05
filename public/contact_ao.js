// 只复用主场景深度，无几何重画、随机噪声或历史帧残影。半分辨率求遮蔽，按深度上采样。
export const CONTACT_AO_FRAGMENT = `
uniform sampler2D tDepth;
uniform mat4 uProjectionInverse;
uniform mat4 uProjection;
uniform vec2 uSceneResolution;
uniform float uRadius;
varying vec2 vUv;
vec3 viewPosition(vec2 uv) {
  float depth=texture2D(tDepth,uv).r;
  vec4 p=uProjectionInverse*vec4(uv*2.0-1.0,depth*2.0-1.0,1.0);
  return p.xyz/p.w;
}
void main() {
  if(texture2D(tDepth,vUv).r>=0.99999) {gl_FragColor=vec4(1.0,0.0,0.0,1.0);return;}
  vec3 p=viewPosition(vUv);
  vec2 pixel=1.0/uSceneResolution;
  vec3 l=viewPosition(vUv-vec2(pixel.x,0.0)),r=viewPosition(vUv+vec2(pixel.x,0.0));
  vec3 b=viewPosition(vUv-vec2(0.0,pixel.y)),t=viewPosition(vUv+vec2(0.0,pixel.y));
  // 在轮廓处选同一表面一侧，避免把天空/远处地面当成法线。
  vec3 dx=abs(l.z-p.z)<abs(r.z-p.z)?p-l:r-p;
  vec3 dy=abs(b.z-p.z)<abs(t.z-p.z)?p-b:t-p;
  vec3 normal=cross(dx,dy);
  normal*=inversesqrt(max(dot(normal,normal),0.000001));
  vec2 uvRadius=vec2(uProjection[0][0],uProjection[1][1])*uRadius/max(-p.z,1.0)*0.5;
  float occlusion=0.0;
  for(int i=0;i<8;i++) {
    float angle=float(i)*2.39996323+0.13;
    float ring=0.3+0.7*(float(i)+1.0)/8.0;
    vec2 uv=vUv+vec2(cos(angle),sin(angle))*uvRadius*ring;
    if(any(lessThan(uv,vec2(0.0)))||any(greaterThan(uv,vec2(1.0)))||texture2D(tDepth,uv).r>=0.99999) continue;
    vec3 delta=viewPosition(uv)-p;
    float distance=max(length(delta),0.001);
    float horizon=max(dot(normal,delta)/distance-0.08,0.0);
    occlusion+=horizon*(1.0-smoothstep(uRadius*0.25,uRadius,distance));
  }
  gl_FragColor=vec4(clamp(1.0-occlusion*1.9/8.0,0.55,1.0),-p.z,0.0,1.0);
}
`;

export const CONTACT_AO_COMPOSITE = `
uniform sampler2D tContactAO;
uniform sampler2D tSceneDepth;
uniform vec2 uAOResolution;
uniform vec2 uCameraRange;
uniform float uContactAO;
float contactVisibility(vec2 uv) {
  float depth=texture2D(tSceneDepth,uv).r;
  if(depth>=0.99999) return 1.0;
  float viewDepth=uCameraRange.x*uCameraRange.y/(uCameraRange.y-depth*(uCameraRange.y-uCameraRange.x));
  vec2 texel=uv*uAOResolution-0.5,base=floor(texel),fraction=fract(texel);
  float sum=0.0,weightSum=0.0;
  for(int y=0;y<2;y++) for(int x=0;x<2;x++) {
    vec2 corner=vec2(float(x),float(y));
    vec2 at=(base+corner+0.5)/uAOResolution;
    vec2 ao=texture2D(tContactAO,at).rg;
    vec2 bilinear=mix(1.0-fraction,fraction,corner);
    float weight=bilinear.x*bilinear.y*exp(-abs(ao.y-viewDepth)/max(2.0,viewDepth*0.004));
    sum+=ao.x*weight;weightSum+=weight;
  }
  return weightSum>0.001?sum/weightSum:1.0;
}
`;
