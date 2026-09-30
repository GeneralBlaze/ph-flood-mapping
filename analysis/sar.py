"""Sentinel-1 loading and preprocessing."""

import ee

from analysis import config


def lga_geometry(name: str) -> ee.Geometry:
    lgas = ee.FeatureCollection(config.BOUNDARIES_ASSET).filter(
        ee.Filter.And(ee.Filter.eq("shapeGroup", "NGA"), ee.Filter.eq("shapeName", name))
    )
    if lgas.size().getInfo() != 1:
        raise ValueError(f"Expected exactly one LGA named {name!r} in {config.BOUNDARIES_ASSET}")
    return lgas.first().geometry()


def s1_collection(region: ee.Geometry, start: str, end: str, orbit: int) -> ee.ImageCollection:
    """IW-mode VH scenes from a single relative orbit, so geometry is consistent."""
    return (
        ee.ImageCollection(config.S1_ASSET)
        .filterBounds(region)
        .filterDate(start, end)
        .filter(ee.Filter.eq("instrumentMode", "IW"))
        .filter(ee.Filter.listContains("transmitterReceiverPolarisation", config.POLARISATION))
        .filter(ee.Filter.eq("relativeOrbitNumber_start", orbit))
        .select(config.POLARISATION)
    )


def despeckle(image: ee.Image) -> ee.Image:
    """Focal median in linear power, returned in dB."""
    linear = ee.Image(10).pow(image.divide(10))
    smoothed = linear.focalMedian(config.SPECKLE_RADIUS_M, "circle", "meters")
    return smoothed.log10().multiply(10).rename(config.POLARISATION)


def baseline_composite(
    region: ee.Geometry, orbit: int, window: tuple[str, str] = config.DRY_SEASON
) -> ee.Image:
    scenes = s1_collection(region, *window, orbit)
    if scenes.size().getInfo() == 0:
        raise ValueError(f"No dry-season scenes for orbit {orbit} in {window}")
    return scenes.map(despeckle).median().clip(region)


def scene_dates(region: ee.Geometry, window: tuple[str, str], orbit: int) -> list[str]:
    """Distinct acquisition dates (UTC) for one orbit; same-day tiles share a date."""
    dates = s1_collection(region, *window, orbit).aggregate_array("system:time_start").map(
        lambda t: ee.Date(t).format("YYYY-MM-dd")
    )
    return sorted(set(dates.getInfo()))


def event_image(region: ee.Geometry, date: str, orbit: int) -> ee.Image:
    day = ee.Date(date)
    scenes = s1_collection(region, day, day.advance(1, "day"), orbit)
    if scenes.size().getInfo() == 0:
        raise ValueError(f"No Sentinel-1 scene on {date} for orbit {orbit}")
    return despeckle(scenes.mosaic()).clip(region)
