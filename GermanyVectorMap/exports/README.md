# SVG exports

Map sections cut out of the vector tiles and written as layered, editable SVG —
the hand-off to Figma. **These files are committed on purpose:** GitHub renders
SVG in the file view, so you can click one and look at the map without
downloading anything.

They are generated, never hand-edited. Regenerate any of them with
[`scripts/export_svg.py`](../scripts/export_svg.py), or let CI do it
(*Actions → Build vector map*, which commits the results back here).

## What is here

| File | Region | Zoom | Notes |
|------|--------|------|-------|
| `germany_overview.svg` | Deutschland | z6 | the low-detail country view |
| `nrw.svg` | Nordrhein-Westfalen | z10 | |
| `koeln_regbez_overview.svg` | Regierungsbezirk Köln | z11 | |
| `koeln_test.svg` | Köln | z13 | the sweet spot for Figma |
| `leverkusen_test.svg` | Leverkusen | z14 | includes buildings and footpaths — heavy |
| `koeln_layers/*.svg` | Köln | z13 | one file per map layer, all sharing one viewBox |

## Using them in Figma

Drag the `.svg` into Figma, or *File → Place image*. It arrives as a frame with
one named group per map layer (`water`, `forest`, `road_motorway`, …). Select a
group, change its fill — the whole layer recolors.

The files in `koeln_layers/` all carry the **same `viewBox`**, so importing them
all and stacking them at the same position reassembles the map with every layer
as an independent Figma layer.

If Figma gets sluggish on the heavier files, re-export without the expensive
layers:

```bash
python3 scripts/export_svg.py --tiles output/germany_game_map.mbtiles \
    --region koeln --exclude-layers building,path \
    --palette config/svg_palette.json --out exports/koeln_light.svg
```

## Colors

The colors on the groups come from [`style/palette.json`](../style/palette.json)
via `scripts/apply_palette.py`. They are placeholders for designing against —
they sit on the `<g>` elements only, never on the individual paths, and
`--no-style` drops them entirely.

## License

These are derived from OpenStreetMap. Every file carries

```xml
<desc>Map data © OpenStreetMap contributors, ODbL 1.0</desc>
```

Keep the credit visible wherever a design made from them is published. See
[../docs/LICENSE_OSM.md](../docs/LICENSE_OSM.md).
