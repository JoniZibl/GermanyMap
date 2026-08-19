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

| zoom | tiles | bytes |
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

## Still open: the Germany build

The Köln run proves the pipeline. The Germany run needs more machine than a
standard GitHub runner (4 GB input, tens of GB of scratch space). Two ways to get it:

```bash
# on your own machine
./build_germany_map
```

or via the same workflow, if you have access to a larger runner — change
`runs-on: ubuntu-latest` in `.github/workflows/build-map.yml`.

The only functional difference at Germany scale is that the `land` layer appears,
because the complete `admin_level=2` relation is present. Layer set, zoom windows,
simplification, attributes, output formats, statistics and SVG export are identical.

## Reproducing any of this

Actions tab → **Build vector map** → *Run workflow* → pick a region. Or:

```bash
cd GermanyVectorMap
./scripts/setup.sh
./build_test_region
```
