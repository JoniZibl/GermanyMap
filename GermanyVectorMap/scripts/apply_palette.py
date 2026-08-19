#!/usr/bin/env python3
"""
Generate the MapLibre style and the SVG export palette from style/palette.json.

Colors live in exactly one file. Change a value there, run this script, and both
the interactive map style and the Figma-bound SVG exports follow:

    python3 scripts/apply_palette.py

    style/palette.json  ->  style/germany-basemap.json   (MapLibre GL style)
                        ->  config/svg_palette.json      (scripts/export_svg.py)

The vector tiles themselves are never touched — geometry and styling stay separate.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SOURCE = "germany"


def zoom_width(stops: list[tuple[int, float]]):
    """MapLibre interpolate expression for a line width."""
    out = ["interpolate", ["linear"], ["zoom"]]
    for zoom, width in stops:
        out += [zoom, width]
    return out


# layer key -> (source-layer, minzoom, width stops)
ROAD_LAYERS = [
    ("road_service", 14, [(14, 0.5), (16, 2), (18, 6)]),
    ("road_residential", 12, [(12, 0.4), (14, 1.2), (16, 4), (18, 12)]),
    ("road_tertiary", 10, [(10, 0.5), (13, 1.5), (16, 6), (18, 16)]),
    ("road_secondary", 9, [(9, 0.6), (13, 2), (16, 8), (18, 20)]),
    ("road_primary", 7, [(7, 0.6), (11, 1.6), (14, 4), (16, 10), (18, 24)]),
    ("road_trunk", 6, [(6, 0.7), (11, 2), (14, 5), (16, 12), (18, 26)]),
    ("road_motorway", 4, [(4, 0.6), (8, 1.2), (11, 2.6), (14, 6), (16, 14), (18, 30)]),
]

PLACE_LAYERS = [
    ("place_city", 3, [(3, 11), (8, 15), (12, 22)]),
    ("place_town", 7, [(7, 10), (12, 14)]),
    ("place_village", 11, [(11, 9), (14, 12)]),
    ("place_suburb", 12, [(12, 9), (15, 12)]),
]

POI_LAYERS = ["poi_castle", "poi_church", "poi_ruin", "poi_monument", "poi_viewpoint",
              "poi_museum", "poi_tower", "poi_historic"]


def build_style(palette: dict, tiles_url: str) -> dict:
    layers: list[dict] = [
        {"id": "background", "type": "background",
         "paint": {"background-color": palette["background"]}},
        {"id": "land", "type": "fill", "source": SOURCE, "source-layer": "land",
         "filter": ["==", ["get", "class"], "country"],
         "paint": {"fill-color": palette["land"]}},
    ]

    for name in ("grass", "forest", "park", "garden"):
        layers.append({
            "id": name, "type": "fill", "source": SOURCE, "source-layer": name,
            "paint": {"fill-color": palette[name],
                      "fill-opacity": ["interpolate", ["linear"], ["zoom"], 6, 0.6, 10, 1]},
        })

    layers.append({
        "id": "water", "type": "fill", "source": SOURCE, "source-layer": "water",
        "paint": {"fill-color": palette["water"]},
    })
    layers.append({
        "id": "waterway", "type": "line", "source": SOURCE, "source-layer": "waterway",
        "layout": {"line-cap": "round", "line-join": "round"},
        "paint": {"line-color": palette["waterway"],
                  "line-width": zoom_width([(5, 0.4), (10, 1), (14, 3), (17, 8)])},
    })
    layers.append({
        "id": "coastline", "type": "line", "source": SOURCE, "source-layer": "coastline",
        "paint": {"line-color": palette["coastline"], "line-width": 0.8},
    })

    layers.append({
        "id": "building", "type": "fill", "source": SOURCE, "source-layer": "building",
        "minzoom": 14,
        "paint": {"fill-color": palette["building"],
                  "fill-outline-color": palette["building_outline"]},
    })

    # road casings first, then the road bodies on top
    for name, minzoom, stops in ROAD_LAYERS:
        if name in ("road_motorway", "road_trunk", "road_primary"):
            layers.append({
                "id": f"{name}_casing", "type": "line", "source": SOURCE, "source-layer": name,
                "minzoom": max(minzoom, 8),
                "layout": {"line-cap": "round", "line-join": "round"},
                "paint": {"line-color": palette["road_casing"],
                          "line-width": zoom_width([(z, w + 1.4) for z, w in stops])},
            })

    layers.append({
        "id": "rail", "type": "line", "source": SOURCE, "source-layer": "rail",
        "layout": {"line-join": "round"},
        "paint": {"line-color": palette["rail"],
                  "line-width": zoom_width([(8, 0.4), (13, 1), (16, 2.5)]),
                  "line-dasharray": [3, 2]},
    })
    layers.append({
        "id": "path", "type": "line", "source": SOURCE, "source-layer": "path",
        "minzoom": 14,
        "layout": {"line-cap": "round"},
        "paint": {"line-color": palette["path"],
                  "line-width": zoom_width([(14, 0.5), (17, 2)]),
                  "line-dasharray": [2, 2]},
    })

    for name, minzoom, stops in ROAD_LAYERS:
        layers.append({
            "id": name, "type": "line", "source": SOURCE, "source-layer": name,
            "minzoom": minzoom,
            "layout": {"line-cap": "round", "line-join": "round"},
            "paint": {"line-color": palette[name], "line-width": zoom_width(stops)},
        })

    for clazz, key, dash in (("country", "boundary_country", [4, 2]),
                             ("state", "boundary_state", [3, 2]),
                             ("county", "boundary_county", [2, 2])):
        layers.append({
            "id": f"boundary_{clazz}", "type": "line", "source": SOURCE,
            "source-layer": "boundary",
            "filter": ["==", ["get", "class"], clazz],
            "paint": {"line-color": palette[key], "line-dasharray": dash,
                      "line-width": zoom_width([(2, 0.6), (8, 1.2), (14, 2)])},
        })

    # points that need no glyphs — always render, even without a font server
    for name in POI_LAYERS:
        layers.append({
            "id": f"{name}_point", "type": "circle", "source": SOURCE, "source-layer": name,
            "paint": {"circle-color": palette["poi"],
                      "circle-radius": zoom_width([(11, 1.6), (15, 3.5)]),
                      "circle-stroke-color": palette["label_halo"], "circle-stroke-width": 0.8},
        })
    layers.append({
        "id": "transport_point", "type": "circle", "source": SOURCE, "source-layer": "transport",
        "paint": {"circle-color": palette["transport"],
                  "circle-radius": zoom_width([(9, 1.5), (15, 4)]),
                  "circle-stroke-color": palette["label_halo"], "circle-stroke-width": 0.8},
    })

    # text layers need glyphs — see the note in docs/STYLING.md
    for name, minzoom, stops in PLACE_LAYERS:
        layers.append({
            "id": f"{name}_label", "type": "symbol", "source": SOURCE, "source-layer": name,
            "minzoom": minzoom,
            "layout": {"text-field": ["get", "name"],
                       "text-font": ["Noto Sans Regular"],
                       "text-size": zoom_width(stops),
                       "text-max-width": 8,
                       "text-padding": 4},
            "paint": {"text-color": palette["label"],
                      "text-halo-color": palette["label_halo"], "text-halo-width": 1.4},
        })
    for name in POI_LAYERS:
        layers.append({
            "id": f"{name}_label", "type": "symbol", "source": SOURCE, "source-layer": name,
            "minzoom": 13,
            "layout": {"text-field": ["get", "name"],
                       "text-font": ["Noto Sans Regular"],
                       "text-size": 11, "text-offset": [0, 1.1], "text-anchor": "top",
                       "text-optional": True},
            "paint": {"text-color": palette["poi"],
                      "text-halo-color": palette["label_halo"], "text-halo-width": 1.2},
        })

    return {
        "version": 8,
        "name": "Germany Vector Map",
        "metadata": {
            "generated-by": "scripts/apply_palette.py — edit style/palette.json, not this file",
            "attribution-required": "© OpenStreetMap contributors, ODbL 1.0",
        },
        "glyphs": "glyphs/{fontstack}/{range}.pbf",
        "sources": {
            SOURCE: {
                "type": "vector",
                "url": tiles_url,
                "attribution": '<a href="https://www.openstreetmap.org/copyright">'
                               '© OpenStreetMap contributors</a>',
            }
        },
        "layers": layers,
    }


def build_svg_palette(palette: dict) -> dict:
    """Group-level presentation attributes for scripts/export_svg.py."""
    def line(color, width, dash=None):
        style = {"fill": "none", "stroke": color, "stroke-width": str(width),
                 "stroke-linejoin": "round", "stroke-linecap": "round"}
        if dash:
            style["stroke-dasharray"] = dash
        return style

    return {
        "land": {"fill": palette["land"], "stroke": "none"},
        "grass": {"fill": palette["grass"], "stroke": "none"},
        "forest": {"fill": palette["forest"], "stroke": "none"},
        "park": {"fill": palette["park"], "stroke": "none"},
        "garden": {"fill": palette["garden"], "stroke": "none"},
        "water": {"fill": palette["water"], "stroke": "none"},
        "waterway": line(palette["waterway"], 1.2),
        "coastline": line(palette["coastline"], 0.8),
        "building": {"fill": palette["building"], "stroke": palette["building_outline"],
                     "stroke-width": "0.2"},
        "rail": line(palette["rail"], 0.8, "3 2"),
        "path": line(palette["path"], 0.6, "2 2"),
        "road_service": line(palette["road_service"], 0.8),
        "road_residential": line(palette["road_residential"], 1.0),
        "road_tertiary": line(palette["road_tertiary"], 1.3),
        "road_secondary": line(palette["road_secondary"], 1.6),
        "road_primary": line(palette["road_primary"], 2.0),
        "road_trunk": line(palette["road_trunk"], 2.4),
        "road_motorway": line(palette["road_motorway"], 2.8),
        "road": line(palette["road_residential"], 1.2),
        "boundary": line(palette["boundary_state"], 1.0, "4 3"),
        "_point": {"fill": palette["poi"], "stroke": "none"},
        "_label": {"fill": palette["label"], "stroke": "none"},
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--palette", default=str(ROOT / "style" / "palette.json"))
    ap.add_argument("--style-out", default=str(ROOT / "style" / "germany-basemap.json"))
    ap.add_argument("--svg-palette-out", default=str(ROOT / "config" / "svg_palette.json"))
    ap.add_argument("--tiles-url", default="mbtiles://output/germany_game_map.mbtiles",
                    help="source url written into the style (the preview server rewrites it)")
    args = ap.parse_args()

    palette = {k: v for k, v in
               json.loads(Path(args.palette).read_text(encoding="utf-8")).items()
               if not k.startswith("_")}

    style = build_style(palette, args.tiles_url)
    Path(args.style_out).write_text(json.dumps(style, indent=2) + "\n", encoding="utf-8")
    print(f"  wrote {args.style_out}  ({len(style['layers'])} style layers)")

    svg_palette = build_svg_palette(palette)
    Path(args.svg_palette_out).write_text(json.dumps(svg_palette, indent=2) + "\n",
                                          encoding="utf-8")
    print(f"  wrote {args.svg_palette_out}  ({len(svg_palette)} layer styles)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
