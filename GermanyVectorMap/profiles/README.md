# The Planetiler profile

This is where the OSM tag → layer rules live.

| File | Purpose |
|------|---------|
| `src/main/java/de/germanyvectormap/GermanyMapProfile.java` | the tag → layer mapping, one method per layer group |
| `src/main/java/de/germanyvectormap/MapConfig.java` | loads `config/layers.yml` + `config/zoom_levels.yml`, applies the geometry settings |
| `src/main/java/de/germanyvectormap/LayerSpec.java` | the pre-computed settings of one layer |
| `src/main/java/de/germanyvectormap/GermanyMapMain.java` | entry point, wires Planetiler together |
| `pom.xml` | **optional**, for IDE support only |

## Building

```bash
../scripts/build_profile.sh
```

Compiles with plain `javac` against `tools/planetiler.jar` into
`tools/germany-map-profile.jar`. No Maven, no repositories, no network. The build
scripts call this automatically and skip it when nothing changed.

`-implicit:none` matters: the shaded `planetiler.jar` carries its own `.java`
sources next to the class files, and without that flag `javac` recompiles them
into your jar.

## Adding a layer

1. **Emit it.** Add a `processX(...)` method in `GermanyMapProfile.java` and call
   it from `processFeature`. Use `config.layer("my_layer")` for its settings and
   `config.apply(feature, spec, minZoom)` to apply zoom window, buffer, minimum
   pixel size, simplification and label grid in one call.
2. **Declare it.** Add a block under `layers:` in `config/layers.yml`.
3. **Place it in zoom space.** Add an entry under `layers:` in
   `config/zoom_levels.yml`.
4. **Style it.** Add a color to `style/palette.json` and a layer to the table in
   `scripts/apply_palette.py`, then run that script.
5. Rebuild: `./build_test_region`.

Never set a color in the profile. Emit `class` and let the style decide.

## Why the rules are Java and not YAML

`processFeature` runs once per OSM element — hundreds of millions of times for a
Germany build. Typed `Set` lookups and `switch` on interned strings keep that path
cheap, and the rules stay reviewable as ordinary code with comments. The knobs
people actually tune between builds — zoom windows, minimum sizes, merging,
name zooms, on/off — are all in the YAML, where they belong.
