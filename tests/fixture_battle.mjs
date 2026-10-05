// 离线渲染压力夹具：使用真实目录的兵种/弹种；不负责服务器战斗判定。
export function createFixtureBattle(catalog) {
  let flying=[],nextShot=0,beat=0,serial=0,fired=0,impacts=0;
  return {
    reset(){flying=[];nextShot=0;beat=0;serial=0;fired=0;impacts=0;},
    step(game,time) {
      const effects=[],alive=[];
      for(const shot of flying) {
        const t=(time-shot.born)/shot.duration;
        if(t>=1) {
          effects.push({type:'impact',x:shot.targetX,y:shot.targetY,kind:shot.kind});impacts++;
        } else {
          shot.x=shot.startX+(shot.targetX-shot.startX)*t;
          shot.y=shot.startY+(shot.targetY-shot.startY)*t;shot.t=t;alive.push(shot);
        }
      }
      flying=alive;
      if(time>=nextShot) {
        nextShot=time+500;const phase=beat++%3,units=game.units;
        for(let i=0;i<units.length;i++) {
          const u=units[i],def=catalog.units[u.kind];
          u.hp=u.maxHp*(i%3===0?.25:i%3===1?.62:1);
          if(i%3!==phase||!def.projectile) continue;
          let j=(i+Math.floor(units.length/2))%units.length,tries=0;
          while(units[j].owner===u.owner&&tries++<units.length) j=(j+1)%units.length;
          const target=units[j];if(!target||target.owner===u.owner) continue;
          const kind=u.kind==='overlord'?(u.kills>=8?'plasmalance':u.kills>=3?'plasma':def.projectile):def.projectile;
          u.dir=Math.atan2(target.y-u.y,target.x-u.x);
          effects.push({type:'muzzle',x:u.x,y:u.y,kind,entityId:u.id,entityKind:u.kind,dir:u.dir});
          flying.push({id:'battle-'+serial++,kind,owner:u.owner,x:u.x,y:u.y,startX:u.x,startY:u.y,
            targetX:target.x,targetY:target.y,born:time,duration:800,t:0});fired++;
        }
      }
      game.projectiles=flying;
      return effects;
    },
    get stats(){return {fired,impacts,activeProjectiles:flying.length};}
  };
}
