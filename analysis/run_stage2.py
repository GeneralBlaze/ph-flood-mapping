"""Stage 2 runner: map flooding for one LGA from one or more Sentinel-1 passes.

Each pass is compared against a dry-season baseline from its own orbit, so
viewing geometry never mixes. A pixel is flooded if any pass flags it; passes
from different orbits fill each other's coverage gaps.

Usage:
    python -m analysis.run_stage2 --lga "Obio/Akpor" --pass 2026-09-29:22 --pass 2026-09-29:30
"""

import argparse
import json
import logging
import re
from datetime import date as Date
from pathlib import Path

import ee

from analysis import config, outputs
from analysis.clusters import name_clusters, top_clusters
from analysis.places import cached_places
from analysis.flood_detection import detect_flood, flooded_hectares
from analysis.sar import baseline_composite, event_image, lga_geometry

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
log = logging.getLogger(__name__)


def slugify(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def parse_pass(value: str) -> tuple[str, int]:
    """'YYYY-MM-DD:ORBIT' -> (date, orbit)."""
    try:
        day, orbit = value.split(":")
        Date.fromisoformat(day)
        return day, int(orbit)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"Expected YYYY-MM-DD:ORBIT, got {value!r}") from exc


def _classify_passes(region: ee.Geometry, passes: list[tuple[str, int]]) -> tuple[list, list[dict]]:
    events, results, stats = [], [], []
    for day, orbit in passes:
        event = event_image(region, day, orbit)
        result = detect_flood(baseline_composite(region, orbit), event, region)
        events.append(event)
        results.append(result)
        stats.append(
            {
                "date": day,
                "orbit": orbit,
                "water_threshold_db": round(result.water_threshold_db, 2),
                "change_threshold_db": round(result.change_threshold_db, 2),
                "flooded_ha": round(flooded_hectares(result.mask, region), 1),
            }
        )
        log.info("Pass %s orbit %d: %s", day, orbit, json.dumps(stats[-1]))
    return list(zip(events, results)), stats


def run(lga: str, passes: list[tuple[str, int]]) -> dict:
    ee.Initialize(project=config.EE_PROJECT)
    region = lga_geometry(lga)
    label = "_".join(f"{d}-o{o}" for d, o in passes)
    out_dir = DATA_DIR / slugify(lga) / f"stage2_{label}"
    out_dir.mkdir(parents=True, exist_ok=True)

    classified, pass_stats = _classify_passes(region, passes)
    mask = ee.ImageCollection([r.mask for _, r in classified]).max().rename("flood").clip(region)
    backdrop = ee.ImageCollection([e for e, _ in classified]).mosaic()

    summary = {
        "lga": lga,
        "baseline_window": config.DRY_SEASON,
        "passes": pass_stats,
        "flooded_ha": round(flooded_hectares(mask, region), 1),
    }
    outputs.write_quicklook(backdrop, mask, region, out_dir / "quicklook.png")
    outputs.write_web_overlay(mask, region, out_dir)
    outputs.write_lga_boundary(region, out_dir / "lga_boundary.geojson")
    polygons_path = out_dir / "flood_polygons.geojson"
    summary["flood_polygons"] = outputs.write_polygons(mask, region, polygons_path)
    (out_dir / "summary.json").write_text(json.dumps(summary, indent=2))

    places = cached_places(outputs.bounds(region), DATA_DIR / slugify(lga) / "osm_places.json")
    name_flood_clusters(polygons_path, out_dir / "flood_clusters.json", places)
    try:
        places = outputs.rank_flooded_places(mask, region)
        (out_dir / "flooded_places.json").write_text(json.dumps(places, indent=2))
    except RuntimeError as exc:
        log.warning("Skipped place ranking (Overpass unavailable): %s", exc)

    log.info("Combined: %.1f ha in %d polygons -> %s", summary["flooded_ha"], summary["flood_polygons"], out_dir)
    return summary


def name_flood_clusters(polygons_path: Path, out_path: Path, places: list[dict] = ()) -> list[dict]:
    collection = json.loads(polygons_path.read_text())
    clusters = name_clusters(top_clusters(collection, config.TOP_CLUSTERS), places)
    out_path.write_text(json.dumps(clusters, indent=2))
    return clusters


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--lga", default=config.LGA_ORDER[0])
    parser.add_argument("--pass", dest="passes", type=parse_pass, action="append", required=True,
                        help="Sentinel-1 pass as YYYY-MM-DD:ORBIT; repeat for several")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    run(args.lga, args.passes)


if __name__ == "__main__":
    main()
