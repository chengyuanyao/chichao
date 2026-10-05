import assert from 'node:assert/strict';
import {createFixtureBattle} from './fixture_battle.mjs';
const catalog={units:{tank:{projectile:'shell'},rifle:{projectile:'bullet'},wolf:{}}};
const battle=createFixtureBattle(catalog);
const game={units:Array.from({length:12},(_,i)=>({id:'u'+i,kind:i%4===0?'wolf':i%2?'rifle':'tank',
  owner:i<6?'a':'b',x:i*20,y:30,hp:100,maxHp:100,kills:0})),projectiles:[]};
const first=battle.step(game,0);
assert.ok(first.some(fx=>fx.type==='muzzle'));
assert.ok(game.projectiles.length>0);
assert.ok(game.projectiles.every(p=>game.units.find(u=>u.x===p.targetX).owner!==p.owner));
const shot=game.projectiles[0],start=shot.x;
battle.step(game,125);assert.notEqual(shot.x,start,'shots travel across snapshots');
const landed=battle.step(game,1000);assert.ok(landed.some(fx=>fx.type==='impact'));
assert.ok(battle.stats.impacts>0);assert.ok(battle.stats.fired>0);
assert.equal(game.units.length,12,'sustained visual load keeps all combatants alive');
battle.reset();assert.equal(battle.stats.fired,0);assert.equal(battle.stats.activeProjectiles,0);
console.log('Battle fixture: enemy targets, real projectile kinds, flight, impacts, persistent armies and reset passed.');
