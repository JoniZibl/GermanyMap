# Test results

## Status

The pipeline is complete and has been run end to end on **real OpenStreetMap
data for the Regierungsbezirk Köln test region**, on a GitHub Actions runner.
All numbers below are measured, not estimated.

Run: [Actions run #2](https://github.com/JoniZibl/GermanyMap/actions/runs/32239403157)
· workflow [`.github/workflows/build-map.yml`](../../.github/workflows/build-map.yml)
· total job time **3 min 22 s** on a 4-core runner.

---

## Regierungsbezirk Köln — measured

```
source OSM PBF      : 213.5 MB   (koeln-regbez-latest.osm.pbf, Geofabrik)
vector tile archive :  62.9 MB   (koeln_regbez_game_map.mbtiles)
                       59.5 MB   (koeln_regbez_game_map.pmtiles)
reduction vs. PBF   : 70.5%
tiles               : 5,265
zoom range          : z0–z14
layers              : 31 of 32
bounds              : 5.52125, 50.22643, 7.79441, 51.253
```

Only `land` is missing, and necessarily so: a sub-region extract is cut out of
Germany, so the `admin_level=2` relation that forms the country area has lost
most of its member ways. It appears in the Germany build.

### Bytes per zoom

Uncompressed layer bytes (Planetiler's layerstats), so these sum to 2.04 GB
rather than to the 1.63 GB gzipped archive — read them as proportions.

| zoom | tiles | bytes | share |
|------|-------|-------|
| z3 | 1 | 85 B |
| z4 | 1 | 269 B |
| z5 | 1 | 988 B |
| z6 | 1 | 2.4 KB |
| z7 | 2 | 11.2 KB |
| z8 | 4 | 45.2 KB |
| z9 | 12 | 197.8 KB |
| z10 | 29 | 464.8 KB |
| z11 | 86 | 1.4 MB |
| z12 | 289 | 4.8 MB |
| z13 | 1,025 | 9.1 MB |
| **z14** | **3,814** | **68.3 MB** |

Exactly the intended shape: the whole-region overview costs kilobytes, the detail
sits at the deepest zoom. z14 alone holds 81% of the data.

### Largest layers

| layer | bytes | share | features | zooms |
|-------|-------|-------|----------|-------|
| `building` | 35.4 MB | 42.0% | 1,636,876 | z14 |
| `grass` | 11.6 MB | 13.8% | 155,180 | z11–z14 |
| `forest` | 7.8 MB | 9.2% | 58,386 | z7–z14 |
| `road_residential` | 6.5 MB | 7.7% | 131,035 | z12–z14 |
| `path` | 6.3 MB | 7.4% | 228,799 | z14 |
| `waterway` | 3.6 MB | 4.2% | 67,644 | z5–z14 |
| `park` | 2.4 MB | 2.8% | 12,700 | z9–z14 |
| `road_service` | 2.2 MB | 2.6% | 92,101 | z14 |
| `road_secondary` | 1.4 MB | 1.6% | 31,953 | z9–z14 |
| `water` | 1.3 MB | 1.5% | 18,402 | z7–z14 |
| `road_tertiary` | 1.3 MB | 1.5% | 27,950 | z10–z14 |
| `garden` | 726.9 KB | 0.8% | 19,593 | z13–z14 |
| `road_primary` | 723.6 KB | 0.8% | 18,402 | z7–z14 |
| `rail` | 513.6 KB | 0.6% | 10,350 | z8–z14 |
| `road_motorway` | 445.3 KB | 0.5% | 9,180 | z4–z14 |
| *(16 more)* | 2.4 MB | 2.8% | | |

One surprise worth knowing about: **`grass` is the second largest layer at 13.8%**
— meadows, scrub and heath are mapped densely in the Rhineland. It is also the
most optional layer on a game/adventure map. `grass: {enabled: false}` in
`config/layers.yml` alone removes ~14% of the archive.

`building` at 42% with 1.6 million features is normal and is the first lever if
the file needs to shrink.

## SVG exports — measured

All produced in the same run, with the project palette applied.

| file | region | zoom | features | size |
|------|--------|------|----------|------|
| `koeln_regbez_overview.svg` | Regierungsbezirk Köln | z11 | 18,239 | 6.1 MB |
| `koeln_test.svg` | Köln | z13 | 27,190 | 3.5 MB |
| `leverkusen_test.svg` | Leverkusen | z14 | 73,518 | 7.2 MB |
| `koeln_layers/` (27 files) | Köln, one per layer | z13 | 27,190 | 3.6 MB total |

The Köln export at z13 (3.5 MB, 27 layers) is the sweet spot for Figma. The
Leverkusen z14 export includes buildings and footpaths and is noticeably heavier
— usable, but drop `building,path` if Figma gets sluggish.

## Extrapolation to Germany

The tileset comes out at **29.5% of the source PBF size**. `germany-latest.osm.pbf`
is roughly 4 GB, which puts the full Germany build at **≈1.2 GB MBTiles / ≈1.1 GB
PMTiles** with the shipped configuration — comfortably below the 2.5–5 GB that was
originally assumed. The Rhineland is denser than the German average, so this is a
conservative estimate rather than an optimistic one.

## Germany with the slim preset — measured

Same input, same zoom range, `config/layers.slim.yml` instead of the default:
13 base-map layers, the other 19 off.
Run: [Actions run #6](https://github.com/JoniZibl/GermanyMap/actions/runs/32244152963)
· 8 min of build time · report: [`reports/germany_game_map-slim.stats.json`](reports/germany_game_map-slim.stats.json).

| | full | slim | Δ |
|---|---|---|---|
| `.mbtiles` | 1.63 GB | **0.96 GB** | **−41.0%** |
| `.mbtiles` + `.pmtiles` | 3.10 GB | 1.78 GB | −42.5% |
| tiles | 231,439 | 223,074 | −3.6% |
| layers | 32 | 13 | |
| reduction vs. PBF | 63.8% | **78.6%** | |
| share of data at z14 | 77.9% | 59.5% | |

Two things worth reading off this:

**The tile count barely drops.** Removing 19 layers cuts 41% of the bytes but
only 3.6% of the tiles — a tile still exists wherever any kept layer has data.
Per-tile overhead is why the saving is −41% and not the −50% that the layer byte
totals on their own suggest.

**`grass` becomes the dominant layer**, at 33.7% (351 MB, 4.3 million polygons
of meadow, scrub and heath), ahead of `forest` at 20.2%. Switching it off as
well would take the build to roughly 0.68 GB.

### Layer distribution, slim

| layer | bytes | share | features |
|-------|-------|-------|----------|
| `grass` | 351 MB | 33.7% | 4,337,341 |
| `forest` | 211 MB | 20.2% | 1,450,046 |
| `road_residential` | 165 MB | 15.8% | 3,289,580 |
| `waterway` | 79 MB | 7.6% | 1,422,726 |
| `water` | 51 MB | 4.9% | 712,290 |
| `park` | 43 MB | 4.2% | 339,643 |
| `road_tertiary` | 38 MB | 3.6% | 767,725 |
| `road_secondary` | 35 MB | 3.4% | 769,512 |
| `garden` | 29 MB | 2.8% | 726,178 |
| `road_primary` | 16 MB | 1.5% | 383,475 |
| `rail` | 13 MB | 1.3% | 260,512 |
| `road_motorway` | 9 MB | 0.8% | 178,666 |
| `road_trunk` | 4 MB | 0.4% | 85,114 |

## Earlier validation

Before the Köln run, the pipeline was validated on the Monaco extract
(`monaco-latest.osm.pbf`, 435 KB → 112 KB MBTiles, 25 of 32 layers, 74.2%
reduction). That run also confirmed things the Köln run does not surface:

- the SVG output rendered to PNG shows the real Monaco coastline, the Monte Carlo
  street network and correct POI names — projection, clipping and paint order are
  right
- `road_layer_mode: single` collapses the road layers into one `road` layer with
  `class` preserved
- `scripts/apply_palette.py` propagates `style/palette.json` into both the
  MapLibre style and the SVG exports

## Germany — measured

Run: [Actions run #3](https://github.com/JoniZibl/GermanyMap/actions/runs/32240142133)
· **13 min** of build time on the same 4-core runner (15 min total including the
4.5 GB download). Full report: [`reports/germany_game_map.stats.json`](reports/germany_game_map.stats.json).

```
source OSM PBF      : 4.49 GB    (germany-latest.osm.pbf, Geofabrik)
vector tile archive : 1.63 GB    (germany_game_map.mbtiles)
                      ~1.48 GB   (germany_game_map.pmtiles)
reduction vs. PBF   : 63.8%
tiles               : 231,439
zoom range          : z0–z14
layers              : 32 of 32   ← `land` is present, as expected
```

### Bytes per zoom

Uncompressed layer bytes (Planetiler's layerstats), so these sum to 2.04 GB
rather than to the 1.63 GB gzipped archive — read them as proportions.

| zoom | tiles | bytes | share |
|------|-------|-------|
| z0 | 1 | **61 B** |
| z1 | 1 | 79 B | 0.0% |
| z2 | 1 | 179 B | 0.0% |
| z3 | 1 | 681 B | 0.0% |
| z4 | 1 | 4.1 KB | 0.0% |
| z5 | 4 | 32.8 KB | 0.0% |
| z6 | 6 | 80.8 KB | 0.0% |
| z7 | 18 | 399.2 KB | 0.0% |
| z8 | 58 | 1.4 MB | 0.1% |
| z9 | 216 | 5.3 MB | 0.3% |
| z10 | 767 | 12.6 MB | 0.6% |
| z11 | 2,887 | 40.6 MB | 1.9% |
| z12 | 11,157 | 135.1 MB | 6.5% |
| z13 | 43,686 | 266.7 MB | 12.8% |
| **z14** | **172,635** | **1.59 GB** | **77.9%** |

All of Germany at z0 is **61 bytes**. z0–z11 together is 60 MB — 2.9% of the
data carries every view from the whole country down to a small town.

What makes z14 dominate is two things multiplying: it has 172,635 tiles against
z13's 43,686 (~4x), *and* three layers appear there for the first time —
`building` (706 MB), `path` (204 MB) and `road_service` (48 MB). Those three are
958 MB, 59% of everything at z14; the other 41% is the finest detail level of
the remaining 29 layers.

### Largest layers

| layer | bytes | share | features | zooms |
|-------|-------|-------|----------|-------|
| `building` | 706.2 MB | 33.7% | 33,765,974 | z14 |
| `grass` | 351.4 MB | 16.8% | 4,337,341 | z11–z14 |
| `forest` | 210.7 MB | 10.1% | 1,450,046 | z7–z14 |
| `path` | 203.6 MB | 9.7% | 7,164,624 | z14 |
| `road_residential` | 164.6 MB | 7.9% | 3,289,580 | z12–z14 |
| `waterway` | 79.3 MB | 3.8% | 1,422,726 | z5–z14 |
| `water` | 51.1 MB | 2.4% | 712,290 | z4–z14 |
| `road_service` | 48.2 MB | 2.3% | 1,911,873 | z14 |
| `park` | 43.4 MB | 2.1% | 339,643 | z9–z14 |
| `road_tertiary` | 37.8 MB | 1.8% | 767,725 | z10–z14 |
| `road_secondary` | 35.2 MB | 1.7% | 769,512 | z9–z14 |
| `land` | 31.3 MB | 1.5% | 453,101 | z0–z14 |

33.7 million buildings and 7.2 million path segments — and the whole thing still
fits in 1.63 GB.

### SVG exports from the Germany tileset

| file | region | zoom | layers | features | size |
|------|--------|------|--------|----------|------|
| `germany_overview.svg` | Deutschland | z6 | 8 | 7,621 | 506 KB |
| `nrw.svg` | Nordrhein-Westfalen | z10 | 15 | 81,379 | 12.0 MB |
| `koeln_test.svg` | Köln | z13 | 28 | 27,792 | 3.6 MB |
| `leverkusen_test.svg` | Leverkusen | z14 | 31 | 81,451 | 8.0 MB |
| `koeln_layers/` | Köln, one file per layer | z13 | 28 files | 27,792 | 3.7 MB |

All committed in [`../exports/`](../exports/). `nrw.svg` at 12 MB is heavy for
Figma — re-export it with `--exclude-layers building,path` if it drags.

The Köln cut from the Germany tileset has 28 layers where the same cut from the
Köln-only tileset had 27: `land` is present now.

### How the estimate did

The Köln run projected Germany at ~1.2 GB from the PBF-size ratio. The measured
result is **1.63 GB** — the projection was 25% low, because the Rhineland turned
out to be *less* dominated by buildings than the national average, not more.
Close enough to plan with, but the measured number is the one to use.

## Germany with the slim preset — measured

Same input, same zoom range, `config/layers.slim.yml` instead of the default:
13 base-map layers, the other 19 off.
Run: [Actions run #6](https://github.com/JoniZibl/GermanyMap/actions/runs/32244152963)
· 8 min of build time · report: [`reports/germany_game_map-slim.stats.json`](reports/germany_game_map-slim.stats.json).

| | full | slim | Δ |
|---|---|---|---|
| `.mbtiles` | 1.63 GB | **0.96 GB** | **−41.0%** |
| `.mbtiles` + `.pmtiles` | 3.10 GB | 1.78 GB | −42.5% |
| tiles | 231,439 | 223,074 | −3.6% |
| layers | 32 | 13 | |
| reduction vs. PBF | 63.8% | **78.6%** | |
| share of data at z14 | 77.9% | 59.5% | |

Two things worth reading off this:

**The tile count barely drops.** Removing 19 layers cuts 41% of the bytes but
only 3.6% of the tiles — a tile still exists wherever any kept layer has data.
Per-tile overhead is why the saving is −41% and not the −50% that the layer byte
totals on their own suggest.

**`grass` becomes the dominant layer**, at 33.7% (351 MB, 4.3 million polygons
of meadow, scrub and heath), ahead of `forest` at 20.2%. Switching it off as
well would take the build to roughly 0.68 GB.

### Layer distribution, slim

| layer | bytes | share | features |
|-------|-------|-------|----------|
| `grass` | 351 MB | 33.7% | 4,337,341 |
| `forest` | 211 MB | 20.2% | 1,450,046 |
| `road_residential` | 165 MB | 15.8% | 3,289,580 |
| `waterway` | 79 MB | 7.6% | 1,422,726 |
| `water` | 51 MB | 4.9% | 712,290 |
| `park` | 43 MB | 4.2% | 339,643 |
| `road_tertiary` | 38 MB | 3.6% | 767,725 |
| `road_secondary` | 35 MB | 3.4% | 769,512 |
| `garden` | 29 MB | 2.8% | 726,178 |
| `road_primary` | 16 MB | 1.5% | 383,475 |
| `rail` | 13 MB | 1.3% | 260,512 |
| `road_motorway` | 9 MB | 0.8% | 178,666 |
| `road_trunk` | 4 MB | 0.4% | 85,114 |

## Earlier validation

Before the Köln run the pipeline was validated on the Monaco extract
(`monaco-latest.osm.pbf`, 435 KB → 112 KB MBTiles, 25 of 32 layers, 74.2%
reduction). That run confirmed things the country builds do not surface:

- the SVG output rendered to PNG shows the real Monaco coastline, the Monte
  Carlo street network and correct POI names — projection, clipping and paint
  order are right
- `road_layer_mode: single` collapses the road layers into one `road` layer with
  `class` preserved
- `scripts/apply_palette.py` propagates `style/palette.json` into both the
  MapLibre style and the SVG exports

## Reproducing any of this

Actions tab → **Build vector map** → *Run workflow* → pick a region. The runner
downloads the extract, builds, measures and commits the SVGs back to
[`../exports/`](../exports/).

Locally:

```bash
cd GermanyVectorMap
./scripts/setup.sh
./build_test_region      # Regierungsbezirk Köln, ~3 min
./build_germany_map      # all of Germany, ~13 min plus the download
```
