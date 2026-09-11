import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {bakeBlastSurface,createBlastSurface,BLAST_FRAGMENT} from '../public/blast_surface.js';
const a=bakeBlastSurface(32),b=bakeBlastSurface(32);
assert.deepEqual(a.data,b.data,'repeatable authored billows');
assert.equal(a.size,64);
for(let tile=0;tile<4;tile++) {
  const samples=[];
  for(let y=0;y<32;y++) for(let x=0;x<32;x++) {
    const i=((y+Math.floor(tile/2)*32)*64+x+(tile%2)*32)*4;
    samples.push(a.data[i]);
    if(x===0||y===0||x===31||y===31) assert.equal(a.data[i],0,'padded transparent silhouette edge');
  }
  assert.ok(new Set(samples).size>60,'internal cloud structure, not a flat disc');
}
const texture=createBlastSurface();assert.equal(texture.image.width,256);
assert.equal(texture.image.data.byteLength,256*256*4);texture.dispose();
assert.equal((BLAST_FRAGMENT.match(/texture2D/g)||[]).length,1,'one sample shading budget');
assert.doesNotMatch(BLAST_FRAGMENT,/\b(?:sin|cos)\(/,'trigonometry runs per particle, not per pixel');
assert.match(BLAST_FRAGMENT,/vAge/);assert.doesNotMatch(BLAST_FRAGMENT,/for\s*\(/);
const source=readFileSync(new URL('../public/render3d.js',import.meta.url),'utf8');
const ordinary=source.slice(source.indexOf("if (type === 'explosion')"),source.indexOf("} else if (type === 'blast')"));
assert.doesNotMatch(ordinary,/shockLayer.spawn/,'conventional explosions do not draw magic rings');
assert.match(ordinary,/burst\(smokeLayer,7/,'ground dust replaces ring');
assert.match(source,/if\(magic\) shockLayer.spawn/,'magical self-destruction keeps distinct energy cue');
assert.match(source,/scorchLayer = createDecalLayer\([\s\S]*?THREE.NormalBlending,true\)/);
console.log('Blast surface passed: deterministic padded atlas, billow detail, 256 KB texture, one sample, age-based heat and ring-free conventional explosions.');
