"""Stage 3: stack per-scene flood masks into per-year and multi-year frequency.

Per year, every rainy-season scene from every orbit is classified against that
year's dry-season baseline for the same orbit. Two counts are kept per pixel:
how often it was observed and how often it was flooded, so pixels outside a
swath are never mistaken for dry ground.

Each year is exported to an Earth Engine asset (batch task, no interactive
timeout) and reused on later runs.
"""

import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import ee

from analysis import config
from analysis.flood_detection import detect_flood
from analysis.sar import baseline_composite, event_image, scene_dates
from analysis.seasons import season_windows

log = logging.getLogger(__name__)
TASK_POLL_INTERVAL_S = 30


def classify_scene(region: ee.Geometry, baseline: ee.Image, day: str, orbit: int) -> ee.Image:
    """Bands: flood (1 = flooded and observed), observed (1 = inside the swath)."""
    event = event_image(region, day, orbit)
    observed = event.mask().rename("observed").unmask(0).clip(region)
    result = detect_flood(baseline, event, region)
    flood = result.mask.And(observed).rename("flood")
    return flood.addBands(observed).toUint8()


def _orbit_scenes(region: ee.Geometry, year: int, orbit: int) -> list[ee.Image]:
    windows = season_windows(year)
    try:
        baseline = baseline_composite(region, orbit, windows.dry)
    except ValueError as exc:
        log.warning("Skipping orbit %d in %d: %s", orbit, year, exc)
        return []
    days = scene_dates(region, windows.wet, orbit)

    scenes = []
    with ThreadPoolExecutor(max_workers=config.EE_WORKERS) as pool:
        futures = {pool.submit(classify_scene, region, baseline, d, orbit): d for d in days}
        for future in as_completed(futures):
            try:
                scenes.append(future.result())
            except (ValueError, ee.EEException) as exc:
                log.warning("Skipping %s orbit %d: %s", futures[future], orbit, exc)
    log.info("  %d orbit %d: %d/%d scenes classified", year, orbit, len(scenes), len(days))
    return scenes


def year_image(region: ee.Geometry, year: int, orbits: list[int]) -> ee.Image:
    """Bands: flood_obs, obs (counts across the rainy season)."""
    scenes = [s for orbit in orbits for s in _orbit_scenes(region, year, orbit)]
    if not scenes:
        raise ValueError(f"No usable scenes in {year}")
    total = ee.ImageCollection(scenes).sum()
    return total.select(["flood", "observed"], ["flood_obs", "obs"]).toUint16().clip(region)


def asset_id(lga_slug: str, year: int) -> str:
    return f"projects/{config.EE_PROJECT}/assets/{lga_slug}/stage3_{year}"


def _ensure_folder(path: str) -> None:
    try:
        ee.data.getAsset(path)
    except ee.EEException:
        ee.data.createFolder(path)


def _asset_exists(path: str) -> bool:
    try:
        ee.data.getAsset(path)
        return True
    except ee.EEException:
        return False


def export_years(region: ee.Geometry, lga_slug: str, years: list[int], orbits: list[int]) -> None:
    """Start export tasks for years without an asset, then wait for all of them."""
    _ensure_folder(f"projects/{config.EE_PROJECT}/assets/{lga_slug}")
    tasks = []
    for year in years:
        target = asset_id(lga_slug, year)
        if _asset_exists(target):
            log.info("%d: cached asset found", year)
            continue
        log.info("%d: classifying scenes", year)
        task = ee.batch.Export.image.toAsset(
            image=year_image(region, year, orbits).set("year", year),
            description=f"{lga_slug}_stage3_{year}",
            assetId=target,
            region=region,
            scale=config.OUTPUT_SCALE_M,
            maxPixels=1e10,
        )
        task.start()
        tasks.append((year, task))
    _wait_for(tasks)


def _wait_for(tasks: list) -> None:
    pending = dict(tasks)
    while pending:
        for year, task in list(pending.items()):
            status = task.status()
            state = status["state"]
            if state == "COMPLETED":
                log.info("%d: export complete", year)
                del pending[year]
            elif state in ("FAILED", "CANCELLED"):
                raise RuntimeError(f"Export for {year} {state}: {status.get('error_message')}")
        if pending:
            time.sleep(TASK_POLL_INTERVAL_S)


def frequency_image(lga_slug: str, years: list[int]) -> ee.Image:
    """Bands: years_flooded, years_observed, flood_obs, obs, frequency_pct."""
    yearly = [ee.Image(asset_id(lga_slug, y)) for y in years]
    flooded_years = ee.ImageCollection(
        [img.select("flood_obs").gte(config.MIN_FLOOD_OBS_PER_YEAR) for img in yearly]
    ).sum()
    observed_years = ee.ImageCollection([img.select("obs").gt(0) for img in yearly]).sum()
    counts = ee.ImageCollection(yearly).sum()
    frequency = counts.select("flood_obs").divide(counts.select("obs").max(1)).multiply(100)
    return ee.Image.cat(
        flooded_years.rename("years_flooded").toUint8(),
        observed_years.rename("years_observed").toUint8(),
        counts.select("flood_obs").toUint16(),
        counts.select("obs").toUint16(),
        frequency.rename("frequency_pct").toFloat(),
    )
