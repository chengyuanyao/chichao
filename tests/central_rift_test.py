# -*- coding: utf-8 -*-
"""裂谷旷野：公平资源、可建造发展区、桥梁实体通行与多局开场。"""
import math
import os
import random
import sys
import time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import server
import rift_map
from map_test import flood_reachable, cell_of


def room_for(seed=51, count=5, bot=False):
    random.seed(seed)
    players=[server.create_human('R%d'%i,server.COLORS[i],team=i+1,spawn=0)
             for i in range(count-(1 if bot else 0))]
    for i,p in enumerate(players):
        p['faction']='tech' if i%2==0 else 'magic'
    room=dict(id='RIFT',name='rift test',status='lobby',hostId=players[0]['id'],
              players={p['id']:p for p in players},chat=[],game=None,createdAt=time.time(),
              selectedMap=rift_map.MAP_ID,neutrals=True)
    if bot:
        ai=server.create_bot(room)
        ai['faction']='magic'
    server.start_game(room)
    return room


def main():
    definition=server.MAPS[rift_map.MAP_ID]
    terrain=server.terrain_for_match(definition)
    terrain._ensure_grid()
    reachable=flood_reachable(terrain,cell_of(terrain,2000,2000))
    assert definition['packedStart'] and not definition['neutralOreGuards']
    assert len(definition['bridges'])==5
    assert server.PUBLIC_MAPS[rift_map.MAP_ID]['resources']==[]
    layouts=set()
    for seed in range(40):
        resources=rift_map.resource_layout(seed)
        assert resources==rift_map.resource_layout(seed)
        layouts.add(tuple((r['x'],r['y']) for r in resources))
        assert len(resources)==10 and sum(r['amount'] for r in resources)==1150000
        distances=[]
        for i in range(5):
            home,contest=resources[i*2:i*2+2]
            assert home['amount']==150000 and contest['amount']==80000
            bx,by=definition['botDeployPoints'][i]
            distances.append(math.hypot(home['x']-bx,home['y']-by))
            for r in (home,contest):
                assert math.hypot(r['x']-2000,r['y']-2000)>950
                assert not terrain.blocked(r['x'],r['y'],72), (seed,r)
                assert cell_of(terrain,r['x'],r['y']) in reachable, (seed, r, 'ore path cell')
        assert max(distances)-min(distances)<2, distances
    assert len(layouts)>35

    # 发展区采用同一旋转模板；同一采样网格上每家至少有 18 个等间距候选选址。
    slots=[]
    for i,(bx,by) in enumerate(definition['botDeployPoints']):
        assert not terrain.blocked(bx,by,70)
        count=0
        for radial in range(1100,1601,125):
            for lateral in range(-250,251,125):
                x,y=rift_map.point(-90+i*72,radial,lateral)
                if not terrain.blocked(x,y,58):
                    count+=1
        slots.append(count)
        sx,sy=definition['spawnPoints'][i]
        vehicle=server.make_unit('mmcv','test',sx,sy)
        for _ in range(1500):
            server.move_toward(terrain,vehicle,bx,by,80,.05)
            assert not terrain.blocked(vehicle['x'],vehicle['y'])
            if math.hypot(vehicle['x']-bx,vehicle['y']-by)<4:
                break
        assert math.hypot(vehicle['x']-bx,vehicle['y']-by)<4, ('deployment route',i)
    assert min(slots)>=18 and max(slots)-min(slots)<=1, slots

    dry=server.Terrain(definition['rivers'],[],4000,4000,definition['mountains'])
    for i,b in enumerate(definition['bridges']):
        assert dry.point_in_water(b['x'],b['y'])
        dx,dy=b['x2']-b['x1'],b['y2']-b['y1']
        length=math.hypot(dx,dy)
        ux,uy=dx/length,dy/length
        for along in range(-100,int(length)+101,10):
            x,y=b['x1']+ux*along,b['y1']+uy*along
            assert not terrain.blocked(x,y,32), ('bridge clearance',i,along)
        for kind in ('overlord','mmcv','harvester','dragon'):
            vehicle=server.make_unit(kind,'test',b['x1']-ux*90,b['y1']-uy*90)
            target=(b['x2']+ux*90,b['y2']+uy*90)
            crossed=False
            for _ in range(500):
                server.move_toward(terrain,vehicle,target[0],target[1],80,.05)
                assert not terrain.blocked(vehicle['x'],vehicle['y'])
                crossed=crossed or math.hypot(vehicle['x']-b['x'],vehicle['y']-b['y'])<90
                if math.hypot(vehicle['x']-target[0],vehicle['y']-target[1])<4:
                    break
            assert crossed and math.hypot(vehicle['x']-target[0],vehicle['y']-target[1])<4, (i,kind)

    for seed,count in ((71,2),(72,4),(73,5)):
        room=room_for(seed,count)
        game=room['game']
        assert len(game['units'])==count and not game['structures']
        assert not game['neutrals'] and not game['neutralCamps']
        assert sorted(r['amount'] for r in game['resources'])==[80000]*5+[150000]*5
        expected=rift_map.resource_layout(game['map']['seed'])
        assert [(r['x'],r['y']) for r in game['resources']]==[(r['x'],r['y']) for r in expected], 'ore silently relocated'
        for _ in range(320):
            server.tick_game(room,.05)
        assert room['status']=='playing'
        assert all(not p['eliminated'] for p in room['players'].values())
        # 真正展开，再走权威建造接口，不能只检查空地圆圈。
        for p in room['players'].values():
            i=p['spawn']
            mcv=next(u for u in game['units'] if u['owner']==p['id'])
            mcv['x'],mcv['y']=definition['botDeployPoints'][i]
            server.issue_deploy(game,p['id'],[mcv['id']])
            assert server.has_active_structure(game,p['id'],'hq' if p['faction']=='tech' else 'mhq')
            x,y=rift_map.point(-90+i*72,1360,155)
            server.place_structure(room,p['id'],'power' if p['faction']=='tech' else 'mpower',x,y,free=True)

    room=room_for(74,5,True)
    ai=next(p for p in room['players'].values() if p.get('isBot'))
    for _ in range(900):
        server.tick_game(room,.05)
    hqs=[s for s in room['game']['structures'] if s['owner']==ai['id'] and server.structure_role(s['kind'])=='hq']
    assert hqs and math.hypot(hqs[0]['x']-2000,hqs[0]['y']-2000)>900
    print('Rift: 40 fair ore seeds, equal build slots %s, 5 migration routes, 20 bridge traversals, 2/4/5-player starts, construction and AI passed.'%slots)


if __name__=='__main__':
    main()
