"""Largest flood patches, named by reverse-geocoding their centres with Nominatim.

Nominatim's usage policy allows at most one request per second with an
identifying User-Agent; keep `limit` modest.
"""

import json
import math
import time
import urllib.parse
import urllib.request
from typing import Any

NOMINATIM_URL = "https://nominatim.openstreetmap.org/reverse"
USER_AGENT = "ph-flood-mapping/0.1 (+https://github.com/GeneralBlaze/ph-flood-mapping)"
REQUEST_INTERVAL_S = 1.1
REQUEST_TIMEOUT_S = 30
METRES_PER_DEG_LAT = 110_574.0
METRES_PER_DEG_LON_EQUATOR = 111_320.0
NAME_FIELDS = ("neighbourhood", "quarter", "suburb", "village", "hamlet", "town", "city_district")


def _local_xy(ring: list[list[float]]) -> list[tuple[float, float]]:
    """Project lon/lat to metres around the ring's mean latitude (fine at LGA scale)."""
    mean_lat = sum(p[1] for p in ring) / len(ring)
    lon_scale = METRES_PER_DEG_LON_EQUATOR * math.cos(math.radians(mean_lat))
    return [(p[0] * lon_scale, p[1] * METRES_PER_DEG_LAT) for p in ring]


def _signed_area(points: list[tuple[float, float]]) -> float:
    return 0.5 * sum(x0 * y1 - x1 * y0 for (x0, y0), (x1, y1) in zip(points, points[1:]))


def polygon_area_ha(ring: list[list[float]]) -> float:
    return abs(_signed_area(_local_xy(ring))) / 1e4


def polygon_centroid(ring: list[list[float]]) -> tuple[float, float]:
    """Area-weighted centroid of a closed lon/lat ring, as (lon, lat)."""
    area = _signed_area([(p[0], p[1]) for p in ring])
    if area == 0:
        return sum(p[0] for p in ring) / len(ring), sum(p[1] for p in ring) / len(ring)
    cx = cy = 0.0
    for (x0, y0), (x1, y1) in zip(ring, ring[1:]):
        cross = x0 * y1 - x1 * y0
        cx += (x0 + x1) * cross
        cy += (y0 + y1) * cross
    return cx / (6 * area), cy / (6 * area)


def top_clusters(collection: dict[str, Any], limit: int) -> list[dict[str, Any]]:
    """Largest polygons by area (outer ring only), with centroid."""
    clusters = []
    for feature in collection.get("features", []):
        geometry = feature.get("geometry") or {}
        if geometry.get("type") != "Polygon":
            continue
        ring = geometry["coordinates"][0]
        lon, lat = polygon_centroid(ring)
        clusters.append({"area_ha": round(polygon_area_ha(ring), 2), "lon": lon, "lat": lat})
    return sorted(clusters, key=lambda c: c["area_ha"], reverse=True)[:limit]


def describe_address(address: dict[str, str]) -> str:
    name = next((address[f] for f in NAME_FIELDS if address.get(f)), None)
    road = address.get("road")
    if name and road:
        return f"{name} ({road})"
    return name or road or "unnamed area"


def reverse_geocode(lat: float, lon: float) -> dict[str, str]:
    query = urllib.parse.urlencode(
        {"format": "jsonv2", "lat": f"{lat:.6f}", "lon": f"{lon:.6f}", "zoom": 17, "addressdetails": 1}
    )
    request = urllib.request.Request(f"{NOMINATIM_URL}?{query}", headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT_S) as response:
        return json.load(response).get("address", {})


def name_clusters(clusters: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return new cluster dicts with a place description; failures are marked, not raised."""
    named = []
    for i, cluster in enumerate(clusters):
        if i:
            time.sleep(REQUEST_INTERVAL_S)
        try:
            address = reverse_geocode(cluster["lat"], cluster["lon"])
            named.append({**cluster, "place": describe_address(address), "address": address})
        except (OSError, json.JSONDecodeError) as exc:
            named.append({**cluster, "place": "lookup failed", "error": str(exc)})
    return named
