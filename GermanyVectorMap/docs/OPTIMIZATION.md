# Size optimization

Every build ends with a report naming the largest layers and what to change. This
document is the ordered playbook behind those suggestions.

Re-run the analysis on any archive at any time:

```bash
python3 scripts/tile_stats.py --tiles output/germany_game_map.mbtiles \
    --input input/germany-latest.osm.pbf --json output/stats.json
```

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

Measured on the Regierungsbezirk Köln test region (see [TEST_RESULTS.md](TEST_RESULTS.md)):

| | |
|---|---|
| source `koeln-regbez-latest.osm.pbf` | 213.5 MB |
| `koeln_regbez_game_map.mbtiles` | 62.9 MB |
| `koeln_regbez_game_map.pmtiles` | 59.5 MB |
| reduction vs. PBF | 70.5% |
| tiles | 5,265 |

The archive lands at **~30% of the source PBF size**. Applied to
`germany-latest.osm.pbf` (~4 GB) that projects to roughly **1.2 GB MBTiles /
1.1 GB PMTiles** for the whole country at z0–z14, with the shipped configuration.

The build prints the exact numbers, and the Rhineland is denser than the German
average, so treat that as an upper-ish bound rather than a floor.

If you want it smaller still, the measured distribution says exactly where to
push: `building` at 42% and `grass` at 14% are three quarters of every megabyte
you would save. Turning `grass` off and moving `building` to z15 roughly halves
the archive with very little visible loss on a game/adventure map.
