# Germany Vector Map

An optimized, multi-zoom **vector** basemap of Germany built from real OpenStreetMap
data. Offline-capable, layer-separated, free of baked-in colors, and prepared for
SVG exports into Figma.

Not a raster map. Not a game project. Just the map data and the pipeline that
produces it.

```
input/germany-latest.osm.pbf                    real OSM data (Geofabrik)
        │
        ▼   Planetiler + profiles/GermanyMapProfile.java
        │   filter → simplify per zoom → merge → tile
        ▼
output/germany_game_map.mbtiles                 master tileset
output/germany_game_map.pmtiles                 same tiles, single file
        │
        ├─► style/germany-basemap.json          MapLibre style (colors live here)
        └─► exports/*.svg                       layered SVG sections for Figma
```

---

## Table of contents

- [Requirements](#requirements)
- [Installation](#installation)
- [Data source](#data-source)
- [Build commands](#build-commands)
- [Configuration](#configuration)
- [Zoom levels](#zoom-levels)
- [Layers](#layers)
- [Styling](#styling)
- [SVG export for Figma](#svg-export-for-figma)
- [Size optimization](#size-optimization)
- [Updating the OSM data](#updating-the-osm-data)
- [License](#license)

---

## Requirements

| Tool | Version | Why |
|------|---------|-----|
| Java | 21+ | Planetiler runs on the JVM |
| Python | 3.9+ | statistics, SVG export, PMTiles conversion |
| curl | any | downloading the extracts |
| RAM | 8 GB for the test region, 16 GB recommended for Germany | |
| Disk | ~2 GB for the test region, ~50 GB scratch for Germany | |

Python packages: `PyYAML`, `pmtiles` — both installed by `scripts/setup.sh`.

**Why Planetiler?** It was the right tool here, and it was checked against the
alternatives first: it reads `.osm.pbf` directly, runs a full country in well
under an hour on a laptop, does per-zoom Douglas-Peucker simplification and tile
post-processing (line merging, polygon union) natively, and writes MBTiles *and*
PMTiles. `tilemaker` is lighter but markedly slower on country-sized input and
its Lua profiles offer less control over per-zoom geometry; `osm2pgsql` + a tile
server means running a database and generating tiles on demand, which conflicts
with the offline, file-based requirement here. See
[docs/TOOLCHAIN.md](docs/TOOLCHAIN.md) for the full comparison.

## Installation

```bash
cd GermanyVectorMap
./scripts/setup.sh
```

This checks Java/Python, downloads `tools/planetiler.jar` (~93 MB) from the
official Planetiler release, installs the two Python packages, and compiles the
map profile into `tools/germany-map-profile.jar`.

## Data source

Real OpenStreetMap data from the [Geofabrik](https://download.geofabrik.de/)
extracts. No geometry is invented, drawn by hand, or approximated — the actual
geographic structure of Germany is preserved throughout.

```bash
./scripts/fetch_data.sh germany          # europe/germany-latest.osm.pbf   (~4 GB)
./scripts/fetch_data.sh nrw              # Nordrhein-Westfalen             (~800 MB)
./scripts/fetch_data.sh koeln_regbez     # Regierungsbezirk Köln           (~250 MB)
```

Regions are defined in [`config/regions.yml`](config/regions.yml). The download
is md5-verified against Geofabrik's published checksum.

## Build commands

### Without installing anything: GitHub Actions

The repository ships [`.github/workflows/build-map.yml`](../.github/workflows/build-map.yml).
Actions tab → **Build vector map** → *Run workflow* → pick a region. The runner
downloads the extract, builds the tileset, runs the statistics and produces the
SVG exports, then offers everything as downloadable artifacts. The measurement
report also lands in the job summary.

This is how the Köln test region was built and measured — see
[docs/TEST_RESULTS.md](docs/TEST_RESULTS.md). Germany needs more disk than a
standard runner offers; build that one locally.

### Locally

**Start with the test region.** It exercises the whole pipeline in a couple of
minutes and lets you check layers, detail levels, file size and the SVG export
before committing to a full country build.

```bash
./build_test_region              # Regierungsbezirk Köln  (downloads the extract if needed)
./build_test_region nrw          # all of Nordrhein-Westfalen
./build_test_region koeln        # only the city, cut out of the Regbez extract
```

Once the result looks right:

```bash
./build_germany_map              # all of Germany
JAVA_XMX=12g ./build_germany_map # give the JVM more heap
```

Both commands run the same eight steps and print the statistics at the end:

1. check the input `.osm.pbf`
2. compile the profile (only when sources changed)
3. read the OSM data
4. apply the filters
5. simplify the geometry per zoom
6. build the zoom levels
7. write `output/<name>.mbtiles` **and** `output/<name>.pmtiles`
8. print size, tile count, zoom range, layers, biggest layers and optimization hints

Anything after `--` goes straight to Planetiler:

```bash
./build_test_region koeln_regbez -- --maxzoom=15 --threads=4
```

See [docs/GERMANY_BUILD.md](docs/GERMANY_BUILD.md) for the exact steps and the
hardware/runtime expectations of the full Germany build.

## Configuration

Two YAML files control the output. Neither contains a single color.

| File | Controls |
|------|----------|
| [`config/layers.yml`](config/layers.yml) | which layers exist, minimum feature sizes, merging, name attributes, per-layer flags |
| [`config/zoom_levels.yml`](config/zoom_levels.yml) | tileset zoom range, per-layer zoom windows, feature-level zoom rules, simplification |
| [`config/regions.yml`](config/regions.yml) | named regions: Geofabrik path + bbox, for builds and SVG exports |

The OSM tag → layer mapping itself is typed Java in
[`profiles/src/main/java/de/germanyvectormap/GermanyMapProfile.java`](profiles/src/main/java/de/germanyvectormap/GermanyMapProfile.java)
— that keeps the per-feature hot path fast and the rules reviewable. Adding a
tag is a few lines there plus an entry in the two YAML files.

## Zoom levels

Tiles are generated for **z0–z14**. Vector tiles are resolution-independent, so a
renderer keeps drawing z15/z16/z17 sharply by overzooming z14 — there is simply
no extra OSM detail past z14. That is what keeps Germany in the low-GB range.
Raise `tileset.max_zoom` to 15 if you need more building/footpath detail and can
afford roughly 3x the size.

| Zoom | What appears |
|------|--------------|
| 0–5 | Germany outline, state areas, largest cities, motorways, major rivers, big lakes, coastline, country/state boundaries |
| 6–8 | trunk + primary roads, medium cities, larger forests, railways, more rivers |
| 9–11 | secondary + tertiary roads, parks, smaller towns and villages, lakes, meadows, stations |
| 12–14 | residential roads, suburbs, smaller waterways, gardens, POIs |
| 14 | buildings, footpaths, tracks, service roads |
| 15+ | rendered by overzooming z14 — stays sharp, gains no new data |

Full table with every feature-level rule: [docs/ZOOM_LEVELS.md](docs/ZOOM_LEVELS.md).

## Layers

32 layers, grouped and named so a style can address them directly:

```
land         boundary      coastline
water        waterway
forest       park          garden        grass
road_motorway  road_trunk  road_primary  road_secondary
road_tertiary  road_residential  road_service  path  rail
building
place_city   place_town    place_village place_suburb
transport
poi_castle   poi_church    poi_ruin      poi_monument
poi_viewpoint poi_museum   poi_tower     poi_historic
```

Every feature carries a `class` attribute (and a `name` from the zoom configured
per layer). POIs are kept in their own layers, strictly separate from the base map.

Full reference with every OSM tag that maps into each layer:
[docs/LAYERS.md](docs/LAYERS.md).

## Styling

**Colors are never baked into the geodata.** Geometry and styling are separate,
by design.

All colors live in one file, [`style/palette.json`](style/palette.json):

```bash
$EDITOR style/palette.json          # water = blue, forest = green, ...
python3 scripts/apply_palette.py    # regenerates both consumers
```

which regenerates:

- `style/germany-basemap.json` — a complete MapLibre GL style (46 layers)
- `config/svg_palette.json` — the group styles used by the SVG export

so one edit changes the interactive map *and* every future Figma export.

Preview a build locally, with no CDN and no internet:

```bash
python3 scripts/serve_tiles.py --tiles output/germany_game_map.mbtiles
# http://localhost:8080/style.json  -> open in Maputnik, QGIS or any MapLibre viewer
```

Details, including how to add glyphs for text labels:
[docs/STYLING.md](docs/STYLING.md).

## SVG export for Figma

The vector tiles stay the master data. Figma only ever receives sections.

```bash
# a named region
python3 scripts/export_svg.py --tiles output/germany_game_map.mbtiles \
    --region koeln --out exports/koeln_test.svg

# all of Germany at low detail
python3 scripts/export_svg.py --tiles output/germany_game_map.mbtiles \
    --region germany --zoom 6 --out exports/germany_overview.svg

# any bbox
python3 scripts/export_svg.py --tiles output/germany_game_map.mbtiles \
    --bbox 6.90,50.92,7.02,50.98 --zoom 14 --out exports/ausschnitt.svg

# one file per layer, all sharing the same viewBox
python3 scripts/export_svg.py --tiles output/germany_game_map.mbtiles \
    --region leverkusen --split --out exports/leverkusen/
```

Each map layer becomes one `<g id="...">` group, so Figma imports it as a named,
selectable group. Colors sit on the group, never on the individual paths — select
a group, change its fill, done. `--no-style` emits pure geometry.

Details and Figma import tips: [docs/SVG_EXPORT.md](docs/SVG_EXPORT.md).

## Size optimization

Every build ends with a report: source PBF size, archive size, tile count, zoom
range, layers, the largest layers by storage, the reduction in percent, and
concrete, file-and-key-specific suggestions for what to change if the result is
too big.

```
   layer                      bytes   share    features   zooms
   building                 35.4 MB   42.0%   1,636,876   z14–z14
   grass                    11.6 MB   13.8%     155,180   z11–z14
   forest                    7.8 MB    9.2%      58,386   z7–z14
   ...
   * `building` uses 42.0% of all layer bytes -> raise `layers.building.min_zoom` ...
   * `grass` uses 13.8% of all layer bytes -> set `grass.enabled: false` ...
   * zoom 14 alone holds 81% of the data -> lowering `tileset.max_zoom` by 1 ...
```

(Real output from the Regierungsbezirk Köln build: 213.5 MB PBF → 62.9 MB
MBTiles, 70.5% reduction, 5,265 tiles.)

Run it again on any archive at any time:

```bash
python3 scripts/tile_stats.py --tiles output/germany_game_map.mbtiles \
    --input input/germany-latest.osm.pbf --json output/stats.json
```

The full playbook of levers, ordered by effect: [docs/OPTIMIZATION.md](docs/OPTIMIZATION.md).

## Updating the OSM data

OSM changes daily. To refresh:

```bash
./scripts/fetch_data.sh germany --force    # re-download the extract
./build_germany_map                        # rebuild from scratch
```

A full rebuild is the recommended path — it is a single command, it takes about
an hour, and it avoids the failure modes of incremental updates. Geofabrik
regenerates its extracts daily; `germany-latest.osm.pbf` always points at the
newest one. Keep the previous `output/*.mbtiles` around until you have checked
the new build.

## License

The map data is **© OpenStreetMap contributors** and licensed under the
**Open Database License (ODbL) 1.0**. That license carries obligations —
attribution, share-alike on derived databases, and keeping the data open.

Read [docs/LICENSE_OSM.md](docs/LICENSE_OSM.md) before you publish or pass on
anything built with this pipeline. The attribution is written into the MBTiles
and PMTiles metadata and into every exported SVG automatically. **Do not remove
those notices.**

The code in this repository (profile, scripts, configuration) is yours to use
freely; the ODbL applies to the OSM-derived data it produces.
