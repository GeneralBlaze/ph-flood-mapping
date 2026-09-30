"""Stage 3 runner: multi-year flood frequency ("repeat offenders") for one LGA.

Usage:
    python -m analysis.run_stage3 --lga "Obio/Akpor" --years 2021-2026
"""

import argparse
import json
import logging
from pathlib import Path

import ee

from analysis import config, outputs
from analysis.clusters import name_clusters, top_clusters
from analysis.run_stage2 import DATA_DIR, slugify
from analysis.sar import lga_geometry
from analysis.seasons import parse_years
from analysis.stacking import export_years, frequency_image, remove_specks

log = logging.getLogger(__name__)
YEARS_PALETTE = ["c6dbef", "9ecae1", "6baed6", "3182bd", "08519c", "08306b"]


def hectares_by_years(freq: ee.Image, region: ee.Geometry, max_years: int) -> dict[int, float]:
    grouped = ee.Image.pixelArea().divide(1e4).addBands(freq.select("years_flooded")).reduceRegion(
        reducer=ee.Reducer.sum().group(groupField=1, groupName="years"),
        geometry=region,
        scale=config.OUTPUT_SCALE_M,
        maxPixels=1e10,
    ).get("groups").getInfo()
    by_years = {int(g["years"]): round(g["sum"], 1) for g in grouped}
    return {y: by_years.get(y, 0.0) for y in range(1, max_years + 1)}


def write_frequency_overlay(freq: ee.Image, region: ee.Geometry, out_dir: Path, max_years: int) -> None:
    years = freq.select("years_flooded").selfMask()
    vis = years.visualize(min=1, max=max_years, palette=YEARS_PALETTE[:max_years])
    url = vis.getThumbURL(
        {"region": region.bounds(), "dimensions": outputs.OVERLAY_PX, "format": "png", "crs": "EPSG:3857"}
    )
    outputs.download(url, out_dir / "frequency_overlay.png")
    south, west, north, east = outputs.bounds(region)
    (out_dir / "frequency_overlay.bounds.json").write_text(json.dumps([[south, west], [north, east]]))

    backdrop = ee.Image(1).clip(region).visualize(palette=["202020"])
    outline = ee.Image().paint(ee.FeatureCollection([ee.Feature(region)]), 0, 2).visualize(palette=["ffcc00"])
    quicklook = ee.ImageCollection([backdrop, vis, outline]).mosaic()
    url = quicklook.getThumbURL({"region": region.bounds(), "dimensions": outputs.QUICKLOOK_PX, "format": "png"})
    outputs.download(url, out_dir / "quicklook.png")


def write_geotiff(freq: ee.Image, region: ee.Geometry, path: Path) -> None:
    image = ee.Image.cat(
        freq.select("years_flooded"),
        freq.select("frequency_pct").round().toUint8(),
    )
    url = image.getDownloadURL(
        {"region": region, "scale": config.OUTPUT_SCALE_M, "format": "GEO_TIFF", "crs": "EPSG:4326"}
    )
    outputs.download(url, path)


def run(lga: str, years: list[int]) -> dict:
    ee.Initialize(project=config.EE_PROJECT)
    region = lga_geometry(lga)
    slug = slugify(lga)
    out_dir = DATA_DIR / slug / f"stage3_{years[0]}-{years[-1]}"
    out_dir.mkdir(parents=True, exist_ok=True)

    export_years(region, slug, years, config.ORBITS)
    freq = frequency_image(slug, years).clip(region)

    repeat = remove_specks(
        freq.select("years_flooded").gte(config.REPEAT_MIN_YEARS), config.REPEAT_MIN_PATCH_PIXELS
    ).rename("flood")
    summary = {
        "lga": lga,
        "years": years,
        "orbits": config.ORBITS,
        "repeat_min_years": config.REPEAT_MIN_YEARS,
        "min_flood_dates_per_year": config.MIN_FLOOD_OBS_PER_YEAR,
        "hectares_by_years_flooded": hectares_by_years(freq, region, len(years)),
    }
    (out_dir / "summary.json").write_text(json.dumps(summary, indent=2))
    write_frequency_overlay(freq, region, out_dir, len(years))
    write_geotiff(freq, region, out_dir / "flood_frequency.tif")
    outputs.write_lga_boundary(region, out_dir / "lga_boundary.geojson")

    polygons_path = out_dir / "repeat_polygons.geojson"
    summary["repeat_polygons"] = outputs.write_polygons(repeat.unmask(0), region, polygons_path)
    (out_dir / "summary.json").write_text(json.dumps(summary, indent=2))

    clusters = name_clusters(top_clusters(json.loads(polygons_path.read_text()), config.TOP_CLUSTERS))
    (out_dir / "repeat_clusters.json").write_text(json.dumps(clusters, indent=2))
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
