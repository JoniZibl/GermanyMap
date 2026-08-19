#!/usr/bin/env python3
"""
Tiny local tile server for previewing a build — no internet, no CDN.

    python3 scripts/serve_tiles.py --tiles output/koeln_regbez_game_map.mbtiles

Then point any MapLibre/Mapbox viewer at:
    http://localhost:8080/style.json      the style from style/ with local tile URLs
    http://localhost:8080/tiles/{z}/{x}/{y}.pbf
    http://localhost:8080/tiles.json      TileJSON
"""
from __future__ import annotations

import argparse
import json
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import mvt  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent


class Handler(BaseHTTPRequestHandler):
    archive: mvt.TileArchive
    style_path: Path

    def log_message(self, fmt, *args):  # quieter output
        pass

    def _send(self, code, body: bytes, ctype: str, gzip_encoded=False):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        if gzip_encoded:
            self.send_header("Content-Encoding", "gzip")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):  # noqa: N802
        path = self.path.split("?")[0]
        if path in ("/", "/index.html"):
            self._send(200, INDEX.encode(), "text/html; charset=utf-8")
            return
        if path == "/tiles.json":
            self._send(200, json.dumps(self.tilejson()).encode(), "application/json")
            return
        if path == "/style.json":
            self._send(200, json.dumps(self.style()).encode(), "application/json")
            return
        if path.startswith("/tiles/") and path.endswith(".pbf"):
            try:
                z, x, y = (int(p) for p in path[len("/tiles/"):-4].split("/"))
            except ValueError:
                self._send(400, b"bad tile path", "text/plain")
                return
            data = self.archive.get_tile(z, x, y)
            if data is None:
                self._send(204, b"", "application/x-protobuf")
                return
            is_gzip = len(data) >= 2 and data[0] == 0x1F and data[1] == 0x8B
            self._send(200, data, "application/x-protobuf", gzip_encoded=is_gzip)
            return
        self._send(404, b"not found", "text/plain")

    def tilejson(self) -> dict:
        meta = self.archive.metadata()
        base = f"http://{self.headers.get('Host', 'localhost:8080')}"
        tj = {
            "tilejson": "3.0.0",
            "name": meta.get("name", "Germany Vector Map"),
            "attribution": meta.get("attribution", ""),
            "minzoom": int(meta.get("minzoom", 0)),
            "maxzoom": int(meta.get("maxzoom", 14)),
            "tiles": [f"{base}/tiles/{{z}}/{{x}}/{{y}}.pbf"],
        }
        if "bounds" in meta:
            tj["bounds"] = [float(v) for v in meta["bounds"].split(",")]
        if "json" in meta:
            tj["vector_layers"] = json.loads(meta["json"]).get("vector_layers", [])
        return tj

    def style(self) -> dict:
        style = json.loads(self.style_path.read_text(encoding="utf-8"))
        base = f"http://{self.headers.get('Host', 'localhost:8080')}"
        for source in style.get("sources", {}).values():
            source.pop("url", None)
            source["tiles"] = [f"{base}/tiles/{{z}}/{{x}}/{{y}}.pbf"]
            meta = self.archive.metadata()
            source["minzoom"] = int(meta.get("minzoom", 0))
            source["maxzoom"] = int(meta.get("maxzoom", 14))
        return style


INDEX = """<!doctype html><meta charset="utf-8">
<title>Germany Vector Map — local preview</title>
<style>body{font:14px/1.6 system-ui,sans-serif;margin:3rem auto;max-width:44rem;padding:0 1rem}
code{background:#f2f2f2;padding:.1rem .3rem;border-radius:3px}</style>
<h1>Germany Vector Map — local tile server</h1>
<p>The tiles are being served. This page deliberately loads no map library from a CDN,
so the preview stays fully offline.</p>
<ul>
  <li><a href="/style.json">/style.json</a> — MapLibre style pointing at this server</li>
  <li><a href="/tiles.json">/tiles.json</a> — TileJSON with the layer list</li>
  <li><code>/tiles/{z}/{x}/{y}.pbf</code> — the vector tiles</li>
</ul>
<p>Open <code>http://localhost:8080/style.json</code> in
<a href="https://maplibre.org/maputnik/">Maputnik</a>, QGIS, or any MapLibre viewer.</p>
"""


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--tiles", required=True)
    ap.add_argument("--style", default=str(ROOT / "style" / "germany-basemap.json"))
    ap.add_argument("--port", type=int, default=8080)
    args = ap.parse_args()

    Handler.archive = mvt.open_archive(args.tiles)
    Handler.style_path = Path(args.style)
    server = ThreadingHTTPServer(("0.0.0.0", args.port), Handler)
    print(f"serving {args.tiles} on http://localhost:{args.port}  (Ctrl-C to stop)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped")
    finally:
        Handler.archive.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
