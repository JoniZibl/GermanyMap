#!/usr/bin/env bash
# Core build: OSM .pbf -> filtered vector tiles -> MBTiles + PMTiles -> statistics.
#
#   scripts/build_map.sh --region koeln_regbez
#   scripts/build_map.sh --input input/germany-latest.osm.pbf --name germany_game_map
#
# Every Planetiler argument can be appended and wins over the YAML config, e.g.
#   scripts/build_map.sh --region nrw -- --maxzoom=15
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"

region=""; input=""; name=""; bounds=""; skip_pmtiles=0; skip_stats=0
extra=()

while [ $# -gt 0 ]; do
  case "$1" in
    --region)   region="$2"; shift 2 ;;
    --input)    input="$2"; shift 2 ;;
    --name)     name="$2"; shift 2 ;;
    --bounds)   bounds="$2"; shift 2 ;;
    --no-pmtiles) skip_pmtiles=1; shift ;;
    --no-stats)   skip_stats=1; shift ;;
    --)         shift; extra+=("$@"); break ;;
    *)          extra+=("$1"); shift ;;
  esac
done

require_java; require_python
[ -f "$PLANETILER_JAR" ] || die "tools/planetiler.jar missing — run scripts/setup.sh first."

# ---------------------------------------------------------------- 1. input ---
step "1/8  Checking input"
if [ -n "$region" ] && [ -z "$input" ]; then
  rel_path=$(region_field "$region" pbf) || exit 1
  [ -n "$rel_path" ] || die "region '$region' is a bbox-only region — pass --input explicitly."
  input="$INPUT_DIR/$(basename "$rel_path")"
  if [ -z "$bounds" ]; then
    parent=$(region_field "$region" parent || true)
    [ -n "$parent" ] && bounds=$(region_field "$region" bbox)
  fi
fi
[ -n "$input" ] || die "no input given — use --region <name> or --input <file.osm.pbf>"
if [ ! -f "$input" ]; then
  die "input not found: $input
    Download it first:   scripts/fetch_data.sh ${region:-<region>}
    Or point --input at an .osm.pbf you already have."
fi
[ -z "$name" ] && name="${region:-germany}_game_map"
ok "input   $input ($(human_size "$input"))"

mkdir -p "$OUTPUT_DIR"
mbtiles="$OUTPUT_DIR/${name}.mbtiles"
pmtiles="$OUTPUT_DIR/${name}.pmtiles"

# ------------------------------------------------------------- 2. profile ---
step "2/8  Building the profile"
"$ROOT/scripts/build_profile.sh"

# ------------------------------------ 3.-7. read, filter, simplify, tile ----
step "3-6/8  Reading OSM data, applying filters, simplifying geometry, building zoom levels"
info "config  $CONFIG_DIR/layers.yml"
info "        $CONFIG_DIR/zoom_levels.yml"
[ -n "$bounds" ] && info "bounds  $bounds"

xmx="${JAVA_XMX:-}"
java_args=()
[ -n "$xmx" ] && java_args+=("-Xmx$xmx")

planetiler_args=(
  "--input=$input"
  "--output=$mbtiles"
  "--layers-config=$CONFIG_DIR/layers.yml"
  "--zoom-config=$CONFIG_DIR/zoom_levels.yml"
  "--tmpdir=${TMPDIR_OVERRIDE:-$ROOT/.tmp}"
  "--force"
  "--output_layerstats"
)
[ -n "$bounds" ] && planetiler_args+=("--bounds=$bounds")
[ ${#extra[@]} -gt 0 ] && planetiler_args+=("${extra[@]}")

start=$(date +%s)
java "${java_args[@]}" -cp "$PLANETILER_JAR:$PROFILE_JAR" \
  de.germanyvectormap.GermanyMapMain "${planetiler_args[@]}"
elapsed=$(( $(date +%s) - start ))
ok "tiles generated in ${elapsed}s"

# ------------------------------------------------------------- 8. outputs ---
step "7/8  Writing PMTiles"
if [ "$skip_pmtiles" = "1" ]; then
  info "skipped (--no-pmtiles)"
else
  if python3 -c "import pmtiles" 2>/dev/null; then
    python3 "$ROOT/scripts/make_pmtiles.py" "$mbtiles" "$pmtiles"
    ok "$pmtiles ($(human_size "$pmtiles"))"
  else
    warn "python package 'pmtiles' not installed — skipping .pmtiles (pip install pmtiles)"
  fi
fi

step "8/8  Statistics"
if [ "$skip_stats" = "1" ]; then
  info "skipped (--no-stats)"
else
  stats_args=(--tiles "$mbtiles" --input "$input" --json "$OUTPUT_DIR/${name}.stats.json")
  [ -f "$pmtiles" ] && stats_args+=(--also "$pmtiles")
  python3 "$ROOT/scripts/tile_stats.py" "${stats_args[@]}"
fi

step "Done"
info "MBTiles : $mbtiles ($(human_size "$mbtiles"))"
[ -f "$pmtiles" ] && info "PMTiles : $pmtiles ($(human_size "$pmtiles"))"
info "Preview : python3 scripts/serve_tiles.py --tiles $mbtiles"
info "SVG     : python3 scripts/export_svg.py --tiles $mbtiles --region koeln --out exports/koeln_test.svg"
