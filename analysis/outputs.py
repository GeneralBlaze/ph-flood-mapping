"""Write Stage 2 results to disk: quick-look image, web overlay, polygons, place ranking."""

import json
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

import ee

from analysis import config
from analysis.places import fetch_places, rank_places

FLOOD_COLOUR = "1f6fff"
DOWNLOAD_TIMEOUT_S = 180
QUICKLOOK_PX = 1600
OVERLAY_PX = 2048


def _download(url: str, path: Path) -> None:
    try:
        with urllib.request.urlopen(url, timeout=DOWNLOAD_TIMEOUT_S) as response:
            path.write_bytes(response.read())
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode(errors="replace")[:500]
        raise RuntimeError(f"Download to {path} failed: {exc} — {detail}") from exc
    except OSError as exc:
        raise RuntimeError(f"Download to {path} failed: {exc}") from exc


def _bounds(region: ee.Geometry) -> tuple[float, float, float, float]:
    """(south, west, north, east) of the region's bounding box."""
    ring = region.bounds().coordinates().get(0).getInfo()
    lons, lats = [p[0] for p in ring], [p[1] for p in ring]
    return min(lats), min(lons), max(lats), max(lons)


def write_quicklook(event: ee.Image, mask: ee.Image, region: ee.Geometry, path: Path) -> None:
    """Radar backdrop with flood in blue, for eyeballing the result."""
    backdrop = event.visualize(min=-25, max=-5, palette=["000000", "ffffff"])
    flood = mask.selfMask().visualize(palette=[FLOOD_COLOUR])
    outline = ee.Image().paint(ee.FeatureCollection([ee.Feature(region)]), 0, 2).visualize(palette=["ffcc00"])
    image = ee.ImageCollection([backdrop, flood, outline]).mosaic()
    url = image.getThumbURL({"region": region.bounds(), "dimensions": QUICKLOOK_PX, "format": "png"})
    _download(url, path)


def write_web_overlay(mask: ee.Image, region: ee.Geometry, directory: Path) -> None:
    """Transparent PNG in Web Mercator plus its bounds, for a Leaflet imageOverlay."""
    image = mask.selfMask().visualize(palette=[FLOOD_COLOUR])
    url = image.getThumbURL(
        {"region": region.bounds(), "dimensions": OVERLAY_PX, "format": "png", "crs": "EPSG:3857"}
    )
    _download(url, directory / "flood_overlay.png")
    south, west, north, east = _bounds(region)
    (directory / "flood_overlay.bounds.json").write_text(json.dumps([[south, west], [north, east]]))


def write_polygons(mask: ee.Image, region: ee.Geometry, path: Path) -> int:
    vectors = mask.selfMask().reduceToVectors(
        geometry=region,
        scale=config.OUTPUT_SCALE_M,
        geometryType="polygon",
        eightConnected=True,
        maxPixels=1e10,
    )
    collection = vectors.getInfo()
    path.write_text(json.dumps(collection))
    return len(collection["features"])


def write_lga_boundary(region: ee.Geometry, path: Path) -> None:
    feature = {"type": "Feature", "properties": {}, "geometry": region.getInfo()}
    path.write_text(json.dumps({"type": "FeatureCollection", "features": [feature]}))


def rank_flooded_places(mask: ee.Image, region: ee.Geometry) -> list[dict[str, Any]]:
    places = fetch_places(_bounds(region))
    if not places:
        return []
    zones = ee.FeatureCollection(
        [
            ee.Feature(ee.Geometry.Point(p["lon"], p["lat"]).buffer(config.PLACE_BUFFER_M), p)
            for p in places
        ]
    ).filterBounds(region)
    hectares = ee.Image.pixelArea().divide(1e4)
    stack = mask.multiply(hectares).rename("flooded_ha").addBands(
        hectares.clip(region).rename("area_ha")
    )
    stats = stack.reduceRegions(zones, ee.Reducer.sum(), config.OUTPUT_SCALE_M).getInfo()
    rows = [
        {k: f["properties"][k] for k in ("name", "place", "lat", "lon", "flooded_ha", "area_ha")}
        for f in stats["features"]
    ]
    return rank_places(rows, config.MIN_FLOODED_HA)
