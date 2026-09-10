"""One-shot scatter planning; no extra per-tick pathfinding or unit AI."""
import math


def scatter_destinations(units, terrain, structures=()):
    if not units:
        return {}
    spacing = max(100.0, max(u["size"] for u in units) * 2.3 + 12)
    cx = sum(u["x"] for u in units) / len(units)
    cy = sum(u["y"] for u in units) / len(units)
    cells = {}
    obstacles = {}
    for s in structures:
        if s.get("hp", 0) <= 0:
            continue
        radius = s["size"] + spacing * .5
        for ix in range(math.floor((s["x"]-radius)/spacing), math.floor((s["x"]+radius)/spacing)+1):
            for iy in range(math.floor((s["y"]-radius)/spacing), math.floor((s["y"]+radius)/spacing)+1):
                obstacles.setdefault((ix, iy), []).append(s)
    result = {}
    # Outer units get out of the way first. Deterministic ordering also handles
    # coincident centres without everyone choosing the same destination.
    ordered = sorted(units, key=lambda u: (-math.hypot(u["x"]-cx, u["y"]-cy), u["id"]))
    for index, unit in enumerate(ordered):
        ux, uy = unit["x"], unit["y"]
        angle = math.atan2(uy-cy, ux-cx) if math.hypot(ux-cx, uy-cy) > 1 else index * 2.399963
        clearance = max(8.0, unit["size"] * .55)
        chosen = (ux, uy)
        # Bounded local search, at most 62 candidates. Never send a unit to the
        # other bank/side of a forest just because that point is unoccupied.
        candidates = [(ux, uy)]
        outward = min(480.0, max(spacing, math.hypot(ux-cx,uy-cy)*1.8))
        preferred_x, preferred_y = ux+math.cos(angle)*outward, uy+math.sin(angle)*outward
        candidates.append((preferred_x,preferred_y))
        for ring in range(1, 6):
            for step in range(12):
                offset = ((step+1)//2) * (1 if step % 2 else -1) * math.pi/6
                a = angle + offset
                candidates.append((preferred_x+math.cos(a)*spacing*ring, preferred_y+math.sin(a)*spacing*ring))
        for x, y in candidates:
            if not (clearance <= x <= terrain.width-clearance and clearance <= y <= terrain.height-clearance):
                continue
            ix, iy = math.floor(x/spacing), math.floor(y/spacing)
            if any((x-px)**2+(y-py)**2 < spacing**2*.99
                   for nx in range(ix-1, ix+2) for ny in range(iy-1, iy+2)
                   for px, py in cells.get((nx, ny), ())):
                continue
            if any(math.hypot(x-s["x"], y-s["y"]) < s["size"]+unit["size"]
                   for s in obstacles.get((ix, iy), ())):
                continue
            if terrain.blocked(x, y, clearance) or terrain.segment_blocked(ux, uy, x, y, padding=clearance):
                continue
            chosen = (x, y)
            break
        result[unit["id"]] = chosen
        cells.setdefault((math.floor(chosen[0]/spacing), math.floor(chosen[1]/spacing)), []).append(chosen)
    return result
