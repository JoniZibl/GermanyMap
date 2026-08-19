# SVG export for Figma

The vector tiles stay the master data. Figma receives sections only — test cuts,
example regions, style references, a simplified Germany overview. The colors get
developed in Figma; the actual map data lives on independently.

## Usage

```bash
# a named region from config/regions.yml
python3 scripts/export_svg.py --tiles output/germany_game_map.mbtiles \
    --region koeln --out exports/koeln_test.svg

# Germany, low detail
python3 scripts/export_svg.py --tiles output/germany_game_map.mbtiles \
    --region germany --zoom 6 --out exports/germany_overview.svg

# NRW
python3 scripts/export_svg.py --tiles output/germany_game_map.mbtiles \
    --region nrw --out exports/nrw.svg

# Leverkusen
python3 scripts/export_svg.py --tiles output/germany_game_map.mbtiles \
    --region leverkusen --out exports/leverkusen.svg

# any bbox: min_lon,min_lat,max_lon,max_lat
python3 scripts/export_svg.py --tiles output/germany_game_map.mbtiles \
    --bbox 6.90,50.92,7.02,50.98 --zoom 14 --out exports/ausschnitt.svg
```

## Options

| Option | Effect |
|--------|--------|
| `--region NAME` | a region from `config/regions.yml` (uses its `svg_zoom`) |
| `--bbox a,b,c,d` | free section, WGS84 lon/lat |
| `--zoom N` | which tile zoom to read — this is the detail level |
| `--split` | one SVG per layer into a directory, all sharing one `viewBox` |
| `--group-by-class` | sub-group per feature class, e.g. `forest__wood` |
| `--layers a,b,c` | only these layers |
| `--exclude-layers a,b` | everything except these |
| `--palette FILE` | group styles (default: the placeholder greys) |
| `--no-style` | pure geometry, no color attributes at all |
| `--no-labels` | skip `<text>` elements for named points |
| `--no-clip` | keep the tile buffer overlap instead of clipping |
| `--simplify PX` | extra Douglas-Peucker pass, default `0.25` |
| `--decimals N` | coordinate precision, default `2` |

## Structure of the output

```xml
<svg viewBox="0 0 1024 768" width="1024" height="768">
  <title>Köln</title>
  <desc>Map data © OpenStreetMap contributors, ODbL 1.0</desc>
  <g id="land"   fill="#F7F5EF" stroke="none">      <path d="…"/> … </g>
  <g id="water"  fill="#A8C8DC" stroke="none">      <path d="…"/> … </g>
  <g id="forest" fill="#BFD1B0" stroke="none">      <path d="…"/> … </g>
  <g id="road_motorway" fill="none" stroke="#F6E3B4" stroke-width="2.8"> … </g>
  <g id="place_city">  <circle …/> <text …>Köln</text> </g>
</svg>
```

- **One `<g id="…">` per map layer**, in correct painting order (land at the
  bottom, labels on top). Figma imports each as a named, selectable group.
- **Colors sit on the group, never on the paths.** Select a group in Figma,
  change its fill, and the whole layer changes. `--no-style` omits them entirely.
- Polygons use `fill-rule="evenodd"`, so holes (a lake inside a forest) stay holes.
- Coordinates are relative (`l` commands) and rounded, which keeps files small.

## Figma import

1. Export the section (start with a city, not the whole country).
2. Drag the `.svg` into Figma, or **File → Place image**.
3. It arrives as a frame containing one group per layer, named exactly as the
   layer.
4. Select a group → set its fill/stroke → the entire layer recolors.
5. Build your palette there, then copy the final values back into
   `style/palette.json` and run `scripts/apply_palette.py` so the interactive map
   and all future exports match.

### `--split` for maximum control

```bash
python3 scripts/export_svg.py --tiles output/germany_game_map.mbtiles \
    --region leverkusen --split --out exports/leverkusen/
```

Writes `land.svg`, `water.svg`, `forest.svg`, `road_motorway.svg`, … Every file
carries the **same `viewBox`**, so importing them all and stacking them at the
same position reassembles the map exactly, with each layer as an independent
Figma layer.

## Keeping files manageable

Figma slows down well before a few hundred thousand vector nodes. Rules of thumb:

| Section | Sensible zoom | Result |
|---------|---------------|--------|
| all of Germany | 5–6 | overview shape, motorways, big cities |
| a Bundesland (NRW) | 8–9 | main road network, forests, cities |
| a Regierungsbezirk | 10–11 | full road hierarchy without buildings |
| a city (Köln) | 12–13 | streets, water, parks, POIs |
| a district (Leverkusen) | 14 | including buildings and footpaths |

If a file gets too heavy:

```bash
# leave out the expensive layers
--exclude-layers building,path,road_service

# or take only what you want to design
--layers land,water,forest,park,road_motorway,road_primary,place_city

# simplify harder
--simplify 1.0
```

The exporter prints the feature count before writing, so you can see what you are
about to hand Figma.

## How the section is cut

Tiles are decoded, projected to the section's pixel space, and clipped to the
exact bbox (Sutherland-Hodgman for polygons, Liang-Barsky for lines). That removes
the duplicated geometry in the tile buffers, so you do not get doubled outlines
along tile edges. `--no-clip` disables it.

If `--zoom` exceeds the tileset's `max_zoom`, the exporter reads the deepest
available zoom instead and says so — the geometry stays sharp, it just carries the
detail stored at that zoom.

## License in exported files

Every SVG contains

```xml
<desc>Map data © OpenStreetMap contributors, ODbL 1.0</desc>
```

Keep it. If the graphic is published, the attribution has to be visible to the
viewer as well — see [LICENSE_OSM.md](LICENSE_OSM.md).
