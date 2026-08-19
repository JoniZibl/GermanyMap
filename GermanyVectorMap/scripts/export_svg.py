#!/usr/bin/env python3
"""
Export a map section from the vector tiles as a layered, Figma-friendly SVG.

The vector tiles stay the master data — this only cuts out a section and writes
it as editable vector paths, one <g> group per map layer.

    # a named region from config/regions.yml
    python3 scripts/export_svg.py --tiles output/germany_game_map.mbtiles \
        --region koeln --out exports/koeln_test.svg

    # all of Germany, low detail
    python3 scripts/export_svg.py --tiles output/germany_game_map.mbtiles \
        --region germany --zoom 6 --out exports/germany_overview.svg

    # any bbox you like  (min_lon,min_lat,max_lon,max_lat)
    python3 scripts/export_svg.py --tiles output/germany_game_map.mbtiles \
        --bbox 6.90,50.92,7.02,50.98 --zoom 14 --out exports/ausschnitt.svg

    # one file per layer, for maximum control in Figma
    python3 scripts/export_svg.py --tiles output/germany_game_map.mbtiles \
        --region leverkusen --split --out exports/leverkusen/

Colors: the groups get neutral placeholder fills so the file is visible when you
open it. They are group-level attributes only — recolor a whole layer in Figma by
selecting its group, or pass --no-style to get pure geometry with no colors at all.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import mvt  # noqa: E402

TILE_PX = 256.0

# Draw order: first entry is painted first (bottom), last is on top.
DEFAULT_ORDER = [
    "land", "grass", "forest", "park", "garden", "water", "waterway", "coastline",
    "building",
    "rail",
    "path", "road_service", "road_residential", "road_tertiary", "road_secondary",
    "road_primary", "road_trunk", "road_motorway", "road",
    "boundary",
    "transport",
    "place_village", "place_suburb", "place_town", "place_city",
    "poi_castle", "poi_church", "poi_ruin", "poi_monument", "poi_viewpoint", "poi_museum",
    "poi_tower", "poi_historic",
]

# Neutral placeholder palette — greys and muted tones on purpose, so nobody
# mistakes it for the final design. Override with --palette or recolor in Figma.
DEFAULT_PALETTE = {
    "land": {"fill": "#ECE9E4", "stroke": "none"},
    "grass": {"fill": "#DFE4D7", "stroke": "none"},
    "forest": {"fill": "#D3DBCB", "stroke": "none"},
    "park": {"fill": "#DCE5D5", "stroke": "none"},
    "garden": {"fill": "#E1E7D9", "stroke": "none"},
    "water": {"fill": "#C6D6E0", "stroke": "none"},
    "waterway": {"fill": "none", "stroke": "#C6D6E0", "stroke-width": "1.2"},
    "coastline": {"fill": "none", "stroke": "#A9BCC8", "stroke-width": "0.8"},
    "building": {"fill": "#DAD5CD", "stroke": "none"},
    "rail": {"fill": "none", "stroke": "#B4B0AA", "stroke-width": "0.8"},
    "path": {"fill": "none", "stroke": "#C4BFB7", "stroke-width": "0.6"},
    "road_service": {"fill": "none", "stroke": "#CFCAC2", "stroke-width": "0.8"},
    "road_residential": {"fill": "none", "stroke": "#BFBAB2", "stroke-width": "1.0"},
    "road_tertiary": {"fill": "none", "stroke": "#B0ABA3", "stroke-width": "1.3"},
    "road_secondary": {"fill": "none", "stroke": "#A6A199", "stroke-width": "1.6"},
    "road_primary": {"fill": "none", "stroke": "#9B968E", "stroke-width": "2.0"},
    "road_trunk": {"fill": "none", "stroke": "#8F8A82", "stroke-width": "2.4"},
    "road_motorway": {"fill": "none", "stroke": "#82796E", "stroke-width": "2.8"},
    "road": {"fill": "none", "stroke": "#A6A199", "stroke-width": "1.2"},
    "boundary": {"fill": "none", "stroke": "#8C8C8C", "stroke-width": "1.0",
                 "stroke-dasharray": "4 3"},
    "_point": {"fill": "#6E6A64", "stroke": "none"},
    "_label": {"fill": "#4A4742", "stroke": "none"},
}

ATTRIBUTION = "Map data © OpenStreetMap contributors, ODbL 1.0"


# ------------------------------------------------------------------ geometry --


def _clip_polygon(ring, rect):
    """Sutherland-Hodgman clip of one ring against an axis aligned rectangle."""
    x0, y0, x1, y1 = rect
    edges = (
        (lambda p: p[0] >= x0, lambda a, b: _isect_x(a, b, x0)),
        (lambda p: p[0] <= x1, lambda a, b: _isect_x(a, b, x1)),
        (lambda p: p[1] >= y0, lambda a, b: _isect_y(a, b, y0)),
        (lambda p: p[1] <= y1, lambda a, b: _isect_y(a, b, y1)),
    )
    out = list(ring)
    for inside, intersect in edges:
        if not out:
            return []
        buf = []
        prev = out[-1]
        prev_in = inside(prev)
        for cur in out:
            cur_in = inside(cur)
            if cur_in:
                if not prev_in:
                    buf.append(intersect(prev, cur))
                buf.append(cur)
            elif prev_in:
                buf.append(intersect(prev, cur))
            prev, prev_in = cur, cur_in
        out = buf
    return out


def _isect_x(a, b, x):
    if b[0] == a[0]:
        return (x, a[1])
    t = (x - a[0]) / (b[0] - a[0])
    return (x, a[1] + t * (b[1] - a[1]))


def _isect_y(a, b, y):
    if b[1] == a[1]:
        return (a[0], y)
    t = (y - a[1]) / (b[1] - a[1])
    return (a[0] + t * (b[0] - a[0]), y)


def _clip_line(points, rect):
    """Liang-Barsky per segment; returns a list of clipped polylines."""
    x0, y0, x1, y1 = rect
    parts = []
    current = []
    for i in range(len(points) - 1):
        seg = _clip_segment(points[i], points[i + 1], x0, y0, x1, y1)
        if seg is None:
            if len(current) > 1:
                parts.append(current)
            current = []
            continue
        a, b = seg
        if current and _close(current[-1], a):
            current.append(b)
        else:
            if len(current) > 1:
                parts.append(current)
            current = [a, b]
    if len(current) > 1:
        parts.append(current)
    return parts


def _close(a, b, eps=1e-9):
    return abs(a[0] - b[0]) < eps and abs(a[1] - b[1]) < eps


def _clip_segment(p, q, x0, y0, x1, y1):
    dx = q[0] - p[0]
    dy = q[1] - p[1]
    t0, t1 = 0.0, 1.0
    for pk, qk in ((-dx, p[0] - x0), (dx, x1 - p[0]), (-dy, p[1] - y0), (dy, y1 - p[1])):
        if pk == 0:
            if qk < 0:
                return None
            continue
        t = qk / pk
        if pk < 0:
            if t > t1:
                return None
            t0 = max(t0, t)
        else:
            if t < t0:
                return None
            t1 = min(t1, t)
    if t0 > t1:
        return None
    return ((p[0] + t0 * dx, p[1] + t0 * dy), (p[0] + t1 * dx, p[1] + t1 * dy))


def _simplify(points, tolerance):
    """Iterative Douglas-Peucker."""
    if tolerance <= 0 or len(points) < 3:
        return points
    keep = [False] * len(points)
    keep[0] = keep[-1] = True
    stack = [(0, len(points) - 1)]
    tol2 = tolerance * tolerance
    while stack:
        first, last = stack.pop()
        if last <= first + 1:
            continue
        ax, ay = points[first]
        bx, by = points[last]
        dx, dy = bx - ax, by - ay
        norm = dx * dx + dy * dy
        best, best_i = -1.0, -1
        for i in range(first + 1, last):
            px, py = points[i]
            if norm == 0:
                d2 = (px - ax) ** 2 + (py - ay) ** 2
            else:
                t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / norm))
                d2 = (px - ax - t * dx) ** 2 + (py - ay - t * dy) ** 2
            if d2 > best:
                best, best_i = d2, i
        if best > tol2:
            keep[best_i] = True
            stack.append((first, best_i))
            stack.append((best_i, last))
    return [p for p, k in zip(points, keep) if k]


# ----------------------------------------------------------------- svg output --


def fmt(value: float, decimals: int) -> str:
    text = f"{value:.{decimals}f}".rstrip("0").rstrip(".")
    return text if text not in ("", "-0") else "0"


def path_data(rings, decimals, close: bool) -> str:
    out = []
    for ring in rings:
        if len(ring) < 2:
            continue
        parts = [f"M{fmt(ring[0][0], decimals)} {fmt(ring[0][1], decimals)}"]
        prev = ring[0]
        for point in ring[1:]:
            parts.append(f"l{fmt(point[0] - prev[0], decimals)} "
                         f"{fmt(point[1] - prev[1], decimals)}")
            prev = point
        if close:
            parts.append("Z")
        out.append("".join(parts))
    return "".join(out)


def esc(text: str) -> str:
    return (str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            .replace('"', "&quot;"))


# ----------------------------------------------------------------- extraction --


def collect(archive, bbox, zoom, wanted_layers, clip, simplify_px, group_by_class):
    """Returns {layer: {class: {"polygons": [...], "lines": [...], "points": [...]}}}."""
    min_lon, min_lat, max_lon, max_lat = bbox
    ox, oy = mvt.lonlat_to_tile(min_lon, max_lat, zoom)
    ex, ey = mvt.lonlat_to_tile(max_lon, min_lat, zoom)
    origin_x, origin_y = ox * TILE_PX, oy * TILE_PX
    width = (ex - ox) * TILE_PX
    height = (ey - oy) * TILE_PX
    view_rect = (0.0, 0.0, width, height)

    x0, y0, x1, y1 = mvt.tile_range(bbox, zoom)
    result: dict[str, dict[str, dict[str, list]]] = {}
    tiles_read = 0
    tiles_missing = 0

    for tx in range(x0, x1 + 1):
        for ty in range(y0, y1 + 1):
            raw = archive.get_tile(zoom, tx, ty)
            if not raw:
                tiles_missing += 1
                continue
            tiles_read += 1
            try:
                decoded = mvt.decode_tile(raw)
            except Exception as exc:  # a corrupt tile must not kill the export
                print(f"  ! could not decode tile {zoom}/{tx}/{ty}: {exc}", file=sys.stderr)
                continue

            tile_x0 = tx * TILE_PX - origin_x
            tile_y0 = ty * TILE_PX - origin_y
            tile_rect = (tile_x0, tile_y0, tile_x0 + TILE_PX, tile_y0 + TILE_PX)
            clip_rect = (max(tile_rect[0], view_rect[0]), max(tile_rect[1], view_rect[1]),
                         min(tile_rect[2], view_rect[2]), min(tile_rect[3], view_rect[3]))
            if clip_rect[0] >= clip_rect[2] or clip_rect[1] >= clip_rect[3]:
                continue

            for name, layer in decoded.items():
                if wanted_layers and name not in wanted_layers:
                    continue
                scale = TILE_PX / layer.extent
                buckets = result.setdefault(name, {})
                for feature in layer.features:
                    clazz = str(feature.attrs.get("class", "")) if group_by_class else ""
                    bucket = buckets.setdefault(clazz, {"polygons": [], "lines": [], "points": []})
                    rings = [[(tile_x0 + px * scale, tile_y0 + py * scale) for px, py in ring]
                             for ring in feature.rings]

                    if feature.geom_type == mvt.POINT:
                        for ring in rings:
                            for point in ring:
                                if (clip_rect[0] <= point[0] <= clip_rect[2]
                                        and clip_rect[1] <= point[1] <= clip_rect[3]):
                                    bucket["points"].append((point, feature.attrs))
                    elif feature.geom_type == mvt.LINESTRING:
                        for ring in rings:
                            pieces = _clip_line(ring, clip_rect) if clip else [ring]
                            for piece in pieces:
                                piece = _simplify(piece, simplify_px)
                                if len(piece) > 1:
                                    bucket["lines"].append(piece)
                    elif feature.geom_type == mvt.POLYGON:
                        out_rings = []
                        for ring in rings:
                            ring = _clip_polygon(ring, clip_rect) if clip else ring
                            ring = _simplify(ring, simplify_px)
                            if len(ring) >= 3:
                                out_rings.append(ring)
                        if out_rings:
                            bucket["polygons"].append(out_rings)

    return result, width, height, tiles_read, tiles_missing


# ---------------------------------------------------------------------- write --


def write_svg(path: Path, groups, width, height, palette, styled, labels, decimals, title):
    parts = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        f'<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" '
        f'viewBox="0 0 {fmt(width, 2)} {fmt(height, 2)}" '
        f'width="{fmt(width, 2)}" height="{fmt(height, 2)}">',
        f"  <title>{esc(title)}</title>",
        f"  <desc>{esc(ATTRIBUTION)}</desc>",
    ]
    for layer_name, buckets in groups:
        style = palette.get(layer_name, {}) if styled else {}
        attrs = "".join(f' {k}="{v}"' for k, v in style.items())
        parts.append(f'  <g id="{esc(layer_name)}"{attrs}>')
        for clazz, bucket in sorted(buckets.items()):
            indent = "    "
            if clazz:
                parts.append(f'    <g id="{esc(layer_name)}__{esc(clazz)}">')
                indent = "      "
            for rings in bucket["polygons"]:
                d = path_data(rings, decimals, close=True)
                if d:
                    parts.append(f'{indent}<path fill-rule="evenodd" d="{d}"/>')
            for line in bucket["lines"]:
                d = path_data([line], decimals, close=False)
                if d:
                    parts.append(f'{indent}<path fill="none" d="{d}"/>')
            point_style = palette.get("_point", {}) if styled else {}
            point_attrs = "".join(f' {k}="{v}"' for k, v in point_style.items())
            for (px, py), attributes in bucket["points"]:
                parts.append(f'{indent}<circle cx="{fmt(px, decimals)}" cy="{fmt(py, decimals)}" '
                             f'r="3"{point_attrs}/>')
                name = attributes.get("name")
                if labels and name:
                    label_style = palette.get("_label", {}) if styled else {}
                    label_attrs = "".join(f' {k}="{v}"' for k, v in label_style.items())
                    parts.append(
                        f'{indent}<text x="{fmt(px + 5, decimals)}" y="{fmt(py + 3.5, decimals)}" '
                        f'font-family="Inter, Helvetica, Arial, sans-serif" font-size="11"'
                        f'{label_attrs}>{esc(name)}</text>')
            if clazz:
                parts.append("    </g>")
        parts.append("  </g>")
    parts.append("</svg>")
    path.write_text("\n".join(parts), encoding="utf-8")
    return path.stat().st_size


# ----------------------------------------------------------------------- main --


def load_regions(path: Path) -> dict:
    if not path.is_file():
        return {}
    import yaml  # noqa: PLC0415
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return data.get("regions", {})


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--tiles", required=True, help="input .mbtiles or .pmtiles")
    ap.add_argument("--region", help="named region from config/regions.yml")
    ap.add_argument("--bbox", help="min_lon,min_lat,max_lon,max_lat")
    ap.add_argument("--zoom", type=int, help="tile zoom to read from (detail level)")
    ap.add_argument("--out", required=True, help="output .svg file, or a directory with --split")
    ap.add_argument("--regions-config", default="config/regions.yml")
    ap.add_argument("--layers", help="comma separated layer allow-list")
    ap.add_argument("--exclude-layers", help="comma separated layer deny-list")
    ap.add_argument("--split", action="store_true", help="write one SVG per layer")
    ap.add_argument("--group-by-class", action="store_true",
                    help="add a sub-group per feature class inside each layer")
    ap.add_argument("--no-style", action="store_true",
                    help="emit pure geometry without any placeholder colors")
    ap.add_argument("--no-labels", action="store_true", help="skip <text> labels for named points")
    ap.add_argument("--no-clip", action="store_true", help="keep the tile buffer overlap")
    ap.add_argument("--palette", help="JSON file overriding the placeholder group styles")
    ap.add_argument("--simplify", type=float, default=0.25,
                    help="extra Douglas-Peucker tolerance in SVG px (default 0.25, 0 = off)")
    ap.add_argument("--decimals", type=int, default=2, help="coordinate precision")
    args = ap.parse_args()

    regions = load_regions(Path(args.regions_config))

    if args.bbox:
        bbox = tuple(float(v) for v in args.bbox.split(","))
        if len(bbox) != 4:
            print("error: --bbox needs 4 comma separated numbers", file=sys.stderr)
            return 1
        title = args.region or "custom section"
        zoom = args.zoom
    elif args.region:
        region = regions.get(args.region)
        if not region:
            print(f"error: unknown region '{args.region}'. Known: {', '.join(sorted(regions))}",
                  file=sys.stderr)
            return 1
        bbox = tuple(float(v) for v in region["bbox"])
        title = region.get("title", args.region)
        zoom = args.zoom if args.zoom is not None else int(region.get("svg_zoom", 12))
    else:
        print("error: pass either --region or --bbox", file=sys.stderr)
        return 1

    if zoom is None:
        print("error: --zoom is required with --bbox", file=sys.stderr)
        return 1

    palette = dict(DEFAULT_PALETTE)
    if args.palette:
        palette.update(json.loads(Path(args.palette).read_text(encoding="utf-8")))

    wanted = set(args.layers.split(",")) if args.layers else None
    excluded = set(args.exclude_layers.split(",")) if args.exclude_layers else set()

    with mvt.open_archive(args.tiles) as archive:
        meta = archive.metadata()
        max_zoom = int(meta.get("maxzoom", 14))
        min_zoom = int(meta.get("minzoom", 0))
        if zoom > max_zoom:
            print(f"  note: tileset stops at z{max_zoom}; reading z{max_zoom} instead of z{zoom}")
            zoom = max_zoom
        if zoom < min_zoom:
            zoom = min_zoom
        x0, y0, x1, y1 = mvt.tile_range(bbox, zoom)
        print(f"  region  : {title}")
        print(f"  bbox    : {', '.join(f'{v:g}' for v in bbox)}")
        print(f"  zoom    : z{zoom}   tiles {x0}..{x1} x {y0}..{y1} "
              f"({(x1 - x0 + 1) * (y1 - y0 + 1)} tiles)")
        groups, width, height, read, missing = collect(
            archive, bbox, zoom, wanted, not args.no_clip, args.simplify, args.group_by_class)

    for name in excluded:
        groups.pop(name, None)

    ordered = [(n, groups[n]) for n in DEFAULT_ORDER if n in groups]
    ordered += [(n, g) for n, g in sorted(groups.items()) if n not in DEFAULT_ORDER]

    total_features = sum(
        len(b["polygons"]) + len(b["lines"]) + len(b["points"])
        for _, buckets in ordered for b in buckets.values())
    print(f"  tiles   : {read} read, {missing} empty/missing")
    print(f"  size    : {width:.0f} x {height:.0f} px")
    print(f"  layers  : {len(ordered)}  ({total_features:,} features)")

    styled = not args.no_style
    labels = not args.no_labels

    if args.split:
        out_dir = Path(args.out)
        out_dir.mkdir(parents=True, exist_ok=True)
        total = 0
        for name, buckets in ordered:
            target = out_dir / f"{name}.svg"
            written = write_svg(target, [(name, buckets)], width, height, palette, styled,
                                labels, args.decimals, f"{title} — {name}")
            total += written
            print(f"    {target}  ({written / 1024:.1f} KB)")
        print(f"  wrote {len(ordered)} files, {total / 1024:.1f} KB total")
    else:
        target = Path(args.out)
        target.parent.mkdir(parents=True, exist_ok=True)
        written = write_svg(target, ordered, width, height, palette, styled, labels,
                            args.decimals, title)
        print(f"  wrote {target}  ({written / 1024:.1f} KB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
