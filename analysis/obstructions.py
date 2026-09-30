"""Buildings standing on the natural drainage path near a suspected site.

Answers "is something built across where the water should go?". Paths come
from MERIT's 90 m flow directions, so their position is approximate: the
corridor is PATH_BUFFER_M wide and results are phrased "on or beside".
"""

from typing import Any

import ee
from shapely.geometry import mapping
from shapely.geometry.base import BaseGeometry
from shapely.ops import unary_union

from analysis.crossings import _to_metres

SEARCH_M = 300          # look along paths this far from the site
PATH_BUFFER_M = 25      # corridor half-width around each path segment
BUILDINGS_ASSET = "GOOGLE/Research/open-buildings/v3/polygons"
BUILDING_MIN_CONFIDENCE = 0.75


def nearby_paths(site: BaseGeometry, paths: list[BaseGeometry], max_m: float) -> list[BaseGeometry]:
    ref_lat = site.centroid.y
    site_m = _to_metres(site, ref_lat)
    return [p for p in paths if site_m.distance(_to_metres(p, ref_lat)) <= max_m]


def describe_obstruction(count: int | None, search_m: float) -> str | None:
    if count is None:
        return None
    if count == 0:
        return f"No buildings found on the natural drainage path within {search_m:.0f} m"
    noun, verb = ("building", "stands") if count == 1 else ("buildings", "stand")
    return f"{count} {noun} {verb} on or beside the natural drainage path within {search_m:.0f} m"


def describe_route(count: int, length_m: float) -> str:
    where = f"the route water should take from here to the nearest drainage channel (about {length_m:.0f} m)"
    if count == 0:
        return f"No buildings found on {where}"
    noun, verb = ("building", "stands") if count == 1 else ("buildings", "stand")
    return f"{count} {noun} {verb} on or beside {where}"


def buildings_on_paths(
    corridors: dict[int, list[BaseGeometry]], sites: dict[int, BaseGeometry]
) -> dict[int, dict[str, Any]]:
    """For each site id: buildings in its path corridor, excluding ones inside the flooded site itself.

    Buildings inside the site are affected by the water; ones along the path may be blocking it.
    One Earth Engine call for all sites.
    """
    if not corridors:
        return {}
    buildings = ee.FeatureCollection(BUILDINGS_ASSET).filter(ee.Filter.gte("confidence", BUILDING_MIN_CONFIDENCE))
    zones = ee.FeatureCollection([
        ee.Feature(ee.Geometry(mapping(unary_union(paths))).buffer(PATH_BUFFER_M),
                   {"sid": sid, "site": ee.Geometry(mapping(sites[sid]))})
        for sid, paths in corridors.items()
    ])

    def in_corridor(zone: ee.Feature) -> ee.FeatureCollection:
        site = ee.Geometry(zone.get("site"))
        return buildings.filterBounds(zone.geometry()).filter(ee.Filter.bounds(site).Not())

    joined = zones.map(lambda z: z.set(
        "footprints", in_corridor(z).geometry().coordinates(),
        "count", in_corridor(z).size(),
        "site", None,
    ).setGeometry(None)).getInfo()
    return {
        int(f["properties"]["sid"]): {"count": f["properties"]["count"], "footprints": f["properties"]["footprints"]}
        for f in joined["features"]
    }
