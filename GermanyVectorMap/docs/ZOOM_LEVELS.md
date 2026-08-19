# Zoom levels and geometry simplification

The governing rule: **the further out you zoom, the less geometry**. Both fewer
*features* and fewer *points per feature*.

## Tileset zoom range

Tiles are generated for **z0–z14** (`tileset.max_zoom` in `config/zoom_levels.yml`).

Vector tiles are resolution-independent. A renderer keeps drawing z15, z16, z17
by *overzooming* the z14 tile: lines, outlines and text stay perfectly sharp at
any scale — there is simply no additional OSM detail past z14. This is the
standard trade-off and it is what keeps a Germany build in the low-GB range
instead of the tens of GB.

Raise it if you genuinely need more detail:

```yaml
tileset:
  max_zoom: 15          # ~2.5-3x larger output
```

## What appears when

| Zoom | Layers that switch on |
|------|----------------------|
| **0** | `land`, `boundary` (country), `coastline` |
| **3** | `place_city` (≥1M inhabitants) |
| **4** | `water`, `road_motorway`, `boundary` (state), `land` (states), cities ≥500k |
| **5** | `waterway` (rivers), cities ≥200k |
| **6** | `road_trunk`, cities ≥100k |
| **7** | `road_primary`, `forest`, `place_town` (≥50k) |
| **8** | `rail` (main lines), `boundary` (county), towns ≥20k |
| **9** | `road_secondary`, `park`, `transport` (major airports), towns |
| **10** | `road_tertiary`, `waterway` (canals) |
| **11** | `place_village` (≥5k), `grass`, `rail` (other), `transport` (stations) |
| **12** | `road_residential`, `place_suburb`, `waterway` (streams), villages, `poi_ruin`, `poi_museum`, `poi_tower` |
| **13** | `garden`, `path` (pedestrian, tracks), hamlets, `poi_church`, `poi_monument`, `poi_viewpoint`, `poi_historic`, `transport` (halts) |
| **14** | `building`, `road_service`, `path` (footways, cycleways) |
| **15+** | overzoomed from z14 — sharp, no new data |

`poi_castle` is an exception: castles and palaces are landmarks, so they start at
**z10**.

Every number above lives in `config/zoom_levels.yml` and can be changed without
touching any code.

## Feature-level rules

Some layers switch on progressively rather than all at once. Those rules sit under
`features:` in `config/zoom_levels.yml`:

```yaml
features:
  waterway:
    river:  5      # rivers early
    canal:  10
    stream: 12     # brooks late
  place_city:
    - { min_population: 1000000, zoom: 3 }
    - { min_population: 500000,  zoom: 4 }
    - { min_population: 200000,  zoom: 5 }
    - { min_population: 100000,  zoom: 6 }
    - { min_population: 0,       zoom: 7 }
```

## Geometry simplification

Three independent mechanisms shrink geometry as you zoom out.

### 1. Point reduction (simplification)

Every line and polygon outline is simplified per zoom with a pixel tolerance.
A coastline stored with 40,000 points at z14 is stored with a few hundred at z5.

```yaml
simplification:
  method: RETAIN_IMPORTANT_POINTS   # keeps corners and characteristic shape
  tolerance: 0.375                  # tile pixels, at every zoom except the deepest
  tolerance_at_max_zoom: 0.0625     # near-full detail at z14
  bands:
    - { max_zoom: 5,  tolerance: 1.0    }   # Germany view: strongly simplified
    - { max_zoom: 8,  tolerance: 0.625  }
    - { max_zoom: 11, tolerance: 0.4375 }   # city view: medium
    - { max_zoom: 13, tolerance: 0.3125 }   # close-up: fine
```

Methods available: `RETAIN_IMPORTANT_POINTS` (default, best shape retention),
`DOUGLAS_PEUCKER`, `VISVALINGAM_WHYATT`, `RETAIN_EFFECTIVE_AREAS`,
`RETAIN_WEIGHTED_EFFECTIVE_AREAS`.

The tolerance is in *tile pixels*, so it is scale-relative: the map stays visually
correct at every zoom, it just stops storing detail nobody can see.

### 2. Small feature removal

A feature smaller than `min_pixel_size` at a given zoom is dropped at that zoom
and reappears further in. A village pond is invisible at z8 and present at z13
without any per-zoom rule being written by hand.

```yaml
forest:
  min_pixel_size: 3.0                # below the deepest zoom
  min_pixel_size_at_max_zoom: 1.0
```

### 3. Merging inside the tile

At every zoom below the deepest, connected line strings are merged and
overlapping polygons are unioned per tile, then short/small leftovers are dropped:

```yaml
road_primary:
  merge_lines: true
  merge_min_length: 0.5      # px — removes fragments a road was split into
forest:
  merge_polygons: true
  merge_min_area: 2.0        # px² — merges adjacent forest patches into one shape
```

This is why `name` only starts at z12–z15 per layer: features with different
names cannot be merged, so withholding the name at low zoom lets far more
geometry collapse into single shapes.

## Checking the result

```bash
python3 scripts/tile_stats.py --tiles output/germany_game_map.mbtiles
```

The "tiles per zoom" table shows the byte distribution across zooms. A healthy
build has the vast majority of its bytes at the deepest one or two zooms and only
kilobytes at z0–z6.
