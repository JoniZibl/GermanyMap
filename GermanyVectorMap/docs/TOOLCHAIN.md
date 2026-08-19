# Why Planetiler

The brief asked to check first whether Planetiler is the right tool. It is, and
here is the comparison it was checked against.

## The requirements that decide it

1. real OSM `.osm.pbf` in, vector tiles out
2. a whole country, on a normal machine, in a sane amount of time
3. **per-zoom** geometry simplification — not one simplified copy, a different
   amount of detail at every zoom
4. aggressive filtering: keep 30 layers, drop everything else
5. offline, file-based output (MBTiles / PMTiles) — no server at runtime
6. no colors in the data

## Candidates

### Planetiler — chosen

- Reads `.osm.pbf` natively, no database, no import step.
- Fast: a Germany extract runs in well under an hour on 4 cores; the planet runs
  in a few hours on a big machine. Requirement 2 is the one that eliminates most
  alternatives, and Planetiler clears it with room to spare.
- Per-zoom Douglas-Peucker / Visvalingam simplification with configurable
  tolerance, plus per-zoom minimum-feature-size filtering, built in (requirement 3).
- Tile post-processing built in: line-string merging and polygon union per tile,
  which is what actually shrinks low zooms (requirement 4).
- Writes MBTiles **and** PMTiles directly (requirement 5).
- Profiles are typed Java, so the tag→layer rules are reviewable and fast, and
  arbitrary logic (population-based zoom, admin level taken from parent relations)
  is straightforward.
- Actively maintained, used in production for planet-scale builds.

Cost: a JVM and a compile step. Both are cheap and scripted here.

### tilemaker

Lighter (C++, no JVM) and its Lua profiles are pleasant for small jobs. But it is
markedly slower on country-sized input, and the per-zoom simplification and tile
post-processing controls are thinner than Planetiler's. For a one-region map it
would be fine; for repeatable Germany builds with fine-grained per-zoom control it
is the weaker fit.

### osm2pgsql + PostGIS + a tile server (Tegola / Martin / t-rex)

The classic stack, and the most flexible: SQL gives unlimited control over what
becomes a layer. But it means running and maintaining a database, the import of a
Germany extract is slow, and tiles are generated on demand — the opposite of a
self-contained offline file. Requirement 5 rules it out. It stays the right answer
when you need ad-hoc querying or frequent minutely updates.

### OpenMapTiles (as a schema, on Planetiler or otherwise)

Planetiler ships an OpenMapTiles-compatible profile, so this was the obvious
shortcut. Rejected for two reasons:

- Its schema is a general-purpose basemap: many more layers and attributes than
  wanted here, including the POI and infrastructure detail the brief explicitly
  excludes. Filtering it down afterwards is harder than emitting the right thing
  in the first place.
- Its layer names and class taxonomy (`transportation`, `transportation_name`,
  `poi` with `subclass`) do not match the requested structure, and would not map
  cleanly onto Figma groups.

It does depend on external Natural Earth and water-polygon shapefiles; the profile
here is OSM-only, taking the country area and coastline from the
`admin_level=2` relation instead. One less data source to fetch, version and
license.

### tippecanoe

Excellent, but it is a GeoJSON→tiles tool, not an OSM tool. Using it would mean a
separate OSM→GeoJSON extraction step (osmium/ogr2ogr) and losing relation handling
along the way. It is the right tool when you already have GeoJSON.

## Conclusion

Planetiler is the best fit for this brief on every requirement that matters, and
the only candidate that clears all six without bolting on another component. The
pipeline is:

```
germany-latest.osm.pbf → Planetiler + GermanyMapProfile → MBTiles → PMTiles
                                                              ↘ layered SVG
```
