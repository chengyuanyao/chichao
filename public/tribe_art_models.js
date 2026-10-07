import * as THREE from './vendor/three.module.min.js';

// 部落近景原语由 river 管线注入；远景与权威碰撞保持独立。
export const TRIBE_ART_KINDS = new Set(['spear','javelin','slinger','tamer','wolf','spider',
  'scorpion','panda','mammoth','tharvester','tmcv','catapult']);
export const TRIBE_ART_STRUCTURES = new Set(['thq','tspiketower','ttoxtower']);
const SKIN=[.58,.40,.25], WOOD=[.34,.23,.12], EDGE=[.52,.36,.18], BONE=[.80,.74,.58];
const HIDE=[.38,.24,.13], DARK=[.13,.10,.07], FUR=3.25;
const surface=(p,s)=>Object.assign(p,{surf:s});
export const paintTeam=shade=>shade;

export function uprightShell(stations,paint,surf,k) {
  const p=k.organicShell(stations.map(([y,w,x,h])=>[y,w,-x,h]),paint,surf);
  p.matrix.premultiply(new THREE.Matrix4().makeRotationZ(Math.PI/2));
  return p;
}

export function rig(parts,pivot,opts={}) {
  const local=new THREE.Matrix4().makeTranslation(-pivot[0],-pivot[1],-pivot[2]);
  for(const p of parts) p.matrix.premultiply(local);
  return {parts,pivot,axis:'z',side:1,mode:'walk',...opts};
}

function humanoid(kind,k) {
  const {box,cyl,ellipsoid,limb,pyr,torus,organicShell,ROT_X90,ROT_Z90}=k;
  const cloak=kind==='tamer';
  const body=[uprightShell(cloak?
    [[2,4.2,-.8,3],[3,4.5,-.6,3.2],[5,4,-.5,2.8],[7,3.8,-.4,2.6],
      [9,3.5,-.2,2.2],[11,3.3,0,2.2],[13,3,0,2],[14,1.3,0,1.1]]:
    [[7,2,0,1.4],[8,2.5,0,1.9],[9.5,2.8,-.2,2],[11,3,-.3,2.1],
      [12.4,2.8,0,2],[13.3,2.5,.2,1.7],[14,1.1,.2,.8]],cloak?HIDE:SKIN,cloak?2:1,k),
    uprightShell([[14.7,.6,.3,.7],[15.1,1.2,.4,1.2],[16,1.5,.4,1.5],
      [17.1,1.3,.2,1.3],[17.8,.7,.1,.7]],SKIN,1,k),
    surface(torus(1.55,.18,6,10,.2,17,0,BONE,ROT_X90),1),
    surface(box(3.9,3.2,5.3,0,7.3,0,paintTeam(.90)),2)];
  const rigs=[];
  for(const side of [-1,1]) {
    const z=side*1.5;
    rigs.push(rig([surface(limb(.85,.62,0,7,z,.5,3.8,z*1.15,DARK),1),
      surface(limb(.65,.5,.5,3.8,z*1.15,.25,1,z*1.2,SKIN),1),
      surface(box(2.2,1,1.8,.6,.7,z*1.2,HIDE),2)],[0,7,z],{side}));
  }
  if(cloak) {
    body.push(surface(ellipsoid(3,.65,3.5,0,13.5,0,HIDE),FUR));
    for(const side of [-1,1]) {
      body.push(surface(box(.4,10,.6,.8,7,side*3.5,.90),2));
      body.push(surface(limb(.8,.6,0,13,side*2.8,3.5,10,side*3,SKIN),1));
    }
    for(let i=0;i<5;i++) body.push(surface(pyr(.45,3.4+i%2,4,0,19+(i%2)*.3,(i-2)*.65,.90),2));
    body.push(surface(cyl(.28,.35,15,6,5,9,2.5,WOOD),1));
    body.push(organicShell([[4.3,.1,17,.1,2.5],[4.8,1.6,17,1.3,2.5],
      [5.8,1.7,17,1.4,2.5],[6.6,.6,17,.6,2.5]],BONE,1));
    for(const side of [-1,1]) body.push(surface(box(.35,.35,.3,6.2,17.4,2.5+side*.6,[1.2,.64,.18]),1));
  } else if(kind==='javelin') {
    body.push(surface(limb(.8,.6,0,13,2.5,7,13,2.5,SKIN),1));
    body.push(surface(limb(.8,.6,0,13,-2.5,-4,18,-2.5,SKIN),1));
    body.push(surface(limb(.2,.18,-8,20,-2.5,7,22,-2.5,WOOD),1));
    body.push(surface(pyr(.6,2.4,5,8,22,-2.5,BONE,ROT_Z90),1));
    for(let i=0;i<3;i++) {
      body.push(surface(limb(.16,.16,-2,8,i-1,-3,19+i,i-1,WOOD),1));
      body.push(surface(pyr(.35,1.5,4,-3,20+i,i-1,.90),2));
    }
    for(const z of [-1,1]) body.push(surface(box(.2,.35,1.1,1.8,16+z*.3,z*.6,.90),2));
  } else if(kind==='slinger') {
    body.push(surface(limb(.8,.6,0,13,2.5,4,18,3,SKIN),1));
    body.push(surface(limb(.8,.6,0,13,-2.5,4,10,-3,SKIN),1));
    body.push(surface(torus(3,.17,5,12,6,19,3,WOOD,ROT_X90),2));
    body.push(surface(ellipsoid(1.3,1.7,1,1,6,3,HIDE),2));
    body.push(surface(box(2.7,.4,3.1,.2,17.5,0,.90),2));
  } else {
    for(const side of [-1,1]) body.push(surface(limb(.8,.6,0,13,side*2.5,4,10,side*2.2,SKIN),1));
    body.push(surface(limb(.21,.25,-4,8,-2.2,17,12,-2.2,WOOD),1));
    body.push(surface(pyr(.65,3,5,18,12,-2.2,BONE,ROT_Z90),1));
    for(const side of [-1,1]) body.push(surface(pyr(.35,2.2,4,-.4,18,side*.8,.90),2));
    body.push(surface(ellipsoid(2.4,.4,2.8,0,13.1,0,HIDE),FUR));
  }
  return {body,rigs,glow:[]};
}

function quadruped(kind,k) {
  const {box,cyl,ellipsoid,limb,pyr,organicShell,cable,ROT_Z90}=k;
  const mammoth=kind==='mammoth',wolf=kind==='wolf';
  const h=mammoth?10.8:wolf?5.6:8.8,z=mammoth?4:wolf?2:3.2;
  const front=mammoth?8.8:wolf?5.2:8.2,back=mammoth?-9.2:wolf?-4.8:-7.6;
  const coat=wolf?[.31,.25,.18]:mammoth?[.30,.20,.12]:[.37,.27,.17];
  const len=mammoth?18:wolf?10:14,depth=mammoth?9:wolf?3.4:5.6;
  const stations=[];
  for(let i=0;i<(mammoth?11:9);i++) {
    const t=i/(mammoth?10:8),f=Math.sin(t*Math.PI)*.8+.2;
    stations.push([(t*2-1)*len,depth*f,h+depth*.6+Math.sin(t*Math.PI)*1.2,depth*f]);
  }
  const body=[organicShell(stations,coat,FUR)];
  const head=[];
  for(let i=0;i<(wolf?7:mammoth?7:6);i++) {
    const t=i/(wolf||mammoth?6:5),f=.2+.8*Math.sin(t*Math.PI);
    head.push([front+3+t*(wolf?10:8),z*f,h+depth*.75,z*f]);
  }
  body.push(organicShell(head,coat,FUR));
  const rigs=[];
  for(const x of [front,back]) for(const side of [-1,1]) {
    const radius=mammoth?2.2:wolf?.8:1.4;
    rigs.push(rig([surface(limb(radius,radius*.7,x,h,side*z,x+.4,h*.45,side*(z+.7),coat),FUR),
      surface(limb(radius*.7,radius*.55,x+.4,h*.45,side*(z+.7),x+.7,.8,side*(z+.8),DARK),FUR),
      surface(ellipsoid(radius*1.3,.7,radius,x+1,.65,side*(z+.8),DARK),1)],
      [x,h,side*z],{side:x===front?side:-side,amp:mammoth?.22:wolf?.36:.30,...(mammoth?{gain:.30}:{})}));
  }
  body.push(surface(box(len*.9,.55,depth*1.6,0,h+depth*1.6,0,.90),2));
  if(wolf) {
    body.push(surface(ellipsoid(1.6,.9,1.1,17,h+1.7,0,DARK),FUR));
    for(const side of [-1,1]) {
      body.push(surface(ellipsoid(.45,.32,.18,13.4,h+3.8,side*1.8,[.04,.035,.03]),1));
      body.push(surface(pyr(1.1,4,5,12,h+6,side*1.7,DARK),FUR));
      body.push(surface(pyr(.25,1,4,16,h+1.8,side*1.2,BONE),1));
      body.push(surface(box(4.5,.6,.2,2,h+2.5,side*3,.90),2));
    }
    body.push(organicShell([[-17,.1,9,.1],[-15,.9,9,1.5],[-13,1.6,8,1.9],[-11,1.2,7,1.4],[-9,.8,7,1],[-7,.6,7,.8]],coat,FUR));
    for(let i=0;i<5;i++) body.push(surface(pyr(.8,1.6,4,2+i*1.2,h+5.6,0,DARK),FUR));
  } else if(mammoth) {
    for(const side of [-1,1]) {
      body.push(cable([[16,13,side*3.8],[23,8,side*6],[31,10,side*7],[33,16,side*7]],.8,BONE,1));
      body.push(surface(box(4,2,1,22,8.5,side*6,.90),2));
    }
    body.push(organicShell([[15,1.2,13,1.4],[19,1.6,11,1.6],[21,1.4,8,1.4],[22,1.2,5,1.3],
      [23,1,3,1.1],[25,.9,2.6,.9],[27,.65,3,.7],[28,.3,4,.4]],coat,FUR));
    for(const side of [-1,1]) {
      body.push(surface(box(18,2,1,0,27,side*5,WOOD),1));
      for(const x of [-7,7]) body.push(surface(cyl(.5,.7,10,6,x,29,side*5,WOOD),1));
    }
    body.push(surface(box(19,2,14,0,34,0,HIDE),2));
    body.push(surface(box(7,8,.35,3,37,0,.90),2));
    for(let i=0;i<9;i++) for(const side of [-1,1]) body.push(surface(pyr(1,4.5,4,-12+i*3,8,side*6,coat),FUR));
  } else {
    for(const side of [-1,1]) {
      body.push(cable([[13,15,side*2],[16,18,side*3],[17,17,side*5]],.55,BONE,1));
      body.push(surface(box(7,5,4,-2,16,side*6,WOOD),1));
      body.push(surface(box(7.3,.6,4.3,-2,19,side*6,.90),2));
      body.push(surface(ellipsoid(2.3,1.2,1.2,-2,18.8,side*6,[1.3,.72,.14]),1));
    }
  }
  return {body,rigs,glow:[]};
}

function arthropod(kind,k) {
  const {box,limb,pyr,organicShell}=k,spider=kind==='spider';
  const coat=spider?[.28,.20,.15]:[.40,.25,.12];
  const body=[organicShell(spider?[[0,.8,8,1],[3,3,9,3],[5,4,9,4],[8,3,9,3],[10,.7,8,1]]:
    [[-11,1,6,1],[-8,3.6,7,2.5],[-5,4,7,3],[-2,3.2,7,2.4],[1,4,7,3],[4,3.2,7,2.4],[7,3.7,7,2.8],[9,1,7,1]],coat,3),
    surface(box(8,.6,6,spider?-7:0,spider?14:10,0,.90),2)];
  if(spider) body.unshift(organicShell([[-17,.8,8,1],[-14,4,10,4],[-11,6,10,5.7],[-8,7,10,6],
    [-5,6,10,5.6],[-3,4.5,9,4],[-1,3,8,3],[1,2,8,2],[2,.8,8,1]],coat,3));
  const groups=[[],[]];
  for(let i=0;i<4;i++) for(const side of [-1,1]) {
    const x=-8+i*4,p=groups[(i+(side>0?0:1))%2],reach=side*(spider?15:12);
    p.push(surface(limb(.65,.5,x,7,side*3,x-3,12,reach*.72,coat),3));
    p.push(surface(limb(.5,.25,x-3,12,reach*.72,x-5,.8,reach,coat),3));
  }
  const pivot=spider?[.5,7,0]:[-.5,5.5,0];
  const rigs=groups.map((p,i)=>rig(p,pivot,{axis:'y',side:i?1:-1,rate:.5,amp:spider?.16:.12,...(spider?{gain:.30}:{})}));
  for(const side of [-1,1]) {
    body.push(surface(pyr(.7,3,5,10,7,side*1.5,BONE),1));
    if(!spider) {
      body.push(surface(limb(1.2,.9,6,7,side*3,13,7,side*8,coat),3));
      body.push(organicShell([[11,.8,7,1,side*8],[14,2.4,7,2,side*8],[17,2.5,7,2,side*8],[19,.4,7,.5,side*8]],coat,3));
      for(const z of [side*6.7,side*9.3]) body.push(surface(limb(.55,.2,17,7,z,22,7,z, BONE),1));
    }
  }
  if(!spider) {
    const tail=[];
    const points=[[-10.4,6.4,0],[-13,11,0],[-13,17,0],[-9,21,0],[-3,20,0],[1,16,0]];
    for(let i=0;i<5;i++) {
      tail.push(surface(limb(1.2-i*.12,1.1-i*.12,...points[i],...points[i+1],coat),3));
      tail.push(surface(box(1.7,.55,2,points[i+1][0],points[i+1][1],0,.90),2));
    }
    tail.push(surface(pyr(.7,3,5,2,15,0,BONE),1));
    rigs.push(rig(tail,[-10.4,6.4,0],{mode:'strike',swing:-.45,attack:.08,duration:.50}));
  }
  return {body,rigs,glow:[]};
}

export function tribeUnitModel(kind,base,k) {
  if(['spear','javelin','slinger','tamer'].includes(kind)) return humanoid(kind,k);
  if(['wolf','mammoth','tharvester'].includes(kind)) return quadruped(kind,k);
  if(['spider','scorpion'].includes(kind)) return arthropod(kind,k);
  if(kind==='panda') {
    // 圆滚黑白兽 + 肩上竹甲：连续体积替换肚身和头，腿走对角步，前掌单独拍击。
    const {box,cyl,ellipsoid,limb,organicShell,ROT_Z90,MAT}=k;
    const W=MAT.pandaWhite,B=MAT.pandaBlack,C=MAT.pandaCream;
    const BAM=MAT.bamboo,BD=MAT.bambooDark;
    const body=[
      organicShell([[-11,3.4,9.4,3.6],[-7,6.8,10.2,7.0],[-2,7.8,10.6,8.2],
        [3,7.4,10.4,7.8],[7,6.0,11.0,6.2],[10.4,3.2,11.4,3.4]],W,FUR),
      organicShell([[10.2,2.4,11.6,2.6],[12.4,5.2,12.2,5.4],[14.8,5.6,12.0,5.8],
        [16.8,3.8,11.4,4.0],[18.2,1.8,10.8,2.0]],W,FUR),
      surface(ellipsoid(2.6,2.0,2.2,15.4,11.0,0,C),FUR),
      surface(ellipsoid(2.8,2.6,1.8,9.2,13.4,2.6,B),FUR),
      surface(ellipsoid(2.8,2.6,1.8,9.2,13.4,-2.6,B),FUR),
      surface(ellipsoid(2.2,2.8,1.6,8.2,17.4,3.3,B),FUR),
      surface(ellipsoid(2.2,2.8,1.6,8.2,17.4,-3.3,B),FUR),
      surface(ellipsoid(4.8,2.4,5.2,-10.2,10.4,0,W),FUR),
      surface(ellipsoid(2.2,1.4,1.4,-14.0,11.0,0,B),FUR),
      surface(ellipsoid(5.2,.7,6.8,-.2,15.2,0,.90),2),
      surface(cyl(1.3,1.3,9.0,6,2.0,14.4,4.2,BAM,ROT_Z90),1),
      surface(cyl(1.3,1.3,9.0,6,2.0,14.4,-4.2,BAM,ROT_Z90),1),
      surface(cyl(.95,.95,6.8,6,1.2,15.6,3.6,BD,ROT_Z90),1),
      surface(cyl(.95,.95,6.8,6,1.2,15.6,-3.6,BD,ROT_Z90),1),
      surface(box(6.2,.85,9.8,1.4,14.0,0,BAM),1),
      surface(box(7.0,2.2,8.2,-1.6,11.8,0,BD),1),
      surface(box(4.4,.45,3.6,3.6,15.0,4.6,BONE),1),
      surface(box(4.4,.45,3.6,3.6,15.0,-4.6,BONE),1)
    ];
    const left=[],right=[];
    for(const [x,side,bag] of [[5.6,1,left],[-6.0,1,left],[5.6,-1,right],[-6.0,-1,right]]) {
      bag.push(surface(limb(1.7,1.3,x,8.0,side*3.4,x+.2,.7,side*3.4,B),FUR));
      bag.push(surface(ellipsoid(1.6,.7,1.3,x+.3,.65,side*3.4,B),FUR));
    }
    const paw=[
      surface(limb(1.55,1.2,6.4,10.2,4.2,12.6,14.8,6.4,B),FUR),
      surface(ellipsoid(2.2,1.4,2.0,14.2,15.6,6.8,B),FUR)
    ];
    return {body,rigs:[
      rig(left,[5.6,8.0,3.4],{side:1,amp:.28}),
      rig(right,[5.6,8.0,-3.4],{side:-1,amp:.28}),
      rig(paw,[6.4,10.2,4.2],{mode:'strike',swing:.55,attack:.12,duration:.55})
    ],glow:base.glow};
  }
  if(kind==='catapult') {
    const {box,cyl,ellipsoid,limb,armorShell,ROT_X90}=k;
    const body=[armorShell([[-17,7,6,8],[-10,9,6,10],[10,9,6,10],[14,7,6,8]],WOOD,1)];
    for(const side of [-1,1]) for(const x of [-10,10]) body.push(surface(limb(1.4,1.1,x,8,side*7,-2,24,side*7,WOOD),1));
    body.push(surface(cyl(2,2,16,8,-2,13,0,HIDE,ROT_X90),2));
    body.push(surface(box(7,5,.5,1,26,7.5,.90),2));
    const arm=[surface(limb(1.4,1,6,10,0,-4,34,0,EDGE),1),
      surface(ellipsoid(4.8,1.3,4.3,-4,30.4,0,.90),2),surface(ellipsoid(4.2,3.8,4,-4,34,0,[.46,.42,.34]),1)];
    const wheels=[];
    for(const side of [-1,1]) {
      wheels.push(surface(cyl(4,4,3,12,0,4,side*10,WOOD,ROT_X90),1));
      wheels.push(surface(cyl(1.2,1.2,3.4,8,0,4,side*10,BONE,ROT_X90),1));
    }
    return {body,rigs:[rig(arm,[-2,13,0],{mode:'strike',swing:-1.20,attack:.18,duration:2.1}),
      rig(wheels,[0,4,0],{mode:'roll',radius:4})],glow:[]};
  }
  if(kind==='tmcv') {
    const {box,limb,cyl,pyr,organicShell}=k,body=[],legs=[[],[],[],[]];
    for(const side of [-1,1]) {
      body.push(organicShell([[-1,1,10,1,side*6],[2,3,11,3.5,side*6],[6,3.2,11,3.8,side*6],
        [10,3,11,3.4,side*6],[13,2.6,11,3,side*6],[15,2.2,12,2.5,side*6],
        [18,2,12,2.1,side*6],[20,1.5,11,1.6,side*6],[22,.4,11,.6,side*6]],HIDE,FUR));
      for(const x of [6,16]) for(const z of [-1.8,1.8]) {
        const i=(x===6?0:2)+(z>0?0:1);
        legs[i].push(surface(limb(.8,.6,x,7.4,side*6+z,x,.8,side*6+z,HIDE),FUR));
      }
      body.push(surface(limb(.5,.4,0,9,side*6,-14,6,side*9,WOOD),1));
      body.push(surface(pyr(.6,3,5,18,16,side*7,BONE),1));
    }
    body.push(surface(box(22,2,21,-16,5,0,WOOD),1));
    body.push(surface(box(20,9,18,-16,11,0,HIDE),2));
    for(const z of [-5,0,5]) body.push(surface(box(21,.5,1.5,-16,16,z,.90),2));
    body.push(surface(cyl(1,1.4,20,6,-23,17,0,WOOD),1));
    body.push(surface(box(10,8,.5,-21,26,0,.90),2));
    return {body,rigs:legs.map((p,i)=>rig(p,[i<2?6:16,7.4,0],{side:i<2?(i%2?1:-1):(i%2?-1:1),amp:.28})),glow:[]};
  }
  return base;
}

export function tribeStructureDetails(kind,s,k) {
  if(!TRIBE_ART_STRUCTURES.has(kind)) return [];
  const {box,cyl,ellipsoid,limb,pyr,torus,part,ROT_X90,ROT_Z90}=k,parts=[];
  const block=(w,h,d,x,y,z,paint,surf=1)=>parts.push(surface(box(w*s,h*s,d*s,x*s,y*s,z*s,paint),surf));
  const pole=(x,z,h)=>parts.push(surface(cyl(.025*s,.04*s,h*s,6,x*s,h*s/2,z*s,WOOD),1));
  // y 从 0 起的薄夯土地基，由 mergeParts 锚定在地表。
  block(1.9,.08,1.7,0,.04,0,[.34,.28,.19]);
  if(kind==='thq') {
    block(1.5,.56,1.1,0,.36,0,HIDE,2);
    for(let layer=0;layer<3;layer++) {
      // 沿 X 的双坡长屋；三层檐带与连续屋脊，兽角有实际落脚点。
      const l=(1.26-layer*.05)*s,d=(.83-layer*.06)*s,b=(.64+layer*.05)*s,t=(1.04+layer*.06)*s;
      const a=[-l,b,-d],c=[l,t,0],v=[l,b,-d],q=[-l,t,0],e=[-l,b,d],f=[l,b,d];
      const vertices=[a,c,v,a,q,c,e,f,c,e,c,q,v,c,f,a,e,q].flat();
      const geo=new THREE.BufferGeometry();geo.setAttribute('position',new THREE.Float32BufferAttribute(vertices,3));
      const uv=[];for(let i=0;i<vertices.length;i+=3) uv.push(vertices[i]/(2*l)+.5,vertices[i+2]/(2*d)+.5);
      geo.setAttribute('uv',new THREE.Float32BufferAttribute(uv,2));geo.computeVertexNormals();
      parts.push(part(geo,0,0,0,[.59-layer*.03,.43,.21],1));
    }
    block(2.35,.04,.06,0,1.17,0,WOOD);
    for(const x of [-.65,.65]) for(const z of [-.53,.53]) {
      pole(x,z,.75);
      parts.push(surface(torus(.05*s,.012*s,4,8,x*s,.49*s,z*s,BONE,ROT_X90),2));
      block(.2,.36,.018,x*.7,.42,z*1.07,.90,2);
    }
    for(const x of [-.85,.85]) for(const side of [-1,1]) {
      parts.push(surface(limb(.026*s,.005*s,x*s,1.18*s,0,x*s,1.39*s,side*.17*s,BONE),1));
    }
    block(.25,.08,.24,-.2,1.20,0,DARK);
    block(.29,.06,.28,-.2,1.29,0,WOOD);
    block(.10,.015,.10,-.2,1.23,0,[1.4,.55,.12]);
    block(.28,.4,.03,.78,.32,0,.90,2);
    for(const side of [-1,1]) {
      pole(.7,side*.35,.80);
      block(.18,.22,.02,.78,.66,side*.35,.90,2);
      for(let i=0;i<5;i++) {
        const x=-.6+i*.26;
        parts.push(surface(pyr(.022*s,.12*s,4,x*s,.69*s,side*.58*s,BONE),1));
        parts.push(surface(pyr(.035*s,.28*s,5,x*s,.18*s,side*.72*s,WOOD),1));
      }
    }
    block(.12,.36,.12,.9,.26,.23,WOOD);
    block(.11,.03,.10,.94,.41,.23,BONE);
    for(const side of [-1,1]) block(.026,.025,.02,.962,.36,.23+side*.03,[1.2,.62,.12]);
    block(.025,.06,.04,.97,.31,.23,BONE);
    block(.035,.018,.06,.97,.26,.23,DARK);
  } else {
    const high=kind==='ttoxtower',h=high?1.28:1;
    for(const x of [-.42,.42]) for(const z of [-.42,.42]) {
      pole(x,z,h);
      parts.push(surface(limb(.023*s,.023*s,x*s,.12*s,z*s,-x*s,(h-.12)*s,z*s,WOOD),1));
      parts.push(surface(torus(.05*s,.012*s,4,8,x*s,(h-.08)*s,z*s,BONE,ROT_X90),2));
    }
    block(1,.09,1,0,h,0,WOOD);
    for(const side of [-1,1]) block(.9,.25,.025,0,h+.14,side*.48,.90,2);
    if(high) {
      for(const side of [-1,1]) {
        parts.push(surface(ellipsoid(.13*s,.19*s,.13*s,side*.30*s,(h+.2)*s,0,[.39,.28,.19]),1));
        block(.03,.15,.025,side*.30,h+.08,.13,[.65,1.4,.28]);
        parts.push(surface(cyl(.018*s,.018*s,.4*s,6,side*.29*s,(h+.31)*s,-.28*s,BONE,ROT_Z90),1));
        parts.push(surface(pyr(.025*s,.12*s,4,side*.4*s,(h+.31)*s,-.28*s,.90),2));
      }
    } else {
      for(let i=0;i<10;i++) {
        const a=i*Math.PI/5;
        parts.push(surface(pyr(.035*s,.28*s,5,Math.cos(a)*.62*s,.16*s,Math.sin(a)*.62*s,WOOD),1));
      }
      parts.push(surface(ellipsoid(.08*s,.09*s,.07*s,0,(h-.12)*s,.52*s,BONE),1));
      block(.10,.025,.035,0,h+.17,.52,BONE);
      block(.03,.07,.035,0,h+.11,.52,BONE);
    }
  }
  return parts;
}
