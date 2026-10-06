"""Street-level drainage account for each suspected site (Stage 6).

Routes water on 30 m FABDEM from each site's lowest point, measures how high it
must rise to escape, names the streets it should follow or cross, counts the
buildings on that route by street, and compares nearby streets' heights with
the flooded ground. Needs Stage 5.

Usage:
    python -m analysis.run_streets --lga "Obio/Akpor"
"""

import argparse
import io
import json
import logging
import math
import urllib.request
from pathlib import Path
from typing import Any

import ee
import numpy as np
from shapely.geometry import LineString, Point, mapping, shape
from shapely.ops import nearest_points
from shapely.prepared import prep

from analysis import config, outputs
from analysis.crossings import cached_roads
from analysis.drainage import FABDEM_ASSET
from analysis.hydro_grid import d8_directions, flow_accumulation, priority_flood, trace
from analysis.obstructions import buildings_on_paths
from analysis.run_stage2 import DATA_DIR, slugify
from analysis.sar import lga_geometry
from analysis.street_story import _nearest_named, compose_story, rim_summary, streets_along

log = logging.getLogger(__name__)
PIXEL_DEG = 1 / 3600                 # FABDEM native grid
GRID_BUFFER_M = 3000                 # room for routes to leave the LGA and reach a channel
NODATA = -9999.0
PERMANENT_WATER_PCT = 50             # JRC occurrence: rivers and creeks act as outlets
FILL_EPS_M = 1e-4
MAX_ROUTE_CELLS = 400                # ~12 km
STREET_TOLERANCE_M = 20              # a 30 m route point this close to a street is "on" it
BARRIER_STREET_M = 40
BUILDING_STREET_M = 30
RIM_SEARCH_M = 300
RIM_SAMPLE_M = 15
RIM_WINDOW_M = 45                    # street height = median along this stretch either side of its closest point
RIM_LIMIT = 3


def _grid_origin(bbox: tuple[float, float, float, float]) -> tuple[float, float, int, int]:
    south, west, north, east = bbox
    west, north = math.floor(west / PIXEL_DEG) * PIXEL_DEG, math.ceil(north / PIXEL_DEG) * PIXEL_DEG
    return west, north, math.ceil((east - west) / PIXEL_DEG), math.ceil((north - south) / PIXEL_DEG)


def load_grid(region: ee.Geometry, cache: Path) -> dict[str, Any]:
    """FABDEM heights with permanent water as NaN outlets, on FABDEM's own 1-arc-second grid."""
    if cache.exists():
        saved = np.load(cache)
        return {"dem": saved["dem"], "west": float(saved["west"]), "north": float(saved["north"])}
    return load_grid_bbox(outputs.bounds(region.buffer(GRID_BUFFER_M)), cache)


def load_grid_bbox(bbox: tuple[float, float, float, float], cache: Path) -> dict[str, Any]:
    """As load_grid, for a (south, west, north, east) box that already includes the routing margin."""
    if cache.exists():
        saved = np.load(cache)
        return {"dem": saved["dem"], "west": float(saved["west"]), "north": float(saved["north"])}
    west, north, cols, rows = _grid_origin(bbox)
    dem = ee.ImageCollection(FABDEM_ASSET).mosaic().select(0).rename("elv").unmask(NODATA).toFloat()
    water = ee.Image(config.JRC_ASSET).select("occurrence").unmask(0).rename("occ").toFloat()
    url = dem.addBands(water).getDownloadURL({"format": "NPY", "crs": "EPSG:4326",
                                              "crs_transform": [PIXEL_DEG, 0, west, 0, -PIXEL_DEG, north],
                                              "dimensions": f"{cols}x{rows}"})
    with urllib.request.urlopen(url, timeout=outputs.DOWNLOAD_TIMEOUT_S) as response:
        raw = np.load(io.BytesIO(response.read()))
    heights = raw["elv"].astype(float)
    heights[(heights <= NODATA + 1) | (raw["occ"] >= PERMANENT_WATER_PCT)] = np.nan
    np.savez_compressed(cache, dem=heights, west=west, north=north)
    return {"dem": heights, "west": west, "north": north}


def cell_centre(grid: dict[str, Any], cell: tuple[int, int]) -> tuple[float, float]:
    r, c = cell
    return grid["west"] + (c + 0.5) * PIXEL_DEG, grid["north"] - (r + 0.5) * PIXEL_DEG


def cell_of(grid: dict[str, Any], lon: float, lat: float) -> tuple[int, int]:
    return int((grid["north"] - lat) / PIXEL_DEG), int((lon - grid["west"]) / PIXEL_DEG)


def _cells_in(grid: dict[str, Any], polygon) -> list[tuple[int, int]]:
    west, south, east, north = polygon.bounds
    r0, c0 = cell_of(grid, west, north)
    r1, c1 = cell_of(grid, east, south)
    inside = prep(polygon)
    cells = [(r, c) for r in range(r0, r1 + 1) for c in range(c0, c1 + 1)
             if inside.contains(Point(cell_centre(grid, (r, c))))]
    return cells or [cell_of(grid, polygon.centroid.x, polygon.centroid.y)]


def _on_channel(grid: dict[str, Any], hydro: dict[str, Any], lon: float, lat: float) -> bool:
    r, c = cell_of(grid, lon, lat)
    rows, cols = hydro["acc"].shape
    return 0 <= r < rows and 0 <= c < cols and hydro["acc"][r, c] >= hydro["channel_cells"]


def _by_water(grid: dict[str, Any], lon: float, lat: float) -> bool:
    """True next to permanent water (NaN), where a bridge deck reads at water level."""
    r, c = cell_of(grid, lon, lat)
    block = grid["dem"][max(0, r - 1): r + 2, max(0, c - 1): c + 2]
    return bool(np.isnan(block).any())


def _height(grid: dict[str, Any], lon: float, lat: float) -> float:
    r, c = cell_of(grid, lon, lat)
    rows, cols = grid["dem"].shape
    return float(grid["dem"][r, c]) if 0 <= r < rows and 0 <= c < cols else math.nan


def _length_m(points: list[tuple[float, float]]) -> float:
    lat_m = 110_574.0
    lon_m = 111_320.0 * math.cos(math.radians(points[0][1]))
    return sum(math.hypot((b[0] - a[0]) * lon_m, (b[1] - a[1]) * lat_m) for a, b in zip(points, points[1:]))


def _rim_heights(site, roads: list[dict[str, Any]], grid: dict[str, Any], hydro: dict[str, Any],
                 ground: float) -> list[dict[str, Any]]:
    """Height of each named street within RIM_SEARCH_M, where it passes closest to the site, relative to the
    flooded ground. Its closest stretch, not its lowest point: a road dipping into a creek valley 300 m away
    says nothing about whether water from this site can reach it."""
    zone = site.buffer(RIM_SEARCH_M / 110_000)
    step, window = RIM_SAMPLE_M / 110_000, RIM_WINDOW_M / 110_000
    samples: dict[str, list[float]] = {}  # pooled by name: OSM splits one street into many ways
    for road in roads:
        name, line = road.get("name"), road["line"]
        if not name or not line.intersects(zone):
            continue
        at = line.project(nearest_points(site, line)[1])
        for i in range(int(2 * window / step) + 1):
            p = line.interpolate(max(0.0, at - window + i * step))
            h = _height(grid, p.x, p.y)
            if site.contains(p) or math.isnan(h) or _on_channel(grid, hydro, p.x, p.y) or _by_water(grid, p.x, p.y):
                continue
            samples.setdefault(name, []).append(h)
    heights = {name: float(np.median(values)) - ground for name, values in samples.items()}
    return [{"name": n, "height_m": round(h, 1)} for n, h in heights.items()]


def building_centres(footprints: list) -> list[tuple[float, float]]:
    centres = [shape({"type": "Polygon", "coordinates": polygon}).centroid for polygon in footprints]
    return [(round(c.x, 6), round(c.y, 6)) for c in centres]


def _buildings_by_street(centres: list[tuple[float, float]], route: list[tuple[float, float]],
                         roads) -> dict[str | None, int]:
    counts: dict[str | None, int] = {}
    line = LineString(route) if len(route) > 1 else None
    for lon, lat in centres:
        centre = Point(lon, lat)
        anchor = line.interpolate(line.project(centre)) if line else centre
        street = _nearest_named((anchor.x, anchor.y), roads, BUILDING_STREET_M)
        counts[street] = counts.get(street, 0) + 1
    return counts


def site_route(grid: dict[str, Any], hydro: dict[str, Any], site) -> dict[str, Any]:
    """Route from the site's lowest cell to a channel, with its rise and barrier location."""
    dem = grid["dem"]
    cells = [cell for cell in _cells_in(grid, site) if not math.isnan(dem[cell])]
    if not cells:
        return {"route": [], "rise_m": 0.0, "barrier": None, "ground": math.nan}
    start = min(cells, key=lambda cell: dem[cell])
    path = trace(hydro["dirs"], hydro["acc"], start, hydro["channel_cells"], MAX_ROUTE_CELLS)
    profile = [dem[cell] for cell in path if not math.isnan(dem[cell])]
    peak = int(np.argmax(profile)) if profile else 0
    # "Flooded ground" = the site's median height: the single lowest cell is often elevation-data noise
    return {"route": [cell_centre(grid, cell) for cell in path],
            "ground": float(np.median([dem[cell] for cell in cells])),
            "rise_m": round(float(max(profile) - dem[start]), 1) if profile else 0.0,
            "barrier": cell_centre(grid, path[peak])}


def build_hydro(grid: dict[str, Any]) -> dict[str, Any]:
    dx = PIXEL_DEG * 111_320.0 * math.cos(math.radians(grid["north"]))
    dy = PIXEL_DEG * 110_574.0
    log.info("Filling and routing %s cells", grid["dem"].size)
    filled = priority_flood(grid["dem"], FILL_EPS_M)
    dirs = d8_directions(filled, dx, dy)
    return {"filled": filled, "dirs": dirs, "acc": flow_accumulation(dirs),
            "channel_cells": int(config.CHANNEL_UPA_KM2 * 1e6 / (dx * dy))}


def story_for(site, routed, roads, grid, hydro, centres) -> dict[str, Any]:
    """Street-level account for one site; centres = building centres (lon, lat) on its route."""
    route = routed["route"]
    rise = routed["rise_m"]
    barrier_street = _nearest_named(routed["barrier"], roads, BARRIER_STREET_M) if routed["barrier"] and rise >= 0.5 else None
    streets = streets_along(route, roads, STREET_TOLERANCE_M)
    by_street = _buildings_by_street(centres, route, roads)
    rim = rim_summary(_rim_heights(site, roads, grid, hydro, routed["ground"]), RIM_LIMIT) \
        if not math.isnan(routed["ground"]) else []
    route_m = _length_m(route) if len(route) > 1 else 0.0
    return {"rise_m": rise, "barrier_street": barrier_street, "streets": streets, "route_m": round(route_m),
            "buildings_by_street": {str(k): v for k, v in by_street.items()}, "rim": rim,
            "story": compose_story(rise, barrier_street, streets, route_m, by_street, rim)}


def run(lga: str) -> dict:
    ee.Initialize(project=config.EE_PROJECT)
    slug = slugify(lga)
    lga_dir = DATA_DIR / slug
    out_dir = lga_dir / "stage6_streets"
    out_dir.mkdir(parents=True, exist_ok=True)
    region = lga_geometry(lga)
    grid = load_grid(region, lga_dir / "fabdem_30m.npz")
    hydro = build_hydro(grid)
    roads = cached_roads(lga_dir / "osm_roads.json")

    features = [f for f in json.loads((lga_dir / "stage5_suspects" / "patches.geojson").read_text())["features"]
                if f["properties"]["category"] == "suspect"]
    sites = {f["properties"]["rank"]: shape(f["geometry"]) for f in features}
    routed = {rank: site_route(grid, hydro, site) for rank, site in sites.items()}
    corridors = {rank: [LineString(r["route"])] for rank, r in routed.items() if len(r["route"]) > 1}
    found = buildings_on_paths(corridors, sites)

    stories, routes, footprints = [], [], []
    for rank in sorted(sites):
        hit = found.get(rank, {"footprints": []})
        story = story_for(sites[rank], routed[rank], roads, grid, hydro, building_centres(hit["footprints"]))
        stories.append({"rank": rank, **story})
        if len(routed[rank]["route"]) > 1:
            routes.append({"type": "Feature", "properties": {"rank": rank},
                           "geometry": mapping(LineString(routed[rank]["route"]))})
        if hit["footprints"]:
            footprints.append({"type": "Feature", "properties": {"rank": rank},
                               "geometry": {"type": "MultiPolygon", "coordinates": hit["footprints"]}})
        log.info("#%d %s", rank, " ".join(story["story"]))

    collection = lambda fs: {"type": "FeatureCollection", "features": fs}  # noqa: E731
    (out_dir / "stories.json").write_text(json.dumps(stories, indent=2))
    (out_dir / "routes.geojson").write_text(json.dumps(collection(routes)))
    (out_dir / "obstructions.geojson").write_text(json.dumps(collection(footprints)))
    summary = {"lga": lga, "sites": len(stories), "hollows": sum(1 for s in stories if s["rise_m"] >= 0.5)}
    (out_dir / "summary.json").write_text(json.dumps(summary, indent=2))
    log.info("Summary: %s", json.dumps(summary))
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--lga", default=config.LGA_ORDER[0])
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    run(args.lga)


if __name__ == "__main__":
    main()
