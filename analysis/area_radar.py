"""Radar steps of a drawn-area run: flood history (2021–2026) and the latest pass.

History comes from the published yearly stacks when the area lies inside an analysed LGA, so the
figures match the map. Elsewhere it is recomputed the same way, scene by scene, with Otsu thresholds
set over the area plus a margin instead of over a whole LGA. The ~300 scenes' histograms are fetched
in two batched requests (water, then change), not one request per scene, so it fits a web request.
"""

import base64
import logging
import math
from datetime import date as Date
from datetime import datetime, timedelta, timezone
from typing import Any

import ee
import numpy as np

from analysis import config
from analysis.ee_assets import asset_exists
from analysis.flood_detection import detect_flood, excluded_water
from analysis.otsu import otsu_threshold
from analysis.sar import baseline_composite, despeckle, event_image, s1_collection
from analysis.seasons import parse_years, season_windows
from analysis.stacking import asset_id, frequency_image, remove_specks
from analysis.terrain_tiles import png_bytes

log = logging.getLogger(__name__)

THRESHOLD_MARGIN_M = 5000          # latest pass: Otsu needs both water and land in view
HISTORY_MARGIN_M = 3000            # history: as accurate as 5 km against the stacks, and twice as fast
HISTORY_HIST_SCALE_M = 30
MAX_SCENES = 600
RECENT_DAYS = 21
SAME_PASS_DAYS = 0                 # other orbits imaged the same day fill swath gaps; other days would blur the date
PATCH_MIN_PIXELS = config.REPEAT_MIN_PATCH_PIXELS   # ~0.5 ha at 10 m
MAX_PATCHES = 8
OVERLAY_PX = 768
OVERLAY_ALPHA = 255                 # the map sets the overlay opacity
LATEST_COLOUR = "1f6fff"
YEARS_PALETTE = ["c6dbef", "9ecae1", "6baed6", "3182bd", "08519c", "08306b"]  # as run_stage3.py


def _day(value: str) -> str:
    d = Date.fromisoformat(value)
    return f"{d.day} {d:%b %Y}"


def _ha(value: float) -> str:
    return "under 0.1 ha" if 0 < value < 0.05 else f"{value:.1f} ha"


def latest_passes(rows: list[list[float]]) -> list[tuple[str, int]]:
    """From [time_ms, orbit] rows: the newest pass, plus other orbits imaged the same day."""
    if not rows:
        return []
    newest = {}
    for t, orbit in rows:
        day = datetime.fromtimestamp(t / 1000, tz=timezone.utc).date()
        if int(orbit) not in newest or day > newest[int(orbit)]:
            newest[int(orbit)] = day
    top = max(newest.values())
    keep = [(day, orbit) for orbit, day in newest.items() if (top - day).days <= SAME_PASS_DAYS]
    return [(day.isoformat(), orbit) for day, orbit in sorted(keep, key=lambda p: (-p[0].toordinal(), p[1]))]


def hectares_by_value(histogram: dict[str, float], cell_m: float) -> dict[int, float]:
    cell_ha = cell_m * cell_m / 1e4
    return {int(float(k)): round(v * cell_ha, 1) for k, v in histogram.items() if k != "null"}


def scene_thresholds(histograms: list[dict[str, Any] | None], cap: float | None = None) -> list[float | None]:
    """Otsu threshold per scene histogram (None where the scene had no pixels), optionally capped."""
    found = []
    for h in histograms:
        if not h or not h.get("histogram"):
            found.append(None)
            continue
        t = otsu_threshold(h["histogram"], h["bucketMeans"])
        found.append(min(t, cap) if cap is not None else t)
    return found


def history_line(area_ha: float, recurrent_ha: float, mode: str, years: str) -> str:
    label = f"Radar flood history {years}" + (" (thresholds set for this area)" if mode == "estimate" else "")
    if recurrent_ha <= 0:
        return f"{label}: no ground flooded in 3 or more rainy seasons."
    share = round(100 * recurrent_ha / area_ha) if area_ha else 0
    return f"{label}: {_ha(recurrent_ha)} ({share}% of the area) flooded in 3 or more rainy seasons."


def latest_line(latest: dict[str, Any] | None) -> str:
    if latest is None:
        return f"No radar pass over the area in the last {RECENT_DAYS // 7} weeks."
    if latest["flooded_ha"] > 0:
        return f"Latest radar pass, {_day(latest['date'])}: {_ha(latest['flooded_ha'])} under water."
    return f"Latest radar pass, {_day(latest['date'])}: no flooding seen."


def traced_line(sites: int, kind: str) -> str:
    if sites == 0:
        return "Nothing large enough to trace: no flooded patch or hollow deeper than 0.3 m."
    if kind == "hollow":
        return ("No flooded patch large enough to trace; the deepest "
                + ("hollow" if sites == 1 else f"{sites} hollows") + " in the ground " + ("is" if sites == 1 else "are")
                + " traced instead.")
    return f"{sites} flooded {'patch' if sites == 1 else 'patches'} inside the area {'is' if sites == 1 else 'are'} traced."


# ---------- Earth Engine ----------

def ring_geometry(ring: list[list[float]]) -> ee.Geometry:
    # Planar edges: the drawn outline's bounding box is then exactly the overlay image's bounds
    return ee.Geometry.Polygon([[[lon, lat] for lat, lon in ring]], None, False)


def _recent_rows(ref: ee.Geometry, today: Date) -> list[list[float]]:
    start = (today - timedelta(days=RECENT_DAYS)).isoformat()
    scenes = (ee.ImageCollection(config.S1_ASSET).filterBounds(ref)
              .filterDate(start, (today + timedelta(days=1)).isoformat())
              .filter(ee.Filter.eq("instrumentMode", "IW"))
              .filter(ee.Filter.listContains("transmitterReceiverPolarisation", config.POLARISATION))
              .filter(ee.Filter.inList("relativeOrbitNumber_start", config.ORBITS)))
    return scenes.reduceColumns(ee.Reducer.toList(2), ["system:time_start", "relativeOrbitNumber_start"]) \
        .get("list").getInfo()


def latest_flood(ring_geom: ee.Geometry, today: Date) -> tuple[ee.Image | None, str | None]:
    """Flood mask (0/1) of the newest pass(es) over the area, and that pass's date."""
    ref = ring_geom.buffer(THRESHOLD_MARGIN_M).bounds()
    passes = latest_passes(_recent_rows(ref, today))
    masks = []
    for day, orbit in passes:
        try:
            masks.append(detect_flood(baseline_composite(ref, orbit), event_image(ref, day, orbit), ref).mask)
        except (ValueError, ee.EEException) as exc:
            log.warning("Skipping pass %s orbit %d: %s", day, orbit, exc)
    if not masks:
        return None, None
    return ee.ImageCollection(masks).max().rename("latest").clip(ring_geom), passes[0][0]


def _published_slug(ring_geom: ee.Geometry, years: list[int]) -> str | None:
    """Slug of the analysed LGA that wholly contains the area, if its yearly stacks exist."""
    from analysis.run_stage2 import slugify  # local import: run_stage2 pulls in Stage 2's own helpers

    lgas = ee.FeatureCollection(config.BOUNDARIES_ASSET).filter(ee.Filter.eq("shapeGroup", "NGA")) \
        .filterBounds(ring_geom)
    rows = lgas.map(lambda f: f.set("inside", f.geometry().contains(ring_geom, 1))) \
        .reduceColumns(ee.Reducer.toList(2), ["shapeName", "inside"]).get("list").getInfo()
    for name, inside in rows:
        slug = slugify(name)
        if inside and all(asset_exists(asset_id(slug, y)) for y in (years[0], years[-1])):
            return slug
    return None


def _scene_maker(ref: ee.Geometry, orbit: int, baseline: ee.Image, has_baseline: ee.Number):
    def make(day: ee.String) -> ee.Image:
        start = ee.Date.parse("YYYY-MM-dd", day)
        event = despeckle(s1_collection(ref, start, start.advance(1, "day"), orbit).mosaic())
        return event.addBands(event.subtract(baseline).rename("diff")).set("ok", has_baseline, "day", day)
    return make


def _wet_scenes(ref: ee.Geometry, years: list[int]) -> ee.List:
    """Every rainy-season pass (date and orbit) with a dry-season baseline: bands VH and diff."""
    collections = []
    for year in years:
        windows = season_windows(year)
        for orbit in config.ORBITS:
            dry = s1_collection(ref, *windows.dry, orbit)
            days = s1_collection(ref, *windows.wet, orbit).aggregate_array("system:time_start") \
                .map(lambda t: ee.Date(t).format("YYYY-MM-dd")).distinct()
            make = _scene_maker(ref, orbit, dry.map(despeckle).median(), dry.size().gt(0))
            collections.append(ee.ImageCollection(days.map(make)).filter(ee.Filter.eq("ok", 1)))
    merged = collections[0]
    for more in collections[1:]:
        merged = merged.merge(more)
    return merged.toList(MAX_SCENES)


def _histogram(image: ee.Image, ref: ee.Geometry) -> ee.Dictionary:
    band = image.bandNames().get(0)
    return image.reduceRegion(ee.Reducer.histogram(maxBuckets=255), ref, HISTORY_HIST_SCALE_M,
                              maxPixels=1e9, bestEffort=True).get(band)


def _estimate_years(ring_geom: ee.Geometry, years: list[int]) -> ee.Image:
    """Years flooded, scene by scene as in Stage 3, with thresholds set over the area plus a margin."""
    ref = ring_geom.buffer(HISTORY_MARGIN_M).bounds()
    not_permanent = excluded_water(ref).Not()
    scenes = _wet_scenes(ref, years)
    count = scenes.size().getInfo()
    if count == 0:
        return ee.Image(0).rename("years_flooded").clip(ring_geom)
    water = scene_thresholds(scenes.map(lambda img: _histogram(ee.Image(img).select("VH"), ref)).getInfo())
    water_list = ee.List([-99 if t is None else t for t in water])

    def change_histogram(i: ee.Number) -> ee.Dictionary:
        img = ee.Image(scenes.get(i))
        dark = img.select("VH").lt(ee.Number(water_list.get(i))).And(not_permanent)
        return _histogram(img.select("diff").updateMask(dark), ref)

    change = scene_thresholds(ee.List.sequence(0, count - 1).map(change_histogram).getInfo(),
                              cap=config.MAX_DIFF_THRESHOLD_DB)
    days = scenes.map(lambda img: ee.Image(img).get("day")).getInfo()
    log.info("History: %d scenes thresholded", count)
    flags = []
    for year in years:
        flooded = []
        for k, day in enumerate(days):
            if not day.startswith(str(year)) or water[k] is None or change[k] is None:
                continue
            img = ee.Image(scenes.get(k))
            hit = img.select("VH").lt(water[k]).And(not_permanent).And(img.select("diff").lt(change[k]))
            patch = hit.selfMask().connectedPixelCount(config.MIN_PATCH_PIXELS + 1, True)
            flooded.append(hit.updateMask(patch.gte(config.MIN_PATCH_PIXELS)).unmask(0).rename("f").toUint8())
        if flooded:
            count_year = ee.ImageCollection(flooded).sum()
            flags.append(remove_specks(count_year.gte(config.MIN_FLOOD_OBS_PER_YEAR), config.YEAR_MIN_PATCH_PIXELS))
    if not flags:
        return ee.Image(0).rename("years_flooded").clip(ring_geom)
    native = ee.Projection(config.WORKING_CRS).atScale(config.OUTPUT_SCALE_M)
    return ee.ImageCollection(flags).sum().rename("years_flooded").clip(ring_geom).reproject(native)


def years_flooded(ring_geom: ee.Geometry) -> tuple[ee.Image, str]:
    """Years flooded (0–6) inside the area, and "published" or "estimate"."""
    years = parse_years(config.STACK_YEARS)
    slug = _published_slug(ring_geom, years)
    if slug:
        own = ee.Image(asset_id(slug, years[0])).projection()  # the stacks' grid, as Stage 3 measured them
        return frequency_image(slug, years).select("years_flooded").reproject(own).clip(ring_geom), "published"
    return _estimate_years(ring_geom, years), "estimate"


MERCATOR_HALF_M = 20037508.34


def _mercator(lon: float, lat: float) -> tuple[float, float]:
    x = lon * MERCATOR_HALF_M / 180
    y = math.log(math.tan(math.pi / 4 + math.radians(lat) / 2)) * MERCATOR_HALF_M / math.pi
    return x, y


def mercator_grid(bbox: tuple[float, float, float, float], max_px: int) -> dict[str, Any]:
    """Pixel grid in Web Mercator exactly covering (south, west, north, east), long side max_px."""
    south, west, north, east = bbox
    x0, y0 = _mercator(west, north)
    x1, y1 = _mercator(east, south)
    width_m, height_m = x1 - x0, y0 - y1
    scale = max(width_m, height_m) / max_px
    cols, rows = max(1, round(width_m / scale)), max(1, round(height_m / scale))
    return {"dimensions": {"width": cols, "height": rows}, "crsCode": "EPSG:3857",
            "affineTransform": {"scaleX": width_m / cols, "shearX": 0, "translateX": x0,
                                "shearY": 0, "scaleY": -height_m / rows, "translateY": y0}}


def colourise(values: np.ndarray, colours: dict[int, str], alpha: int) -> np.ndarray:
    """RGBA image: each listed value in its hex colour at the given opacity; anything else transparent."""
    rgba = np.zeros((*values.shape, 4), dtype=np.uint8)
    for value, hex_colour in colours.items():
        rgba[values == value] = [*bytes.fromhex(hex_colour), alpha]
    return rgba


def overlay_png(classes: ee.Image, colours: dict[int, str], bbox: tuple[float, float, float, float]) -> str:
    """Web Mercator PNG of a one-band class image over the box, as a data URI for a Leaflet imageOverlay.

    The class values are fetched with computePixels and coloured here: the read-only service account
    may compute but not create thumbnail links, and Earth Engine's own PNGs cannot be transparent.
    """
    grid = mercator_grid(bbox, OVERLAY_PX)
    pixels = ee.data.computePixels({"expression": classes.unmask(0).toUint8().rename("v"),
                                    "fileFormat": "NUMPY_NDARRAY", "grid": grid})
    png = png_bytes(colourise(np.asarray(pixels["v"]), colours, OVERLAY_ALPHA))
    return "data:image/png;base64," + base64.b64encode(png).decode()


def hectares_where(mask: ee.Image, ring_geom: ee.Geometry) -> dict[int, float]:
    histogram = mask.unmask(0).toUint8().rename("v").reduceRegion(
        ee.Reducer.frequencyHistogram(), ring_geom, config.OUTPUT_SCALE_M, maxPixels=1e9).getInfo()
    return hectares_by_value(histogram.get("v") or {}, config.OUTPUT_SCALE_M)


def patches(mask: ee.Image, ring_geom: ee.Geometry) -> list[dict[str, Any]]:
    """The largest connected patches of a 0/1 mask inside the area, simplified to ~5 m."""
    cleaned = remove_specks(mask.unmask(0), PATCH_MIN_PIXELS)
    vectors = cleaned.selfMask().reduceToVectors(geometry=ring_geom, scale=config.OUTPUT_SCALE_M,
                                                 geometryType="polygon", eightConnected=True, maxPixels=1e9)
    largest = vectors.map(lambda f: f.set("area_m2", f.geometry().area(1)).setGeometry(f.geometry().simplify(5))) \
        .sort("area_m2", False).limit(MAX_PATCHES)
    return [{"geometry": f["geometry"], "area_ha": round(f["properties"]["area_m2"] / 1e4, 2)}
            for f in largest.getInfo()["features"]]
