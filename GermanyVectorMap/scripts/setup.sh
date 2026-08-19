#!/usr/bin/env bash
# One-time setup: fetch Planetiler, check the toolchain, install the python helpers.
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"

step "Checking toolchain"
require_java
require_python
ok "java  $(java_banner)"
ok "python $(python3 --version)"

step "Planetiler $PLANETILER_VERSION"
mkdir -p "$TOOLS_DIR"
if [ -f "$PLANETILER_JAR" ]; then
  ok "already present ($(human_size "$PLANETILER_JAR"))"
else
  url="https://github.com/onthegomap/planetiler/releases/download/v${PLANETILER_VERSION}/planetiler.jar"
  info "downloading $url"
  curl -fSL --retry 4 --retry-delay 2 -o "$PLANETILER_JAR.part" "$url" \
    || die "download failed — grab planetiler.jar manually and put it in tools/"
  mv "$PLANETILER_JAR.part" "$PLANETILER_JAR"
  ok "downloaded ($(human_size "$PLANETILER_JAR"))"
fi

step "Python packages"
python3 -c "import yaml" 2>/dev/null && ok "PyYAML" || {
  info "installing PyYAML"; python3 -m pip install --quiet PyYAML || warn "install PyYAML manually"; }
python3 -c "import pmtiles" 2>/dev/null && ok "pmtiles" || {
  info "installing pmtiles"; python3 -m pip install --quiet pmtiles || warn "install pmtiles manually"; }

step "Offline map preview (optional)"
if command -v npm >/dev/null 2>&1; then
  if [ -d "$TOOLS_DIR/node_modules/maplibre-gl" ]; then
    ok "maplibre-gl already vendored"
  else
    info "vendoring maplibre-gl so scripts/serve_tiles.py needs no network"
    (cd "$TOOLS_DIR" && npm install --no-audit --no-fund --silent maplibre-gl@6.4.1) \
      && ok "vendored into tools/node_modules" \
      || warn "could not vendor maplibre-gl — the preview will load it from unpkg.com instead"
  fi
else
  info "npm not found — the preview will load maplibre-gl from unpkg.com"
fi

step "Building the map profile"
"$ROOT/scripts/build_profile.sh"

step "Ready"
info "next:  ./build_test_region          # Regierungsbezirk Köln"
info "then:  ./build_germany_map          # all of Germany"
