import * as THREE from './vendor/three.module.min.js';

// Authored river-sample assets. All coordinates are local model space; simulation
// footprints stay in the authoritative catalog. Far LOD retains the old assets.
export const RIVER_ART_KINDS = new Set(['tank','overlord','overlord_v1','overlord_v2','dragon','rifle','mage']);

function part(geo, x, y, z, paint, surf=0) {
  return {geo,matrix:new THREE.Matrix4().makeTranslation(x,y,z),surf,
    ...(Array.isArray(paint)?{rgb:paint}:{shade:paint})};
}

// A continuous, UV-unwrapped shell along X. Each station is [x, halfWidth,
// lowerY, upperY]; chamfered shoulders give a readable cast/sloped armor silhouette.
export function armorShell(stations, paint, surf=0) {
  const pos=[],uv=[],idx=[];
  stations.forEach(([x,w,b,t],s)=>{
    const h=t-b;
    const ring=[[w*.94,b],[w,b+h*.10],[w,b+h*.84],[w*.88,t],
      [-w*.88,t],[-w,b+h*.84],[-w,b+h*.10],[-w*.94,b],[w*.94,b]];
    ring.forEach(([z,y],j)=>{pos.push(x,y,z);uv.push(s/(stations.length-1),j/8);});
  });
  for(let s=0;s<stations.length-1;s++) for(let j=0;j<8;j++) {
    const a=s*9+j,b=a+9;idx.push(a,a+1,b,a+1,b+1,b);
  }
  // End caps use separate vertices/normals, not smoothed into the hull sides.
  for(const s of [0,stations.length-1]) {
    const start=pos.length/3,[x,w,b,t]=stations[s];
    pos.push(x,(b+t)*.5,0);uv.push(.5,.5);
    for(let j=0;j<9;j++) {
      const i=(s*9+j)*3;pos.push(pos[i],pos[i+1],pos[i+2]);
      uv.push(pos[i+2]/(w*2)+.5,(pos[i+1]-b)/(t-b));
    }
    for(let j=0;j<8;j++) {
      if(s===0) idx.push(start,start+j+2,start+j+1);
      else idx.push(start,start+j+1,start+j+2);
    }
  }
  const geo=new THREE.BufferGeometry();
  geo.setAttribute('position',new THREE.Float32BufferAttribute(pos,3));
  geo.setAttribute('uv',new THREE.Float32BufferAttribute(uv,2));
  for(let i=0;i<idx.length;i+=3) [idx[i+1],idx[i+2]]=[idx[i+2],idx[i+1]];
  geo.setIndex(idx);
  // Armor is manufactured plate: do not smooth the entire top into its sides.
  // Geometric chamfers carry the edge highlight, planar faces stay planar.
  const hard=geo.toNonIndexed();hard.computeVertexNormals();geo.dispose();
  return part(hard,0,0,0,paint,surf);
}

function cable(points,r,paint,surf=0) {
  const curve=new THREE.CatmullRomCurve3(points.map(p=>new THREE.Vector3(...p)));
  return part(new THREE.TubeGeometry(curve,Math.max(8,points.length*3),r,6,false),0,0,0,paint,surf);
}

// Continuous low-poly anatomical volume. Stations are [x,width,centerY,height,z?].
// Smooth side normals and separate caps avoid the old intersecting tube/egg body.
export function organicShell(stations,paint,surf=3) {
  const segments=10,pos=[],uv=[],indices=[];
  stations.forEach(([x,w,y,h,z=0],s)=>{
    for(let j=0;j<=segments;j++) {
      const a=j/segments*Math.PI*2;
      pos.push(x,y+Math.sin(a)*h,z+Math.cos(a)*w);uv.push(s/(stations.length-1),j/segments);
    }
  });
  for(let s=0;s<stations.length-1;s++) for(let j=0;j<segments;j++) {
    const a=s*(segments+1)+j,b=a+segments+1;indices.push(a,b,a+1,a+1,b,b+1);
  }
  for(const s of [0,stations.length-1]) {
    const [x,w,y,h,z=0]=stations[s],c=pos.length/3;
    pos.push(x,y,z);uv.push(.5,.5);
    for(let j=0;j<=segments;j++) {
      const a=j/segments*Math.PI*2;
      pos.push(x,y+Math.sin(a)*h,z+Math.cos(a)*w);uv.push(.5+Math.cos(a)*.5,.5+Math.sin(a)*.5);
    }
    for(let j=0;j<segments;j++) indices.push(c,c+j+(s===0?1:2),c+j+(s===0?2:1));
  }
  const geo=new THREE.BufferGeometry();geo.setAttribute('position',new THREE.Float32BufferAttribute(pos,3));
  geo.setAttribute('uv',new THREE.Float32BufferAttribute(uv,2));geo.setIndex(indices);geo.computeVertexNormals();
  const normals=geo.attributes.normal;
  for(let s=0;s<stations.length;s++) {
    const a=s*(segments+1),b=a+segments,n=new THREE.Vector3().fromBufferAttribute(normals,a)
      .add(new THREE.Vector3().fromBufferAttribute(normals,b)).normalize();
    normals.setXYZ(a,n.x,n.y,n.z);normals.setXYZ(b,n.x,n.y,n.z);
  }
  return part(geo,0,0,0,paint,surf);
}

function wingPoint(a,b,side) {
  const leading=5-a*16;
  const chord=Math.max(.35,14*(1-a)+2.8*Math.sin(a*Math.PI)*(.5+.5*Math.sin(a*Math.PI*8)));
  return [leading-chord*b,
    14+Math.sin(a*Math.PI*.8)*15-Math.sin(b*Math.PI)*Math.sin(a*Math.PI)*3.8,
    side*(4+a*21)];
}

function membrane(side) {
  const pos=[],uv=[],idx=[],rows=8,cols=6;
  for(let u=0;u<=rows;u++) for(let v=0;v<=cols;v++) {
    const a=u/rows,b=v/cols;
    pos.push(...wingPoint(a,b,side));
    uv.push(a,b);
  }
  for(let u=0;u<rows;u++) for(let v=0;v<cols;v++) {
    const a=u*(cols+1)+v,b=a+cols+1;
    idx.push(a,b,a+1,a+1,b,b+1);
  }
  if(side<0) for(let i=0;i<idx.length;i+=3) [idx[i+1],idx[i+2]]=[idx[i+2],idx[i+1]];
  const g=new THREE.BufferGeometry();g.setAttribute('position',new THREE.Float32BufferAttribute(pos,3));
  g.setAttribute('uv',new THREE.Float32BufferAttribute(uv,2));g.setIndex(idx);
  g.computeVertexNormals();
  // Separate underside vertices retain curved normals instead of cancelling them.
  const normals=Array.from(g.attributes.normal.array),vertices=pos.length/3,back=[];
  for(let i=0;i<idx.length;i+=3) back.push(idx[i]+vertices,idx[i+2]+vertices,idx[i+1]+vertices);
  g.setAttribute('position',new THREE.Float32BufferAttribute(pos.concat(pos),3));
  g.setAttribute('uv',new THREE.Float32BufferAttribute(uv.concat(uv),2));
  g.setAttribute('normal',new THREE.Float32BufferAttribute(normals.concat(normals.map(v=>-v)),3));
  g.setIndex(idx.concat(back));
  return part(g,0,0,0,[.26,.29,.27],3);
}

export function riverUnitModel(kind, base, k) {
  if(!RIVER_ART_KINDS.has(kind)) return base;
  const {box,cyl,sph,ellipsoid,limb,trackedHull,recoiling,MAT,ROT_Z90,ROT_X90}=k;
  const steel=[.24,.27,.29],dark=[.075,.092,.10],edge=[.43,.44,.40];
  const finish=model=>{
    for(const p of [...model.body,...(model.rigs||[]).flatMap(r=>r.parts)]) {
      if((p.rgb===steel||p.rgb===edge)&&(p.surf==null||p.surf===0)) p.surf=.25;
    }
    return model;
  };
  if(kind==='tank') {
    const body=trackedHull(34,20,7.5,.60).concat([
      armorShell([[-15,7.5,7,11],[-10,9,7,13],[7,8.8,7,12],[17,7,7.2,9]],[.34,.38,.34]),
      cyl(6.5,7.8,2,16,-1,13,0,dark),
      armorShell([[-9,5.6,14,16.2],[-6,7.3,13.5,18],[3,7,13.5,18.4],[9,4.1,14,16.8]],.90),
      cyl(2.1,2.4,5.6,12,8.4,15.5,0,dark,ROT_Z90),
      recoiling(cyl(.92,1.24,19,12,19,15.5,0,steel,ROT_Z90)),
      recoiling(cyl(1.40,1.40,2.4,12,28,15.5,0,dark,ROT_Z90)),
      cyl(2.8,2.8,.65,12,-3,18.7,1,.65),
      box(2.4,1.0,1.7,2.2,19,-2,dark),
      cable([[-10,12,6],[-14,11,8],[-15,8,7]],.25,edge),
    ]);
    for(const side of [-1,1]) {
      for(let i=0;i<5;i++) body.push(box(4.3,2.9,.55,-11+i*5,9.0,side*10.2,.65));
      body.push(cable([[-9,16,side*5.3],[-5,19,side*6],[2,19,side*5.5]],.18,edge));
      for(let i=0;i<4;i++) body.push(box(.55,.45,3.2,-12+i*1.2,13.1,side*3,steel));
      for(let i=0;i<6;i++) body.push(cyl(.18,.18,.16,6,-8+i*2.2,18.15,side*4.6,[.56,.58,.54]));
      body.push(cyl(.3,.3,5.8,6,-6,21.2,side*3.9,steel));
    }
    return finish({body,glow:[box(.55,.55,2.6,3.5,19,-2,[1.05,1.22,1.25])]});
  }
  if(kind==='dragon') {
    const body=[
      organicShell([[-20,.65,5,.8],[-13,2.4,7,2.8],[-6,4.8,9,4.5],[1,4.5,10.5,4.1],
        [6,3.2,13,3.6],[9,2.2,18,3],[13,2.1,23,2.8],[20,2,26,2]], [.26,.29,.28]),
      // Brow, cheek and muzzle form one continuous volume rather than a box
      // floating above a rectangular jaw. The open mouth remains real geometry.
      organicShell([[16,1.8,26,1.7],[20,2.9,27.2,2.6],[23,2.5,27,2.0],
        [27,1.75,26.4,1.25],[30,1.35,26.1,.85]],.65),
      organicShell([[21,1.8,24,.7],[24,2.0,23.7,.65],[28,1.45,24.2,.55],[30,1.15,24.8,.3]],dark),
      organicShell([[-34,.10,3,.15,3],[-28,.38,4,.45,2],[-20,.80,6,1,0],[-12,1.15,7,1.4,0]],[.22,.25,.24]),
    ];
    const rigs=[];
    for(const side of [-1,1]) {
      body.push(organicShell([[12,.05,35,.07,side*4],[15,.24,34.8,.35,side*3.6],
        [18,.45,32.6,.65,side*2.7],[20,.65,29.2,.8,side*1.8]],edge,.25));
      body.push(ellipsoid(1.25,.72,.32,23.5,27.7,side*2.45,dark));
      for(let i=0;i<3;i++) body.push(cyl(.08,.25,1.25,5,25+i*1.25,24.6,side*1.65,edge));
      for(const x of [-8,6]) {
        body.push(limb(1.5,1.05,x,7,side*3.7,x+2,3.7,side*5.3,steel));
        body.push(limb(1,.7,x+2,3.7,side*5.3,x+3,.8,side*5.7,dark));
        body.push(ellipsoid(2.3,.65,1.5,x+4,.8,side*5.7,edge));
      }
      const wing=[membrane(side),cable([wingPoint(0,0,side),wingPoint(.5,0,side),wingPoint(1,0,side)],.52,.60)];
      for(let i=0;i<4;i++) {
        const span=.3+i*.23;
        wing.push(cable([wingPoint(0,.1,side),wingPoint(span*.55,.4,side),wingPoint(span,1,side)],.18,edge));
      }
      const pivot=[3,14,side*4];
      for(const p of wing) p.matrix.premultiply(new THREE.Matrix4().makeTranslation(-pivot[0],-pivot[1],-pivot[2]));
      rigs.push({parts:wing,pivot,axis:'x',side,mode:'wing'});
    }
    for(let i=0;i<5;i++) body.push(armorShell([[-10+i*3,3.8,11.5,13],[-8+i*3,3.3,12,14]],.70));
    return finish({body,rigs,glow:[box(.6,.45,.10,23.8,27.7,2.72,[1.1,1.35,1.5]),box(.6,.45,.10,23.8,27.7,-2.72,[1.1,1.35,1.5])]});
  }
  if(kind==='rifle'||kind==='mage') {
    const cloth=kind==='mage'?[.22,.24,.31]:[.22,.25,.20];
    const body=[ellipsoid(1.55,3.4,2.45,0,10.7,0,cloth),
      ellipsoid(1.25,1.62,1.30,.1,16.05,0,kind==='mage'?cloth:[.43,.34,.27]),
      ellipsoid(.75,.95,.8,0,14.25,0,cloth),
      box(1.55,3.5,3.1,-1.65,10.7,0,cloth),
      limb(1.1,.78,0,12.6,3.2,2.8,9.2,3.1,cloth),
      limb(.85,.62,2.8,9.2,3.1,6.0,10.5,1.2,cloth),
      limb(1.1,.78,0,12.6,-3.2,3.8,10.2,-2.6,cloth),
      limb(.85,.62,3.8,10.2,-2.6,6.3,10.5,.6,cloth)];
    body.forEach(p=>p.surf=2);
    body[1].surf=kind==='rifle'?0:2;
    body[2].surf=0;
    if(kind==='rifle') {
      // Helmet rim, face opening, vest webbing and pouches break the mannequin silhouette.
      body.push(ellipsoid(1.4,1.0,1.48,-.1,16.75,0,[.25,.28,.24]));
      body.push(ellipsoid(1.5,.16,1.55,.05,16.4,0,[.25,.28,.24]));
      const face=ellipsoid(.5,.68,.87,1.07,15.8,0,[.43,.34,.27]);face.surf=3;body.push(face);
      body.push(part(new THREE.BoxGeometry(.5,2.6,3.3),1.42,11.3,0,.60,2));
      for(const side of [-1,1]) {
        body.push(part(new THREE.BoxGeometry(.22,3.7,.30),1.60,11,side*1.3,cloth,2));
        body.push(part(new THREE.BoxGeometry(.75,1.45,.95),1.9,9.5,side*1.0,cloth,2));
      }
    } else {
      body.push(part(new THREE.CylinderGeometry(2.1,3.5,5.2,10,1,true),0,6.8,0,.65,2));
    }
    const rigs=[];
    for(const side of [-1,1]) {
      const leg=[limb(1.05,.8,0,0,0,.5,-3,0,cloth),limb(.8,.65,.5,-3,0,0,-5.7,0,cloth),
        ellipsoid(1.6,.72,1.05,.65,-6,0,dark)];leg.forEach(p=>p.surf=2);
      rigs.push({parts:leg,pivot:[0,7.0,side*1.5],axis:'z',side,mode:'walk'});
    }
    if(kind==='rifle') body.push(box(4.8,1.2,1.0,5.8,10.5,.7,dark),cyl(.27,.33,5.5,8,10,10.5,.7,steel,ROT_Z90));
    else body.push(cable([[8,1,.7],[8,8,.7],[9,17,.7]],.32,edge),sph(1.25,10,9,17,.7,[.45,.64,.78]));
    return finish({body,rigs,glow:kind==='mage'?[sph(.70,8,9,17,.7,[1.05,1.4,1.6])]:[]});
  }
  if(kind==='overlord'||kind==='overlord_v1') {
    const veteran=kind==='overlord_v1',plate=veteran?[.25,.27,.29]:[.38,.40,.38];
    const body=trackedHull(43,30,9,.48).concat([
      armorShell([[-20,10,9,13],[-14,12.8,8.8,17],[9,12.5,9,16.7],[21,10,10,13]],plate),
      cyl(9.3,10,2.1,20,-1,17.5,0,dark),
      armorShell([[-12,7.7,18,22],[-7,10,18,25.7],[4,9.7,18,25],[12,6.8,19,22]],.58),
      box(7,1.1,11,-10,25,0,plate),
      cyl(2.8,2.8,.65,16,-3,26.2,-1,plate),
      box(1.7,1.1,2,2,26.5,-2,dark)
    ]),glow=[];
    for(const side of [-1,1]) {
      for(let i=0;i<6;i++) {
        body.push(box(5.0,4.2,.7,-15+i*5.7,11.5,side*15.4,i%3===0?.55:plate));
        body.push(cyl(.22,.22,.22,6,-9+i*3,25.4,side*6.5,edge));
      }
      for(let i=0;i<7;i++) body.push(box(.6,.5,6,-18+i*1.1,17.0,side*4.2,dark));
      body.push(cyl(2.2,2.6,5.7,12,11,21.5,side*4.0,plate,ROT_Z90));
      body.push(recoiling(cyl(1.15,1.42,22,12,23,21.5,side*4.0,steel,ROT_Z90)));
      body.push(recoiling(cyl(1.8,1.8,3.2,12,34,21.5,side*4.0,dark,ROT_Z90)));
      body.push(cable([[-11,23,side*7],[-12,26,side*9],[-4,26.5,side*9]],.22,edge));
      body.push(cyl(.2,.28,8,6,-11,28.4,side*6,steel));
      if(veteran) for(let i=0;i<3;i++) {
        glow.push(recoiling(cyl(1.51,1.51,.42,10,20+i*4,21.5,side*4,[.32,1.6,1.85],ROT_Z90)));
      }
      glow.push(box(.6,.4,1.7,17,14.4,side*8.7,[1.10,1.04,.78]));
    }
    return finish({body,glow});
  }
  // The titan retains shoulder pivots so its transform animation and real
  // cannon picking remain compatible; torso panels and hydraulics are rebuilt below.
  // Replace only the central torso. The former height-only filter also deleted
  // both shoulder armor housings, leaving exposed pivots and disconnected arms.
  const body=base.body.filter(p=>p.matrix.elements[13]<28||p.matrix.elements[13]>39
    ||Math.abs(p.matrix.elements[14])>=12),glow=base.glow.slice();
  if(kind==='overlord_v2') {
    body.push(cyl(3.1,3.6,9.0,16,-1,30.5,0,dark));
    body.push(armorShell([[-8,7.4,29,36],[-3,9.2,28.5,39],[2,9,29,39],[8.2,5,31,35]],.57));
    body.push(armorShell([[-7,5.4,33,40],[-3,5.4,33,40]],steel));
    for(const side of [-1,1]) {
      body.push(cyl(2.4,2.4,3.3,12,-.4,36.4,side*11.6,steel,ROT_X90));
      body.push(limb(.70,.70,-4,28,side*5,-5,37,side*8,[.6,.64,.64]));
      for(let i=0;i<5;i++) body.push(cyl(.20,.20,.25,6,-3+i*1.5,39.15,side*5.3,edge));
      body.push(cable([[-4,30,side*6],[-5,24,side*7],[-3,17,side*7]],.42,edge));
      body.push(cable([[-7,38,side*8],[-6,41,side*11],[-1,39,side*14]],.48,dark));
      for(let i=0;i<4;i++) body.push(box(3.4,.48,.6,-8.9,34+i*1.4,side*7.8,steel));
      body.push(cyl(2.0,2.0,.7,12,.4,14.4,side*9.1,edge,ROT_X90));
    }
  }
  return finish({body,glow});
}

export function riverStructureDetails(kind,s,k) {
  const {box,cyl}=k,parts=[];
  if(!['hq','mhq','factory'].includes(kind)) return parts;
  const stone=[.48,.46,.40],metal=[.30,.34,.34],dark=[.11,.14,.14],trim=[.57,.59,.55];
  const block=(w,h,d,x,y,z,color,surf=1)=>{const p=box(w*s,h*s,d*s,x*s,y*s,z*s,color);p.surf=surf===0&&color===trim?.25:surf;parts.push(p);};
  const column=(rt,rb,h,x,y,z,color,surf=1)=>{const p=cyl(rt*s,rb*s,h*s,16,x*s,y*s,z*s,color);p.surf=surf===0&&color===trim?.25:surf;parts.push(p);};
  const arch=(w,h,d,x,y,z,color,surf=1)=>{
    const shape=new THREE.Shape(),r=w*s*.5,ry=h*s,thick=s*.035;
    shape.moveTo(-r,0);
    for(let i=1;i<=16;i++){const a=Math.PI-i*Math.PI/16;shape.lineTo(Math.cos(a)*r,Math.sin(a)*ry);}
    for(let i=16;i>=0;i--){const a=Math.PI-i*Math.PI/16;shape.lineTo(Math.cos(a)*(r-thick),Math.sin(a)*(ry-thick));}
    shape.closePath();
    const geo=new THREE.ExtrudeGeometry(shape,{depth:d*s,bevelEnabled:false,steps:1});
    geo.translate(0,0,-d*s*.5);parts.push(part(geo,x*s,y*s,z*s,color,surf===0&&color===trim?.25:surf));
  };
  if(kind==='factory') {
    // Assembly hall with a recessed bay, ribbed roof and attached service wing.
    block(1.85,.09,1.65,0,.045,0,stone);
    block(.12,.72,1.30,-.72,.45,0,metal,0);
    block(.12,.72,1.30,.72,.45,0,metal,0);
    block(1.45,.68,.10,0,.43,-.60,metal,0);
    block(1.32,.49,.06,0,.31,.54,dark,0);
    for(let i=0;i<7;i++) block(1.30,.035,.07,0,.12+i*.068,.58,trim,0);
    arch(1.55,.48,1.38,0,.78,0,.72,0);
    for(let i=0;i<7;i++) arch(1.57,.49,.027,0,.78,-.66+i*.22,trim,0);
    block(.40,.42,.98,.96,.28,-.13,metal,0);
    block(.44,.04,1.03,.96,.51,-.13,trim,0);
    for(let i=0;i<4;i++) block(.035,.15,.12,1.17,.37,-.42+i*.20,[.15,.25,.29],4);
    column(.065,.08,.88,-.94,.55,-.46,metal,0);
    column(.09,.09,.06,-.94,1.02,-.46,trim,0);
    block(.05,.05,.08,-.63,.72,.70,[1.4,1.0,.5],4);
    block(.05,.05,.08,.63,.72,.70,[1.4,1.0,.5],4);
    return parts;
  }
  if(kind==='hq') {
    // Military command complex: service hangars, recessed gates, observation
    // deck, roof equipment and a slender communications spine, not a silo.
    block(1.85,.07,1.65,0,.035,0,stone);
    block(.64,.53,1.20,0,.33,-.06,metal,0);
    for(const side of [-1,1]) {
      const x=side*.63;
      block(.52,.31,1.10,x,.225,-.04,stone);
      arch(.56,.20,1.12,x,.38,-.04,.40,0);
      for(let j=0;j<5;j++) arch(.575,.21,.018,x,.38,-.49+j*.225,metal,0);
      block(.35,.25,.016,x,.205,.521,dark,0);
      for(let j=0;j<7;j++) block(.35,.010,.019,x,.095+j*.032,.532,metal,0);
      block(.10,.16,1.13,side*.95,.15,-.04,stone);
      for(let j=0;j<4;j++) {
        block(.026,.10,.105,side*.904,.30,-.38+j*.23,dark,0);
        block(.021,.027,.078,side*.92,.32,-.38+j*.23,[.65,.75,.75],0);
      }
      block(.13,.07,.34,side*.22,.63,-.34,dark,0);
      for(let j=0;j<6;j++) block(.14,.02,.013,side*.22,.68,-.48+j*.055,trim,0);
      parts.push(cable([[side*s*.44,s*.19,-s*.55],[side*s*.40,s*.55,-s*.55],[side*s*.21,s*.64,-s*.48]],s*.013,metal));
    }
    block(.39,.68,.41,0,.95,-.10,stone);
    block(.56,.19,.53,0,1.31,-.10,metal,0);
    block(.50,.085,.016,0,1.33,.173,[.12,.21,.22],0);
    for(const side of [-1,1]) {
      block(.016,.085,.45,side*.287,1.33,-.10,[.12,.21,.22],0);
      for(let j=0;j<5;j++) block(.029,.13,.024,-.23+j*.115,1.33,.19,trim,0);
    }
    block(.64,.05,.61,0,1.44,-.10,.55,0);
    block(.22,.17,.23,0,1.56,-.08,metal,0);
    column(.027,.042,.34,0,1.79,0,trim,0);
    for(let j=0;j<5;j++) block(.015,.05,.07,0,1.64+j*.065,0,metal,0);
    block(.30,.30,.026,0,.23,.554,dark,0);
    block(.018,.26,.018,0,.23,.575,trim,0);
    for(let i=0;i<4;i++) block(.36,.026,.11,0,.035+i*.026,.78-i*.09,stone);
    block(.49,.045,.035,0,.53,.56,.70,0);
    for(const side of [-1,1]) {
      block(.018,.045,.018,side*.19,.42,.576,[1.1,1.04,.80],0);
      column(.006,.006,.42,side*.76,.70,-.41,trim,0);
    }
  } else {
    // Arcane keep: masonry nave, actual open arches, buttresses and a copper
    // ribbed cupola. Dark recesses are geometry, not luminous white cylinders.
    column(.86,.90,.09,0,.045,0,stone);
    column(.52,.60,.43,0,.30,-.07,stone);
    column(.48,.55,.08,0,.56,-.07,trim);
    column(.29,.39,.71,0,.93,-.07,stone);
    column(.38,.34,.07,0,1.31,-.07,trim);
    const roof=part(new THREE.SphereGeometry(s*.42,20,10,0,Math.PI*2,0,Math.PI*.5),0,s*1.36,-s*.07,[.23,.37,.34],0);
    roof.geo.scale(1,1.3,1);parts.push(roof);
    column(.055,.09,.28,0,1.94,-.07,.67,0);
    for(let i=0;i<8;i++) {
      const a=i*Math.PI/4,x=Math.sin(a),z=Math.cos(a),cx=x*.56,cz=z*.56-.07;
      column(.055,.08,.56,cx,.37,cz,stone);
      column(.096,.096,.055,cx,.67,cz,trim);
      const rib=cable([[x*s*.40,s*1.36,(z*.40-.07)*s],[x*s*.34,s*1.68,(z*.34-.07)*s],[0,s*1.91,-s*.07]],s*.013,trim,0);parts.push(rib);
      const wall=box(.09*s,.49*s,.05*s,x*s*.33,.93*s,(z*.33-.07)*s,dark);wall.matrix.multiply(new THREE.Matrix4().makeRotationY(a));wall.surf=1;parts.push(wall);
      parts.push(cable([[x*s*.72,s*.11,(z*.72-.07)*s],[x*s*.64,s*.65,(z*.64-.07)*s],[x*s*.33,s*1.02,(z*.33-.07)*s]],s*.045,stone,1));
      const band=box(.10*s,.07*s,.07*s,x*s*.62,.47*s,(z*.62-.07)*s,.70);band.surf=2;parts.push(band);
    }
    block(.43,.32,.06,0,.23,.52,dark);
    arch(.43,.27,.13,0,.36,.54,trim);
    for(const side of [-1,1]) block(.045,.29,.13,side*.213,.215,.54,trim);
    for(let i=0;i<4;i++) block(.46,.03,.115,0,.035+i*.029,.86-i*.095,stone);
    column(.055,.055,.08,0,.54,.56,[1.08,1.30,1.40],4);
  }
  return parts;
}

export function artJointAngle(rig,time,travel,motion) {
  if(rig.mode==='wing') return rig.side*(.035+Math.sin(time*.0015+rig.side*.2)*.055+motion*.05);
  return rig.side*Math.sin(travel*.25)*Math.min(.42,motion*.45);
}
