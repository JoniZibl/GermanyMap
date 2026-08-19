#!/usr/bin/env bash
# Downloads an OpenStreetMap extract from Geofabrik into input/.
#   scripts/fetch_data.sh germany
#   scripts/fetch_data.sh koeln_regbez
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"

region="${1:-}"
if [ -z "$region" ]; then
  echo "usage: scripts/fetch_data.sh <region>"; echo; echo "known regions:"; list_regions; exit 1
fi

rel_path=$(region_field "$region" pbf) || exit 1
[ -n "$rel_path" ] || die "region '$region' has no 'pbf:' entry (it is a bbox-only sub-region)."

mkdir -p "$INPUT_DIR"
target="$INPUT_DIR/$(basename "$rel_path")"
url="$GEOFABRIK_BASE/$rel_path"

step "Fetching $region"
info "$url"
if [ -f "$target" ]; then
  info "already downloaded: $target ($(human_size "$target"))"
  info "delete it or pass --force to re-download"
  [ "${2:-}" = "--force" ] || exit 0
fi

curl -fSL --retry 4 --retry-delay 2 --progress-bar -o "$target.part" "$url" \
  || die "download failed. Geofabrik may be unreachable from this machine."
mv "$target.part" "$target"
ok "saved $target ($(human_size "$target"))"

# Geofabrik publishes an md5 next to every extract — verify when we can.
if curl -fsSL --retry 2 -o "$target.md5" "$url.md5" 2>/dev/null; then
  if command -v md5sum >/dev/null 2>&1; then
    (cd "$INPUT_DIR" && md5sum -c "$(basename "$target").md5" >/dev/null 2>&1) \
      && ok "md5 verified" || warn "md5 mismatch — the download may be corrupt"
  fi
  rm -f "$target.md5"
fi

step "License"
info "This data is © OpenStreetMap contributors, licensed under the ODbL 1.0."
info "See docs/LICENSE_OSM.md before you redistribute anything derived from it."
