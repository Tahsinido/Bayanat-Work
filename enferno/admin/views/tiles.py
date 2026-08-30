"""Map tile serving from the local store.

Sits behind the admin blueprint, so the same session check that guards every
other admin route guards this one. Tiles are ordinary map imagery rather than
case data, but there is no reason to expose an open proxy either.

The route only ever reads from the store and, on a miss, from the configured
upstream. It is deliberately incapable of reaching outside the tile tree: z, x
and y arrive as integers from the URL rule and are recombined into a path, so
there is no string from the request that could climb out of the directory.
"""

from __future__ import annotations

from flask import Response, current_app

from enferno.utils import offline_tiles
from . import admin

# One year. A tile at a given z/x/y is stable, and re-fetching them is exactly
# the network traffic this feature exists to avoid.
_CACHE_SECONDS = 31536000

# 1x1 transparent PNG, returned where a tile is genuinely missing. Leaflet
# renders a broken-image box for a 404, which looks like a fault; a transparent
# tile reads as "nothing mapped here", which is the truth when offline outside
# the seeded region.
_BLANK_PNG = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4"
    "890000000a49444154789c63000100000500010d0a2db40000000049454e44ae426082"
)


@admin.get("/api/tiles/<int:z>/<int:x>/<int:y>.png")
def api_map_tile(z: int, x: int, y: int) -> Response:
    """Serve one map tile, from disk where possible.

    Returns:
        - the tile image, or a transparent tile when it is not held and cannot
          be fetched.
    """
    if z < 0 or z > 22:
        return Response(_BLANK_PNG, mimetype="image/png")

    span = 1 << z
    if not (0 <= x < span and 0 <= y < span):
        return Response(_BLANK_PNG, mimetype="image/png")

    data = offline_tiles.get_tile(z, x, y)
    if data is None:
        # Not an error the client can act on, and not worth a broken tile icon.
        # Short cache so it is retried once a connection comes back, rather than
        # a blank square being remembered for a year.
        response = Response(_BLANK_PNG, mimetype="image/png")
        response.headers["Cache-Control"] = "public, max-age=60"
        response.headers["X-Tile-Source"] = "missing"
        return response

    response = Response(data, mimetype="image/png")
    response.headers["Cache-Control"] = f"public, max-age={_CACHE_SECONDS}, immutable"
    response.headers["X-Tile-Source"] = "store"
    return response


@admin.get("/api/tiles/status")
def api_map_tile_status() -> Response:
    """What the local store holds, for the admin settings screen and support."""
    from enferno.utils.http_response import HTTPResponse

    stats = offline_tiles.store_stats()
    return HTTPResponse.success(
        data={
            "enabled": offline_tiles.enabled(),
            "root": stats["root"],
            "exists": stats["exists"],
            "tiles": stats["tiles"],
            "bytes": stats["bytes"],
            "zooms": stats["zooms"],
            "maxZoom": offline_tiles.max_zoom(),
            # Whether a fill-on-miss upstream is configured, never the URL --
            # it can carry a provider API key.
            "sourceConfigured": bool(offline_tiles.source_template()),
            "regions": sorted(offline_tiles.REGIONS),
            "mapsEndpoint": current_app.config.get("MAPS_API_ENDPOINT", ""),
        }
    )
