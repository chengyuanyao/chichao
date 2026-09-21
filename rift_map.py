# -*- coding: utf-8 -*-
"""五车争霸·裂谷旷野：独立地图，地形按五个等角扇区生成。"""
import math
import random

MAP_ID = "central_rift"


def point(angle, radial, lateral=0):
    a = math.radians(angle)
    return (round(2000 + math.cos(a)*radial - math.sin(a)*lateral),
            round(2000 + math.sin(a)*radial + math.cos(a)*lateral))


def resource_layout(seed):
    # 同类矿共用局部偏移，再旋转到五个方向：保留随机性，不让某一家抽到远矿。
    rng = random.Random(int(seed) ^ 0x51F7)
    offsets = [(rng.uniform(-12, 12), rng.uniform(-12, 12)) for _ in range(2)]
    resources = []
    for sector in range(5):
        angle = -90 + sector*72
        for group, heading, radial, lateral, amount in (
                (0, angle, 1560, -35, 150000),
                (1, angle+36, 1010, 0, 80000)):
            dr, dl = offsets[group]
            x, y = point(heading, radial+dr, lateral+dl)
            resources.append({"x": x, "y": y, "amount": amount, "public": True})
    return resources


def build_map():
    result = {
        "id": MAP_ID, "name": "五车争霸·裂谷旷野", "width": 4000, "height": 4000,
        "maxPlayers": 5, "theme": "temperate", "visualStyle": "river_valley",
        "bridgeDeckHeight": 18, "packedStart": True, "neutralOreGuards": False,
        "authoredLandscape": True, "publicOreCount": 0,
        "briefing": ("五辆折叠基地车从无矿中央出发，五处高台背靠林岩。"
                     "五条河谷与五座桥连接侧翼，中央保留绕行通路。"
                     "后方五片15万主矿、交界五片8万争夺矿，同类矿每局等量小幅偏移；无中立守军。"),
        "spawnPoints": [(2000,1810),(2181,1941),(2112,2154),(1888,2154),(1819,1941)],
        "spawnLabels": ["中央北位", "中央东北位", "中央东南位", "中央西南位", "中央西北位"],
        "mountains": [], "landforms": [], "rivers": [], "bridges": [], "roads": [],
        "visualTrails": [], "botDeployPoints": [], "bonusResources": resource_layout(0),
    }
    for sector in range(5):
        angle = -90+72*sector
        x, y = point(angle, 1360)
        result["botDeployPoints"].append((x,y))
        result["landforms"].append(dict(x=x,y=y,kind="plateau",angle=angle,
            length=1050,width=820,height=95,bend=25))
        for radial,lateral,radius in [(1810,-270,165),(1860,-85,175),
                                      (1830,115,170),(1750,295,145),
                                      (1240,-395,160),(1150,385,145)]:
            px,py=point(angle,radial,lateral)
            result["mountains"].append(dict(x=px,y=py,r=radius))
        px,py=point(angle,1760)
        result["landforms"].append(dict(x=px,y=py,kind="ridge",angle=angle+90,
            length=890,width=280,height=90,bend=70))
        boundary=angle+36
        river_points=[point(boundary,1250),point(boundary,1480,35),
                      point(boundary,1820,-35),point(boundary,2410,70)]
        river_points[-1]=tuple(max(0,min(4000,v)) for v in river_points[-1])
        for a,b in zip(river_points,river_points[1:]):
            result["rivers"].append(dict(x1=a[0],y1=a[1],x2=b[0],y2=b[1],width=175))
        a,b=river_points[1],river_points[2]
        cx,cy=(a[0]+b[0])/2,(a[1]+b[1])/2
        dx,dy=b[0]-a[0],b[1]-a[1]
        length=math.hypot(dx,dy)
        ux,uy=-dy/length,dx/length
        entry=(round(cx-ux*170),round(cy-uy*170))
        exit_point=(round(cx+ux*170),round(cy+uy*170))
        result["bridges"].append(dict(x=cx,y=cy,x1=entry[0],y1=entry[1],
            x2=exit_point[0],y2=exit_point[1],width=175,deckHeight=18,ramp=120))
        # 自然弯曲土路，中央不汇成笔直五叉路；道路与视觉路线同一份数据。
        route=[point(angle,480,60),point(angle,710,100),point(angle,920,25),
               point(angle,1130,-55),point(angle,1390,-10)]
        trails=[dict(width=80,points=route),
                dict(width=62,points=[point(angle,1430,70),point(angle+12,1480),
                     point(angle+22,1610),entry]),
                dict(width=62,points=[exit_point,point(angle+50,1610),
                     point(angle+60,1490),point(angle+72,1430,-70)])]
        result["visualTrails"].extend(trails)
        for trail in trails:
            for a,b in zip(trail["points"],trail["points"][1:]):
                result["roads"].append(dict(x1=a[0],y1=a[1],x2=b[0],y2=b[1],width=trail["width"]))
        result["roads"].append(dict(x1=entry[0],y1=entry[1],x2=exit_point[0],
                                    y2=exit_point[1],width=150))
    return result
