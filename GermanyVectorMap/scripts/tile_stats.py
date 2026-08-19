#!/usr/bin/env python3
"""
Measure a generated tileset and suggest size optimizations.

Reports everything the build is supposed to account for:
  * size of the source OSM PBF
  * size of the finished vector tile archive
  * number of tiles and the zoom range
  * layers contained in the tileset
  * the largest layers by storage
  * the approximate reduction in percent

If Planetiler was run with --output_layerstats (the build scripts do), the
per-layer numbers come from the exact <archive>.layerstats.tsv.gz it wrote.
Otherwise the tiles are decoded directly, which is slower but needs nothing
beyond the standard library.

    python3 scripts/tile_stats.py --tiles output/germany_game_map.mbtiles \
                                  --input input/germany-latest.osm.pbf
"""

from __future__ import annotations

import argparse
import collections
import gzip
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import mvt  # noqa: E402


def human(num_bytes: float) -> str:
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if abs(num_bytes) < 1024 or unit == "TB":
            return f"{num_bytes:,.1f} {unit}" if unit != "B" else f"{int(num_bytes)} B"
        num_bytes /= 1024
    return f"{num_bytes:.1f} TB"


# ----------------------------------------------------------------- gathering --


def read_layerstats(path: Path):
    """Parses Planetiler's layerstats TSV into per-layer and per-zoom aggregates."""
    layers = collections.defaultdict(
        lambda: {"bytes": 0, "features": 0, "attr_bytes": 0, "tiles": 0,
                 "min_zoom": 99, "max_zoom": -1, "by_zoom": collections.Counter()})
    zoom_bytes = collections.Counter()
    zoom_tiles = collections.defaultdict(set)
    total_archived = {}

    with gzip.open(path, "rt") as fh:
        header = fh.readline().rstrip("\n").split("\t")
        idx = {name: i for i, name in enumerate(header)}
        for line in fh:
            parts = line.rstrip("\n").split("\t")
            if len(parts) < len(header):
                continue
            z = int(parts[idx["z"]])
            x = int(parts[idx["x"]])
            y = int(parts[idx["y"]])
            name = parts[idx["layer"]]
            lb = int(parts[idx["layer_bytes"]])
            lf = int(parts[idx["layer_features"]])
            ab = int(parts[idx["layer_attr_bytes"]])
            entry = layers[name]
            entry["bytes"] += lb
            entry["features"] += lf
            entry["attr_bytes"] += ab
            entry["tiles"] += 1
            entry["min_zoom"] = min(entry["min_zoom"], z)
            entry["max_zoom"] = max(entry["max_zoom"], z)
            entry["by_zoom"][z] += lb
            zoom_bytes[z] += lb
            zoom_tiles[z].add((x, y))
            total_archived[(z, x, y)] = int(parts[idx["archived_tile_bytes"]])

    return (dict(layers), zoom_bytes,
            {z: len(v) for z, v in zoom_tiles.items()},
            sum(total_archived.values()))


def scan_tiles(archive_path: Path, limit: int | None):
    """Fallback: decode tiles from the archive itself (uncompressed layer sizes)."""
    layers = collections.defaultdict(
        lambda: {"bytes": 0, "features": 0, "attr_bytes": 0, "tiles": 0,
                 "min_zoom": 99, "max_zoom": -1, "by_zoom": collections.Counter()})
    zoom_bytes = collections.Counter()
    zoom_tiles = collections.Counter()
    archive = mvt.MBTiles(archive_path)
    scanned = 0
    for z, x, y, raw in archive.iter_tiles():
        zoom_tiles[z] += 1
        try:
            decoded = mvt.decode_tile(raw)
        except Exception:
            continue
        for name, layer in decoded.items():
            approx = sum(sum(len(r) for r in f.rings) * 4 + 16 for f in layer.features)
            entry = layers[name]
            entry["bytes"] += approx
            entry["features"] += len(layer.features)
            entry["tiles"] += 1
            entry["min_zoom"] = min(entry["min_zoom"], z)
            entry["max_zoom"] = max(entry["max_zoom"], z)
            entry["by_zoom"][z] += approx
            zoom_bytes[z] += approx
        scanned += 1
        if limit and scanned >= limit:
            break
    archive.close()
    return dict(layers), zoom_bytes, dict(zoom_tiles), 0


# --------------------------------------------------------------- suggestions --

# layer -> (knob description, config file the knob lives in)
TUNING = {
    "building": [
        "raise `layers.building.min_zoom` in config/zoom_levels.yml (14 -> 15) so buildings "
        "only appear at the deepest zoom",
        "raise `building.min_pixel_size` in config/layers.yml (2.0 -> 3.0) to drop sheds and "
        "garages",
        "set `building.enabled: false` if the map never shows individual houses",
    ],
    "path": [
        "raise `layers.path.min_zoom` (14 -> 15)",
        "trim `path.classes` — dropping `footway` usually removes most of the volume",
        "raise `path.merge_min_length` (1.0 -> 2.0)",
    ],
    "road_service": [
        "raise `layers.road_service.min_zoom` (14 -> 15)",
        "set `road_service.enabled: false` — service roads rarely matter on a game map",
    ],
    "road_residential": [
        "raise `layers.road_residential.min_zoom` (12 -> 13)",
        "raise `road_residential.name_min_zoom` (14 -> 15) to drop street name labels",
    ],
    "forest": [
        "raise `forest.min_pixel_size` (3.0 -> 5.0)",
        "raise `forest.merge_min_area` (2.0 -> 4.0)",
    ],
    "grass": [
        "raise `grass.min_pixel_size` (3.0 -> 6.0)",
        "set `grass.enabled: false` — meadows are the most optional nature layer",
    ],
    "garden": ["raise `layers.garden.min_zoom` (13 -> 14)", "set `garden.enabled: false`"],
    "water": ["raise `water.min_pixel_size` (2.0 -> 3.0)"],
    "waterway": [
        "set `waterway.include_stream: false` to drop the smallest brooks",
        "raise `features.waterway.stream` (12 -> 13) in config/zoom_levels.yml",
    ],
    "boundary": [
        "set `boundary.include_counties: false` to drop the Landkreis lines",
    ],
    "rail": ["raise `features.rail.other` (11 -> 12)"],
}

POI_HINT = ("raise the layer's zoom in `features.poi` (config/zoom_levels.yml) or set "
            "`enabled: false` in config/layers.yml")


def suggestions(layers: dict, zoom_bytes: collections.Counter, total: int, max_zoom: int) -> list[str]:
    out: list[str] = []
    if total <= 0:
        return out
    ranked = sorted(layers.items(), key=lambda kv: kv[1]["bytes"], reverse=True)

    for name, entry in ranked[:6]:
        share = entry["bytes"] / total * 100
        if share < 4:
            continue
        head = f"`{name}` uses {share:.1f}% of all layer bytes"
        if name in TUNING:
            for tip in TUNING[name]:
                out.append(f"{head} -> {tip}")
        elif name.startswith("poi_"):
            out.append(f"{head} -> {POI_HINT}")
        else:
            out.append(f"{head} -> raise its `min_zoom` or `min_pixel_size`")

    # attribute-heavy layers: names are usually the culprit
    for name, entry in ranked[:10]:
        if entry["bytes"] > total * 0.02 and entry["attr_bytes"] > entry["bytes"] * 0.45:
            out.append(
                f"`{name}` spends {entry['attr_bytes'] / entry['bytes'] * 100:.0f}% of its bytes on "
                f"attributes -> raise `{name}.name_min_zoom` in config/layers.yml")

    # zoom distribution
    if zoom_bytes:
        deepest = zoom_bytes.get(max_zoom, 0)
        if total and deepest / total > 0.55:
            out.append(
                f"zoom {max_zoom} alone holds {deepest / total * 100:.0f}% of the data -> lowering "
                f"`tileset.max_zoom` by 1 roughly divides the archive by ~3 (renderers keep "
                f"drawing deeper zooms by overzooming)")

    road_layers = [n for n in layers if n.startswith("road_")]
    if len(road_layers) > 3:
        road_share = sum(layers[n]["bytes"] for n in road_layers) / total * 100
        if road_share > 25:
            out.append(
                f"the {len(road_layers)} road layers together use {road_share:.1f}% -> set "
                f"`road_layer_mode: single` in config/layers.yml to store them in one layer with "
                f"a `class` attribute (fewer key/value tables per tile)")

    out.append("global lever: raise `simplification.tolerance` in config/zoom_levels.yml "
               "(0.375 -> 0.5) — fewer points on every line and outline at every zoom")
    return out


# ---------------------------------------------------------------------- main --


def main() -> int:
    ap = argparse.ArgumentParser(description="Measure a Germany Vector Map tileset.")
    ap.add_argument("--tiles", required=True, help="output .mbtiles or .pmtiles")
    ap.add_argument("--input", help="source .osm.pbf, for the reduction figure")
    ap.add_argument("--layerstats", help="Planetiler layerstats tsv.gz (auto-detected)")
    ap.add_argument("--also", action="append", default=[],
                    help="extra archive to list the size of (e.g. the .pmtiles twin)")
    ap.add_argument("--top", type=int, default=15, help="how many layers to list")
    ap.add_argument("--json", help="write the report as JSON to this path")
    ap.add_argument("--scan-limit", type=int, default=0,
                    help="max tiles to decode in fallback mode (0 = all)")
    args = ap.parse_args()

    tiles_path = Path(args.tiles)
    if not tiles_path.is_file():
        print(f"error: {tiles_path} not found", file=sys.stderr)
        return 1

    tiles_size = tiles_path.stat().st_size
    pbf_size = Path(args.input).stat().st_size if args.input and Path(args.input).is_file() else 0

    stats_path = Path(args.layerstats) if args.layerstats else Path(
        str(tiles_path) + ".layerstats.tsv.gz")
    used_layerstats = stats_path.is_file()
    if used_layerstats:
        layers, zoom_bytes, zoom_tiles, _ = read_layerstats(stats_path)
    else:
        layers, zoom_bytes, zoom_tiles, _ = scan_tiles(tiles_path, args.scan_limit or None)

    with mvt.open_archive(tiles_path) as archive:
        meta = archive.metadata()
        tile_count = archive.tile_count()
        if isinstance(archive, mvt.MBTiles):
            zoom_tiles = archive.tile_counts_by_zoom() or zoom_tiles

    min_zoom = int(meta.get("minzoom", min(zoom_tiles) if zoom_tiles else 0))
    max_zoom = int(meta.get("maxzoom", max(zoom_tiles) if zoom_tiles else 14))
    total_layer_bytes = sum(e["bytes"] for e in layers.values()) or 1

    # ------------------------------------------------------------------ print
    w = 78
    print("=" * w)
    print(f"  {meta.get('name', tiles_path.stem)} — tileset report")
    print("=" * w)
    print(f"  source OSM PBF      : {human(pbf_size) if pbf_size else '(not given)'}"
          + (f"   [{args.input}]" if pbf_size else ""))
    print(f"  vector tile archive : {human(tiles_size)}   [{tiles_path.name}]")
    for extra in args.also:
        p = Path(extra)
        if p.is_file():
            print(f"                        {human(p.stat().st_size)}   [{p.name}]")
    if pbf_size:
        reduction = (1 - tiles_size / pbf_size) * 100
        print(f"  reduction vs. PBF   : {reduction:.1f}%  "
              f"({human(pbf_size)} -> {human(tiles_size)})")
    print(f"  tiles               : {tile_count:,}")
    print(f"  zoom range          : z{min_zoom}–z{max_zoom}")
    print(f"  layers              : {len(layers)}")
    print(f"  bounds              : {meta.get('bounds', '?')}")
    print(f"  attribution         : {meta.get('attribution', '?')[:60]}")
    print(f"  layer sizes from    : {'Planetiler layerstats' if used_layerstats else 'tile scan (approximate)'}")

    print("\n" + "-" * w)
    print("  tiles per zoom")
    print("-" * w)
    for z in sorted(zoom_tiles):
        bar = "#" * min(40, int(40 * zoom_bytes.get(z, 0) / max(zoom_bytes.values() or [1])))
        print(f"   z{z:<3} {zoom_tiles[z]:>10,} tiles   {human(zoom_bytes.get(z, 0)):>12}  {bar}")

    print("\n" + "-" * w)
    print(f"  largest layers by storage (top {args.top})")
    print("-" * w)
    print(f"   {'layer':<20}{'bytes':>12}{'share':>8}{'features':>12}   zooms")
    ranked = sorted(layers.items(), key=lambda kv: kv[1]["bytes"], reverse=True)
    for name, entry in ranked[:args.top]:
        share = entry["bytes"] / total_layer_bytes * 100
        zr = f"z{entry['min_zoom']}–z{entry['max_zoom']}" if entry["max_zoom"] >= 0 else "-"
        print(f"   {name:<20}{human(entry['bytes']):>12}{share:>7.1f}%"
              f"{entry['features']:>12,}   {zr}")
    if len(ranked) > args.top:
        rest = sum(e["bytes"] for _, e in ranked[args.top:])
        print(f"   {'(' + str(len(ranked) - args.top) + ' more)':<20}{human(rest):>12}"
              f"{rest / total_layer_bytes * 100:>7.1f}%")

    tips = suggestions(layers, zoom_bytes, total_layer_bytes, max_zoom)
    if tips:
        print("\n" + "-" * w)
        print("  size optimization suggestions")
        print("-" * w)
        for tip in tips:
            print(f"   * {tip}")
    print("=" * w)

    if args.json:
        report = {
            "archive": str(tiles_path),
            "archive_bytes": tiles_size,
            "source_pbf": args.input,
            "source_pbf_bytes": pbf_size,
            "reduction_percent": round((1 - tiles_size / pbf_size) * 100, 2) if pbf_size else None,
            "tiles": tile_count,
            "min_zoom": min_zoom,
            "max_zoom": max_zoom,
            "tiles_per_zoom": {str(k): v for k, v in sorted(zoom_tiles.items())},
            "bytes_per_zoom": {str(k): v for k, v in sorted(zoom_bytes.items())},
            "layers": {
                name: {
                    "bytes": e["bytes"],
                    "share_percent": round(e["bytes"] / total_layer_bytes * 100, 2),
                    "features": e["features"],
                    "attr_bytes": e["attr_bytes"],
                    "min_zoom": e["min_zoom"],
                    "max_zoom": e["max_zoom"],
                } for name, e in ranked},
            "suggestions": tips,
            "metadata": {k: v for k, v in meta.items() if k != "json"},
        }
        Path(args.json).write_text(json.dumps(report, indent=2, ensure_ascii=False))
        print(f"  JSON report written to {args.json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
