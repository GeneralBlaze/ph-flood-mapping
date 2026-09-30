"""Drainage flow paths with direction, from MERIT Hydro's D8 flow-direction band.

Each channel cell becomes one short segment from its centre to the centre of
the neighbour it drains into, so the network carries its downstream direction.
Used for flow arrows on the site and for finding buildings built across paths.
"""

import math
from typing import Any

import ee

from analysis.drainage import MERIT_ASSET, channel_mask

PIXEL_DEG = 1 / 1200  # MERIT Hydro is 3 arc-seconds
# D8 code -> (columns east, rows north)
D8_OFFSETS = {1: (1, 0), 2: (1, -1), 4: (0, -1), 8: (-1, -1), 16: (-1, 0), 32: (-1, 1), 64: (0, 1), 128: (1, 1)}


def flow_segments(points: list[tuple[float, float, int, float]]) -> list[dict[str, Any]]:
    """points: (lon, lat, d8_code, upstream_km2). Outlets (0) and no-data codes are skipped."""
    segments = []
    for lon, lat, code, upa in points:
        offset = D8_OFFSETS.get(int(code))
        if offset is None:
            continue
        dx, dy = offset
        segments.append({
            "coords": ((lon, lat), (lon + dx * PIXEL_DEG, lat + dy * PIXEL_DEG)),
            "bearing": math.degrees(math.atan2(dx, dy)) % 360,
            "upa_km2": upa,
        })
    return segments


def channel_cells(region: ee.Geometry) -> list[tuple[float, float, int, float]]:
    """Centre, D8 code and upstream area of every expected-channel cell in region."""
    merit = ee.Image(MERIT_ASSET)
    projection = merit.projection().getInfo()
    cells = ee.Image.pixelLonLat().addBands(merit.select(["dir", "upa"])).updateMask(channel_mask(merit))
    lists = cells.reduceRegion(
        reducer=ee.Reducer.toList(),
        geometry=region,
        crs=projection["crs"],
        crsTransform=projection["transform"],
        maxPixels=1e8,
    ).getInfo()
    return list(zip(lists["longitude"], lists["latitude"], lists["dir"], lists["upa"]))


def to_geojson(segments: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "properties": {"bearing": round(s["bearing"]), "upa_km2": round(s["upa_km2"], 2)},
                "geometry": {"type": "LineString", "coordinates": [list(c) for c in s["coords"]]},
            }
            for s in segments
        ],
    }


def pixel_key(lon: float, lat: float) -> tuple[int, int]:
    """Index of the MERIT cell containing (lon, lat).

    MERIT's grid is offset by half a cell (origin -180.000417°), so cell *centres*
    sit on whole multiples of 1/1200°; rounding, not flooring, finds the cell.
    """
    return round(lon / PIXEL_DEG), round(lat / PIXEL_DEG)


def _centre(key: tuple[int, int]) -> tuple[float, float]:
    return key[0] * PIXEL_DEG, key[1] * PIXEL_DEG


def trace_downstream(
    lon: float, lat: float, grid: dict[tuple[int, int], tuple[int, float]], stop_upa_km2: float, max_steps: int
) -> list[tuple[float, float]]:
    """Cell centres water follows from (lon, lat) until it reaches a channel, leaves the grid or loops."""
    key = pixel_key(lon, lat)
    route, visited = [_centre(key)], {key}
    for _ in range(max_steps):
        cell = grid.get(key)
        if cell is None or cell[1] >= stop_upa_km2:
            break
        offset = D8_OFFSETS.get(int(cell[0]))
        if offset is None:
            break
        key = (key[0] + offset[0], key[1] + offset[1])
        if key in visited:
            break
        visited.add(key)
        route.append(_centre(key))
    return route


def flow_grid(region: ee.Geometry) -> dict[tuple[int, int], tuple[int, float]]:
    """D8 code and upstream area for every MERIT cell in region, keyed by pixel_key."""
    merit = ee.Image(MERIT_ASSET)
    projection = merit.projection().getInfo()
    lists = ee.Image.pixelLonLat().addBands(merit.select(["dir", "upa"])).reduceRegion(
        reducer=ee.Reducer.toList(),
        geometry=region,
        crs=projection["crs"],
        crsTransform=projection["transform"],
        maxPixels=1e8,
    ).getInfo()
    return {
        pixel_key(lon, lat): (int(d8), upa)
        for lon, lat, d8, upa in zip(lists["longitude"], lists["latitude"], lists["dir"], lists["upa"])
    }
