"""Locally stored map tiles, so the maps keep working without internet.

Field teams work where there is no connection, and a map that goes blank is a
map that cannot be used to place a coordinate. Tiles for the regions that matter
are therefore held on disk and served from this host.

The store is a plain {z}/{x}/{y}.png directory tree. Nothing clever: it is the
layout every tile tool understands, so the folder can be seeded by this app's
own command, copied from another machine, or dropped in from a provider export,
and it will still work.

Serving is offline-first. A cached tile is returned from disk without touching
the network. Only on a miss is the upstream source consulted, and the result is
written into the store on the way past, so ordinary use fills in whatever the
bulk seed did not cover. With no connection the misses simply fail -- quickly,
thanks to the circuit breaker below, rather than hanging the map on a timeout
for every tile in view.

NOTE ON SOURCES: no upstream is configured by default, and this module will not
invent one. Bulk-downloading from the public OpenStreetMap tile servers is
against their tile usage policy, so the operator has to point
OFFLINE_TILES_SOURCE at something they are entitled to draw from -- a paid
provider, or their own tile server.
"""

from __future__ import annotations

import math
import os
import threading
import time
from typing import Iterable, Iterator, Optional

from enferno.utils.logging_utils import get_logger

logger = get_logger()

# Bounding boxes as (min_lon, min_lat, max_lon, max_lat), padded slightly beyond
# the borders so the frame around an edge site is not empty.
REGIONS = {
    "iraq": (38.74, 28.99, 48.65, 37.42),
    "syria": (35.68, 32.26, 42.43, 37.35),
}

TILE_SUFFIX = ".png"

# When upstream is unreachable -- which is the whole point of this feature --
# every uncached tile in the viewport would otherwise wait for its own timeout.
# After this many consecutive failures, stop trying for a while and fail misses
# instantly, so panning offline stays responsive.
_FAILURE_THRESHOLD = 3
_BACKOFF_SECONDS = 60

_state_lock = threading.Lock()
_consecutive_failures = 0
_backoff_until = 0.0


# --------------------------------------------------------------------------
# Configuration
# --------------------------------------------------------------------------


def _cfg(key, default=None):
    try:
        from flask import current_app

        return current_app.config.get(key, default)
    except Exception:
        try:
            from enferno.settings import Config

            return getattr(Config, key, default)
        except Exception:
            return default


def enabled() -> bool:
    """Whether maps should be served from the local store."""
    return bool(_cfg("OFFLINE_TILES_ENABLED", False))


def store_root() -> str:
    """Directory holding the tile tree."""
    return _cfg("OFFLINE_TILES_DIR") or "/app/enferno/tiles"


def source_template() -> str:
    """Upstream {z}/{x}/{y} URL used to fill misses, or empty when unset."""
    return (_cfg("OFFLINE_TILES_SOURCE") or "").strip()


def max_zoom() -> int:
    """Deepest zoom the store is expected to hold."""
    try:
        return max(0, min(int(_cfg("OFFLINE_TILES_MAX_ZOOM", 12)), 19))
    except (TypeError, ValueError):
        return 12


# --------------------------------------------------------------------------
# Tile arithmetic
# --------------------------------------------------------------------------


def lon_to_x(lon: float, zoom: int) -> int:
    return int((lon + 180.0) / 360.0 * (1 << zoom))


def lat_to_y(lat: float, zoom: int) -> int:
    """Web Mercator row. Latitude runs the opposite way to y."""
    lat = max(-85.05112878, min(85.05112878, lat))
    rad = math.radians(lat)
    return int((1.0 - math.asinh(math.tan(rad)) / math.pi) / 2.0 * (1 << zoom))


def tile_bounds(bbox, zoom: int) -> tuple:
    """(x_min, y_min, x_max, y_max) covering a bounding box at this zoom."""
    min_lon, min_lat, max_lon, max_lat = bbox
    span = (1 << zoom) - 1
    x_min = max(0, min(span, lon_to_x(min_lon, zoom)))
    x_max = max(0, min(span, lon_to_x(max_lon, zoom)))
    # Higher latitude is a lower row number.
    y_min = max(0, min(span, lat_to_y(max_lat, zoom)))
    y_max = max(0, min(span, lat_to_y(min_lat, zoom)))
    return x_min, y_min, x_max, y_max


def iter_tiles(regions: Iterable, min_zoom: int, max_z: int) -> Iterator:
    """Every (z, x, y) covering the named regions, de-duplicated.

    Iraq and Syria share a border, so their boxes overlap; a seen-set keeps the
    overlap from being fetched twice.
    """
    boxes = [REGIONS[name] for name in regions]
    for zoom in range(min_zoom, max_z + 1):
        seen = set()
        for bbox in boxes:
            x_min, y_min, x_max, y_max = tile_bounds(bbox, zoom)
            for x in range(x_min, x_max + 1):
                for y in range(y_min, y_max + 1):
                    if (x, y) in seen:
                        continue
                    seen.add((x, y))
                    yield zoom, x, y


def count_tiles(regions: Iterable, min_zoom: int, max_z: int) -> int:
    """How many tiles a seed over this range would cover."""
    regions = list(regions)
    return sum(1 for _ in iter_tiles(regions, min_zoom, max_z))


# --------------------------------------------------------------------------
# Store
# --------------------------------------------------------------------------


def tile_path(z: int, x: int, y: int, root: Optional[str] = None) -> str:
    return os.path.join(root or store_root(), str(z), str(x), str(y) + TILE_SUFFIX)


def has_tile(z: int, x: int, y: int, root: Optional[str] = None) -> bool:
    path = tile_path(z, x, y, root)
    return os.path.isfile(path) and os.path.getsize(path) > 0


def read_tile(z: int, x: int, y: int, root: Optional[str] = None) -> Optional[bytes]:
    path = tile_path(z, x, y, root)
    try:
        with open(path, "rb") as f:
            data = f.read()
        return data or None
    except OSError:
        return None


def write_tile(z: int, x: int, y: int, data: bytes, root: Optional[str] = None) -> bool:
    """Write a tile atomically, so a killed seed never leaves half a file."""
    if not data:
        return False
    path = tile_path(z, x, y, root)
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        tmp = path + ".part"
        with open(tmp, "wb") as f:
            f.write(data)
        os.replace(tmp, path)
        return True
    except OSError as e:
        logger.error(f"Could not store tile {z}/{x}/{y}: {e}")
        return False


def store_stats(root: Optional[str] = None) -> dict:
    """Tile count and bytes on disk, per zoom level."""
    root = root or store_root()
    per_zoom = {}
    total_files = 0
    total_bytes = 0
    if not os.path.isdir(root):
        return {"root": root, "exists": False, "tiles": 0, "bytes": 0, "zooms": {}}

    for entry in sorted(os.listdir(root)):
        zdir = os.path.join(root, entry)
        if not entry.isdigit() or not os.path.isdir(zdir):
            continue
        files = 0
        size = 0
        for dirpath, _dirnames, filenames in os.walk(zdir):
            for name in filenames:
                if not name.endswith(TILE_SUFFIX):
                    continue
                files += 1
                try:
                    size += os.path.getsize(os.path.join(dirpath, name))
                except OSError:
                    pass
        per_zoom[int(entry)] = {"tiles": files, "bytes": size}
        total_files += files
        total_bytes += size

    return {
        "root": root,
        "exists": True,
        "tiles": total_files,
        "bytes": total_bytes,
        "zooms": per_zoom,
    }


# --------------------------------------------------------------------------
# Upstream fill
# --------------------------------------------------------------------------


def _upstream_allowed() -> bool:
    """False while the circuit breaker is open after repeated failures."""
    with _state_lock:
        return time.time() >= _backoff_until


def _record_success() -> None:
    global _consecutive_failures, _backoff_until
    with _state_lock:
        _consecutive_failures = 0
        _backoff_until = 0.0


def _record_failure() -> None:
    global _consecutive_failures, _backoff_until
    with _state_lock:
        _consecutive_failures += 1
        if _consecutive_failures >= _FAILURE_THRESHOLD:
            _backoff_until = time.time() + _BACKOFF_SECONDS


def reset_breaker() -> None:
    """Clear the failure state. Used by the seeder, which wants every attempt."""
    _record_success()


def build_url(template: str, z: int, x: int, y: int) -> str:
    """Fill a {z}/{x}/{y} template, resolving {s} to a fixed subdomain.

    {s} is a client-side load-spreading trick; server-side there is one request
    at a time, so a stable value keeps the URL cacheable.
    """
    return (
        template.replace("{z}", str(z))
        .replace("{x}", str(x))
        .replace("{y}", str(y))
        .replace("{s}", "a")
    )


def fetch_tile(z: int, x: int, y: int, template: Optional[str] = None, timeout: float = 5.0):
    """Fetch one tile from upstream. Returns bytes, or None.

    Short timeout on purpose: offline, this has to fail fast enough that panning
    the map does not stall.
    """
    template = template if template is not None else source_template()
    if not template:
        return None

    import requests

    try:
        response = requests.get(
            build_url(template, z, x, y),
            timeout=timeout,
            headers={"User-Agent": "Bayanat offline tile cache"},
        )
        if response.status_code == 200 and response.content:
            _record_success()
            return response.content
        # A 404 is a real answer, not a connectivity problem: some sources have
        # no tile past their own maximum zoom.
        if response.status_code == 404:
            _record_success()
            return None
        _record_failure()
        return None
    except Exception:
        _record_failure()
        return None


def get_tile(z: int, x: int, y: int) -> Optional[bytes]:
    """A tile from the store, falling back to upstream and caching the result.

    Disk first, always: that is what makes the map work with no connection.
    """
    data = read_tile(z, x, y)
    if data is not None:
        return data

    if not source_template() or not _upstream_allowed():
        return None

    data = fetch_tile(z, x, y)
    if data:
        write_tile(z, x, y, data)
    return data
