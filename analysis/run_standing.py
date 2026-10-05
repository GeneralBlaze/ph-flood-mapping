"""Standing-water runner: compare a post-rain pass with a later pass after dry days.

Both passes must share a relative orbit so viewing geometry is identical.
If Stage 5 has run for the LGA, each suspected site is also marked as still
under water, drained, or dry on both dates.

Usage:
    python -m analysis.run_standing --lga "Obio/Akpor" --before 2026-09-29:22 --after 2026-10-05:22
"""

import argparse
import json
import logging
from pathlib import Path
from typing import Any

import ee

from analysis import config, outputs
from analysis.crossings import fetch_roads
from analysis.flood_detection import detect_flood
from analysis.persistence import STANDING, class_hectares, hectares_by_class, persistence_image, site_status
from analysis.places import cached_places
from analysis.run_stage2 import DATA_DIR, name_flood_clusters, parse_pass, slugify
from analysis.sar import baseline_composite, event_image, lga_geometry

log = logging.getLogger(__name__)
# 0 transparent; drained pale, still standing deep blue, new mid blue (blue is reserved for water);
# not imaged in neutral grey so it never reads as "dry"
PALETTE = ["000000", "a9c8f0", "0b3fa8", "3d8fd9", "8a8a8a"]


def _mask(region: ee.Geometry, day: str, orbit: int) -> tuple[ee.Image, ee.Image, dict[str, Any]]:
    event = event_image(region, day, orbit)
    result = detect_flood(baseline_composite(region, orbit), event, region)
    stats = {"date": day, "orbit": orbit, "water_threshold_db": round(result.water_threshold_db, 2),
             "change_threshold_db": round(result.change_threshold_db, 2)}
    log.info("Pass %s", json.dumps(stats))
    return result.mask, event, stats


def _write_overlay(classes: ee.Image, region: ee.Geometry, out_dir: Path) -> None:
    image = classes.selfMask().visualize(min=0, max=4, palette=PALETTE)
    url = image.getThumbURL({"region": region.bounds(), "dimensions": outputs.OVERLAY_PX, "format": "png",
                             "crs": "EPSG:3857"})
    outputs.download(url, out_dir / "standing_overlay.png")
    south, west, north, east = outputs.bounds(region)
    (out_dir / "standing_overlay.bounds.json").write_text(json.dumps([[south, west], [north, east]]))


def site_statuses(stage5_dir: Path, before: ee.Image, after: ee.Image, covered: ee.Image) -> list[dict[str, Any]]:
    """Share of each suspected site wet on each date, and its status."""
    features = [f for f in json.loads((stage5_dir / "patches.geojson").read_text())["features"]
                if f["properties"]["category"] == "suspect"]
    if not features:
        return []
    zones = ee.FeatureCollection([ee.Feature(ee.Geometry(f["geometry"]), {"rank": f["properties"]["rank"]})
                                  for f in features])
    stack = ee.Image.cat(before.unmask(0).rename("before"), after.unmask(0).rename("after"),
                         covered.unmask(0).rename("covered")).toFloat()
    result = stack.reduceRegions(zones, ee.Reducer.mean(), config.OUTPUT_SCALE_M).getInfo()
    rows = []
    for f in result["features"]:
        p = f["properties"]
        covered = p.get("covered") or 0.0
        # wet shares of the imaged part only; uncovered pixels are 0 in both masks
        before_frac = (p.get("before") or 0.0) / covered if covered else 0.0
        after_frac = (p.get("after") or 0.0) / covered if covered else 0.0
        rows.append({"rank": p["rank"], "covered": round(covered, 2), "before_frac": round(before_frac, 2),
                     "after_frac": round(after_frac, 2),
                     "status": site_status(before_frac, after_frac, covered, config.STANDING_SITE_MIN_FRAC)})
    return sorted(rows, key=lambda r: r["rank"])


def run(lga: str, before_pass: tuple[str, int], after_pass: tuple[str, int]) -> dict:
    if before_pass[1] != after_pass[1]:
        raise ValueError("Both passes must come from the same relative orbit")
    ee.Initialize(project=config.EE_PROJECT)
    region = lga_geometry(lga)
    lga_dir = DATA_DIR / slugify(lga)
    out_dir = lga_dir / f"standing_{before_pass[0]}_{after_pass[0]}-o{after_pass[1]}"
    out_dir.mkdir(parents=True, exist_ok=True)

    before, before_event, before_stats = _mask(region, *before_pass)
    after, after_event, after_stats = _mask(region, *after_pass)
    covered = before_event.mask().gt(0).And(after_event.mask().gt(0)).rename("covered")
    classes = persistence_image(before, after, covered).clip(region)
    hectares = hectares_by_class(class_hectares(classes, region, config.OUTPUT_SCALE_M))
    log.info("Hectares: %s", hectares)

    _write_overlay(classes, region, out_dir)
    standing = classes.eq(STANDING).rename("flood")
    outputs.write_quicklook(after_event, standing, region, out_dir / "quicklook.png")
    outputs.write_lga_boundary(region, out_dir / "lga_boundary.geojson")
    polygons_path = out_dir / "standing_polygons.geojson"
    polygon_count = outputs.write_polygons(standing, region, polygons_path)
    places = cached_places(outputs.bounds(region), lga_dir / "osm_places.json")
    try:
        roads = fetch_roads(outputs.bounds(region.buffer(1000)), lga_dir / "osm_roads.json")
    except RuntimeError as exc:
        log.warning("Road names unavailable (Overpass down); sites may be named by coordinates: %s", exc)
        roads = []
    name_flood_clusters(polygons_path, out_dir / "standing_clusters.json", places, roads)

    sites = []
    stage5_dir = lga_dir / "stage5_suspects"
    if (stage5_dir / "patches.geojson").exists():
        sites = site_statuses(stage5_dir, before, after, covered)
        (out_dir / "site_status.json").write_text(json.dumps(sites, indent=2))

    summary = {"lga": lga, "before": before_stats, "after": after_stats, "hectares": hectares,
               "standing_polygons": polygon_count,
               "sites_by_status": {s: sum(1 for r in sites if r["status"] == s) for s in ("standing", "drained", "dry", "not_imaged")}}
    (out_dir / "summary.json").write_text(json.dumps(summary, indent=2))
    log.info("Summary: %s", json.dumps(summary))
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--lga", default=config.LGA_ORDER[0])
    parser.add_argument("--before", type=parse_pass, required=True, help="Post-rain pass, YYYY-MM-DD:ORBIT")
    parser.add_argument("--after", type=parse_pass, required=True, help="Pass after the dry spell, same orbit")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    run(args.lga, args.before, args.after)


if __name__ == "__main__":
    main()
