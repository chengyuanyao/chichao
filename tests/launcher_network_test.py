"""Explicit binding must also work for launcher health and hosted AI clients."""
import os
import sys
import threading
from unittest.mock import patch
from urllib.request import ProxyHandler, build_opener

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import server
from server_agent_lifecycle_test import make_room


def main():
    for host, expected in (("0.0.0.0", "127.0.0.1"), ("127.0.0.1", "127.0.0.1"),
                           ("192.168.137.1", "192.168.137.1")):
        with patch.object(server, "HOST", host):
            assert server.local_server_host() == expected
    with patch.object(server, "HOST", "127.0.0.2"), patch.object(server, "RTS_AGENT_DIR", "/fake"), \
            patch.object(server, "RTS_AGENT_EXECUTABLE", "/fake/python"):
        room, player = make_room()
        request = server.prepare_server_agent(room, player)
        try:
            command = request["command"]
            assert command[command.index("--base") + 1] == "http://127.0.0.2:%d" % server.PORT
        finally:
            server.stop_server_agent(room["id"], player["id"])
        httpd = server.ThreadedHTTPServer((server.local_server_host(), 0), server.GameHandler)
        worker = threading.Thread(target=httpd.serve_forever, daemon=True)
        worker.start()
        try:
            port = httpd.server_address[1]
            with build_opener(ProxyHandler({})).open("http://127.0.0.2:%d/api/health" % port, timeout=3) as response:
                assert response.status == 200
        finally:
            httpd.shutdown()
            httpd.server_close()
            worker.join(3)
    print("Launcher network: bind-specific health and hosted AI URLs passed.")


if __name__ == "__main__":
    main()
