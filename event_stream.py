# -*- coding: utf-8 -*-
"""Bounded SSE transport; compression is per connection and outside room locks."""
import socket
import zlib

WRITE_TIMEOUT = 1.5


def accepts_gzip(value):
    accepted = {}
    for item in (value or '').lower().split(','):
        parts = item.strip().split(';')
        name = parts[0].strip()
        quality = 1.0
        for parameter in parts[1:]:
            if parameter.strip().startswith('q='):
                try:
                    quality = float(parameter.strip()[2:])
                except ValueError:
                    quality = 0.0
        accepted[name] = 0 < quality <= 1
    return accepted.get('gzip', accepted.get('*', False))


class StateEncoder(object):
    def __init__(self, gzip_enabled):
        self.compressor = zlib.compressobj(1, zlib.DEFLATED, 31) if gzip_enabled else None

    def encode(self, message):
        if self.compressor is None:
            return message
        # Each SSE event must be immediately decodable without waiting for a
        # later event or an end-of-stream trailer. Browser handles decompression.
        return self.compressor.compress(message) + self.compressor.flush(zlib.Z_SYNC_FLUSH)


def configure_socket(connection):
    connection.settimeout(WRITE_TIMEOUT)
    connection.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
    # Request a small kernel send buffer; OS-specific actual sizes can differ.
    # Do not change receive buffers
    # or other HTTP endpoints. One blocking send, never a producer-side queue.
    connection.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, 16384)
