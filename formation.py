# -*- coding: utf-8 -*-
"""Facing-aware group-move slots. Collision and pathing stay in issue_move."""
from __future__ import print_function

import math

FORMATION_MODES = ("box", "line", "wedge")
FORMATION_SPACING = 52.0
WEDGE_DEPTH = 0.86


def normalize_formation(value, default="box"):
    if value is None:
        return default
    text = str(value).strip().lower()
    if text in FORMATION_MODES:
        return text
    return default


def resolve_move_formation(player, payload_formation=None):
    """Prefer the command payload; otherwise the seat default (box)."""
    if payload_formation is not None and str(payload_formation).strip():
        text = str(payload_formation).strip().lower()
        if text in FORMATION_MODES:
            return text
    return normalize_formation((player or {}).get("formation"))


def formation_spacing(units):
    """Base 52, stretched a little when the group includes tanks or dragons."""
    if not units:
        return FORMATION_SPACING
    max_size = 0.0
    for unit in units:
        max_size = max(max_size, float(unit.get("size") or 0.0))
    return max(FORMATION_SPACING, FORMATION_SPACING * 0.70 + max_size * 1.2)


def march_basis(origin_x, origin_y, target_x, target_y):
    """Forward = centroid → click. Right is perpendicular (clockwise)."""
    dx = float(target_x) - float(origin_x)
    dy = float(target_y) - float(origin_y)
    length = math.hypot(dx, dy)
    if length < 1e-6:
        return 1.0, 0.0, 0.0, -1.0
    fx, fy = dx / length, dy / length
    return fx, fy, fy, -fx


def formation_offsets(count, style, spacing=FORMATION_SPACING):
    """Local (right, forward) slots. Forward is the march direction."""
    style = normalize_formation(style)
    n = int(count)
    if n <= 0:
        return []
    if n == 1:
        return [(0.0, 0.0)]
    if style == "line":
        return [((index - (n - 1) / 2.0) * spacing, 0.0) for index in range(n)]
    if style == "wedge":
        return _wedge_offsets(n, spacing)
    return _box_offsets(n, spacing)


def _box_offsets(count, spacing):
    columns = max(1, int(math.ceil(math.sqrt(count))))
    rows = int(math.ceil(count / float(columns)))
    offsets = []
    for index in range(count):
        row = index // columns
        column = index % columns
        right = (column - (columns - 1) / 2.0) * spacing
        # 前排（row 0）在行军方向更靠前，方阵仍以点击为中心。
        forward = ((rows - 1) / 2.0 - row) * spacing
        offsets.append((right, forward))
    return offsets


def _wedge_row_counts(count):
    rows = []
    remaining = int(count)
    width = 1
    while remaining > 0:
        take = width if remaining > width else remaining
        rows.append(take)
        remaining -= take
        width += 1
    return rows


def _wedge_offsets(count, spacing):
    """Arrowhead: tip sits on the click, ranks trail behind and widen."""
    rows = _wedge_row_counts(count)
    depth = spacing * WEDGE_DEPTH
    offsets = []
    for row, width in enumerate(rows):
        for index in range(width):
            right = (index - (width - 1) / 2.0) * spacing
            forward = -row * depth
            offsets.append((right, forward))
    return offsets


def formation_world_slots(origin_x, origin_y, target_x, target_y, count, style,
                          spacing=FORMATION_SPACING):
    fx, fy, rx, ry = march_basis(origin_x, origin_y, target_x, target_y)
    slots = []
    for right, forward in formation_offsets(count, style, spacing):
        slots.append((
            target_x + rx * right + fx * forward,
            target_y + ry * right + fy * forward,
        ))
    return slots


def assign_nearest_slots(units, slots):
    """Greedy nearest-slot matching; keep the caller's unit order."""
    remaining = list(slots)
    assigned = {}
    for unit in units:
        ux, uy = unit["x"], unit["y"]
        best_index = 0
        best_dist = None
        for index, slot in enumerate(remaining):
            dist = (slot[0] - ux) ** 2 + (slot[1] - uy) ** 2
            if best_dist is None or dist < best_dist:
                best_dist = dist
                best_index = index
        assigned[unit["id"]] = remaining.pop(best_index)
    return assigned
