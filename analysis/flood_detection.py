"""Stage 2: classify newly flooded pixels from a baseline/event pair.

Two Otsu thresholds, both computed per scene:
1. water threshold on the event image — separates dark (water-like) from land;
2. change threshold on the backscatter drop, computed only over dark,
   non-permanent pixels — separates new flood from surfaces that are always dark
   (tarmac, radar shadow). Otsu over the whole LGA fails because flood is a
   small fraction of it and the histogram is not bimodal.
"""

from dataclasses import dataclass

import ee

from analysis import config
from analysis.otsu import otsu_threshold


@dataclass(frozen=True)
class FloodResult:
    mask: ee.Image
    difference: ee.Image
    water_threshold_db: float
    change_threshold_db: float


def excluded_water(region: ee.Geometry) -> ee.Image:
    """Water that is not flooding: permanent, tidal or intermittent (JRC), or mangrove.

    In estuarine LGAs such as Port Harcourt, tide height differs between dates,
    so creek edges and mangrove fringes would otherwise read as new flooding.
    """
    occurrence = ee.Image(config.JRC_ASSET).select("occurrence").unmask(0)
    mangrove = ee.ImageCollection(config.WORLDCOVER_ASSET).first().eq(config.MANGROVE_CLASS)
    return occurrence.gte(config.TIDAL_OCCURRENCE_PCT).Or(mangrove).clip(region)


def _histogram_threshold(image: ee.Image, region: ee.Geometry) -> float:
    band = image.bandNames().get(0)
    histogram = image.reduceRegion(
        reducer=ee.Reducer.histogram(maxBuckets=255),
        geometry=region,
        scale=config.HISTOGRAM_SCALE_M,
        maxPixels=1e10,
        bestEffort=True,
    ).get(band).getInfo()
    if not histogram:
        raise ValueError("Empty histogram — region has no valid pixels")
    return otsu_threshold(histogram["histogram"], histogram["bucketMeans"])


def detect_flood(baseline: ee.Image, event: ee.Image, region: ee.Geometry) -> FloodResult:
    difference = event.subtract(baseline).rename("diff")
    not_permanent = excluded_water(region).Not()

    water_t = _histogram_threshold(event, region)
    dark = event.lt(water_t).And(not_permanent)

    change_t = min(
        _histogram_threshold(difference.updateMask(dark), region),
        config.MAX_DIFF_THRESHOLD_DB,
    )
    flooded = dark.And(difference.lt(change_t))
    patch_size = flooded.selfMask().connectedPixelCount(config.MIN_PATCH_PIXELS + 1, True)
    mask = flooded.updateMask(patch_size.gte(config.MIN_PATCH_PIXELS)).unmask(0).rename("flood")

    return FloodResult(mask.clip(region), difference, water_t, change_t)


def flooded_hectares(mask: ee.Image, region: ee.Geometry) -> float:
    area = mask.multiply(ee.Image.pixelArea()).reduceRegion(
        reducer=ee.Reducer.sum(),
        geometry=region,
        scale=config.OUTPUT_SCALE_M,
        maxPixels=1e10,
    ).get("flood")
    return ee.Number(area).divide(1e4).getInfo()
