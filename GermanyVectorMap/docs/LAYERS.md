# Layers

32 layers. Every feature carries a `class` attribute; `name` is written from the
zoom configured per layer (`name_min_zoom` in `config/layers.yml`). No colors,
ever — see [STYLING.md](STYLING.md).

Enable/disable a layer with `enabled: false` in `config/layers.yml`; change its
zoom window in `config/zoom_levels.yml`.

---

## Background / administrative

### `land` — polygon
Germany's area itself, plus the Bundesländer.

| OSM | class |
|-----|-------|
| relation `type=boundary` + `boundary=administrative` + `admin_level=2` | `country` |
| relation `type=boundary` + `boundary=administrative` + `admin_level=4` | `state` |

Only relations qualify (`type=boundary` exists on relations only), so closed
boundary ways cannot leak in as bogus polygons. Set `include_states: false` to
keep only the country area.

> The land area, and therefore the coastline, comes from OSM itself — no external
> Natural Earth or water-polygon shapefile is needed, and the build stays OSM-only.
> In a *sub-region* extract (Köln, NRW) the `admin_level=2` relation is cut off by
> the extract boundary and cannot be assembled; Planetiler logs
> `osm_boundary_missing_way` and skips it. That is expected and harmless — the
> full Germany extract contains the complete relation.

### `boundary` — line
| admin_level | class | from zoom |
|-------------|-------|-----------|
| 2 | `country` | 0 |
| 4 | `state` | 4 |
| 6 | `county` | 8 |

The admin level is taken from the **relations a way belongs to**, using the most
significant (lowest) level — a way that is both a municipal and a state border is
correctly drawn as a state border. Offshore segments (`maritime=yes`) are dropped
unless `include_maritime: true`. `include_counties: false` removes the Landkreis lines.

### `coastline` — line
`natural=coastline`. The shoreline as a line, for styling the coast edge.

---

## Water

### `water` — polygon
| OSM | class |
|-----|-------|
| `natural=water` | value of `water=*`, else `water` (lake, pond, lagoon, reservoir, …) |
| `landuse=reservoir`, `landuse=basin` | `reservoir` / `basin` |
| `waterway=riverbank`, `waterway=dock` | `riverbank` / `dock` |

`water=wastewater` and `water=sewage` are excluded. Small ponds survive the
`min_pixel_size` filter only at high zoom, so lakes appear far out and ponds late.

### `waterway` — line
| class | from zoom | note |
|-------|-----------|------|
| `river` | 5 | short fragments are removed by line merging at low zoom |
| `canal` | 10 | |
| `stream` | 12 | `include_stream: false` removes all brooks |
| `ditch`, `drain` | 14 | **off by default** (`include_ditch_drain`) |

Carries `structure` = `bridge`/`tunnel` from z12.

---

## Nature

| Layer | OSM | classes |
|-------|-----|---------|
| `forest` | `landuse=forest`, `natural=wood` | `forest`, `wood` |
| `park` | `leisure=park\|nature_reserve\|recreation_ground\|common`, `boundary=national_park\|protected_area` | the matched value |
| `garden` | `leisure=garden`, `landuse=allotments\|orchard\|vineyard` | the matched value |
| `grass` | `landuse=meadow\|grass\|village_green`, `natural=grassland\|heath\|scrub` | the matched value |

`grass` is the most optional of the four — it is the first thing to switch off if
the map feels noisy or the file is too large.

---

## Roads

One layer per road class by default (`road_layer_mode: split`), which maps 1:1
onto Figma groups. Set `road_layer_mode: single` to collapse them into one `road`
layer with the same `class` attribute — slightly smaller tiles, see
[OPTIMIZATION.md](OPTIMIZATION.md).

| Layer | OSM `highway=` | from zoom |
|-------|----------------|-----------|
| `road_motorway` | `motorway`, `motorway_link` | 4 |
| `road_trunk` | `trunk`, `trunk_link` | 6 |
| `road_primary` | `primary`, `primary_link` | 7 |
| `road_secondary` | `secondary`, `secondary_link` | 9 |
| `road_tertiary` | `tertiary`, `tertiary_link` | 10 |
| `road_residential` | `residential`, `unclassified`, `living_street` | 12 |
| `road_service` | `service` | 14 |
| `path` | `footway`/`path`, `cycleway`, `track`, `pedestrian`, `steps`, `bridleway` | 13–15 by class |

Attributes: `class`, `link` (1 on ramps), `structure` (`bridge`/`tunnel`, z12+),
`name` (per-layer zoom), `ref` (motorway/trunk numbers, z8/z9+).
Draw order within a tile follows the OSM layer/bridge/tunnel z-order.

Driveways and parking aisles are excluded from `road_service` by default
(`include_driveways`, `include_parking_aisles`).

### `rail` — line
`railway=rail|light_rail|subway|tram|narrow_gauge|funicular`.
Main lines (`usage=main|branch`) from z8, everything else from z11. Sidings, yards
and spurs are off by default (`include_service_tracks`). Abandoned and disused
track is never included.

---

## Buildings

### `building` — polygon, z14 only
Any `building=*` except `building=no`. No attributes by default — set
`keep_class: true` to keep a coarse `class` for the notable types (church, castle,
train_station, hospital, …).

Buildings never appear at country or regional level; `min_pixel_size: 2.0` drops
sheds and garages. This is usually the largest layer — see [OPTIMIZATION.md](OPTIMIZATION.md).

---

## Places

Taken from **nodes only** — the matching admin relations would duplicate every
label. Requires a `name`.

| Layer | `place=` | zoom by population |
|-------|----------|--------------------|
| `place_city` | `city` | ≥1M → z3, ≥500k → z4, ≥200k → z5, ≥100k → z6, else z7 |
| `place_town` | `town` | ≥50k → z7, ≥20k → z8, else z9 |
| `place_village` | `village` | ≥5k → z11, else z12 |
| `place_village` | `hamlet`, `isolated_dwelling` | z13 |
| `place_suburb` | `suburb`, `quarter`, `borough`, `neighbourhood` | z12 |

Attributes: `class`, `name`, `population`, `capital` (2 = Berlin, 4 = state capital).
A label grid thins dense areas at low zoom so the biggest places win.

---

## Transport

### `transport` — point
| OSM | class | from zoom |
|-----|-------|-----------|
| `railway=station` | `station` | 11 |
| `railway=halt` | `halt` | 13 |
| `aeroway=aerodrome` with `iata` or international | `airport` | 9 |
| `aeroway=aerodrome`, other | `airport` | 13 |

Attributes: `class`, `name`, `ref` (IATA code).

---

## POIs

Kept in separate layers, strictly apart from the base map layers, so they can be
toggled and styled on their own.

| Layer | OSM | classes | from zoom |
|-------|-----|---------|-----------|
| `poi_castle` | `historic=castle\|palace\|fort`, `building=castle` | `castle`, `palace`, `fortress`, or the `castle_type` value | 10 |
| `poi_church` | `amenity=place_of_worship`, `building=church\|chapel\|cathedral\|monastery` | the `religion` value, else the building type | 13 |
| `poi_ruin` | `historic=ruins\|archaeological_site`, `ruins=yes` | `ruins`, `archaeological_site` | 12 |
| `poi_monument` | `historic=monument\|memorial`, `man_made=obelisk` | `monument`, `memorial`, `obelisk` | 13 |
| `poi_viewpoint` | `tourism=viewpoint` | `viewpoint` | 13 |
| `poi_museum` | `tourism=museum` | `museum` | 12 |
| `poi_tower` | `man_made=tower` (landmark types only), `man_made=lighthouse`, `historic=tower` | `observation`, `bell_tower`, `watchtower`, `lighthouse`, `historic`, … | 12 |
| `poi_historic` | remaining `historic=*` worth showing | `manor`, `monastery`, `fort`, `city_gate`, `heritage`, `aqueduct`, … | 13 |

Polygons become a point on the surface, so a castle is one marker, not an outline.
Named POIs win over unnamed ones when the label grid thins points out.

Purely technical towers (communication, lighting, monitoring masts) are **never**
included.

---

## Deliberately excluded

Never emitted, at any zoom — this is what keeps the map slim and readable:

post boxes · waste baskets · power towers and power lines · single trees ·
parking meters · house numbers · shops and retail · restaurants and cafés ·
benches · traffic signs and signals · lane counts · speed limits · fences and
walls · street lamps · technical infrastructure · surface/material tags ·
opening hours · operator and brand tags · every other OSM micro-attribute

To add something back, extend `GermanyMapProfile.java` and give it a layer in the
two YAML files.
