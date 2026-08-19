# Size optimization

Every build ends with a report naming the largest layers and what to change. This
document is the ordered playbook behind those suggestions.

Re-run the analysis on any archive at any time:

```bash
python3 scripts/tile_stats.py --tiles output/germany_game_map.mbtiles \
    --input input/germany-latest.osm.pbf --json output/stats.json
```

## The quickest lever: the slim preset

If the map is a base-map backdrop — roads, water, nature, no buildings, no
labels, no POIs — use the ready-made preset instead of tuning layer by layer:

```bash
./build_test_region  -- --layers-config=config/layers.slim.yml
./build_germany_map  -- --layers-config=config/layers.slim.yml
```

It keeps 13 layers (`road_motorway` … `road_residential`, `rail`, `water`,
`waterway`, `forest`, `park`, `garden`, `grass`) and switches off the other 19.
Measured on the Germany build: **1.63 GB -> 0.96 GB** (−41%), 78.6% smaller
than the source PBF. The tile count barely moves (231,439 → 223,074, −3.6%):
tiles still exist wherever a road or a forest does, they just carry less. That
is why this is −41% rather than the −50% the layer bytes alone suggest.

After the preset, `grass` becomes the single biggest layer at 33.7% (351 MB of
4.3 million meadow, scrub and heath polygons). Switching it off too takes
Germany to roughly **0.68 GB**.

What it costs you: the country/state background area (`land`), the coastline,
all borders, every place label, buildings, footpaths, service roads, stations
and all POIs. `config/layers.slim.yml` lists them at the top; flip any
`enabled: false` back to `true` to get one back.

## Levers, strongest first

### 1. Lower the deepest zoom — the single biggest lever

Each extra zoom level roughly triples the data. Typically ~75-80% of a tileset
sits at the deepest zoom alone.

```yaml
# config/zoom_levels.yml
tileset:
  max_zoom: 13        # from 14
```

Renderers keep drawing deeper zooms by overzooming, so the map still works at
z14–z17 — it just carries less detail. Check the "tiles per zoom" table to see
what you would be giving up.

### 2. Buildings

Usually the largest single layer.

```yaml
# config/zoom_levels.yml
layers:
  building: { min_zoom: 15 }     # only at the deepest zoom

# config/layers.yml
building:
  min_pixel_size: 3.0            # drops sheds, garages, carports
  enabled: false                 # nuclear option
```

### 3. Paths and footways

`path` is regularly the second largest layer, because footways are everywhere.

```yaml
# config/layers.yml
path:
  classes: [track, pedestrian]   # drop footway + cycleway — usually most of the volume
  merge_min_length: 2.0
```

### 4. Small roads

```yaml
# config/zoom_levels.yml
layers:
  road_residential: { min_zoom: 13 }
  road_service:     { min_zoom: 15 }

# config/layers.yml
road_service:
  enabled: false
```

### 5. Names and labels

Names are pure string payload *and* they block geometry merging, so they cost
twice. Raising `name_min_zoom` is often a surprisingly large win.

```yaml
# config/layers.yml
road_residential: { name_min_zoom: 15 }
road_tertiary:    { name_min_zoom: 14 }
```

Thin out point labels with the label grid:

```yaml
place_village:
  label_grid_max_zoom: 13
  label_grid_size: 128     # bigger cell
  label_grid_limit: 2      # fewer per cell
```

### 6. Simplify harder

Global, affects every line and outline at every zoom:

```yaml
# config/zoom_levels.yml
simplification:
  tolerance: 0.5           # from 0.375
  bands:
    - { max_zoom: 5,  tolerance: 1.5 }
    - { max_zoom: 8,  tolerance: 1.0 }
```

### 7. Collapse the road layers

```yaml
# config/layers.yml
road_layer_mode: single
```

All roads land in one `road` layer with the same `class` attribute. Each vector
tile layer carries its own key/value dictionary, so 8 road layers means 8
dictionaries per tile; one layer means one. Expect a few percent overall.

You lose the 1:1 mapping onto Figma groups — the SVG exporter can restore it with
`--group-by-class`, which emits `road__motorway`, `road__primary`, … sub-groups.

### 8. Drop nature layers you do not draw

```yaml
grass:  { enabled: false }     # meadows/scrub — the most optional
garden: { enabled: false }
```

### 9. Drop POI layers

Small individually, but they add up, and they are trivially separable:

```yaml
poi_historic:  { enabled: false }
poi_monument:  { enabled: false }
```

Or push them deeper:

```yaml
# config/zoom_levels.yml
features:
  poi:
    poi_church: 15
```

### 10. Smaller minimum feature sizes

```yaml
# config/layers.yml
forest: { min_pixel_size: 5.0, merge_min_area: 4.0 }
water:  { min_pixel_size: 3.0 }
grass:  { min_pixel_size: 6.0 }
```

## Format choice: MBTiles or PMTiles?

The build produces both. They contain identical tiles.

| | MBTiles | PMTiles |
|---|---------|---------|
| Container | SQLite database | single flat file |
| Size | baseline | **~20-25% smaller** (identical tiles stored once) |
| Local random access | fast (SQLite index) | fast (embedded directory) |
| Serving | needs a tile server | HTTP range requests, no server |
| Tooling | very broad (QGIS, tilelive, mbutil, …) | growing (MapLibre, QGIS plugin, `pmtiles` CLI) |
| Editing / re-processing | easy — it is SQL | read-oriented |

**Recommendation:** keep `.mbtiles` as the working master — it is the format every
tool reads and it is trivial to inspect and re-process with SQL. Ship `.pmtiles`
as the distribution artifact: smaller, one file, and it works straight off static
storage with no server.

## What a good result looks like

Both figures below are measured, not projected — see [TEST_RESULTS.md](TEST_RESULTS.md).

| | Regierungsbezirk Köln | **Germany** |
|---|---|---|
| source `.osm.pbf` | 213.5 MB | **4.49 GB** |
| `.mbtiles` | 62.9 MB | **1.63 GB** |
| `.pmtiles` | 59.5 MB | **~1.48 GB** |
| reduction vs. PBF | 70.5% | **63.8%** |
| tiles | 5,265 | **231,439** |
| layers | 31 of 32 | **32 of 32** |
| build time (4 cores) | 3 min | **13 min** |

The archive lands at ~30–36% of the source PBF size. Germany at z0–z14 is
**1.63 GB** — a whole country, offline, on a phone if you want it there.

Where the bytes sit, for Germany:

| layer | share | features |
|-------|-------|----------|
| `building` | 33.7% | 33,765,974 |
| `grass` | 16.8% | 4,337,341 |
| `forest` | 10.1% | 1,450,046 |
| `path` | 9.7% | 7,164,624 |
| `road_residential` | 7.9% | 3,289,580 |

**z14 alone holds 78% of the data**, z12+z13 another 19%, and everything from
z0 to z11 together is 2.9% (60 MB) — the entire country overview costs less than
a photo.

Of that z14 bulk, 59% is the three layers that exist *only* there — `building`,
`path`, `road_service` — and the remaining 41% is the finest detail level of the
other 29 layers.

> Per-layer and per-zoom byte figures are **uncompressed** layer sizes, which is
> what Planetiler's layerstats reports. They sum to 2.04 GB, against a 1.63 GB
> gzipped archive. Use them for proportions, not to add up to the file size.

**To halve it**, the measured distribution says exactly where to push:
`grass: {enabled: false}` (−16.8%) plus `building: {min_zoom: 15}` (−33.7% at
z14) takes Germany to roughly 800 MB with very little visible loss on a
game/adventure map. Dropping `path` as well gets it under 700 MB.
