# Building all of Germany

Run the test region first ([TEST_RESULTS.md](TEST_RESULTS.md) explains why and
what to check). Once that looks right, the country build is the same pipeline
with a bigger input — no configuration changes needed.

## The short version

```bash
cd GermanyVectorMap
./scripts/setup.sh          # once: Java/Python check, Planetiler, profile
./build_germany_map         # downloads germany-latest.osm.pbf if missing, then builds
```

Output:

```
output/germany_game_map.mbtiles
output/germany_game_map.pmtiles
output/germany_game_map.stats.json
output/germany_game_map.mbtiles.layerstats.tsv.gz
```

## Step by step

### 1. Get the data

```bash
./scripts/fetch_data.sh germany
```

Downloads `https://download.geofabrik.de/europe/germany-latest.osm.pbf` (~4 GB)
into `input/` and verifies the md5 Geofabrik publishes next to it.

If your network cannot reach Geofabrik, download the file anywhere else and drop
it into `input/germany-latest.osm.pbf` — nothing else in the pipeline cares where
it came from. Mirrors: <https://download.openstreetmap.fr/extracts/europe/>,
<https://planet.osm.org/> (full planet, then cut with `osmium extract`).

### 2. Check the machine

Measured on a 4-core / 16 GB GitHub runner (the Köln and Germany columns are
real numbers from [TEST_RESULTS.md](TEST_RESULTS.md), NRW is interpolated):

| | Test region (Köln) | NRW | Germany |
|---|---|---|---|
| input | 213 MB | ~800 MB | 4.49 GB |
| output `.mbtiles` | 62.9 MB | ~400 MB | 1.63 GB |
| RAM | 4 GB | 6 GB | **8-16 GB** |
| scratch disk | ~2 GB | ~8 GB | **~25 GB** |
| build time (4 cores) | **3 min** | ~6 min | **13 min** |
| + download | 15 s | ~40 s | ~2 min |

Germany is far quicker than it sounds — 13 minutes of actual work on four cores.
More cores scale it down close to linearly.

```bash
JAVA_XMX=12g ./build_germany_map                 # more heap
TMPDIR_OVERRIDE=/mnt/big/tmp ./build_germany_map # scratch on another disk
```

`build_germany_map` warns before starting if the volume has less than 40 GB free.
That threshold is deliberately conservative; the measured run used about 25 GB.

With less than ~10 GB of RAM, hand Planetiler a disk-backed node map:

```bash
./build_germany_map -- --nodemap-type=sortedtable --storage=mmap
```

Slower, but it completes on a small machine.

### 3. Build

```bash
./build_germany_map
```

The eight steps are the same as for the test region: check input → compile the
profile → read OSM → filter → simplify → build zoom levels → write MBTiles +
PMTiles → statistics.

### 4. Check the result

The build prints the report. What to look at:

- **archive size** — see the expectations in [OPTIMIZATION.md](OPTIMIZATION.md)
- **layers** — all 32 should be present (a sub-region build is missing `land`;
  the Germany build must have it, because the `admin_level=2` relation is complete)
- **largest layers** — `building` and `path` on top is normal
- **tiles per zoom** — most bytes at z13/z14, only kilobytes at z0-z6
- **suggestions** — act on them if the size is above what you want

```bash
python3 scripts/serve_tiles.py --tiles output/germany_game_map.mbtiles
# open http://localhost:8080/style.json in Maputnik or QGIS and zoom around
```

Check specifically: does Germany's outline appear at z0-z3? Do the Bundesland
borders show from z4? Are motorways continuous across the country at z5-z6? Does
zooming into Köln reveal streets, then buildings, with no visible pop-in gaps?

### 5. Export sections

```bash
python3 scripts/export_svg.py --tiles output/germany_game_map.mbtiles \
    --region germany --zoom 6 --out exports/germany_overview.svg
python3 scripts/export_svg.py --tiles output/germany_game_map.mbtiles \
    --region koeln --out exports/koeln_test.svg
```

## Differences to the test region build

Only one thing behaves differently, and it is an improvement:

**The `land` layer works.** A sub-region extract (Köln, NRW) is cut out of
Germany, so the `admin_level=2` relation that forms Germany's area is missing
most of its member ways. Planetiler reports `osm_boundary_missing_way` and skips
the polygon — the test build has no `land` layer, and the background shows
through. The full Germany extract contains the complete relation, so the country
area, and with it the coastline as a rendered shape, appears from z0.

Everything else — layer set, zoom windows, simplification, attributes, output
formats, statistics, SVG export — is identical. That is the point of testing on a
region first.

## If the build fails

| Symptom | Cause | Fix |
|---------|-------|-----|
| `OutOfMemoryError` | heap too small | `JAVA_XMX=12g`, or `--nodemap-type=sortedtable --storage=mmap` |
| `No space left on device` | scratch disk full | `TMPDIR_OVERRIDE=/path/with/40GB` |
| `osm_boundary_missing_way` in the log | boundary relations cut by the extract | expected for sub-regions; must not appear in bulk for Germany |
| download stops halfway | network | re-run `./scripts/fetch_data.sh germany --force` |
| `Java <n> found, but Planetiler needs Java 21+` | old JDK | install a JDK 21+ and put it first on `PATH` |

Planetiler's own log is verbose on purpose — it names the phase, the thread
utilization and the data errors it encountered. Data errors in the low thousands
across a country extract are normal OSM noise, not a broken build.
