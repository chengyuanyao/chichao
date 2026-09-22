# -*- coding: utf-8 -*-
"""Real HTTP: hold an old move before dispatch; stop must overtake it safely."""
import json
import threading
from urllib.request import Request, build_opener, ProxyHandler
from urllib.error import HTTPError
from unittest.mock import patch
from command_priority_test import make_room
import server


def main():
    room, owner, _ = make_room()
    game = room['game']
    unit = server.make_unit('overlord', owner['id'], 1500, 900)
    game['units'] = [unit]
    entered, release = threading.Event(), threading.Event()

    class DelayedHandler(server.GameHandler):
        def log_message(self, *_):
            pass

        def room_action(self, data):
            if data.get('payload', {}).get('input', {}).get('sequence') == 1:
                entered.set()
                assert release.wait(5), 'test failed to release delayed request'
            return super(DelayedHandler, self).room_action(data)

    with patch.dict(server.ROOMS, {room['id']: room}, clear=True):
        httpd = server.ThreadedHTTPServer(('127.0.0.1', 0), DelayedHandler)
        thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        thread.start()
        url = 'http://127.0.0.1:%d/api/action' % httpd.server_address[1]

        def post(action, payload, token=None):
            data = {'roomId': room['id'], 'playerId': owner['id'],
                    'token': token or owner['token'], 'action': action, 'payload': payload}
            opener = build_opener(ProxyHandler({}))
            request = Request(url, json.dumps(data).encode(), {'Content-Type': 'application/json'})
            try:
                with opener.open(request, timeout=6) as response:
                    return response.status, json.load(response)
            except HTTPError as error:
                return error.code, json.load(error)

        try:
            assert post('commandChannel', {'matchId': game['uid']}, 'invalid')[0] == 403
            status, opened = post('commandChannel', {'matchId': game['uid']})
            assert status == 200 and 'room' not in opened
            payload = {'command': 'move', 'unitIds': [unit['id']], 'x': 2500, 'y': 900,
                       'input': {'matchId': game['uid'], 'channel': opened['channel'], 'sequence': 1}}
            delayed = []
            worker = threading.Thread(target=lambda: delayed.append(post('command', payload)), daemon=True)
            worker.start()
            assert entered.wait(3)
            stop = dict(payload, command='stop', input=dict(payload['input'], sequence=2))
            status, ack = post('command', stop)
            assert status == 200 and ack['acceptedUnits'] == 1
            assert 'room' not in ack and len(json.dumps(ack)) < 100
            release.set()
            worker.join(5)
            assert delayed[0][1]['acceptedUnits'] == 0
            assert unit['order'] != 'move'
            assert post('command', stop)[1]['acceptedUnits'] == 0
            # Existing non-sequenced clients / AI keep their full dynamic response.
            status, legacy = post('command', {'command': 'stop', 'unitIds': [unit['id']]})
            assert status == 200 and legacy['room']['game']['matchId'] == game['uid']
            assert '_inputSequence' not in json.dumps(legacy)
            assert 'inputChannels' not in json.dumps(legacy)
            print('HTTP regression: H overtook delayed move; late/duplicate orders ignored; ACK %d vs snapshot %d bytes; auth/privacy/legacy passed'
                  % (len(json.dumps(ack)), len(json.dumps(legacy))))
        finally:
            release.set()
            httpd.shutdown()
            httpd.server_close()
            thread.join(3)


if __name__ == '__main__':
    main()
