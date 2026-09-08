#!/usr/bin/env python3
"""Read-only browser renderer fixture; never creates rooms or starts game workers.

    python tests/visual_benchmark_server.py --port 8876
    python tests/visual_benchmark_server.py --baseline-public artifacts/baseline/public

Open /tests/visual_benchmark.html?scenario=army&count=400&shadows=structures.
Use &renderer=/baseline/render3d.js to compare an archived public directory.
"""

import argparse
import json
import sys
from http.server import SimpleHTTPRequestHandler, HTTPServer
from pathlib import Path
from socketserver import ThreadingMixIn
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import server


def fixture_catalog():
    return {
        "maps": server.PUBLIC_MAPS,
        "units": server.UNIT_TYPES,
        "structures": server.STRUCTURE_TYPES,
        "sight": {
            "units": {key: server.unit_sight_radius(value)
                      for key, value in server.UNIT_TYPES.items()},
            "structures": {key: value.get("sight", 350)
                           for key, value in server.STRUCTURE_TYPES.items()},
        },
    }


class FixtureHandler(SimpleHTTPRequestHandler):
    baseline_public = None

    extensions_map = dict(SimpleHTTPRequestHandler.extensions_map,
                          **{".js": "text/javascript", ".mjs": "text/javascript",
                             ".webp": "image/webp"})

    def end_headers(self):
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def do_GET(self):
        path = urlsplit(self.path).path
        if path == "/benchmark-data.json":
            data = json.dumps(fixture_catalog(), ensure_ascii=False).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
            return
        if path == "/":
            self.send_response(302)
            self.send_header("Location", "/tests/visual_benchmark.html")
            self.end_headers()
            return
        # Renderer textures are absolute /assets URLs in both revisions.
        if path.startswith("/assets/"):
            self.path = "/public" + self.path
        super().do_GET()

    def translate_path(self, path):
        clean = unquote(urlsplit(path).path)
        if clean.startswith("/baseline/") and self.baseline_public:
            base = self.baseline_public
            target = (base / clean[len("/baseline/"):]).resolve()
        else:
            base = ROOT
            target = (base / clean.lstrip("/")).resolve()
        try:
            target.relative_to(base)
        except ValueError:
            return str(ROOT / "tests" / "__invalid_path__")
        return str(target)


class FixtureServer(ThreadingMixIn, HTTPServer):
    daemon_threads = True


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8876)
    parser.add_argument("--baseline-public", type=Path)
    args = parser.parse_args()
    if args.baseline_public:
        FixtureHandler.baseline_public = args.baseline_public.resolve(strict=True)
    httpd = FixtureServer(("127.0.0.1", args.port), FixtureHandler)
    print("Renderer fixture: http://127.0.0.1:%d/tests/visual_benchmark.html" % args.port,
          flush=True)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()


if __name__ == "__main__":
    main()
