"""Plain-language account of where water from a site should go, street by street.

Built from a 30 m flow route (hydro_grid), named OSM streets and FABDEM heights.
FABDEM is accurate to roughly 1-2 m in towns, so heights are rounded, small
differences are called "about level", and the wording says "should", not "does".
"""

import math
from typing import Any

from shapely.geometry import Point

METRES_PER_DEG_LAT = 110_574.0
METRES_PER_DEG_LON_EQUATOR = 111_320.0
FOLLOW_MIN_POINTS = 3      # route points near a street before we say it "follows" it
LEVEL_M = 0.5              # differences smaller than this are within the elevation data's noise
RISE_MIN_M = 0.5
DISTANCE_STEP_M = 50


def _metres(lat: float) -> tuple[float, float]:
    return METRES_PER_DEG_LON_EQUATOR * math.cos(math.radians(lat)), METRES_PER_DEG_LAT


def _nearest_named(point: tuple[float, float], roads: list[dict[str, Any]], tolerance_m: float) -> str | None:
    lon_m, lat_m = _metres(point[1])
    p = Point(point)
    best, best_m = None, tolerance_m
    for road in roads:
        if not road.get("name"):
            continue
        nearest = road["line"].interpolate(road["line"].project(p))
        metres = math.hypot((nearest.x - point[0]) * lon_m, (nearest.y - point[1]) * lat_m)
        if metres <= best_m:
            best, best_m = road["name"], metres
    return best


def streets_along(route: list[tuple[float, float]], roads: list[dict[str, Any]], tolerance_m: float) -> list[dict[str, Any]]:
    """Named streets the route runs along or crosses, in the order water meets them."""
    names = [_nearest_named(p, roads, tolerance_m) for p in route]
    streets: list[dict[str, Any]] = []
    for index, name in enumerate(names):
        if name and all(s["name"] != name for s in streets):
            count = names.count(name)
            streets.append({"name": name, "role": "follows" if count >= FOLLOW_MIN_POINTS else "crosses",
                            "first_index": index})
    return streets


def rim_summary(lows: list[dict[str, Any]], limit: int) -> list[dict[str, Any]]:
    """Nearby streets from lowest (the likeliest way out) upwards."""
    return sorted(lows, key=lambda r: r["height_m"])[:limit]


def _join(parts: list[str]) -> str:
    return parts[0] if len(parts) == 1 else ", ".join(parts[:-1]) + " and " + parts[-1]


def _rounded(metres: float) -> int:
    return int(round(metres / DISTANCE_STEP_M) * DISTANCE_STEP_M) or DISTANCE_STEP_M


ON_CHANNEL_M = 75          # routes shorter than this: the site is already on a drainage line
BUILDING_STREET_MIN = 3    # name the street most buildings stand along only if it has this many
BUILDING_STREET_SHARE = 0.25


def _opening(rise_m: float, barrier_street: str | None, route_m: float) -> str:
    if rise_m >= RISE_MIN_M:
        where = f", at the low point on {barrier_street}" if barrier_street else ""
        return (f"Water has to rise about {rise_m:.1f} m before it can flow out{where}. "
                "This is a hollow with no natural way out at ground level.")
    if route_m < ON_CHANNEL_M:
        return ("The site sits on a natural drainage line, so water should flow straight away. Water that stays "
                "points to a blocked or undersized drain or culvert.")
    return ("The ground falls away from here, so water should run off on its own. Water that stays points to "
            "blocked or undersized drains or culverts rather than the lie of the land.")


def _route_sentence(rise_m: float, streets: list[dict[str, Any]], route_m: float) -> str:
    lead = "From there it should" if rise_m >= RISE_MIN_M else "It should"
    distance = f"about {_rounded(route_m)} m away"
    if not streets:
        return f"{lead} reach the nearest drainage channel {distance}, without following a named street."
    verbs = [f"{'follow' if s['role'] == 'follows' else 'cross'} {s['name']}" for s in streets]
    return f"{lead} {_join(verbs)} to the nearest drainage channel, {distance}."


def _buildings_sentence(buildings_by_street: dict[str | None, int]) -> str:
    total = sum(buildings_by_street.values())
    if total == 0:
        return "No buildings found on that route."
    noun, verb = ("building", "stands") if total == 1 else ("buildings", "stand")
    sentence = f"{total} {noun} {verb} on or beside that route"
    named = {k: v for k, v in buildings_by_street.items() if k}
    if named:
        street, count = max(named.items(), key=lambda kv: kv[1])
        if count >= BUILDING_STREET_MIN and count / total >= BUILDING_STREET_SHARE:
            sentence += f", {count} of them along {street}"
    return sentence + "."


def _listed(rim: list[dict[str, Any]], with_height: bool) -> str:
    return ", ".join(f"{r['name']} ({abs(r['height_m']):.1f} m)" if with_height else r["name"] for r in rim)


def _rim_sentences(rim: list[dict[str, Any]]) -> list[str]:
    lower = [r for r in rim if r["height_m"] <= -LEVEL_M]
    level = [r for r in rim if abs(r["height_m"]) < LEVEL_M]
    higher = [r for r in rim if r["height_m"] >= LEVEL_M]
    sentences = []
    if lower:
        them, drains = ("it", "a blocked or missing drain") if len(lower) == 1 else ("them", "blocked or missing drains")
        sentences.append(f"Lower than the flooded ground: {_listed(lower, True)}. Water should be able to reach "
                         f"{them}, so check for {drains} in between.")
    if level:
        sentences.append(f"About level with the flooded ground: {_listed(level, False)}.")
    if higher:
        sentences.append(f"Higher than the flooded ground: {_listed(higher, True)}.")
    return sentences


def compose_story(rise_m: float, barrier_street: str | None, streets: list[dict[str, Any]], route_m: float,
                  buildings_by_street: dict[str | None, int], rim: list[dict[str, Any]]) -> list[str]:
    story = [_opening(rise_m, barrier_street, route_m)]
    if rise_m >= RISE_MIN_M or route_m >= ON_CHANNEL_M:
        story += [_route_sentence(rise_m, streets, route_m), _buildings_sentence(buildings_by_street)]
    return story + _rim_sentences(rim)
