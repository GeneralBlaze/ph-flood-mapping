"""Stage 5 rules: classify repeat-flood patches and rank suspected drainage problems.

Pure functions so the rules can be read, tested and argued with. Earth Engine
only supplies the per-patch statistics.
"""

from typing import Any

from analysis.terrain_classes import HOLLOW_M

RAISED_HAND_M = 3.0          # both HAND models at/above this: water should drain away
NATURAL_HAND_M = 1.0         # both HAND models below this: floodplain, flooding is expected
MAJOR_RIVER_UPA_KM2 = 50.0   # patch touches a river draining at least this much land
CHANNEL_NEAR_M = 150.0       # patch sits on an expected channel corridor
CROSSING_NEAR_M = 150.0      # a major road crosses that channel this close
WETLAND_FRACTION = 0.3       # share mapped as wetland/mangrove (ESA WorldCover) that makes it natural
CROSSING_BONUS_M = 2.0       # anomaly credit for a nearby road crossing
URBAN_MIN_FRACTION = 0.25    # engineered drainage exists where people have built
MIN_MEAN_YEARS = 1.0         # below this at 30 m the patch is too thin to measure reliably
YEARS_TOTAL = 6


def _reasons(stats: dict[str, Any], anomaly_m: float, crossing_dist_m: float | None, raised: bool) -> list[str]:
    reasons = [f"Standing water in about {round(stats['mean_years'])} of the last {YEARS_TOTAL} rainy seasons"]
    if raised:
        reasons.append(f"Sits {anomaly_m:.1f} m above the nearest drainage channel, so water should drain away")
    if crossing_dist_m is not None:
        reasons.append(
            f"A road crosses the expected channel {crossing_dist_m:.0f} m away; "
            "a missing or blocked culvert would pool water like this"
        )
    if stats["hollow_m"] <= HOLLOW_M:
        reasons.append("Lies in a local hollow, which can trap water even with working drains")
    if stats.get("built_frac", 0) > 0:
        reasons.append(f"Built-up land (buildings, roads, paving): {round(stats['built_frac'] * 100)}%")
    if stats.get("buildings", 0) > 0:
        reasons.append(f"About {stats['buildings']} buildings inside the flooded area")
    return reasons


def classify_patch(stats: dict[str, Any], crossing_dist_m: float | None) -> dict[str, Any]:
    """Return a new dict: stats plus category (suspect|natural|unclear), kind, anomaly_m, score, reasons."""
    anomaly_m = min(stats["hand_m"], stats["hand_fab_m"])
    near_major_river = stats["max_upa_km2"] >= MAJOR_RIVER_UPA_KM2
    very_low = max(stats["hand_m"], stats["hand_fab_m"]) < NATURAL_HAND_M
    wetland = stats.get("wetland_frac", 0) >= WETLAND_FRACTION
    if near_major_river or very_low or wetland:
        if wetland:
            why = "Mapped as wetland or mangrove"
        elif near_major_river:
            why = "Beside a major river"
        else:
            why = "Low ground right beside a channel"
        return {**stats, "category": "natural", "kind": "floodplain", "anomaly_m": anomaly_m, "score": 0,
                "reasons": [f"{why}: flooding here is expected, not a sign of blocked drains"]}

    if stats.get("on_airfield"):
        return {**stats, "category": "unclear", "kind": None, "anomaly_m": anomaly_m, "score": 0,
                "reasons": ["On or beside an airfield runway, taxiway or apron: smooth paving appears as water "
                            "on radar, so this is most likely not flooding"]}

    if stats["mean_years"] < MIN_MEAN_YEARS:
        return {**stats, "category": "unclear", "kind": None, "anomaly_m": anomaly_m, "score": 0,
                "reasons": ["Area is too small or thin to measure reliably at 30 m"]}

    if stats.get("built_frac", 0.0) < URBAN_MIN_FRACTION:
        return {**stats, "category": "unclear", "kind": None, "anomaly_m": anomaly_m, "score": 0,
                "reasons": ["Floods repeatedly but is not built-up: more likely a seasonal pond, farmland "
                            "or borrow pit than a blocked drain"]}

    raised = anomaly_m >= RAISED_HAND_M
    on_channel = stats["dist_channel_m"] <= CHANNEL_NEAR_M
    crossing = crossing_dist_m if (crossing_dist_m is not None and crossing_dist_m <= CROSSING_NEAR_M and on_channel) else None
    if not raised and crossing is None:
        return {**stats, "category": "unclear", "kind": None, "anomaly_m": anomaly_m, "score": 0,
                "reasons": ["Floods repeatedly, but the terrain does not clearly say it should drain"]}

    magnitude = anomaly_m + (CROSSING_BONUS_M if crossing is not None else 0.0)
    return {
        **stats,
        "category": "suspect",
        "kind": "raised_ground" if raised else "road_crossing",
        "anomaly_m": anomaly_m,
        "score": stats["mean_years"] * magnitude,
        "reasons": _reasons(stats, anomaly_m, crossing, raised),
    }


def rank_suspects(patches: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Suspects only, highest score first (larger area breaks ties), numbered from 1."""
    suspects = [p for p in patches if p["category"] == "suspect"]
    ordered = sorted(suspects, key=lambda p: (p["score"], p["area_ha"]), reverse=True)
    return [{**p, "rank": i} for i, p in enumerate(ordered, 1)]
