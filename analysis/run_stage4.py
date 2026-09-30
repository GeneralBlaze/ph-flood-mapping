"""Stage 4 runner: expected drainage network and terrain stack for one LGA.

Usage:
    python -m analysis.run_stage4 --lga "Obio/Akpor"
"""

import argparse
import json
import logging
from pathlib import Path

import ee

from analysis import config, outputs
from analysis.drainage import MERIT_ASSET, channel_mask, hydro_region, terrain_asset_id, terrain_stack
from analysis.ee_assets import asset_exists, ensure_folder, wait_for_tasks
from analysis.run_stage2 import DATA_DIR, slugify
from analysis.sar import lga_geometry

log = logging.getLogger(__name__)
HAND_PALETTE = ["f7f1e1", "e8d8b0", "d4b97f", "b8925a", "8c5a2b", "5c3a1c"]  # earth tones; blue is reserved for water
HAND_VIS_MAX_M = 10
NETWORK_SCALE_M = 90
NETWORK_MIN_PIXELS = 3
HAND_OVERLAY_PX = 1024  # 30 m data; larger previews exceed EE memory


def export_terrain(region: ee.Geometry, lga_slug: str) -> str:
    target = terrain_asset_id(lga_slug)
    if asset_exists(target):
        log.info("Terrain stack: cached asset found")
        return target
    ensure_folder(f"projects/{config.EE_PROJECT}/assets/{lga_slug}")
    task = ee.batch.Export.image.toAsset(
        image=terrain_stack(region),
        description=f"{lga_slug}_stage4_terrain",
        assetId=target,
        region=region,
        crs=config.WORKING_CRS,
        scale=config.TERRAIN_SCALE_M,
        maxPixels=1e10,
    )
    task.start()
    log.info("Terrain stack: export started")
    wait_for_tasks([("terrain stack", task)])
    return target


def write_hand_overlay(terrain: ee.Image, lga: ee.Geometry, out_dir: Path) -> None:
    vis = terrain.select("hand_m").clip(lga).visualize(min=0, max=HAND_VIS_MAX_M, palette=HAND_PALETTE)
    url = vis.getThumbURL(
        {"region": lga.bounds(), "dimensions": HAND_OVERLAY_PX, "format": "png", "crs": "EPSG:3857"}
    )
    outputs.download(url, out_dir / "hand_overlay.png")
    south, west, north, east = outputs.bounds(lga)
    (out_dir / "hand_overlay.bounds.json").write_text(json.dumps([[south, west], [north, east]]))


def write_network(region: ee.Geometry, path: Path) -> int:
    """Expected channels at MERIT's native resolution, as polygons, for display."""
    channel = channel_mask(ee.Image(MERIT_ASSET))
    patch = channel.selfMask().connectedPixelCount(NETWORK_MIN_PIXELS + 1, True)
    network = channel.updateMask(patch.gte(NETWORK_MIN_PIXELS)).selfMask()
    vectors = network.reduceToVectors(
        geometry=region, scale=NETWORK_SCALE_M, geometryType="polygon", eightConnected=True, maxPixels=1e10
    )
    collection = vectors.getInfo()
    path.write_text(json.dumps(collection))
    return len(collection["features"])


def terrain_summary(terrain: ee.Image, lga: ee.Geometry) -> dict:
    stats = terrain.select(["hand_m", "dist_channel_m", "hollow_m"]).reduceRegion(
        reducer=ee.Reducer.percentile([10, 50, 90]),
        geometry=lga,
        scale=config.TERRAIN_SCALE_M,
        maxPixels=1e10,
    ).getInfo()
    channel_km2 = terrain.select("channel").multiply(ee.Image.pixelArea()).reduceRegion(
        ee.Reducer.sum(), lga, config.TERRAIN_SCALE_M, maxPixels=1e10
    ).get("channel")
    return {
        "percentiles": {k: round(v, 2) for k, v in stats.items()},
        "channel_km2_in_lga": round(ee.Number(channel_km2).divide(1e6).getInfo(), 2),
    }


def run(lga_name: str) -> dict:
    ee.Initialize(project=config.EE_PROJECT)
    lga = lga_geometry(lga_name)
    slug = slugify(lga_name)
    region = hydro_region(lga)
    out_dir = DATA_DIR / slug / "stage4_terrain"
    out_dir.mkdir(parents=True, exist_ok=True)

    terrain = ee.Image(export_terrain(region, slug))
    summary = {
        "lga": lga_name,
        "channel_upa_km2": config.CHANNEL_UPA_KM2,
        "buffer_m": config.HYDRO_BUFFER_M,
        **terrain_summary(terrain, lga),
    }
    write_hand_overlay(terrain, lga, out_dir)
    summary["network_polygons"] = write_network(lga.buffer(2000), out_dir / "drainage_network.geojson")
    outputs.write_lga_boundary(lga, out_dir / "lga_boundary.geojson")
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
