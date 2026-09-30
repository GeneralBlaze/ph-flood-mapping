"""Where OpenStreetMap roads cross expected drainage channels.

A road embankment across a channel with no (or a blocked) culvert is the
classic cause of water pooling upstream, so crossings are Stage 5 evidence.
Geometry is in lon/lat; distances use a local equirectangular projection,
which is accurate to well under 1% at LGA scale.
"""

import json
import math
from pathlib import Path
from typing import Any

from shapely.geometry import LineString
from shapely.geometry.base import BaseGeometry
from shapely.ops import transform

from analysis.places import REQUEST_TIMEOUT_S, query_overpass

ROAD_TYPES = "motorway|trunk|primary|secondary|tertiary|unclassified|residential|service|living_street"
# Roads usually built on embankments; residential lanes and service roads cross channels
# almost everywhere in a dense city and would make every channel-side patch a suspect.
MAJOR_ROAD_TYPES = {"motorway", "trunk", "primary", "secondary", "tertiary"}
METRES_PER_DEG_LAT = 110_574.0
METRES_PER_DEG_LON_EQUATOR = 111_320.0


def fetch_roads(bbox: tuple[float, float, float, float], cache: Path) -> list[dict[str, Any]]:
    """Roads inside (south, west, north, east); the raw response is cached to disk."""
    if cache.exists():
        return parse_roads(json.loads(cache.read_text()))
    south, west, north, east = bbox
    query = (
        f"[out:json][timeout:{REQUEST_TIMEOUT_S}];"
        f'way["highway"~"^({ROAD_TYPES})$"]({south},{west},{north},{east});'
        "out tags geom;"
    )
    payload = query_overpass(query)
    cache.write_text(json.dumps(payload))
    return parse_roads(payload)


def parse_roads(payload: dict[str, Any]) -> list[dict[str, Any]]:
    roads = []
    for element in payload.get("elements", []):
        coords = [(p["lon"], p["lat"]) for p in element.get("geometry", [])]
        if element.get("type") != "way" or len(coords) < 2:
            continue
        tags = element.get("tags", {})
        roads.append({"name": tags.get("name"), "highway": tags.get("highway"), "line": LineString(coords)})
    return roads


def major_roads(roads: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [r for r in roads if r["highway"] in MAJOR_ROAD_TYPES]


def crossing_points(roads: list[dict[str, Any]], channels: list[BaseGeometry]) -> list[dict[str, Any]]:
    """One point per place a road passes through a channel polygon and out again."""
    points = []
    for road in roads:
        for channel in channels:
            if not road["line"].crosses(channel):
                continue
            inside = road["line"].intersection(channel)
            pieces = getattr(inside, "geoms", [inside])
            points.extend({"point": piece.centroid, "road": road["name"]} for piece in pieces if not piece.is_empty)
    return points


def _to_metres(geometry: BaseGeometry, ref_lat: float) -> BaseGeometry:
    lon_scale = METRES_PER_DEG_LON_EQUATOR * math.cos(math.radians(ref_lat))
    return transform(lambda x, y, z=None: (x * lon_scale, y * METRES_PER_DEG_LAT), geometry)


def nearest_distance_m(target: BaseGeometry, points: list[dict[str, Any]]) -> tuple[float | None, str | None]:
    """Distance in metres from target to the nearest crossing, and that crossing's road name."""
    if not points:
        return None, None
    ref_lat = target.centroid.y
    target_m = _to_metres(target, ref_lat)
    best = min(points, key=lambda p: target_m.distance(_to_metres(p["point"], ref_lat)))
    return target_m.distance(_to_metres(best["point"], ref_lat)), best["road"]
