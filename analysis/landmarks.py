"""Named landmarks from OpenStreetMap, so people can recognise where a site is.

Schools, churches, markets, hospitals, filling stations and similar places are
what residents give directions by ("behind Rumuokoro Market"). Coverage depends
on what volunteers have mapped: usually good along main roads, thin elsewhere.
"""

import json
import math
from pathlib import Path
from typing import Any

from analysis.places import REQUEST_TIMEOUT_S, query_overpass

METRES_PER_DEG_LAT = 110_574.0
METRES_PER_DEG_LON_EQUATOR = 111_320.0
DUPLICATE_M = 200          # same name this close = same place mapped twice
DISTANCE_STEP_M = 50       # distances are rounded; positions are approximate anyway
BESIDE_M = 50

AMENITY_KINDS = {
    "school": "school", "college": "college", "university": "university", "hospital": "hospital",
    "clinic": "clinic", "marketplace": "market", "fuel": "filling station", "bank": "bank",
    "police": "police station", "townhall": "town hall", "bus_station": "bus park",
}
SHOP_KINDS = {"mall": "mall", "supermarket": "supermarket"}
RELIGION_KINDS = {"christian": "church", "muslim": "mosque"}
CHURCH_WORDS = ("church", "chapel", "cathedral", "parish", "ministry", "ministries", "assembly", "tabernacle")
MOSQUE_WORDS = ("mosque", "masjid")
COMPASS = ["north", "north-east", "east", "south-east", "south", "south-west", "west", "north-west"]


def landmark_kind(tags: dict[str, str]) -> str | None:
    amenity = tags.get("amenity")
    if amenity == "place_of_worship":
        return RELIGION_KINDS.get(tags.get("religion", "")) or _religion_from_name(tags.get("name", ""))
    if amenity in AMENITY_KINDS:
        return AMENITY_KINDS[amenity]
    if tags.get("shop") in SHOP_KINDS:
        return SHOP_KINDS[tags["shop"]]
    if tags.get("junction") == "roundabout":
        return "roundabout"
    return None


def _religion_from_name(name: str) -> str:
    lowered = name.lower()
    if any(w in lowered for w in MOSQUE_WORDS):
        return "mosque"
    if any(w in lowered for w in CHURCH_WORDS):
        return "church"
    return "place of worship"


def _offset_m(lat: float, lon: float, other: dict[str, Any]) -> tuple[float, float]:
    """(north, east) metres from (lat, lon) to other."""
    lon_scale = METRES_PER_DEG_LON_EQUATOR * math.cos(math.radians(lat))
    return (other["lat"] - lat) * METRES_PER_DEG_LAT, (other["lon"] - lon) * lon_scale


def parse_landmarks(payload: dict[str, Any]) -> list[dict[str, Any]]:
    landmarks: list[dict[str, Any]] = []
    for element in payload.get("elements", []):
        tags = element.get("tags", {})
        kind = landmark_kind(tags)
        position = element if element.get("type") == "node" else element.get("center")
        if not tags.get("name") or kind is None or not position:
            continue
        mark = {"name": tags["name"], "kind": kind, "lat": position["lat"], "lon": position["lon"]}
        if any(m["name"] == mark["name"] and math.hypot(*_offset_m(m["lat"], m["lon"], mark)) < DUPLICATE_M
               for m in landmarks):
            continue
        landmarks.append(mark)
    return landmarks


def fetch_landmarks(bbox: tuple[float, float, float, float], cache: Path,
                    budget_s: float | None = None) -> list[dict[str, Any]]:
    """Landmarks inside (south, west, north, east); the raw response is cached to disk."""
    if cache.exists():
        return parse_landmarks(json.loads(cache.read_text()))
    south, west, north, east = bbox
    box = f"({south},{west},{north},{east})"
    amenities = "|".join(["place_of_worship", *AMENITY_KINDS])
    query = (
        f"[out:json][timeout:{REQUEST_TIMEOUT_S}];("
        f'nwr["amenity"~"^({amenities})$"]["name"]{box};'
        f'nwr["shop"~"^({"|".join(SHOP_KINDS)})$"]["name"]{box};'
        f'nwr["junction"="roundabout"]["name"]{box};'
        ");out center tags;"
    )
    payload = query_overpass(query, budget_s)
    cache.write_text(json.dumps(payload))
    return parse_landmarks(payload)


def compass(north_m: float, east_m: float) -> str:
    bearing = math.degrees(math.atan2(east_m, north_m)) % 360
    return COMPASS[round(bearing / 45) % 8]


def nearby_landmarks(lat: float, lon: float, landmarks: list[dict[str, Any]], max_m: float,
                     limit: int) -> list[dict[str, Any]]:
    """Closest landmarks within max_m, with distance and direction from the point."""
    found = []
    for mark in landmarks:
        north, east = _offset_m(lat, lon, mark)
        distance = math.hypot(north, east)
        if distance <= max_m:
            found.append({"name": mark["name"], "kind": mark["kind"], "distance_m": round(distance),
                          "direction": compass(north, east)})
    return sorted(found, key=lambda m: m["distance_m"])[:limit]


def _distance_phrase(mark: dict[str, Any]) -> str:
    if mark["distance_m"] < BESIDE_M:
        return "beside it"
    rounded = int(round(mark["distance_m"] / DISTANCE_STEP_M) * DISTANCE_STEP_M)
    return f"{rounded} m {mark['direction']}"


def describe_nearby(near: list[dict[str, Any]]) -> str | None:
    """'Mile 3 Market (market), 100 m east · St Mary's (church), 200 m north', or None."""
    if not near:
        return None
    return " · ".join(f"{_label(m)}, {_distance_phrase(m)}" for m in near)


def _label(mark: dict[str, Any]) -> str:
    """Name, plus the kind in brackets unless the name already says it."""
    if mark["kind"].lower() in mark["name"].lower():
        return mark["name"]
    return f"{mark['name']} ({mark['kind']})"
