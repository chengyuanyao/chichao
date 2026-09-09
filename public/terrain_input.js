// Input follows the same bilinear height field used to place units/buildings.
// Walk only the cells crossed by the ray; do not raycast every terrain triangle
// on mousemove. Each cell is a quadratic along a ray, solved without iteration.
const EPS = 1e-7;

export function prepareTerrainInput(field, terrain = {}) {
  let minHeight = Infinity, maxHeight = -Infinity;
  for (const height of field.values) {
    minHeight = Math.min(minHeight, height);
    maxHeight = Math.max(maxHeight, height);
  }
  const bridges = [];
  if (terrain.visualStyle === 'river_valley') {
    for (const b of terrain.bridges || []) {
      if (![b.x1,b.y1,b.x2,b.y2].every(Number.isFinite)) continue;
      const length = Math.hypot(b.x2-b.x1,b.y2-b.y1);
      if (length < .01) continue;
      const deck = Number(b.deckHeight) || Number(terrain.bridgeDeckHeight) || 18;
      bridges.push({x:b.x1,z:b.y1,ux:(b.x2-b.x1)/length,uz:(b.y2-b.y1)/length,
        length,halfWidth:(b.width || 150)*.5+6,ramp:Math.max(40,Number(b.ramp)||110),deck});
      minHeight = Math.min(minHeight,0,deck);
      maxHeight = Math.max(maxHeight,0,deck);
    }
  }
  return {field,bridges,minHeight,maxHeight};
}

function firstRoot(a,b,c) {
  if (Math.abs(c) < EPS) return 0;
  if (Math.abs(a) < EPS) {
    const root = -c/b;
    return root >= -EPS && root <= 1+EPS ? Math.max(0,Math.min(1,root)) : null;
  }
  const discriminant = b*b-4*a*c;
  if (discriminant < -EPS) return null;
  const sqrt = Math.sqrt(Math.max(0,discriminant));
  // Stable roots even when b and sqrt nearly cancel.
  const q = -.5*(b+(b >= 0 ? sqrt : -sqrt));
  let best = null;
  for (const root of [q/a,Math.abs(q)>EPS ? c/q : -b/(2*a)]) {
    if (root >= -EPS && root <= 1+EPS && (best == null || root < best)) {
      best = Math.max(0,Math.min(1,root));
    }
  }
  return best;
}

function fieldIntersection(ray,field,start,end) {
  const ox=ray.origin.x, oy=ray.origin.y, oz=ray.origin.z;
  const dx=ray.direction.x, dy=ray.direction.y, dz=ray.direction.z;
  const cellX=field.width/field.segX, cellZ=field.height/field.segY;
  const ixAt=t=>Math.max(0,Math.min(field.segX-1,Math.floor((ox+dx*t)/cellX)));
  const izAt=t=>Math.max(0,Math.min(field.segY-1,Math.floor((oz+dz*t)/cellZ)));
  let ix=ixAt(start+EPS), iz=izAt(start+EPS), t=start;
  const stepX=dx>=0?1:-1, stepZ=dz>=0?1:-1;
  const deltaX=Math.abs(dx)>EPS?cellX/Math.abs(dx):Infinity;
  const deltaZ=Math.abs(dz)>EPS?cellZ/Math.abs(dz):Infinity;
  let nextX=Math.abs(dx)>EPS?((ix+(stepX>0?1:0))*cellX-ox)/dx:Infinity;
  let nextZ=Math.abs(dz)>EPS?((iz+(stepZ>0?1:0))*cellZ-oz)/dz:Infinity;
  const h=field.values;
  for (let cells=0; cells<=field.segX+field.segY+2; cells++) {
    if(ix<0 || iz<0 || ix>=field.segX || iz>=field.segY || t>end+EPS) break;
    const stop=Math.max(t,Math.min(nextX,nextZ,end));
    const a=iz*field.cols+ix;
    const f=at=>{
      const u=(ox+dx*at)/cellX-ix, v=(oz+dz*at)/cellZ-iz;
      const top=h[a]*(1-u)+h[a+1]*u;
      const bottom=h[a+field.cols]*(1-u)+h[a+field.cols+1]*u;
      return oy+dy*at-(top*(1-v)+bottom*v);
    };
    const f0=f(t), fm=f((t+stop)*.5), f1=f(stop);
    const qa=2*(f0+f1-2*fm), qb=f1-f0-qa;
    const root=firstRoot(qa,qb,f0);
    if(root!=null) return t+(stop-t)*root;
    if(stop>=end-EPS) break;
    if(nextX<=stop+EPS) {ix+=stepX;nextX+=deltaX;}
    if(nextZ<=stop+EPS) {iz+=stepZ;nextZ+=deltaZ;}
    t=stop;
  }
  return null;
}

export function intersectTerrainInput(ray, input, near=0, far=12000) {
  if(!input || ![ray.origin.x,ray.origin.y,ray.origin.z,
    ray.direction.x,ray.direction.y,ray.direction.z].every(Number.isFinite)) return null;
  const {field}=input;
  let start=Math.max(0,near), end=far;
  // Clip against the map and its cached vertical extent before visiting cells.
  for(const [axis,min,max] of [['x',0,field.width],['y',input.minHeight-EPS,input.maxHeight+EPS],['z',0,field.height]]) {
    const origin=ray.origin[axis], direction=ray.direction[axis];
    if(Math.abs(direction)<EPS) {
      if(origin<min || origin>max) return null;
    } else {
      const a=(min-origin)/direction, b=(max-origin)/direction;
      start=Math.max(start,Math.min(a,b));end=Math.min(end,Math.max(a,b));
      if(end<start) return null;
    }
  }
  let best=fieldIntersection(ray,field,start,end);
  for(const b of input.bridges) {
    const along0=(ray.origin.x-b.x)*b.ux+(ray.origin.z-b.z)*b.uz;
    const alongD=ray.direction.x*b.ux+ray.direction.z*b.uz;
    // Main deck and the two linear ramps; identical to bridgeSurfaceHeightAt.
    for(const [lo,hi,slope,intercept] of [
      [-b.ramp,0,b.deck/b.ramp,b.deck],
      [0,b.length,0,b.deck],
      [b.length,b.length+b.ramp,-b.deck/b.ramp,b.deck*(1+b.length/b.ramp)]
    ]) {
      const denominator=ray.direction.y-slope*alongD;
      if(Math.abs(denominator)<EPS) continue;
      const t=(slope*along0+intercept-ray.origin.y)/denominator;
      if(t<start-EPS || t>end+EPS || (best!=null && t>=best)) continue;
      const along=along0+alongD*t;
      const lateral=-(ray.origin.x+ray.direction.x*t-b.x)*b.uz+(ray.origin.z+ray.direction.z*t-b.z)*b.ux;
      if(along>=lo-EPS && along<=hi+EPS && Math.abs(lateral)<=b.halfWidth+EPS) best=t;
    }
  }
  return best==null ? null : {x:ray.origin.x+ray.direction.x*best,
    y:ray.origin.z+ray.direction.z*best,height:ray.origin.y+ray.direction.y*best};
}
