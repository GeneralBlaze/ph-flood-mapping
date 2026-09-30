"""Stage 5 runner: rank suspected drainage problems for one LGA.

Needs Stage 3 (repeat-flood polygons) and Stage 4 (terrain asset, channel network).

Usage:
    python -m analysis.run_stage5 --lga "Obio/Akpor"
"""

import argparse
import json
import logging
from pathlib import Path
from typing import Any

import ee
from shapely.geometry import shape

from analysis import config, outputs
from analysis.clusters import name_clusters, polygon_area_ha, polygon_centroid
from analysis.crossings import crossing_points, fetch_roads, major_roads, nearest_distance_m
from analysis.drainage import terrain_asset_id
from analysis.run_stage2 import DATA_DIR, slugify
from analysis.sar import lga_geometry
from analysis.seasons import parse_years
from analysis.stacking import frequency_image
from analysis.suspects import classify_patch, rank_suspects

log = logging.getLogger(__name__)
BUILDINGS_ASSET = "GOOGLE/Research/open-buildings/v3/polygons"
WORLDCOVER_ASSET = "ESA/WorldCover/v200"
WETLAND_CLASSES = [90, 95]  # herbaceous wetland, mangroves
BUILT_CLASS = 50
BUILDING_MIN_CONFIDENCE = 0.75
STATS_BANDS = ["years_flooded", "hand_m", "hand_fab_m", "hollow_m", "dist_channel_m", "upa_km2"]


def _load_patches(stage3_dir: Path) -> list[dict[str, Any]]:
    collection = json.loads((stage3_dir / "repeat_polygons.geojson").read_text())
    patches = []
    for i, feature in enumerate(collection["features"]):
        ring = feature["geometry"]["coordinates"][0]
        lon, lat = polygon_centroid(ring)
        patches.append({"id": i, "geometry": feature["geometry"], "area_ha": round(polygon_area_ha(ring), 2),
                        "lat": lat, "lon": lon})
    return patches


def patch_statistics(patches: list[dict[str, Any]], slug: str, years: list[int]) -> dict[int, dict[str, Any]]:
    """Per-patch terrain/flood statistics and building counts, keyed by patch id."""
    cover = ee.ImageCollection(WORLDCOVER_ASSET).first()
    stack = ee.Image.cat(
        frequency_image(slug, years).select("years_flooded").toFloat(),
        ee.Image(terrain_asset_id(slug)).select(STATS_BANDS[1:]),
        cover.remap(WETLAND_CLASSES, [1] * len(WETLAND_CLASSES), 0).rename("wetland").toFloat(),
        cover.eq(BUILT_CLASS).rename("built").toFloat(),
    )
    reducer = ee.Reducer.mean().combine(ee.Reducer.min(), sharedInputs=True).combine(ee.Reducer.max(), sharedInputs=True)
    buildings = ee.FeatureCollection(BUILDINGS_ASSET).filter(ee.Filter.gte("confidence", BUILDING_MIN_CONFIDENCE))
    zones = ee.FeatureCollection([ee.Feature(ee.Geometry(p["geometry"]), {"pid": p["id"]}) for p in patches])
    zones = zones.map(lambda f: f.set("buildings", buildings.filterBounds(f.geometry()).size()))
    result = stack.reduceRegions(zones, reducer, config.TERRAIN_SCALE_M).getInfo()
    return {int(f["properties"]["pid"]): f["properties"] for f in result["features"]}


def _patch_stats(raw: dict[str, Any], patch: dict[str, Any]) -> dict[str, Any]:
    def get(key: str, default: float = 0.0) -> float:
        value = raw.get(key)
        return default if value is None else float(value)

    return {
        "id": patch["id"],
        "area_ha": patch["area_ha"],
        "lat": patch["lat"],
        "lon": patch["lon"],
        "mean_years": get("years_flooded_mean"),
        "hand_m": get("hand_m_mean"),
        "hand_fab_m": get("hand_fab_m_mean"),
        "hollow_m": get("hollow_m_mean"),
        "dist_channel_m": get("dist_channel_m_min", 1e6),
        "max_upa_km2": get("upa_km2_max"),
        "buildings": int(get("buildings")),
        "wetland_frac": get("wetland_mean"),
        "built_frac": get("built_mean"),
    }


def classify_all(patches, raw_stats, crossings) -> list[dict[str, Any]]:
    classified = []
    for patch in patches:
        stats = _patch_stats(raw_stats.get(patch["id"], {}), patch)
        distance, road = nearest_distance_m(shape(patch["geometry"]), crossings)
        result = classify_patch(stats, distance)
        classified.append({**result, "crossing_road": road if result.get("kind") == "road_crossing" else None})
    return classified


def _feature(patch: dict[str, Any], result: dict[str, Any]) -> dict[str, Any]:
    keep = ("id", "category", "kind", "rank", "score", "mean_years", "anomaly_m", "area_ha", "buildings",
            "built_frac", "reasons")
    return {"type": "Feature", "geometry": patch["geometry"], "properties": {k: result.get(k) for k in keep}}


def run(lga_name: str, years: list[int]) -> dict:
    ee.Initialize(project=config.EE_PROJECT)
    slug = slugify(lga_name)
    lga_dir = DATA_DIR / slug
    stage3_dir = lga_dir / f"stage3_{years[0]}-{years[-1]}"
    out_dir = lga_dir / "stage5_suspects"
    out_dir.mkdir(parents=True, exist_ok=True)

    patches = _load_patches(stage3_dir)
    log.info("%d repeat-flood patches", len(patches))
    raw_stats = patch_statistics(patches, slug, years)

    region = lga_geometry(lga_name)
    roads = fetch_roads(outputs.bounds(region.buffer(1000)), lga_dir / "osm_roads.json")
    channels = [shape(f["geometry"]) for f in
                json.loads((lga_dir / "stage4_terrain" / "drainage_network.geojson").read_text())["features"]]
    crossings = crossing_points(major_roads(roads), channels)
    log.info("%d roads, %d road-channel crossings", len(roads), len(crossings))

    classified = classify_all(patches, raw_stats, crossings)
    ranked = rank_suspects(classified)
    rank_by_id = {r["id"]: r["rank"] for r in ranked}
    classified = [{**c, "rank": rank_by_id.get(c["id"])} for c in classified]

    named = name_clusters([{k: r[k] for k in ("rank", "area_ha", "lat", "lon")} for r in ranked[: config.TOP_CLUSTERS]])
    places = {n["rank"]: n["place"] for n in named}
    suspects = [
        {**{k: r[k] for k in ("rank", "kind", "score", "mean_years", "anomaly_m", "area_ha", "buildings", "built_frac",
                              "lat", "lon", "reasons", "crossing_road")},
         "place": places.get(r["rank"], "unnamed area")}
        for r in ranked
    ]

    by_id = {p["id"]: p for p in patches}
    geojson = {"type": "FeatureCollection", "features": [_feature(by_id[c["id"]], c) for c in classified]}
    (out_dir / "patches.geojson").write_text(json.dumps(geojson))
    (out_dir / "suspects.json").write_text(json.dumps(suspects, indent=2))

    counts = {cat: sum(1 for c in classified if c["category"] == cat) for cat in ("suspect", "natural", "unclear")}
    summary = {"lga": lga_name, "years": years, "patches": len(patches), "categories": counts,
               "suspects_by_kind": {k: sum(1 for s in suspects if s["kind"] == k) for k in ("raised_ground", "road_crossing")},
               "roads": len(roads), "crossings": len(crossings)}
    (out_dir / "summary.json").write_text(json.dumps(summary, indent=2))
    log.info("Summary: %s", json.dumps(summary))
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--lga", default=config.LGA_ORDER[0])
    parser.add_argument("--years", type=parse_years, default=parse_years(config.STACK_YEARS))
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    run(args.lga, args.years)


if __name__ == "__main__":
    main()
