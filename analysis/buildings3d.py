"""Data for the 3D site view: terrain tiles and buildings with heights (Stage 7).

Terrain: Terrarium tiles from the 30 m FABDEM grid that Stage 6 cached.
Buildings: Google Open Buildings v3 footprints around each site, each given the
mean height from Open Buildings 2.5D Temporal (latest year). Buildings on the
Stage 6 drainage route are flagged so the 3D view can colour them.

Usage:
    python -m analysis.buildings3d --lga "Obio/Akpor"
"""

import argparse
import json
import logging
from typing import Any

import ee
import numpy as np
from shapely.geometry import shape

from analysis import config
from analysis.obstructions import BUILDINGS_ASSET, PATH_BUFFER_M
from analysis.run_stage2 import DATA_DIR, slugify
from analysis.run_streets import PIXEL_DEG
from analysis.terrain_tiles import write_tiles

log = logging.getLogger(__name__)
HEIGHTS_ASSET = "GOOGLE/Research/open-buildings-temporal/v1"
HEIGHT_SCALE_M = 4                   # native resolution of the height raster
DEFAULT_HEIGHT_M = 3.0               # one storey, when no height was measured
MIN_HEIGHT_M = 1.0
RADIUS_M = 400                       # buildings shown around each site
BUILDING_MIN_CONFIDENCE = 0.7
COORD_DECIMALS = 6
TERRAIN_ZOOMS = range(11, 14)
REQUEST_DEADLINE_MS = 120_000        # Earth Engine requests occasionally hang; fail and retry instead
ATTEMPTS = 2
DEG_PER_M = 1 / 110_000


def _round(value: Any) -> Any:
    return round(value, COORD_DECIMALS) if isinstance(value, float) else [_round(v) for v in value]


def building_feature(stats: dict[str, Any], geometry: dict[str, Any], route_zone) -> dict[str, Any]:
    measured = stats.get("mean")
    height = round(measured, 1) if measured is not None and measured >= MIN_HEIGHT_M else DEFAULT_HEIGHT_M
    on_route = bool(route_zone is not None and route_zone.intersects(shape(geometry)))
    return {"type": "Feature", "properties": {"h": height, "on_route": on_route},
            "geometry": {"type": geometry["type"], "coordinates": _round(geometry["coordinates"])}}


def _heights_image() -> ee.Image:
    latest = ee.ImageCollection(HEIGHTS_ASSET).sort("inference_time_epoch_s", False).first()
    return latest.select("building_height").updateMask(latest.select("building_presence").gt(0.5))


def site_buildings(site, route_zone, heights: ee.Image) -> dict[str, Any]:
    area = ee.Geometry(site.buffer(RADIUS_M * DEG_PER_M).__geo_interface__)
    footprints = (ee.FeatureCollection(BUILDINGS_ASSET)
                  .filterBounds(area)
                  .filter(ee.Filter.gte("confidence", BUILDING_MIN_CONFIDENCE))
                  .select([]))
    measured = heights.reduceRegions(footprints, ee.Reducer.mean(), HEIGHT_SCALE_M).getInfo()
    return {"type": "FeatureCollection", "features": [
        building_feature(f["properties"], f["geometry"], route_zone) for f in measured["features"]
        if f["geometry"]["type"] == "Polygon"
    ]}


def _fetch_with_retry(site, zone, heights: ee.Image) -> dict[str, Any]:
    for attempt in range(1, ATTEMPTS + 1):
        try:
            return site_buildings(site, zone, heights)
        except ee.EEException as exc:
            if attempt == ATTEMPTS:
                raise
            log.warning("Retrying after Earth Engine error: %s", exc)
    raise AssertionError("unreachable")


def run(lga: str) -> dict:
    ee.Initialize(project=config.EE_PROJECT)
    ee.data.setDeadline(REQUEST_DEADLINE_MS)
    lga_dir = DATA_DIR / slugify(lga)
    out_dir = lga_dir / "stage7_3d"
    saved = np.load(lga_dir / "fabdem_30m.npz")
    grid = {"dem": saved["dem"], "west": float(saved["west"]), "north": float(saved["north"])}
    tiles = write_tiles(grid, PIXEL_DEG, TERRAIN_ZOOMS, out_dir / "terrain")
    rows, cols = grid["dem"].shape
    bounds = [grid["west"], grid["north"] - rows * PIXEL_DEG, grid["west"] + cols * PIXEL_DEG, grid["north"]]
    log.info("%d terrain tiles", tiles)

    sites = {f["properties"]["rank"]: shape(f["geometry"])
             for f in json.loads((lga_dir / "stage5_suspects" / "patches.geojson").read_text())["features"]
             if f["properties"]["category"] == "suspect"}
    routes = {f["properties"]["rank"]: shape(f["geometry"])
              for f in json.loads((lga_dir / "stage6_streets" / "routes.geojson").read_text())["features"]}
    heights = _heights_image()
    counts = {}
    (out_dir / "buildings").mkdir(parents=True, exist_ok=True)
    for rank, site in sorted(sites.items()):
        target = out_dir / "buildings" / f"{rank}.geojson"
        if target.exists():  # resume: sites already fetched are kept
            counts[rank] = len(json.loads(target.read_text())["features"])
            continue
        zone = routes[rank].buffer(PATH_BUFFER_M * DEG_PER_M) if rank in routes else None
        collection = _fetch_with_retry(site, zone, heights)
        target.write_text(json.dumps(collection, separators=(",", ":")))
        counts[rank] = len(collection["features"])
        log.info("#%d: %d buildings", rank, counts[rank])

    summary = {"lga": lga, "terrain_tiles": tiles, "terrain_zooms": [TERRAIN_ZOOMS.start, TERRAIN_ZOOMS.stop - 1],
               "terrain_bounds": bounds, "buildings": counts}
    (out_dir / "summary.json").write_text(json.dumps(summary, indent=2))
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--lga", default=config.LGA_ORDER[0])
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    run(args.lga)


if __name__ == "__main__":
    main()
