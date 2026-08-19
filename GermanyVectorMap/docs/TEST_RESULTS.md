# Test results and validation status

## Summary

The pipeline is complete and was validated end to end against **real
OpenStreetMap data**. It was **not** yet run against Köln/NRW/Germany, because
the environment it was built in cannot reach the Geofabrik download servers.
Details and the exact commands to finish that step are below.

---

## What was validated

The full chain was executed on a real OSM extract (Monaco, 435 KB, the
`monaco-latest.osm.pbf` used as Planetiler's own test fixture):

```
input .osm.pbf → profile compile → Planetiler → MBTiles → PMTiles → statistics
                                                        ↘ layered SVG → rendered check
```

| Step | Result |
|------|--------|
| `scripts/build_profile.sh` | compiles cleanly against Planetiler 0.10.2, Java 21 |
| `scripts/build_map.sh` | all 8 steps run, no errors |
| MBTiles written | 112 KB, 15 tiles, z0–z14, 25 layers present |
| PMTiles written | 84.7 KB (−24.4% vs. MBTiles) |
| `scripts/tile_stats.py` | full report incl. per-layer bytes and suggestions |
| `scripts/export_svg.py` | valid SVG, one `<g>` per layer, correct paint order |
| SVG rendered to PNG | geometry verified visually — real coastline, real street network, correct POI names |
| `road_layer_mode: single` | verified: all roads collapse into one `road` layer, `class` preserved |
| `scripts/apply_palette.py` | palette propagates to both the MapLibre style and the SVG export |

### Measured numbers (Monaco)

```
source OSM PBF      : 434.9 KB
vector tile archive : 112.0 KB   (monaco.mbtiles)
                      84.7 KB    (monaco.pmtiles)
reduction vs. PBF   : 74.2%
tiles               : 15
zoom range          : z0–z14
layers              : 25

largest layers        bytes   share   features   zooms
  building          32.2 KB   25.4%      1,229   z14–z14
  path              24.6 KB   19.3%      1,108   z14–z14
  road_primary      18.8 KB   14.8%        487   z8–z14
  road_residential  14.3 KB   11.3%        300   z12–z14
  road_service       5.5 KB    4.3%        230   z14–z14
```

25 of the 30 layers appear. The five that do not (`land`, `road_motorway`,
`road_trunk`, `place_town`, `poi_ruin`) simply have no matching features in
Monaco — there is no motorway in Monaco, and the `admin_level=2` relation is cut
off by the extract boundary. Both are expected; see below.

### What the layer/attribute check confirmed

```
boundary         z7-14   fields = class, admin_level
building         z14-14  fields = (none)
coastline        z8-14   fields = class
forest           z12-14  fields = class
park             z11-14  fields = class, name
place_city       z7-14   fields = class, name, population
poi_castle       z10-14  fields = class, name
road_primary     z8-14   fields = class, link, name, structure
water            z13-14  fields = class, name
waterway         z12-14  fields = class, structure
…
```

Exactly the designed structure: geometry plus `class`, `name` only from its
configured zoom, `structure` for bridges/tunnels, `population` on places — and no
color attribute anywhere.

---

## What was not run, and why

`./build_test_region` (Regierungsbezirk Köln) and `./build_germany_map` could not
be executed here. The build environment's network policy blocks the OSM data
hosts:

```
download.geofabrik.de       → 403 (blocked by egress policy)
planet.openstreetmap.org    → unreachable
download.openstreetmap.fr   → unreachable
overpass-api.de             → unreachable
```

Only `github.com`, `raw.githubusercontent.com`, Maven Central and PyPI are
reachable, which is why a GitHub-hosted OSM extract was used to validate the
pipeline instead. No German extract is available from any reachable host.

This is an environment restriction, not a pipeline limitation. Nothing in the
code, configuration or scripts is specific to the test extract.

---

## Finishing the job on your machine

On any machine that can reach `download.geofabrik.de`:

```bash
cd GermanyVectorMap
./scripts/setup.sh            # Java/Python check, Planetiler jar, compile profile

./build_test_region           # Regierungsbezirk Köln — ~250 MB in, 2-5 minutes
```

Check the report it prints, then:

```bash
./build_germany_map           # ~4 GB in, 45-120 minutes
```

### What to check on the Köln run

- [ ] all layers except `land` present (`land` needs the full Germany extract)
- [ ] `building` and `path` are the largest layers — that is normal
- [ ] most bytes at z13/z14, only kilobytes at z0–z6
- [ ] `python3 scripts/serve_tiles.py --tiles output/koeln_regbez_game_map.mbtiles`
      and zoom from z6 to z16 — no gaps, no pop-in, sharp lines
- [ ] `python3 scripts/export_svg.py --tiles output/koeln_regbez_game_map.mbtiles --region koeln --out exports/koeln_test.svg`
      and open it in Figma — one named group per layer

### The one difference at Germany scale

The `land` layer appears. A sub-region extract cannot assemble the
`admin_level=2` relation that forms Germany's area, so the Köln and NRW builds
have no `land` layer and Planetiler logs `osm_boundary_missing_way`. The full
Germany extract contains the complete relation, so the country area — and with it
the coastline as a filled shape — renders from z0.

Everything else is identical between the two builds.
