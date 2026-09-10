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
import uuid
from http.server import SimpleHTTPRequestHandler, HTTPServer
from pathlib import Path
from socketserver import ThreadingMixIn
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import server


def fixture_catalog():
    maps = {key: dict(value, resources=server.MAPS[key].get("bonusResources", []))
            for key, value in server.PUBLIC_MAPS.items()}
    # Show one real, deterministic peripheral ore layout, not invented markers.
    # This is an isolated data-only fixture: no rooms, AI or server workers.
    definition = server.MAPS["central_scramble"]
    game = {"map": {"width": 4000, "height": 4000, "seed": 90241},
            "resources": [], "terrainCtx": server.terrain_for_match(definition)}
    server.add_random_resources(
        game, definition["publicOreCount"], definition["spawnPoints"], guarded=False,
        fixed_amount=definition["publicOreAmount"],
        sector_points=definition["botDeployPoints"],
        sector_radius=definition["publicOreSectorRadius"],
        sector_jitter_degrees=definition["publicOreSectorJitterDegrees"],
        sector_clearance=definition["publicOreSectorClearance"])
    maps["central_scramble"]["resources"] = game["resources"]
    return {
        "maps": maps,
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

    def do_POST(self):
        # Local fixture-only screenshot export. No caller-supplied filesystem path,
        # no overwrite, and no cross-origin requests from other websites.
        expected_origin = "http://127.0.0.1:%d" % self.server.server_port
        if (urlsplit(self.path).path != "/capture" or
                self.headers.get("Origin") != expected_origin or
                self.headers.get("Content-Type") != "image/png"):
            self.send_error(403)
            return
        try:
            size = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            size = 0
        if not 8 <= size <= 16 * 1024 * 1024:
            self.send_error(413)
            return
        png = self.rfile.read(size)
        if len(png) != size or not png.startswith(b"\x89PNG\r\n\x1a\n"):
            self.send_error(400)
            return
        folder = ROOT / "artifacts" / "river-art-captures"
        folder.mkdir(parents=True, exist_ok=True)
        target = folder / ("render-" + uuid.uuid4().hex + ".png")
        target.write_bytes(png)
        result = json.dumps({"path": str(target)}, ensure_ascii=False).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(result)))
        self.end_headers()
        self.wfile.write(result)

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
