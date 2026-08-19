#!/usr/bin/env bash
# Compiles the Planetiler profile in profiles/ into tools/germany-map-profile.jar
source "$(dirname "${BASH_SOURCE[0]}")/lib.sh"

require_java
[ -f "$PLANETILER_JAR" ] || die "tools/planetiler.jar missing — run scripts/setup.sh first."

sources=$(find "$PROFILE_SRC" -name '*.java')
[ -n "$sources" ] || die "no Java sources found under $PROFILE_SRC"

# rebuild only when a source file is newer than the jar
if [ -f "$PROFILE_JAR" ]; then
  newest=$(find "$PROFILE_SRC" -name '*.java' -newer "$PROFILE_JAR" -print -quit)
  if [ -z "$newest" ]; then
    ok "profile jar is up to date ($(human_size "$PROFILE_JAR"))"
    exit 0
  fi
fi

build_dir=$(mktemp -d)
trap 'rm -rf "$build_dir"' EXIT
info "compiling $(echo "$sources" | wc -l | tr -d ' ') source files"
# -implicit:none keeps Planetiler's own bundled sources out of our jar
javac -nowarn -implicit:none -d "$build_dir" -cp "$PLANETILER_JAR" $sources
jar --create --file "$PROFILE_JAR" -C "$build_dir" .
ok "built $PROFILE_JAR ($(human_size "$PROFILE_JAR"))"
