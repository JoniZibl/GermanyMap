# GermanyMap

Contains **[GermanyVectorMap/](GermanyVectorMap/)** — a pipeline that turns real
OpenStreetMap data into an optimized, multi-zoom, offline vector map of Germany.

```bash
cd GermanyVectorMap
./scripts/setup.sh          # Java/Python check, Planetiler, compile the profile
./build_test_region         # Regierungsbezirk Köln — validates the pipeline
./build_germany_map         # all of Germany
```

Produces `germany_game_map.mbtiles` + `.pmtiles`, 30 clearly named layers, no
colors baked into the data, and layered SVG exports for Figma.

Start with **[GermanyVectorMap/README.md](GermanyVectorMap/README.md)**.
Current validation status: **[GermanyVectorMap/docs/TEST_RESULTS.md](GermanyVectorMap/docs/TEST_RESULTS.md)**.

Map data © OpenStreetMap contributors, [ODbL 1.0](GermanyVectorMap/docs/LICENSE_OSM.md).
