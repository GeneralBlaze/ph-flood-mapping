"""Standing water: which flooding drained away and which is still there after a dry spell.

Compares two flood masks from the same orbit, one taken just after heavy rain and
one after several dry days. Land that drains normally clears within a day or two,
so water still present on the second date points to drainage that is not working.
"""

from typing import Any

import ee

DRAINED, STANDING, NEW, NOT_IMAGED = 1, 2, 3, 4
CLASS_NAMES = {DRAINED: "drained", STANDING: "standing", NEW: "new", NOT_IMAGED: "not_imaged"}
MIN_COVERED_FRAC = 0.5  # a site must be at least half inside both radar swaths to be judged


def persistence_image(before: ee.Image, after: ee.Image, covered: ee.Image) -> ee.Image:
    """0 dry on both dates, 1 drained, 2 still standing, 3 wet only on the second date,
    4 outside the radar swath on either date (no information, not dry)."""
    before, after = before.unmask(0).gt(0), after.unmask(0).gt(0)
    classes = (
        before.And(after.Not()).multiply(DRAINED)
        .add(before.And(after).multiply(STANDING))
        .add(after.And(before.Not()).multiply(NEW))
    )
    return classes.where(covered.unmask(0).Not(), NOT_IMAGED).rename("persistence").toByte()


def class_hectares(image: ee.Image, region: ee.Geometry, scale: float) -> list[dict[str, Any]]:
    """Area per class as [{'class': n, 'sum': m2}, ...]."""
    result = ee.Image.pixelArea().addBands(image).reduceRegion(
        reducer=ee.Reducer.sum().group(groupField=1, groupName="class"),
        geometry=region,
        scale=scale,
        maxPixels=1e10,
    ).getInfo()
    return result.get("groups", [])


def hectares_by_class(groups: list[dict[str, Any]]) -> dict[str, float]:
    totals = {name: 0.0 for name in CLASS_NAMES.values()}
    for group in groups:
        name = CLASS_NAMES.get(int(group["class"]))
        if name:
            totals[name] = round(group["sum"] / 1e4, 1)
    return totals


def site_status(before_frac: float, after_frac: float, covered: float, min_frac: float) -> str:
    """'standing' if a meaningful share is still wet, 'drained' if it was wet and cleared, 'dry',
    or 'not_imaged' when the radar did not see enough of the site on both dates.
    Fractions are shares of the imaged part of the site."""
    if covered < MIN_COVERED_FRAC:
        return "not_imaged"
    if after_frac >= min_frac:
        return "standing"
    if before_frac >= min_frac:
        return "drained"
    return "dry"
