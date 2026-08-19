#!/usr/bin/env bash
# Shared helpers for the Germany Vector Map build scripts.

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
INPUT_DIR="$ROOT/input"
OUTPUT_DIR="$ROOT/output"
CONFIG_DIR="$ROOT/config"
TOOLS_DIR="$ROOT/tools"
EXPORT_DIR="$ROOT/exports"
PROFILE_SRC="$ROOT/profiles/src/main/java"

PLANETILER_VERSION="${PLANETILER_VERSION:-0.10.2}"
PLANETILER_JAR="$TOOLS_DIR/planetiler.jar"
PROFILE_JAR="$TOOLS_DIR/germany-map-profile.jar"
GEOFABRIK_BASE="${GEOFABRIK_BASE:-https://download.geofabrik.de}"

c_reset=$'\033[0m'; c_bold=$'\033[1m'; c_dim=$'\033[2m'
c_green=$'\033[32m'; c_yellow=$'\033[33m'; c_red=$'\033[31m'; c_blue=$'\033[36m'

step() { printf '\n%s==>%s %s%s%s\n' "$c_blue" "$c_reset" "$c_bold" "$*" "$c_reset"; }
info() { printf '    %s\n' "$*"; }
warn() { printf '%s !! %s%s\n' "$c_yellow" "$*" "$c_reset" >&2; }
die()  { printf '%s !! %s%s\n' "$c_red" "$*" "$c_reset" >&2; exit 1; }
ok()   { printf '%s  ✓ %s%s\n' "$c_green" "$*" "$c_reset"; }

human_size() {
  local file="$1"
  [ -f "$file" ] || { echo "-"; return; }
  local bytes; bytes=$(stat -c%s "$file" 2>/dev/null || stat -f%z "$file")
  python3 -c "
b=$bytes
for u in ('B','KB','MB','GB','TB'):
    if b < 1024 or u=='TB':
        print(f'{b:.1f} {u}' if u!='B' else f'{int(b)} B'); break
    b/=1024
"
}

# Reads java.specification.version — robust against wrapper banners such as the
# "Picked up JAVA_TOOL_OPTIONS" line that some environments print to stderr.
java_version() {
  java -XshowSettings:properties -version 2>&1 \
    | sed -n 's/.*java\.specification\.version *= *\([0-9][0-9]*\).*/\1/p' | head -1
}

java_banner() {
  java -version 2>&1 | grep -v 'Picked up ' | head -1
}

require_java() {
  command -v java >/dev/null 2>&1 || die "Java is not installed. Planetiler needs Java 21 or newer."
  local version
  version=$(java_version)
  if [ -z "$version" ] || [ "$version" -lt 21 ] 2>/dev/null; then
    die "Java ${version:-<unknown>} found, but Planetiler needs Java 21+.  ($(java_banner))"
  fi
}

require_python() {
  command -v python3 >/dev/null 2>&1 || die "python3 is required for the stats and SVG tools."
}

# region_field <region> <field>  ->  prints the value from config/regions.yml
region_field() {
  python3 - "$CONFIG_DIR/regions.yml" "$1" "$2" <<'PY'
import sys, yaml
cfg, region, field = sys.argv[1], sys.argv[2], sys.argv[3]
data = yaml.safe_load(open(cfg, encoding="utf-8")) or {}
regions = data.get("regions", {})
if region not in regions:
    sys.stderr.write(f"unknown region '{region}'. Known: {', '.join(sorted(regions))}\n")
    raise SystemExit(2)
entry = regions[region]
value = entry.get(field)
if value is None and field == "pbf" and "parent" in entry:
    value = regions.get(entry["parent"], {}).get("pbf")
if value is None:
    raise SystemExit(0)
print(",".join(str(v) for v in value) if isinstance(value, list) else value)
PY
}

list_regions() {
  python3 -c "
import yaml
d = yaml.safe_load(open('$CONFIG_DIR/regions.yml', encoding='utf-8')) or {}
for name, r in (d.get('regions') or {}).items():
    print(f\"  {name:<16} {r.get('title','')}\")
"
}
