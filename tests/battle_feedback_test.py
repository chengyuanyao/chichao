"""Cosmetic event identities must be accurate without exposing hidden sources."""
from command_priority_test import make_room
import server


def main():
    room, me, enemy = make_room()
    game = room['game']
    game['structures'] = []
    shooter = server.make_unit('artillery', me['id'], 1200, 1200)
    victim = server.make_unit('tank', enemy['id'], 1250, 1200)
    game['units'] = [shooter, victim]
    game['effects'] = []
    server.launch_projectile(game, shooter, victim, server.UNIT_TYPES['artillery'])
    muzzle = server.public_effect(game['effects'][-1])
    assert muzzle['entityId'] == shooter['id'] and muzzle['entityKind'] == 'artillery'
    assert muzzle['kind'] == 'siege' and 'damage' not in muzzle
    server.tick_projectiles(room, 1, {u['id']: u for u in game['units']})
    impact = next(e for e in game['effects'] if e['type'] == 'impact')
    assert server.public_effect(impact)['kind'] == 'siege'
    assert 'sourceKind' not in server.public_effect(impact)
    server.apply_damage(room, victim, 99999, me['id'])
    server.remove_destroyed(room)
    wreck = next(e for e in game['effects'] if e.get('wreck'))
    assert wreck['entityKind'] == 'tank' and wreck['size'] == victim['size']
    assert server.public_effect(wreck)['entityId'] == victim['id']
    # Removal for deploy/fold is cosmetic completion, not a violent casualty.
    shooter['_silentRemoval'] = True
    shooter['hp'] = 0
    game['effects'] = []
    server.remove_destroyed(room)
    assert not game['effects']
    # Hidden battle feedback uses the same authoritative vision gate as before.
    game['units'] = [server.make_unit('rifle', me['id'], 300, 300)]
    game['effects'] = [dict(wreck, id='far_fx', x=3500, y=3000)]
    server.invalidate_game_snapshot(game)
    assert not server.public_game(game, me['id'])['effects']
    print('Battle event feedback passed: exact muzzle/impact kinds, confirmed wrecks, silent transformation, hidden-effect privacy.')


if __name__ == '__main__':
    main()
