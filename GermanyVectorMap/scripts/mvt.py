"""
Minimal, dependency-free Mapbox Vector Tile reader plus MBTiles/PMTiles access.

Used by tile_stats.py and export_svg.py. Deliberately has no third-party
requirements so the toolchain keeps working offline; the optional `pmtiles`
package is only needed to read .pmtiles archives.

Vector tile spec: https://github.com/mapbox/vector-tile-spec/tree/master/2.1
"""

from __future__ import annotations

import gzip
import math
import sqlite3
import threading
import zlib
from dataclasses import dataclass, field
from typing import Iterator

# ---------------------------------------------------------------- protobuf ---

WIRE_VARINT, WIRE_64, WIRE_LEN, WIRE_32 = 0, 1, 2, 5


def _varint(buf: bytes, pos: int) -> tuple[int, int]:
    result = 0
    shift = 0
    while True:
        byte = buf[pos]
        pos += 1
        result |= (byte & 0x7F) << shift
        if not byte & 0x80:
            return result, pos
        shift += 7


def _zigzag(value: int) -> int:
    return (value >> 1) ^ -(value & 1)


def _fields(buf: bytes, start: int = 0, end: int | None = None) -> Iterator[tuple[int, int, object]]:
    """Yields (field_number, wire_type, value) where value is an int or a (start, end) slice."""
    pos = start
    end = len(buf) if end is None else end
    while pos < end:
        key, pos = _varint(buf, pos)
        field_no, wire = key >> 3, key & 0x7
        if wire == WIRE_VARINT:
            value, pos = _varint(buf, pos)
            yield field_no, wire, value
        elif wire == WIRE_LEN:
            length, pos = _varint(buf, pos)
            yield field_no, wire, (pos, pos + length)
            pos += length
        elif wire == WIRE_64:
            yield field_no, wire, int.from_bytes(buf[pos:pos + 8], "little")
            pos += 8
        elif wire == WIRE_32:
            yield field_no, wire, int.from_bytes(buf[pos:pos + 4], "little")
            pos += 4
        else:
            raise ValueError(f"unsupported protobuf wire type {wire}")


def _packed_varints(buf: bytes, start: int, end: int) -> list[int]:
    out = []
    pos = start
    while pos < end:
        value, pos = _varint(buf, pos)
        out.append(value)
    return out


# ------------------------------------------------------------ vector tiles ---

POINT, LINESTRING, POLYGON = 1, 2, 3
GEOM_NAME = {0: "unknown", POINT: "point", LINESTRING: "line", POLYGON: "polygon"}


@dataclass
class Feature:
    geom_type: int
    attrs: dict
    rings: list[list[tuple[int, int]]]
    fid: int | None = None

    @property
    def kind(self) -> str:
        return GEOM_NAME.get(self.geom_type, "unknown")


@dataclass
class Layer:
    name: str
    extent: int = 4096
    version: int = 2
    features: list[Feature] = field(default_factory=list)


def _decode_value(buf: bytes, start: int, end: int):
    for no, wire, val in _fields(buf, start, end):
        if no == 1 and wire == WIRE_LEN:
            s, e = val
            return buf[s:e].decode("utf-8", "replace")
        if no == 2:
            import struct
            return struct.unpack("<f", val.to_bytes(4, "little"))[0]
        if no == 3:
            import struct
            return struct.unpack("<d", val.to_bytes(8, "little"))[0]
        if no == 4:
            return val
        if no == 5:
            return val
        if no == 6:
            return _zigzag(val)
        if no == 7:
            return bool(val)
    return None


def _decode_geometry(cmds: list[int], geom_type: int) -> list[list[tuple[int, int]]]:
    """Turns the command/parameter stream into rings of absolute tile coordinates."""
    rings: list[list[tuple[int, int]]] = []
    current: list[tuple[int, int]] = []
    x = y = 0
    i = 0
    n = len(cmds)
    while i < n:
        cmd_int = cmds[i]
        i += 1
        cmd_id = cmd_int & 0x7
        count = cmd_int >> 3
        if cmd_id == 1:  # MoveTo
            for _ in range(count):
                if i + 1 >= n:
                    break
                x += _zigzag(cmds[i])
                y += _zigzag(cmds[i + 1])
                i += 2
                if geom_type == POINT:
                    rings.append([(x, y)])
                else:
                    if current:
                        rings.append(current)
                    current = [(x, y)]
        elif cmd_id == 2:  # LineTo
            for _ in range(count):
                if i + 1 >= n:
                    break
                x += _zigzag(cmds[i])
                y += _zigzag(cmds[i + 1])
                i += 2
                current.append((x, y))
        elif cmd_id == 7:  # ClosePath
            if current:
                current.append(current[0])
                rings.append(current)
                current = []
        else:
            break
    if current:
        rings.append(current)
    return rings


def decode_tile(data: bytes) -> dict[str, Layer]:
    """Decodes a (possibly gzip/deflate compressed) vector tile into layers."""
    data = decompress(data)
    layers: dict[str, Layer] = {}
    for no, wire, val in _fields(data):
        if no != 3 or wire != WIRE_LEN:
            continue
        s, e = val
        layer = _decode_layer(data, s, e)
        layers[layer.name] = layer
    return layers


def _decode_layer(buf: bytes, start: int, end: int) -> Layer:
    name = ""
    extent = 4096
    version = 2
    keys: list[str] = []
    values: list = []
    feature_spans: list[tuple[int, int]] = []
    for no, wire, val in _fields(buf, start, end):
        if no == 1 and wire == WIRE_LEN:
            s, e = val
            name = buf[s:e].decode("utf-8", "replace")
        elif no == 2 and wire == WIRE_LEN:
            feature_spans.append(val)
        elif no == 3 and wire == WIRE_LEN:
            s, e = val
            keys.append(buf[s:e].decode("utf-8", "replace"))
        elif no == 4 and wire == WIRE_LEN:
            s, e = val
            values.append(_decode_value(buf, s, e))
        elif no == 5:
            extent = val
        elif no == 15:
            version = val
    layer = Layer(name=name, extent=extent, version=version)
    for s, e in feature_spans:
        layer.features.append(_decode_feature(buf, s, e, keys, values))
    return layer


def _decode_feature(buf: bytes, start: int, end: int, keys: list[str], values: list) -> Feature:
    fid = None
    geom_type = 0
    tags: list[int] = []
    cmds: list[int] = []
    for no, wire, val in _fields(buf, start, end):
        if no == 1:
            fid = val
        elif no == 2 and wire == WIRE_LEN:
            s, e = val
            tags = _packed_varints(buf, s, e)
        elif no == 2:
            tags.append(val)
        elif no == 3:
            geom_type = val
        elif no == 4 and wire == WIRE_LEN:
            s, e = val
            cmds = _packed_varints(buf, s, e)
        elif no == 4:
            cmds.append(val)
    attrs = {}
    for i in range(0, len(tags) - 1, 2):
        ki, vi = tags[i], tags[i + 1]
        if ki < len(keys) and vi < len(values):
            attrs[keys[ki]] = values[vi]
    return Feature(geom_type=geom_type, attrs=attrs, rings=_decode_geometry(cmds, geom_type),
                   fid=fid)


def decompress(data: bytes) -> bytes:
    if len(data) >= 2 and data[0] == 0x1F and data[1] == 0x8B:
        return gzip.decompress(data)
    if len(data) >= 2 and data[0] == 0x78:
        try:
            return zlib.decompress(data)
        except zlib.error:
            pass
    return data


# ------------------------------------------------------------ tile archives ---


class TileArchive:
    """Common interface over .mbtiles and .pmtiles."""

    def metadata(self) -> dict:
        raise NotImplementedError

    def get_tile(self, z: int, x: int, y: int) -> bytes | None:
        """Returns raw tile bytes for XYZ (Google/slippy) coordinates, or None."""
        raise NotImplementedError

    def tile_count(self) -> int:
        raise NotImplementedError

    def close(self) -> None:
        pass

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()


class MBTiles(TileArchive):
    """
    Read-only MBTiles access.

    SQLite connections are bound to the thread that created them, so every thread
    gets its own read-only connection. Without this a threaded consumer (the
    preview server) raises "SQLite objects created in a thread can only be used
    in that same thread" on the first concurrent request.
    """

    def __init__(self, path):
        self.path = str(path)
        self._local = threading.local()

    @property
    def db(self) -> sqlite3.Connection:
        conn = getattr(self._local, "conn", None)
        if conn is None:
            conn = sqlite3.connect(f"file:{self.path}?mode=ro", uri=True)
            self._local.conn = conn
        return conn

    def metadata(self) -> dict:
        return dict(self.db.execute("SELECT name, value FROM metadata").fetchall())

    def get_tile(self, z: int, x: int, y: int) -> bytes | None:
        flipped = (1 << z) - 1 - y  # MBTiles stores rows in TMS order
        row = self.db.execute(
            "SELECT tile_data FROM tiles WHERE zoom_level=? AND tile_column=? AND tile_row=?",
            (z, x, flipped)).fetchone()
        return row[0] if row else None

    def tile_count(self) -> int:
        return self.db.execute("SELECT COUNT(*) FROM tiles").fetchone()[0]

    def tile_counts_by_zoom(self) -> dict[int, int]:
        return dict(self.db.execute(
            "SELECT zoom_level, COUNT(*) FROM tiles GROUP BY zoom_level ORDER BY zoom_level"))

    def iter_tiles(self):
        for z, x, row, data in self.db.execute(
                "SELECT zoom_level, tile_column, tile_row, tile_data FROM tiles"):
            yield z, x, (1 << z) - 1 - row, data

    def close(self):
        """Closes this thread's connection; other threads close their own."""
        conn = getattr(self._local, "conn", None)
        if conn is not None:
            conn.close()
            self._local.conn = None


class PMTiles(TileArchive):
    def __init__(self, path):
        from pmtiles.reader import Reader, MmapSource  # noqa: PLC0415
        self._fh = open(path, "rb")
        self._reader = Reader(MmapSource(self._fh))
        self._lock = threading.Lock()

    def metadata(self) -> dict:
        return self._reader.metadata()

    def get_tile(self, z: int, x: int, y: int) -> bytes | None:
        # the reader keeps seek state, so serialize concurrent readers
        with self._lock:
            try:
                return self._reader.get(z, x, y)
            except Exception:
                return None

    def tile_count(self) -> int:
        return self._reader.header().get("tile_entries_count", 0)

    def close(self):
        self._fh.close()


def open_archive(path) -> TileArchive:
    path = str(path)
    if path.endswith(".pmtiles"):
        return PMTiles(path)
    return MBTiles(path)


# ---------------------------------------------------------------- geo utils ---


def lonlat_to_tile(lon: float, lat: float, zoom: int) -> tuple[float, float]:
    """WGS84 -> fractional slippy tile coordinates."""
    lat = max(min(lat, 85.05112878), -85.05112878)
    n = 1 << zoom
    x = (lon + 180.0) / 360.0 * n
    rad = math.radians(lat)
    y = (1.0 - math.asinh(math.tan(rad)) / math.pi) / 2.0 * n
    return x, y


def tile_to_lonlat(x: float, y: float, zoom: int) -> tuple[float, float]:
    n = 1 << zoom
    lon = x / n * 360.0 - 180.0
    lat = math.degrees(math.atan(math.sinh(math.pi * (1 - 2 * y / n))))
    return lon, lat


def tile_range(bbox: tuple[float, float, float, float], zoom: int):
    """bbox = (min_lon, min_lat, max_lon, max_lat) -> (x0, y0, x1, y1) inclusive tile range."""
    min_lon, min_lat, max_lon, max_lat = bbox
    x0f, y0f = lonlat_to_tile(min_lon, max_lat, zoom)
    x1f, y1f = lonlat_to_tile(max_lon, min_lat, zoom)
    n = 1 << zoom
    x0 = max(0, min(n - 1, int(math.floor(x0f))))
    y0 = max(0, min(n - 1, int(math.floor(y0f))))
    x1 = max(0, min(n - 1, int(math.floor(x1f))))
    y1 = max(0, min(n - 1, int(math.floor(y1f))))
    return x0, y0, x1, y1
