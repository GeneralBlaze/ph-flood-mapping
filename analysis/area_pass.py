"""Full analysis of a drawn area, in five steps that each fit one web request.

1. history    radar flood history 2021–2026 and its flooded patches
2. latest     the latest radar pass and its flooded patches
3. routes     the patches merged into sites (or terrain hollows if none), each routed on FABDEM:
              where its water should go and how far it must rise
4. buildings  Open Buildings footprints standing on those routes
5. streets    OSM streets and landmarks, and the street-level account for each site

The browser keeps each step's result and sends what the next step needs, so the server holds no
state between requests beyond a /tmp cache of the elevation grid. Anything sent back is checked here.
"""

import logging
import math
import os
import tempfile
from datetime import date as Date
from pathlib import Path
from typing import Any

import ee
import numpy as np
from shapely.errors import GEOSException
from shapely.geometry import LineString, Polygon, box, mapping, shape
from shapely.ops import unary_union
from shapely.validation import make_valid

from analysis import config
from analysis.area_radar import (
    LATEST_COLOUR, MAX_PATCHES, YEARS_PALETTE, hectares_where, history_line, latest_flood, latest_line, overlay_png,
    patches, ring_geometry, traced_line, years_flooded,
)
from analysis.area_request import METRES_PER_DEG_LAT, METRES_PER_DEG_LON_EQUATOR, AreaError, area_km2, bbox_with_margin, ring_key
from analysis.crossings import fetch_roads
from analysis.landmarks import describe_nearby, fetch_landmarks, nearby_landmarks
from analysis.obstructions import buildings_on_paths
from analysis.run_streets import (
    GRID_BUFFER_M, MAX_ROUTE_CELLS, PIXEL_DEG, build_hydro, building_centres, cell_centre, load_grid_bbox,
    site_route, story_for,
)
from analysis.seasons import parse_years

log = logging.getLogger(__name__)

CACHE_DIR = Path(os.environ.get("AREA_CACHE_DIR", tempfile.gettempdir())) / "ph-area"
MAX_SITES = 5
MAX_SITE_COORDS = 2000
SITE_MARGIN_M = 500
ROUTE_MARGIN_M = GRID_BUFFER_M + 200    # routes stay on the routing grid
MAX_CENTRES = 1000
MAX_FOOTPRINTS = 300                    # drawn on the map; the count and street totals use them all
HOLLOW_MIN_DEPTH_M = 0.3
HOLLOW_LIMIT = 3
ROADS_MARGIN_M = 300
LANDMARK_MARGIN_M = 600
NEARBY_MAX_M = 600
ROADS_BUDGET_S = 60                     # Overpass time per lookup, so a slow mirror cannot run out the request
LANDMARKS_BUDGET_S = 30
YEARS_TEXT = config.STACK_YEARS.replace("-", "–")


# ---------- checks on what the browser sends back ----------

def _inside(points: list[tuple[float, float]], bbox: tuple[float, float, float, float]) -> bool:
    south, west, north, east = bbox
    return all(west <= lon <= east and south <= lat <= north for lon, lat in points)


def _number(value: Any, what: str) -> float:
    if not isinstance(value, (int, float)) or isinstance(value, bool) or not math.isfinite(value):
        raise AreaError(f"Bad {what} in the request.")
    return float(value)


def _point(value: Any, what: str) -> tuple[float, float]:
    if not isinstance(value, (list, tuple)) or len(value) != 2:
        raise AreaError(f"Bad {what} in the request.")
    return _number(value[0], what), _number(value[1], what)


def _coords(polygon) -> list[tuple[float, float]]:
    return [c for part in getattr(polygon, "geoms", [polygon]) for c in part.exterior.coords]


def parse_sites(sites: Any, ring: list[list[float]], limit: int = MAX_SITES) -> list[Polygon]:
    if not isinstance(sites, list) or len(sites) > limit:
        raise AreaError(f"Expected up to {limit} sites.")
    bbox = bbox_with_margin(ring, SITE_MARGIN_M)
    polygons = []
    for item in sites:
        geometry = item.get("geometry") if isinstance(item, dict) else None
        if not isinstance(geometry, dict) or geometry.get("type") not in ("Polygon", "MultiPolygon"):
            raise AreaError("Each site must be a polygon.")
        try:
            polygon = shape(geometry)
            detail = len(_coords(polygon))
        except (ValueError, TypeError, IndexError, AttributeError, GEOSException) as exc:
            raise AreaError("Each site must be a polygon.") from exc
        if detail > MAX_SITE_COORDS:  # checked before any repair work on a huge outline
            raise AreaError("A site outline is too detailed.")
        try:
            if not polygon.is_valid:
                polygon = make_valid(polygon).buffer(0)  # e.g. a self-crossing outline: keep its area
        except (ValueError, GEOSException) as exc:
            raise AreaError("Each site must be a polygon.") from exc
        if polygon.is_empty or polygon.geom_type not in ("Polygon", "MultiPolygon"):
            raise AreaError("Each site must be a polygon.")
        if not _inside(_coords(polygon), bbox):
            raise AreaError("A site lies outside the drawn area.")
        polygons.append(polygon)
    return polygons


def parse_routed(routed: Any, ring: list[list[float]]) -> list[dict[str, Any]]:
    if not isinstance(routed, list) or len(routed) > MAX_SITES:
        raise AreaError(f"Expected up to {MAX_SITES} routes.")
    bbox = bbox_with_margin(ring, ROUTE_MARGIN_M)
    parsed = []
    for item in routed:
        if not isinstance(item, dict) or not isinstance(item.get("route"), list):
            raise AreaError("Bad route in the request.")
        route = [_point(p, "route point") for p in item["route"][: MAX_ROUTE_CELLS + 1]]
        barrier = None if item.get("barrier") is None else _point(item["barrier"], "barrier")
        centres = [_point(p, "building") for p in (item.get("centres") or [])[:MAX_CENTRES]]
        if not _inside(route + centres + ([barrier] if barrier else []), bbox):
            raise AreaError("A route lies outside the routing area.")
        ground = item.get("ground")
        parsed.append({"route": route, "barrier": barrier, "centres": centres,
                       "rise_m": _number(item.get("rise_m"), "rise"),
                       "ground": math.nan if ground is None else _number(ground, "ground height")})
    return parsed


def _hectares(polygon: Polygon) -> float:
    lat = polygon.centroid.y
    m2_per_deg2 = METRES_PER_DEG_LAT * METRES_PER_DEG_LON_EQUATOR * math.cos(math.radians(lat))
    return round(polygon.area * m2_per_deg2 / 1e4, 2)


def merge_patches(recurrent: list[Any], latest: list[Any], limit: int = MAX_SITES) -> list[dict[str, Any]]:
    """Recurrent and latest flood patches as one set of sites: overlapping patches join; largest first."""
    tagged = [(shape(p["geometry"]), "recurrent") for p in recurrent] + [(shape(p["geometry"]), "latest") for p in latest]
    union = unary_union([g for g, _ in tagged])
    parts = list(getattr(union, "geoms", [union])) if not union.is_empty else []
    sites = []
    for part in parts:
        sources = {source for g, source in tagged if g.intersects(part)}
        sites.append({"geometry": mapping(part), "area_ha": _hectares(part), "kind": "flood",
                      "recurrent": "recurrent" in sources, "latest": "latest" in sources})
    return sorted(sites, key=lambda site: site["area_ha"], reverse=True)[:limit]


# ---------- terrain fallback ----------

def _cells_inside(grid: dict[str, Any], ring: list[list[float]]) -> np.ndarray:
    outline = Polygon([(lon, lat) for lat, lon in ring])
    rows, cols = grid["dem"].shape
    inside = np.zeros((rows, cols), dtype=bool)
    west, south, east, north = outline.bounds
    r0, r1 = max(0, int((grid["north"] - north) / PIXEL_DEG)), min(rows, int((grid["north"] - south) / PIXEL_DEG) + 1)
    c0, c1 = max(0, int((west - grid["west"]) / PIXEL_DEG)), min(cols, int((east - grid["west"]) / PIXEL_DEG) + 1)
    from shapely import contains_xy  # vectorised point-in-polygon

    rr, cc = np.mgrid[r0:r1, c0:c1]
    lons = grid["west"] + (cc + 0.5) * PIXEL_DEG
    lats = grid["north"] - (rr + 0.5) * PIXEL_DEG
    inside[r0:r1, c0:c1] = contains_xy(outline, lons, lats)
    return inside


def _groups(mask: np.ndarray) -> list[list[tuple[int, int]]]:
    seen = np.zeros_like(mask)
    groups = []
    rows, cols = mask.shape
    for start in zip(*np.nonzero(mask)):
        if seen[start]:
            continue
        seen[start] = True
        stack, cells = [start], []
        while stack:
            r, c = stack.pop()
            cells.append((int(r), int(c)))
            for dr in (-1, 0, 1):
                for dc in (-1, 0, 1):
                    n = (r + dr, c + dc)
                    if 0 <= n[0] < rows and 0 <= n[1] < cols and mask[n] and not seen[n]:
                        seen[n] = True
                        stack.append(n)
        groups.append(cells)
    return groups


def hollow_sites(grid: dict[str, Any], filled: np.ndarray, ring: list[list[float]], min_depth: float,
                 limit: int) -> list[dict[str, Any]]:
    """Deepest hollows inside the area (by volume), as site polygons: used when radar finds no flooding."""
    depth = np.nan_to_num(filled - grid["dem"], nan=0.0)
    cell_m2 = (PIXEL_DEG * 111_320.0 * math.cos(math.radians(grid["north"]))) * (PIXEL_DEG * 110_574.0)
    hollows = []
    for cells in _groups((depth >= min_depth) & _cells_inside(grid, ring)):
        depths = [depth[c] for c in cells]
        half = PIXEL_DEG / 2
        squares = [box(x - half, y - half, x + half, y + half) for x, y in (cell_centre(grid, c) for c in cells)]
        hollows.append({"geometry": mapping(unary_union(squares)), "area_ha": round(len(cells) * cell_m2 / 1e4, 2),
                        "max_depth_m": round(float(max(depths)), 1), "volume": float(sum(depths))})
    hollows.sort(key=lambda h: h["volume"], reverse=True)
    return [{k: v for k, v in h.items() if k != "volume"} for h in hollows[:limit]]


# ---------- the four steps (these call Earth Engine or Overpass) ----------

def _grid(ring: list[list[float]]) -> dict[str, Any]:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    return load_grid_bbox(bbox_with_margin(ring, GRID_BUFFER_M), CACHE_DIR / f"{ring_key(ring)}.npz")


def _bounds(ring: list[list[float]]) -> list[list[float]]:
    south, west, north, east = bbox_with_margin(ring, 0)
    return [[south, west], [north, east]]


def run_history(ring: list[list[float]]) -> dict[str, Any]:
    geom = ring_geometry(ring)
    years_img, mode = years_flooded(geom)
    by_years = hectares_where(years_img, geom)
    recurrent_ha = round(sum(ha for years, ha in by_years.items() if years >= config.REPEAT_MIN_YEARS), 1)
    max_years = len(parse_years(config.STACK_YEARS))
    colours = {years: YEARS_PALETTE[years - 1] for years in range(1, max_years + 1)}
    overlay = overlay_png(years_img, colours, bbox_with_margin(ring, 0))
    return {"mode": mode, "recurrent_ha": recurrent_ha,
            "overlay": {"kind": "history", "bounds": _bounds(ring), "url": overlay},
            "patches": patches(years_img.gte(config.REPEAT_MIN_YEARS), geom),
            "line": history_line(area_km2(ring) * 100, recurrent_ha, mode, YEARS_TEXT)}


def run_latest(ring: list[list[float]], today: Date | None = None) -> dict[str, Any]:
    geom = ring_geometry(ring)
    mask, day = latest_flood(geom, today or Date.today())
    if mask is None:
        return {"latest": None, "overlay": None, "patches": [], "line": latest_line(None)}
    # Pin to the 10 m radar grid: an overlay request would otherwise rerun speckle filtering
    # and patch cleanup at the image's much finer pixel size
    mask = mask.reproject(ee.Projection(config.WORKING_CRS).atScale(config.OUTPUT_SCALE_M))
    latest = {"date": day, "flooded_ha": hectares_where(mask, geom).get(1, 0.0)}
    overlay = None
    if latest["flooded_ha"] > 0:
        overlay = {"kind": "latest", "bounds": _bounds(ring),
                   "url": overlay_png(mask, {1: LATEST_COLOUR}, bbox_with_margin(ring, 0))}
    return {"latest": latest, "overlay": overlay, "patches": patches(mask, geom), "line": latest_line(latest)}


def _json_number(value: float) -> float | None:
    return None if math.isnan(value) else round(value, 2)


def run_routes(ring: list[list[float]], recurrent: Any, latest: Any) -> dict[str, Any]:
    parse_sites(recurrent, ring, MAX_PATCHES)
    parse_sites(latest, ring, MAX_PATCHES)
    sites = merge_patches(recurrent, latest)
    grid = _grid(ring)
    hydro = build_hydro(grid)
    if not sites:
        hollows = hollow_sites(grid, hydro["filled"], ring, HOLLOW_MIN_DEPTH_M, HOLLOW_LIMIT)
        sites = [{**h, "kind": "hollow"} for h in hollows]
    routed = []
    for site in sites:
        r = site_route(grid, hydro, shape(site["geometry"]))
        routed.append({"route": [[round(x, 6), round(y, 6)] for x, y in r["route"]],
                       "rise_m": r["rise_m"], "ground": _json_number(r["ground"]),
                       "barrier": [round(v, 6) for v in r["barrier"]] if r["barrier"] else None})
    kind = sites[0]["kind"] if sites else "hollow"
    return {"sites": sites, "routed": routed, "line": traced_line(len(sites), kind)}


def run_buildings(ring: list[list[float]], sites: Any, routed: Any) -> dict[str, Any]:
    polygons = parse_sites(sites, ring)
    routes = parse_routed(routed, ring)
    if len(routes) != len(polygons):
        raise AreaError("Sites and routes do not match.")
    corridors = {i: [LineString(r["route"])] for i, r in enumerate(routes) if len(r["route"]) > 1}
    found = buildings_on_paths(corridors, dict(enumerate(polygons)))
    result = []
    for i in range(len(polygons)):
        footprints = found.get(i, {"footprints": []})["footprints"]
        result.append({"count": len(footprints), "footprints": footprints[:MAX_FOOTPRINTS],
                       "centres": [list(c) for c in building_centres(footprints)[:MAX_CENTRES]]})
    return {"buildings": result}


def _try_osm(fetch, bbox, cache: Path, budget_s: float) -> tuple[list[dict[str, Any]], bool]:
    try:
        return fetch(bbox, cache, budget_s), True
    except RuntimeError as exc:
        log.warning("Overpass unavailable: %s", exc)
        return [], False


def run_streets(ring: list[list[float]], sites: Any, routed: Any) -> dict[str, Any]:
    polygons = parse_sites(sites, ring)
    routes = parse_routed(routed, ring)
    if len(routes) != len(polygons):
        raise AreaError("Sites and routes do not match.")
    grid = _grid(ring)
    hydro = build_hydro(grid)
    points = [[lat, lon] for r in routes for lon, lat in r["route"]] + ring
    key = ring_key(ring)
    roads, roads_ok = _try_osm(fetch_roads, bbox_with_margin(points, ROADS_MARGIN_M), CACHE_DIR / f"{key}_roads.json",
                               ROADS_BUDGET_S)
    marks, _ = _try_osm(fetch_landmarks, bbox_with_margin(ring, LANDMARK_MARGIN_M), CACHE_DIR / f"{key}_marks.json",
                          LANDMARKS_BUDGET_S)
    stories = []
    for polygon, r in zip(polygons, routes):
        story = story_for(polygon, r, roads, grid, hydro, r["centres"])
        centre = polygon.representative_point()
        stories.append({"story": story["story"], "streets": story["streets"], "rise_m": story["rise_m"],
                        "nearby": describe_nearby(nearby_landmarks(centre.y, centre.x, marks, NEARBY_MAX_M, 2))})
    return {"stories": stories, "streets_available": roads_ok}
