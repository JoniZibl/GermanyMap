# OpenStreetMap license — ODbL

Everything this pipeline produces is derived from OpenStreetMap. That carries
legal obligations. Read this before publishing or passing anything on.

## The license

OpenStreetMap data is **© OpenStreetMap contributors**, licensed under the
**Open Database License (ODbL) v1.0**.

- License text: <https://opendatacommons.org/licenses/odbl/1-0/>
- OSM copyright page: <https://www.openstreetmap.org/copyright>
- OSMF licence guidelines: <https://osmfoundation.org/wiki/Licence>

The cartography you build on top (your styles, icons, palettes) is **your** work.
The underlying data stays ODbL.

## 1. Attribution — always required

Any map, image, export or app that shows this data must credit OSM visibly:

> © OpenStreetMap contributors

with a link to <https://www.openstreetmap.org/copyright> where a link is possible.

The pipeline puts the attribution in automatically:

| Artifact | Where |
|----------|-------|
| `*.mbtiles` | `metadata` table, `attribution` + `license` rows |
| `*.pmtiles` | archive metadata |
| `style/germany-basemap.json` | `sources.germany.attribution` — MapLibre renders it |
| `exports/*.svg` | `<desc>` element in every file |

**Do not remove these notices.** For an SVG placed in a design, the `<desc>` is
not visible to a viewer — you still have to put the credit somewhere the viewer
can see it (a corner of the graphic, a caption, an imprint, an about screen).

## 2. Share-Alike — for derived *databases*

This is the part people miss. ODbL distinguishes:

- **Produced Work** — a visual output: a rendered map image, a PNG, a printed
  poster, a screenshot, a design in Figma. Requires **attribution only**. Your
  styling and colors stay yours.
- **Derivative Database** — a modified or extracted *dataset*: the `.mbtiles` and
  `.pmtiles` files this pipeline produces, and arguably the layered `.svg` exports
  since they still carry structured geometry.

If you **publicly distribute a Derivative Database**, you must offer it under the
ODbL as well, and make the underlying data available in a machine-readable form.

In practice:

| What you do | What you owe |
|-------------|--------------|
| Show the map in your app or on your site | attribution |
| Publish a rendered image / poster / video | attribution |
| Design in Figma from an SVG export and publish the design | attribution |
| Ship `germany_game_map.mbtiles` / `.pmtiles` to users or hand it to a client | attribution **+ ODbL** on that file |
| Publish the layered SVG exports as reusable assets | attribution **+ ODbL** (treat them as data) |
| Keep everything internal, never distribute | attribution is still good practice; no distribution obligation is triggered |

Bundling the tileset inside an application counts as distributing it.

## 3. Keeping it open

If you distribute a Derivative Database, recipients must be able to get the data
in an open format under the same terms. Do not add contractual or technical
restrictions on top that would prevent that.

## 4. Practical checklist

- [ ] Attribution visible wherever the map is shown
- [ ] `attribution` / `license` metadata left intact in `.mbtiles` and `.pmtiles`
- [ ] `<desc>` left intact in exported SVGs
- [ ] If you ship the tileset: state ODbL 1.0 and say where the data came from
- [ ] Note the date of the OSM extract you built from, so people know the vintage

## 5. Suggested notices

Short form, for a map corner or an about screen:

```
Map data © OpenStreetMap contributors, ODbL 1.0
```

Long form, when distributing the tileset:

```
This map/database contains information from OpenStreetMap,
which is made available under the Open Database License (ODbL) v1.0.
https://www.openstreetmap.org/copyright
https://opendatacommons.org/licenses/odbl/1-0/

Source extract: Geofabrik germany-latest.osm.pbf, downloaded <DATE>.
Processed with Planetiler; layers filtered and geometry simplified.
```

---

*This is a practical summary written to be useful, not legal advice. For anything
commercially significant, read the license text and, if in doubt, ask a lawyer.*
