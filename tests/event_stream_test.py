# -*- coding: utf-8 -*-
"""Streaming gzip must deliver each event promptly; slow peers have bounded writes."""
import json
import socket
import time
import zlib
from command_priority_test import make_room
import server
import event_stream


def main():
    for value in ('gzip', 'br, gzip, deflate', '*;q=0.5'):
        assert event_stream.accepts_gzip(value)
    for value in (None, '', 'br', 'gzip;q=0', '*;q=1,gzip;q=0', 'gzip;q=nan'):
        assert not event_stream.accepts_gzip(value)
    room, owner, _ = make_room()
    game = room['game']
    game['units'] = [server.make_unit('overlord', owner['id'], 1500+i%10*40, 900+i//10*40)
                     for i in range(100)]
    server.issue_move(game, owner['id'], {u['id'] for u in game['units']}, 2400, 1700)
    encoder = event_stream.StateEncoder(True)
    decoder = zlib.decompressobj(31)
    raw_bytes = wire_bytes = 0
    durations = []
    for i in range(40):
        server.tick_game(room, .05)
        data = server.public_room(room, viewer_id=owner['id'], full=i==0)
        raw = ('event: state\ndata: '+json.dumps(data,ensure_ascii=False,separators=(',',':'))+'\n\n').encode('utf-8')
        start = time.perf_counter()
        encoded = encoder.encode(raw)
        durations.append((time.perf_counter()-start)*1000)
        assert decoder.decompress(encoded) == raw, 'must decode before any later event arrives'
        assert event_stream.StateEncoder(False).encode(raw) == raw
        raw_bytes += len(raw); wire_bytes += len(encoded)
    assert wire_bytes < raw_bytes * .5
    print('100-unit SSE: %d -> %d bytes (%.1f%% reduction), compression %.3f ms/event'
          % (raw_bytes,wire_bytes,100*(1-wire_bytes/raw_bytes),sum(durations)/len(durations)))

    # Real TCP slow reader: no fake timeout exception. A blocked send used to
    # wait indefinitely; verify the actual socket deadline, outside room locks.
    listener = socket.socket()
    listener.bind(('127.0.0.1',0)); listener.listen(1)
    client = socket.socket()
    client.setsockopt(socket.SOL_SOCKET,socket.SO_RCVBUF,1024)
    client.connect(listener.getsockname())
    peer,_ = listener.accept()
    try:
        event_stream.configure_socket(peer)
        assert peer.gettimeout() == event_stream.WRITE_TIMEOUT
        start = time.perf_counter()
        try:
            # Windows loopback may accept a large initial send into its fast
            # path buffer even with a small SO_SNDBUF. Fill in event-sized chunks.
            chunk = b'x' * 32768
            for _ in range(8192):
                start = time.perf_counter()
                peer.sendall(chunk)
            raise AssertionError('non-reading peer unexpectedly drained entire payload')
        except socket.timeout:
            elapsed = time.perf_counter()-start
            assert .9 < elapsed < 3.5, elapsed
            print('Non-reading TCP peer: write stopped after %.2f seconds' % elapsed)
    finally:
        peer.close();client.close();listener.close()


if __name__ == '__main__':
    main()
