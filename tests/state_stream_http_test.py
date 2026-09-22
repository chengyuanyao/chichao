# -*- coding: utf-8 -*-
"""Actual SSE headers/frames: gzip and legacy identity, full reconnect, cleanup."""
import http.client
import json
import threading
import time
import zlib
from urllib.parse import urlencode
from unittest.mock import patch
from command_priority_test import make_room
import server


def main():
    room, owner, _ = make_room()
    class QuietHandler(server.GameHandler):
        def log_message(self, *_):
            pass

    with patch.dict(server.ROOMS, {room['id']:room}, clear=True):
        httpd=server.ThreadedHTTPServer(('127.0.0.1',0),QuietHandler)
        thread=threading.Thread(target=httpd.serve_forever,daemon=True);thread.start()
        path='/api/events?'+urlencode({'roomId':room['id'],'playerId':owner['id'],'token':owner['token']})
        try:
            for encoding in ('gzip','identity','gzip'):
                connection=http.client.HTTPConnection('127.0.0.1',httpd.server_address[1],timeout=3)
                try:
                    connection.request('GET',path,headers={'Accept-Encoding':encoding})
                    response=connection.getresponse()
                    assert response.status==200
                    assert response.getheader('Content-Encoding')==('gzip' if encoding=='gzip' else None)
                    decoder=zlib.decompressobj(31) if encoding=='gzip' else None
                    buffer=b''; frames=[]
                    while len(frames)<2:
                        chunk=response.read(1)
                        assert chunk, 'stream unexpectedly closed'
                        buffer+=decoder.decompress(chunk) if decoder else chunk
                        while b'\n\n' in buffer:
                            message,buffer=buffer.split(b'\n\n',1)
                            frames.append(json.loads(message.split(b'data: ',1)[1].decode('utf-8')))
                    assert frames[0]['game']['terrain']
                    assert 'terrain' not in frames[1]['game']
                    assert frames[0]['game']['matchId']==room['game']['uid']
                finally:
                    response.close();connection.close()
            deadline=time.monotonic()+3
            while owner['connections'] and time.monotonic()<deadline:
                time.sleep(.05)
            assert owner['connections']==0, 'disconnected SSE leaked player connections'
            print('Actual SSE HTTP: gzip/identity decoding, full reconnect, dynamic frames and connection cleanup passed.')
        finally:
            httpd.shutdown();httpd.server_close();thread.join(3)


if __name__=='__main__':
    main()
