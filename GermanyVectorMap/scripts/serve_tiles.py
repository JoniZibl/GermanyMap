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
    maplibre_js: str
    maplibre_css: str

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
            page = (VIEWER
                    .replace("MAPLIBRE_JS", self.maplibre_js)
                    .replace("MAPLIBRE_CSS", self.maplibre_css))
            self._send(200, page.encode(), "text/html; charset=utf-8")
            return
        if path.startswith("/vendor/") and VENDOR.is_dir():
            target = (VENDOR / path[len("/vendor/"):]).resolve()
            if VENDOR.resolve() in target.parents and target.is_file():
                ctype = ("text/css" if target.suffix == ".css"
                         else "text/javascript" if target.suffix in (".mjs", ".js")
                         else "application/octet-stream")
                self._send(200, target.read_bytes(), ctype)
                return
            self._send(404, b"not found", "text/plain")
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


VIEWER = """<!doctype html>
<meta charset="utf-8">
<title>Germany Vector Map — preview</title>
<link rel="stylesheet" href="MAPLIBRE_CSS">
<style>
  html, body { margin:0; height:100%; background:#F4F1EA; font:13px/1.5 system-ui, sans-serif; }
  #map { position:absolute; inset:0; }
  #hud { position:absolute; z-index:2; top:10px; left:10px; background:rgba(255,255,255,.92);
         padding:10px 13px; border-radius:8px; box-shadow:0 1px 6px rgba(0,0,0,.18); max-width:19rem; }
  #hud b { display:block; margin-bottom:.35rem; }
  #hud code { background:#eee; padding:0 .25rem; border-radius:3px; }
  #err { color:#a33; }
</style>
<div id="hud">
  <b>Germany Vector Map</b>
  <span id="info">loading…</span>
  <div id="err"></div>
</div>
<div id="map"></div>
<script type="module">
  // maplibre-gl v6 ships named exports only — there is no default export
  import { Map, NavigationControl, ScaleControl } from "MAPLIBRE_JS";
  const info = document.getElementById("info");
  const err  = document.getElementById("err");
  try {
    const tj = await (await fetch("/tiles.json")).json();
    const map = new Map({
      container: "map",
      style: "/style.json",
      center: tj.bounds ? [(tj.bounds[0]+tj.bounds[2])/2, (tj.bounds[1]+tj.bounds[3])/2] : [10.45, 51.16],
      zoom: tj.bounds ? 6 : 5,
      minZoom: tj.minzoom, maxZoom: 18,
      attributionControl: { compact: false },
    });
    map.addControl(new NavigationControl());
    map.addControl(new ScaleControl());
    if (tj.bounds) map.fitBounds([[tj.bounds[0],tj.bounds[1]],[tj.bounds[2],tj.bounds[3]]], {padding:20, duration:0});
    const layers = (tj.vector_layers || []).length;
    const upd = () => info.innerHTML =
      `${layers} layers · tiles z${tj.minzoom}–z${tj.maxzoom}<br>` +
      `view z${map.getZoom().toFixed(1)}` +
      (map.getZoom() > tj.maxzoom ? ` <i>(overzoomed from z${tj.maxzoom})</i>` : "");
    map.on("load", upd); map.on("zoom", upd);
    map.on("error", e => { err.textContent = String(e.error || e); });
  } catch (e) {
    err.textContent = "could not start: " + e;
  }
</script>
"""

# The map viewer is the one place that pulls a library off the network. The tiles,
# the style and the data stay local. Vendor it for a fully offline preview:
#   cd tools && npm install maplibre-gl
# and the server picks up tools/node_modules automatically.
CDN_JS = "https://unpkg.com/maplibre-gl@6.4.1/dist/maplibre-gl.mjs"
CDN_CSS = "https://unpkg.com/maplibre-gl@6.4.1/dist/maplibre-gl.css"
VENDOR = ROOT / "tools" / "node_modules" / "maplibre-gl" / "dist"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--tiles", required=True)
    ap.add_argument("--style", default=str(ROOT / "style" / "germany-basemap.json"))
    ap.add_argument("--port", type=int, default=8080)
    args = ap.parse_args()

    Handler.archive = mvt.open_archive(args.tiles)
    Handler.style_path = Path(args.style)
    if VENDOR.is_dir():
        Handler.maplibre_js = "/vendor/maplibre-gl.mjs"
        Handler.maplibre_css = "/vendor/maplibre-gl.css"
        print("using the vendored maplibre-gl in tools/node_modules — fully offline")
    else:
        Handler.maplibre_js, Handler.maplibre_css = CDN_JS, CDN_CSS
        print("map library comes from unpkg.com (the only network call).")
        print("For a fully offline preview:  cd tools && npm install maplibre-gl")
    server = ThreadingHTTPServer(("0.0.0.0", args.port), Handler)
    print()
    print(f"  Map:    http://localhost:{args.port}/")
    print(f"  Style:  http://localhost:{args.port}/style.json")
    print(f"  Tiles:  http://localhost:{args.port}/tiles/{{z}}/{{x}}/{{y}}.pbf")
    print(f"\n  serving {args.tiles}  (Ctrl-C to stop)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped")
    finally:
        Handler.archive.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
