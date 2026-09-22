# -*- coding: utf-8 -*-
"""Massive units must not deadlock around shared navigation cell centres."""
import math
import time
from central_rift_test import room_for
import server


def crossing(index=0, kind='overlord'):
    room = room_for()
    game = room['game']
    owner = next(iter(room['players']))
    terrain = game['terrainCtx']
    bridge = server.MAPS['central_rift']['bridges'][index]
    dx, dy = bridge['x2'] - bridge['x1'], bridge['y2'] - bridge['y1']
    length = math.hypot(dx, dy)
    ux, uy = dx / length, dy / length
    army = []
    for i in range(53):
        along, across = 200 + i // 8 * 40, (i % 8 - 3.5) * 36
        x = bridge['x1'] - ux * along - uy * across
        y = bridge['y1'] - uy * along + ux * across
        x, y = terrain.nearest_open_point(x, y, bridge['x1'], bridge['y1'], 20)
        army.append(server.make_unit(kind, owner, x, y))
    game['units'] += army
    server.issue_move(game, owner, {u['id'] for u in army},
                      bridge['x2'] + ux * 330, bridge['y2'] + uy * 330)
    started = time.perf_counter()
    for _ in range(1200):
        server.tick_game(room, .05)
        assert all(not terrain.blocked(u['x'], u['y'], u['size'] * .5) for u in army)
    passed = sum((u['x'] - bridge['x2']) * ux + (u['y'] - bridge['y2']) * uy > 0 for u in army)
    assert passed == 53, ('shared-waypoint deadlock', index, passed)
    print('Bridge %d: 53/53 %s crossed without water/cliff clipping; %.2f ms/tick incl checks'
          % (index, kind, (time.perf_counter() - started) / 1.2))


if __name__ == '__main__':
    for index in range(5):
        crossing(index)
    crossing(0, 'dragon')
