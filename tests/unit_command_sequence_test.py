# -*- coding: utf-8 -*-
"""Late/duplicate HTTP unit orders must not undo newer orders."""
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import server
from command_priority_test import make_room, tick_for


def main():
    room, owner, enemy = make_room()
    game = room['game']
    channel = server.open_command_channel(room, owner, {'matchId': game['uid']})['channel']
    units = [server.make_unit('overlord', owner['id'], 1700 + i % 8 * 36,
                              800 + i // 8 * 36) for i in range(53)]
    game['units'] = units
    ids = [u['id'] for u in units]

    def command(seq, kind='move', chosen=None, **extra):
        payload = {'command': kind, 'unitIds': ids if chosen is None else chosen,
                   'x': 2400, 'y': 900,
                   'input': {'matchId': game['uid'], 'channel': channel, 'sequence': seq}}
        payload.update(extra)
        return server.handle_sequenced_command(room, owner, payload)

    assert command(2)['acceptedUnits'] == 53
    before = [(u['x'], u['y']) for u in units]
    tick_for(room, 1.0)
    moved = sum((u['x']-p[0])**2 + (u['y']-p[1])**2 > 25 for u, p in zip(units, before))
    assert moved == 53, moved
    command(4, 'stop')
    assert command(3)['acceptedUnits'] == 0
    assert command(4)['acceptedUnits'] == 0
    assert all(u['order'] != 'move' for u in units)
    # Partial overlap and independently reordered groups, not a global watermark.
    command(6, chosen=ids[:1], x=2600)
    assert command(5, chosen=ids[:2], x=2100)['acceptedUnits'] == 1
    assert units[0]['_inputSequence'] == 6 and units[1]['_inputSequence'] == 5
    alien = server.make_unit('tank', enemy['id'], 500, 500)
    game['units'].append(alien)
    assert command(7, chosen=[alien['id']])['acceptedUnits'] == 0
    assert '_inputSequence' not in alien
    mcv = server.make_unit('mcv', owner['id'], 1500, 1700)
    game['units'].append(mcv)
    assert command(8, 'deploy', [mcv['id']])['acceptedUnits'] == 1
    buildings = len(game['structures'])
    assert command(8, 'deploy', [mcv['id']])['acceptedUnits'] == 0
    assert len(game['structures']) == buildings
    # Patrol retries cannot append a waypoint twice.
    command(9, 'patrol', ids[:1], x=2200)
    nodes = list(units[0]['_patrolPoints'])
    assert command(9, 'patrol', ids[:1], x=2200)['acceptedUnits'] == 0
    assert units[0]['_patrolPoints'] == nodes
    # Old pages/matches cannot reclaim control; fresh channel starts at seq 1.
    fresh = server.open_command_channel(room, owner, {'matchId': game['uid']})['channel']
    try:
        command(99)
        raise AssertionError('old channel accepted')
    except ValueError:
        pass
    channel = fresh
    assert command(1)['acceptedUnits'] == 53
    old_match = game['uid']
    game['uid'] = 'new-match'
    try:
        command(2, input={'channel': channel, 'sequence': 2, 'matchId': old_match})
        raise AssertionError('old match accepted')
    except ValueError:
        pass
    print('Sequenced orders: 53 moving overlords, stale stop/move, duplicate, overlap, ownership and rematch passed')


if __name__ == '__main__':
    main()
