# Styling

**Colors are never baked into the geodata.** The vector tiles carry geometry, a
`class`, and sometimes a `name`. Nothing else. Every visual decision is made
afterwards, and can be changed without rebuilding a single tile.

## One palette, two consumers

```
style/palette.json
        │
        ├──► style/germany-basemap.json    MapLibre GL style (interactive map)
        └──► config/svg_palette.json       group styles for the SVG export
```

```bash
$EDITOR style/palette.json
python3 scripts/apply_palette.py
```

`style/palette.json` is a flat list of names to colors:

```json
{
  "water":            "#A8C8DC",
  "forest":           "#BFD1B0",
  "park":             "#CFE0BE",
  "road_motorway":    "#F6E3B4",
  "road_primary":     "#FFFFFF",
  "road_residential": "#EDEAE3",
  "building":         "#E4DCCD"
}
```

Change `water` and every water polygon in Germany changes — in the interactive
map and in every SVG you export from then on.

## Editing the style directly

`style/germany-basemap.json` is a normal MapLibre GL style. Regenerating it from
the palette overwrites it, so if you hand-edit it (adding layers, changing line
widths, adding filters), either stop using `apply_palette.py` or move your
changes into the generator in `scripts/apply_palette.py` — the layer table there
is plain, readable Python.

Line widths per zoom live in that table:

```python
("road_motorway", 4, [(4, 0.6), (8, 1.2), (11, 2.6), (14, 6), (16, 14), (18, 30)]),
#  layer          minzoom  [(zoom, width), …]
```

## Previewing

```bash
python3 scripts/serve_tiles.py --tiles output/germany_game_map.mbtiles
# or point it straight at the .pmtiles — both formats work
```

Then open **http://localhost:8080/** — that is a real, interactive MapLibre map
of your build, styled with `style/germany-basemap.json`, with zoom controls, a
scale bar and a readout of the current zoom (including whether you are
overzooming past the deepest tile zoom).

Also served:

- `/style.json` — the style with local tile URLs patched in
- `/tiles.json` — TileJSON including the layer list
- `/tiles/{z}/{x}/{y}.pbf` — the tiles

Open `/style.json` in [Maputnik](https://maplibre.org/maputnik/) or QGIS
(*Layer → Add Layer → Add Vector Tile Layer*) to edit the style interactively.

`scripts/setup.sh` vendors maplibre-gl into `tools/node_modules`, so the preview
runs with no network at all. Without that it loads the library from unpkg.com —
the tiles, the style and the data always stay local either way.

## Text labels need glyphs

The style references `glyphs/{fontstack}/{range}.pbf` for the `Noto Sans Regular`
font stack. Font glyphs are a rendering asset, not map data, so they are not
shipped here. Three options:

1. **Do nothing.** MapLibre falls back to drawing the labels without the glyph
   atlas, which is what the local preview does — you will see one 404 per font
   range in the console and readable text on the map. Good enough to review a
   build, not good enough to ship.
2. **Local glyphs (offline).** Download a PBF font stack, e.g. from
   [maplibre/demotiles](https://github.com/maplibre/demotiles) or generate one
   with [`fontnik`](https://github.com/mapbox/node-fontnik), and put it in
   `style/glyphs/Noto Sans Regular/0-255.pbf`, `256-511.pbf`, …
3. **Remote glyphs.** Point `"glyphs"` at a hosted endpoint. This is the only part
   of the setup that would then require internet.

## Attribution in the style

The style carries

```json
"attribution": "<a href=\"https://www.openstreetmap.org/copyright\">© OpenStreetMap contributors</a>"
```

on its source. MapLibre renders it in the corner. Do not remove it — see
[LICENSE_OSM.md](LICENSE_OSM.md).
