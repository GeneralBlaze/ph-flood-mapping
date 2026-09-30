"""Stage 4: where water *should* drain.

Builds one 30 m terrain stack over the LGA plus a buffer (drainage ignores LGA
borders) and exports it as an Earth Engine asset for Stage 5.

Resampling, recorded deliberately:
- MERIT Hydro (~90 m) up to 30 m: nearest neighbour for categorical/accumulated
  bands (upstream area, channel mask), bilinear for HAND.
- FABDEM is native 30 m.
- Stage 3 flood frequency (10 m) is averaged down to 30 m in Stage 5.
"""

import ee

from analysis import config

MERIT_ASSET = "MERIT/Hydro/v1_0_1"
FABDEM_ASSET = "projects/sat-io/open-datasets/FABDEM"


def hydro_region(lga: ee.Geometry) -> ee.Geometry:
    return lga.buffer(config.HYDRO_BUFFER_M)


def channel_mask(merit: ee.Image) -> ee.Image:
    return merit.select("upa").gte(config.CHANNEL_UPA_KM2).rename("channel")


def distance_to_channel(channel: ee.Image) -> ee.Image:
    """Metres to the nearest expected channel, computed on the 30 m working grid."""
    pixels = channel.selfMask().fastDistanceTransform(config.MAX_CHANNEL_DISTANCE_PX, "pixels", "squared_euclidean")
    grid = ee.Projection(config.WORKING_CRS).atScale(config.TERRAIN_SCALE_M)
    return pixels.sqrt().multiply(config.TERRAIN_SCALE_M).reproject(grid).rename("dist_channel_m")


def local_hollow(region: ee.Geometry) -> ee.Image:
    """Ground height minus the median of its surroundings; negative = hollow."""
    dem = ee.ImageCollection(FABDEM_ASSET).filterBounds(region).mosaic().select(0).rename("elv_m")
    surroundings = dem.focalMedian(config.HOLLOW_RADIUS_M, "circle", "meters")
    return dem.addBands(dem.subtract(surroundings).rename("hollow_m"))


def hand_from_fabdem(dem: ee.Image, channel: ee.Image) -> ee.Image:
    """Height above the lowest channel within CHANNEL_SEARCH_M, on building-free FABDEM.

    MERIT's HAND is built on 2000-era elevation that still contains buildings,
    which inflates it in dense urban areas; this version cross-checks it.
    """
    channel_elevation = dem.updateMask(channel)
    lowest_nearby = channel_elevation.focalMin(config.CHANNEL_SEARCH_M, "circle", "meters")
    return dem.subtract(lowest_nearby).max(0).rename("hand_fab_m")


def terrain_stack(region: ee.Geometry) -> ee.Image:
    """Bands: hand_m, hand_fab_m, upa_km2, channel, dist_channel_m, elv_m, hollow_m (all 30 m)."""
    merit = ee.Image(MERIT_ASSET)
    channel = channel_mask(merit)
    terrain = local_hollow(region)
    stack = ee.Image.cat(
        merit.select("hnd").resample("bilinear").rename("hand_m"),
        hand_from_fabdem(terrain.select("elv_m"), channel),
        merit.select("upa").rename("upa_km2"),
        channel,
        distance_to_channel(channel),
        terrain,
    )
    return stack.toFloat().clip(region)


def terrain_asset_id(lga_slug: str) -> str:
    return f"projects/{config.EE_PROJECT}/assets/{lga_slug}/stage4_terrain"
