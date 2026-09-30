"""Named places from OpenStreetMap, used to describe where flooding was found."""

import json
import logging
from pathlib import Path
import urllib.parse
import urllib.request
from typing import Any

OVERPASS_URLS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
    "https://overpass.private.coffee/api/interpreter",
]
PLACE_TYPES = "suburb|neighbourhood|quarter|village|town|hamlet"
REQUEST_TIMEOUT_S = 90
log = logging.getLogger(__name__)


def _post_overpass(url: str, query: str) -> dict[str, Any]:
    data = urllib.parse.urlencode({"data": query}).encode()
    request = urllib.request.Request(url, data=data, headers={"User-Agent": "ph-flood-mapping/0.1"})
    with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT_S) as response:
        return json.load(response)


def fetch_places(bbox: tuple[float, float, float, float]) -> list[dict[str, Any]]:
    """Fetch named place nodes inside (south, west, north, east), trying each mirror in turn."""
    south, west, north, east = bbox
    query = (
        f"[out:json][timeout:{REQUEST_TIMEOUT_S}];"
        f'node["place"~"^({PLACE_TYPES})$"]["name"]({south},{west},{north},{east});'
        "out body;"
    )
    return parse_overpass_places(query_overpass(query))


def query_overpass(query: str) -> dict[str, Any]:
    """Run an Overpass QL query, trying each mirror in turn."""
    errors = []
    for url in OVERPASS_URLS:
        try:
            return _post_overpass(url, query)
        except (OSError, json.JSONDecodeError) as exc:
            errors.append(f"{url}: {exc}")
    raise RuntimeError("All Overpass mirrors failed: " + "; ".join(errors))


def parse_overpass_places(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """Keep named nodes, first occurrence per name."""
    seen: set[str] = set()
    places = []
    for element in payload.get("elements", []):
        tags = element.get("tags", {})
        name = tags.get("name")
        if element.get("type") != "node" or not name or name in seen:
            continue
        seen.add(name)
        places.append(
            {"name": name, "place": tags.get("place"), "lat": element["lat"], "lon": element["lon"]}
        )
    return places


def rank_places(rows: list[dict[str, Any]], min_flooded_ha: float) -> list[dict[str, Any]]:
    """Return new rows with flooded_pct, dropping near-dry places, most flooded first."""
    enriched = [
        {**row, "flooded_pct": 100.0 * row["flooded_ha"] / row["area_ha"]}
        for row in rows
        if row["area_ha"] > 0 and row["flooded_ha"] >= min_flooded_ha
    ]
    return sorted(enriched, key=lambda r: r["flooded_pct"], reverse=True)


def cached_places(bbox: tuple[float, float, float, float], cache: Path) -> list[dict[str, Any]]:
    """Named places, cached to disk; returns [] (with a warning) if Overpass is down."""
    if cache.exists():
        return json.loads(cache.read_text())
    try:
        places = fetch_places(bbox)
    except RuntimeError as exc:
        log.warning("Place names unavailable, labels may read 'unnamed area': %s", exc)
        return []
    cache.write_text(json.dumps(places))
    return places
