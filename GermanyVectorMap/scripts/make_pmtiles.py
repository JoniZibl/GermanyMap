#!/usr/bin/env python3
"""
Convert an MBTiles archive to PMTiles — same tiles, one file, smaller (duplicate
tiles are stored once) and directly readable over HTTP range requests.

Uses the official `pmtiles` Go CLI when it is on PATH (streaming, low memory).
Otherwise falls back to the pure-python `pmtiles` package, which buffers one
entry per tile in memory — fine up to a few million tiles, i.e. fine for a
Germany build at zoom 14.

    python3 scripts/make_pmtiles.py output/germany_game_map.mbtiles \
                                    output/germany_game_map.pmtiles
"""
from __future__ import annotations

import shutil
import sqlite3
import subprocess
import sys
from pathlib import Path


def archive_maxzoom(mbtiles: Path) -> int:
    """The conversion filters on zoom <= maxzoom, so read the real value from the archive."""
    with sqlite3.connect(f"file:{mbtiles}?mode=ro", uri=True) as db:
        row = db.execute("SELECT value FROM metadata WHERE name='maxzoom'").fetchone()
        if row and str(row[0]).strip().isdigit():
            return int(row[0])
        row = db.execute("SELECT MAX(zoom_level) FROM tiles").fetchone()
        return int(row[0]) if row and row[0] is not None else 99


def main() -> int:
    if len(sys.argv) < 3:
        print("usage: make_pmtiles.py <in.mbtiles> <out.pmtiles> [maxzoom]", file=sys.stderr)
        return 1
    src, dst = Path(sys.argv[1]), Path(sys.argv[2])
    if not src.is_file():
        print(f"error: {src} not found", file=sys.stderr)
        return 1
    maxzoom = int(sys.argv[3]) if len(sys.argv) > 3 else archive_maxzoom(src)
    if dst.exists():
        dst.unlink()

    cli = shutil.which("pmtiles")
    if cli:
        subprocess.run([cli, "convert", str(src), str(dst)], check=True)
    else:
        from pmtiles.convert import mbtiles_to_pmtiles  # noqa: PLC0415
        mbtiles_to_pmtiles(str(src), str(dst), maxzoom)

    src_size, dst_size = src.stat().st_size, dst.stat().st_size
    saved = (1 - dst_size / src_size) * 100 if src_size else 0
    print(f"    {src.name} {src_size / 1024 ** 2:.1f} MB -> "
          f"{dst.name} {dst_size / 1024 ** 2:.1f} MB ({-saved:+.1f}% size, "
          f"{'via pmtiles CLI' if cli else 'via python pmtiles'})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
