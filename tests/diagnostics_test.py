"""Authenticated telemetry, bounded data, asynchronous persistence and restart."""
import copy
import http.client
import json
import os
import tempfile
import threading
import time
from urllib.error import HTTPError
from urllib.request import Request, build_opener, ProxyHandler
from unittest.mock import patch

from command_priority_test import make_room
import diagnostics
import server
import battle_report


def rejects(fn):
    try:
        fn()
    except ValueError:
        return
    raise AssertionError("expected validation failure")


def main():
    room, alpha, beta = make_room()
    match = room["game"]["uid"]
    payload = {"clientRunId": "test-run", "sequence": 1, "frames": 600, "ms": 10000,
               "p95Ms": 18, "periods": [{"time": 0, "frames": 600, "ms": 10000}],
               "probeSamples": 2, "probeMs": 80, "probeMaxMs": 50, "settings": {"width": 1280},
               "token": "must-not-persist", "chat": "private", "viewerId": beta["id"]}
    assert diagnostics.accept(room, alpha, match, payload, clock=1)
    clean = diagnostics.state(room)["clients"][alpha["id"]]["runs"][0]
    assert clean["viewerId"] == alpha["id"] and clean["averageFps"] == 60
    assert "token" not in clean and "chat" not in clean
    rejects(lambda: diagnostics.accept(room, alpha, match, payload, clock=2))
    assert not diagnostics.accept(room, alpha, match, payload, clock=3)  # duplicate cannot overwrite
    rejects(lambda: diagnostics.accept(room, alpha, "old-match", payload, clock=5))
    for value in (float("nan"), float("inf"), -1, "40", True):
        rejects(lambda: diagnostics.sanitize(dict(payload, frames=value)))
    rejects(lambda: diagnostics.sanitize(dict(payload, periods=[{}] * 121)))
    rejects(lambda: diagnostics.sanitize(dict(payload, clientRunId="../../secret")))
    rejects(lambda: diagnostics.sanitize(dict(payload, clientRunId=123)))
    # A first terminal detail may follow a periodic summary immediately.
    assert diagnostics.accept(room, alpha, match, dict(payload, full=True, sequence=2), clock=3.1)
    assert diagnostics.accept(room, alpha, match, dict(payload, full=False, periods=[], sequence=3), clock=6)
    retained = diagnostics.state(room)["clients"][alpha["id"]]["runs"][0]
    assert retained["periods"] and retained["detailReceivedAt"]
    for i in range(6):
        diagnostics.accept(room, alpha, match, dict(payload, clientRunId="run%d" % i), clock=10+i*3)
    entry = diagnostics.state(room)["clients"][alpha["id"]]
    assert len(entry["runs"]) == 4 and entry["omittedRuns"] == 3
    for i in range(5000):
        room["game"]["elapsed"] = i * 30
        diagnostics.metric(room, "tickWorkMs", 2)
    data = diagnostics.snapshot(room)
    assert len(data["periods"]) <= 120 and data["server"]["tickWorkMs"]["count"] == 5000
    assert sum(p["metrics"].get("tickWorkMs", {}).get("count", 0) for p in data["periods"]) == 5000
    room["game"]["elapsed"] = 20
    with tempfile.TemporaryDirectory() as directory:
        writer = diagnostics.ArchiveWriter(directory)
        with patch.object(diagnostics, "WRITER", writer):
            diagnostics.queue_archive(room, force=True)
            room["status"] = "finished"
            battle_report.finish(room)
            diagnostics.accept(room, beta, match, payload, clock=1)
        writer.close()
        saved = writer.read(match)
        assert saved["status"] == "finished" and saved["report"]["matchId"] == match
        assert beta["id"] in saved["clients"] and not saved["report"].get("incomplete")
        assert "must-not-persist" not in json.dumps(saved)
        reopened = diagnostics.ArchiveWriter(directory)
        reopened.close()
        assert len(reopened.history()["archives"]) == 1
        rejects(lambda: reopened.read("../secret"))
        limited = diagnostics.ArchiveWriter(directory, max_bytes=1)
        limited.submit(saved)
        limited.close()
        assert limited.history()["archiveError"] and os.path.isfile(os.path.join(directory, match + ".json"))

    # Actual HTTP authentication and rate limiting; no writes outside temporary directory.
    room, alpha, beta = make_room()
    match = room["game"]["uid"]
    with patch.dict(server.ROOMS, {room["id"]: room}, clear=True):
        httpd = server.ThreadedHTTPServer(("127.0.0.1", 0), server.GameHandler)
        thread = threading.Thread(target=httpd.serve_forever, daemon=True); thread.start()
        base = "http://127.0.0.1:%d" % httpd.server_address[1]
        opener = build_opener(ProxyHandler({}))
        body = {"roomId": room["id"], "playerId": alpha["id"], "token": alpha["token"], "matchId": match, "performance": payload}
        def post(value):
            try:
                with opener.open(Request(base + "/api/telemetry", json.dumps(value).encode(), {"Content-Type": "application/json"}), timeout=3) as r:
                    return r.status, json.load(r)
            except HTTPError as error:
                return error.code, json.load(error)
        try:
            before = alpha["lastSeen"]
            assert post(dict(body, token="wrong"))[0] == 403
            assert post(dict(body, playerId=beta["id"]))[0] == 403
            assert post(body)[0] == 200
            assert alpha["lastSeen"] == before, "telemetry cannot keep abandoned rooms alive"
            assert post(body)[0] == 400
            # Reject oversized headers before sending the body; Windows may reset
            # a connection when the rejected body is still being uploaded.
            connection = http.client.HTTPConnection("127.0.0.1", httpd.server_address[1], timeout=3)
            connection.putrequest("POST", "/api/telemetry")
            connection.putheader("Content-Length", "140000")
            connection.endheaders()
            assert connection.getresponse().status == 400
            connection.close()
            with opener.open(base + "/api/diagnostics") as r:
                assert json.load(r)["live"][0]["matchId"] == match
            # Remote-admin gate without creating a real LAN listener.
            fake = object.__new__(server.GameHandler)
            fake.path = "/api/diagnostics"; fake.client_address = ("203.0.113.42", 42)
            responses = []; fake.send_json = lambda status, obj: responses.append(status)
            fake.do_GET(); assert responses == [403]
        finally:
            httpd.shutdown(); httpd.server_close(); thread.join(3)
    print("Diagnostics passed: schema/privacy, sessions, rate/stale isolation, bounded windows, final/late archives, restart, quota and HTTP auth/local-only access.")


if __name__ == "__main__":
    main()
