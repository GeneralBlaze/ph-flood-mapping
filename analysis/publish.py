"""Copy finished pipeline outputs into web/data/ and write the site manifest.

Only public-facing fields are published: hotspot records are stripped of raw
geocoder responses, and coordinates are rounded to ~1 m to keep files small.

Usage:
    python -m analysis.publish
"""

import json
import logging
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from analysis import config
from analysis.landmarks import describe_nearby, nearby_landmarks, parse_landmarks
from analysis.run_stage2 import DATA_DIR, slugify

WEB_DATA_DIR = Path(__file__).resolve().parent.parent / "web" / "data"
COORD_DECIMALS = 5
# geoBoundaries spellings -> names people use
DISPLAY_NAMES = {"Port-Harcourt": "Port Harcourt"}
HOTSPOT_FIELDS = ("area_ha", "lat", "lon", "place")
SUSPECT_FIELDS = ("rank", "kind", "place", "area_ha", "mean_years", "anomaly_m", "buildings", "built_frac",
                  "lat", "lon", "reasons", "crossing_road", "path_buildings")
NEARBY_MAX_M = 600
NEARBY_LIMIT = 3
log = logging.getLogger(__name__)


def round_coordinates(geometry: dict[str, Any], decimals: int) -> dict[str, Any]:
    """Return a copy of a GeoJSON geometry with coordinates rounded."""

    def _round(value: Any) -> Any:
        if isinstance(value, (int, float)):
            return round(value, decimals)
        return [_round(v) for v in value]

    return {**geometry, "coordinates": _round(geometry["coordinates"])}


def compact_flow(collection: dict[str, Any]) -> list[list[float]]:
    """[[lon1, lat1, lon2, lat2, upstream_km2], ...] — a fifth of the GeoJSON size."""
    rows = []
    for f in collection["features"]:
        (lon1, lat1), (lon2, lat2) = f["geometry"]["coordinates"]
        rows.append([round(lon1, COORD_DECIMALS), round(lat1, COORD_DECIMALS),
                     round(lon2, COORD_DECIMALS), round(lat2, COORD_DECIMALS), round(f["properties"]["upa_km2"], 1)])
    return rows


def _read(path: Path) -> Any:
    return json.loads(path.read_text())


def _write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, separators=(",", ":")))


def _publish_geojson(source: Path, target: Path) -> None:
    collection = _read(source)
    features = [
        {"type": "Feature", "properties": {}, "geometry": round_coordinates(f["geometry"], COORD_DECIMALS)}
        for f in collection.get("features", [])
        if f.get("geometry")
    ]
    _write_json(target, {"type": "FeatureCollection", "features": features})


def _publish_hotspots(source: Path, target: Path) -> None:
    clusters = _read(source)
    public = [
        {"rank": i, **{k: c[k] for k in HOTSPOT_FIELDS}}
        for i, c in enumerate(clusters, 1)
        if c.get("place") != "lookup failed"
    ]
    _write_json(target, public)


def _latest(directory: Path, pattern: str) -> Path | None:
    matches = sorted(p for p in directory.glob(pattern) if (p / "summary.json").exists())
    return matches[-1] if matches else None


def _event_entry(stage2: Path, slug: str, web_data: Path) -> dict[str, Any]:
    summary = _read(stage2 / "summary.json")
    date = summary["passes"][0]["date"]
    overlay = f"{slug}/event_{date}.png"
    hotspots = f"{slug}/event_{date}_hotspots.json"
    (web_data / slug).mkdir(parents=True, exist_ok=True)
    shutil.copyfile(stage2 / "flood_overlay.png", web_data / overlay)
    _publish_hotspots(stage2 / "flood_clusters.json", web_data / hotspots)
    return {
        "date": date,
        "orbits": [p["orbit"] for p in summary["passes"]],
        "flooded_ha": summary["flooded_ha"],
        "overlay": overlay,
        "bounds": _read(stage2 / "flood_overlay.bounds.json"),
        "hotspots": hotspots,
    }


def _frequency_entry(stage3: Path, slug: str, web_data: Path) -> dict[str, Any]:
    summary = _read(stage3 / "summary.json")
    overlay = f"{slug}/frequency.png"
    hotspots = f"{slug}/frequency_hotspots.json"
    polygons = f"{slug}/repeat_areas.geojson"
    shutil.copyfile(stage3 / "frequency_overlay.png", web_data / overlay)
    _publish_hotspots(stage3 / "repeat_clusters.json", web_data / hotspots)
    _publish_geojson(stage3 / "repeat_polygons.geojson", web_data / polygons)
    return {
        "years": summary["years"],
        "repeat_min_years": summary["repeat_min_years"],
        "min_flood_dates_per_year": summary.get("min_flood_dates_per_year", 1),
        "hectares_by_years_flooded": summary["hectares_by_years_flooded"],
        "overlay": overlay,
        "bounds": _read(stage3 / "frequency_overlay.bounds.json"),
        "hotspots": hotspots,
        "repeat_areas": polygons,
    }


def _terrain_entry(stage4: Path, slug: str, web_data: Path) -> dict[str, Any]:
    summary = _read(stage4 / "summary.json")
    overlay = f"{slug}/hand.png"
    drainage = f"{slug}/drainage_network.geojson"
    (web_data / slug).mkdir(parents=True, exist_ok=True)
    shutil.copyfile(stage4 / "hand_overlay.png", web_data / overlay)
    _publish_geojson(stage4 / "drainage_network.geojson", web_data / drainage)
    flow = f"{slug}/flow.json"
    has_flow = (stage4 / "flow_paths.geojson").exists()
    if has_flow:
        _write_json(web_data / flow, compact_flow(_read(stage4 / "flow_paths.geojson")))
    return {
        "flow": flow if has_flow else None,
        "channel_upa_km2": summary["channel_upa_km2"],
        "hand_overlay": overlay,
        "hand_bounds": _read(stage4 / "hand_overlay.bounds.json"),
        "drainage": drainage,
    }


def merge_site_status(suspects: list[dict[str, Any]], statuses: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Copy of suspects with water_now: 'standing' | 'drained' | 'dry' | None (not measured)."""
    by_rank = {s["rank"]: s["status"] for s in statuses}
    return [{**s, "water_now": by_rank.get(s["rank"])} for s in suspects]


def _standing_entry(standing: Path, slug: str, web_data: Path) -> dict[str, Any]:
    summary = _read(standing / "summary.json")
    after = summary["after"]["date"]
    overlay = f"{slug}/standing_{after}.png"
    hotspots = f"{slug}/standing_{after}_hotspots.json"
    (web_data / slug).mkdir(parents=True, exist_ok=True)
    shutil.copyfile(standing / "standing_overlay.png", web_data / overlay)
    _publish_hotspots(standing / "standing_clusters.json", web_data / hotspots)
    return {
        "before": summary["before"]["date"],
        "after": after,
        "orbit": summary["after"]["orbit"],
        "hectares": summary["hectares"],
        "overlay": overlay,
        "bounds": _read(standing / "standing_overlay.bounds.json"),
        "hotspots": hotspots,
    }


# Reasons written by Stage 5 from the 90 m route; Stage 6's 30 m street account supersedes them.
OLD_ROUTE_MARKERS = ("route water should take", "natural drainage path", "no traceable route")


def apply_stories(suspects: list[dict[str, Any]], stories: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Copy of suspects with the Stage 6 street account; the older 90 m route reason and count are replaced."""
    by_rank = {s["rank"]: s for s in stories}
    out = []
    for suspect in suspects:
        story = by_rank.get(suspect["rank"])
        if story is None:
            out.append({**suspect, "story": None})
            continue
        reasons = [r for r in suspect["reasons"] if not any(m in r.lower() for m in OLD_ROUTE_MARKERS)]
        out.append({**suspect, "reasons": reasons, "story": story["story"],
                    "path_buildings": sum(story["buildings_by_street"].values())})
    return out


def _suspects_entry(stage5: Path, slug: str, web_data: Path, standing: Path | None) -> dict[str, Any]:
    summary = _read(stage5 / "summary.json")
    listed = f"{slug}/suspects.json"
    areas = f"{slug}/suspect_areas.geojson"
    public = [
        {**{k: s.get(k) for k in SUSPECT_FIELDS}, "anomaly_m": round(s["anomaly_m"], 1), "mean_years": round(s["mean_years"], 1)}
        for s in _read(stage5 / "suspects.json")
    ]
    status_file = standing / "site_status.json" if standing else None
    if status_file and status_file.exists():
        public = merge_site_status(public, _read(status_file))
    stage6 = stage5.parent / "stage6_streets"
    if (stage6 / "stories.json").exists():
        public = apply_stories(public, _read(stage6 / "stories.json"))
    _write_json(web_data / listed, public)
    features = [
        {"type": "Feature", "properties": {"rank": f["properties"]["rank"]},
         "geometry": round_coordinates(f["geometry"], COORD_DECIMALS)}
        for f in _read(stage5 / "patches.geojson")["features"]
        if f["properties"]["category"] == "suspect"
    ]
    _write_json(web_data / areas, {"type": "FeatureCollection", "features": features})
    extras = {}
    for name in ("routes", "obstructions"):
        # Prefer the 30 m street-level routes when Stage 6 has run
        source = stage6 / f"{name}.geojson" if (stage6 / f"{name}.geojson").exists() else stage5 / f"{name}.geojson"
        if source.exists():
            extras[name] = f"{slug}/{name}.geojson"
            _write_json(web_data / extras[name], _rank_features(_read(source)))
    return {"counts": summary["categories"], "list": listed, "areas": areas, **extras}


def _rank_features(collection: dict[str, Any]) -> dict[str, Any]:
    """Keep only the rank property and round coordinates."""
    return {"type": "FeatureCollection", "features": [
        {"type": "Feature", "properties": {"rank": f["properties"]["rank"]},
         "geometry": round_coordinates(f["geometry"], COORD_DECIMALS)}
        for f in collection["features"]
    ]}


def _view3d_entry(stage7: Path, slug: str, web_data: Path) -> dict[str, Any]:
    summary = _read(stage7 / "summary.json")
    terrain, buildings = web_data / slug / "terrain3d", web_data / slug / "buildings3d"
    for source, target in ((stage7 / "terrain", terrain), (stage7 / "buildings", buildings)):
        if target.exists():
            shutil.rmtree(target)
        shutil.copytree(source, target)
    low, high = summary["terrain_zooms"]
    return {"terrain": f"{slug}/terrain3d/{{z}}/{{x}}/{{y}}.png", "minzoom": low, "maxzoom": high,
            "bounds": summary["terrain_bounds"], "buildings": f"{slug}/buildings3d"}


def _publish_landmarks(lga_dir: Path, slug: str, web_data: Path) -> tuple[list[dict[str, Any]], str | None]:
    """Compact [[lat, lon, kind, name], ...] for the map; also returns the parsed list."""
    cache = lga_dir / "osm_landmarks.json"
    if not cache.exists():
        return [], None
    landmarks = parse_landmarks(_read(cache))
    path = f"{slug}/landmarks.json"
    _write_json(web_data / path, [[round(m["lat"], COORD_DECIMALS), round(m["lon"], COORD_DECIMALS), m["kind"], m["name"]]
                                  for m in landmarks])
    return landmarks, path


def _add_nearby(path: Path, landmarks: list[dict[str, Any]]) -> None:
    """Rewrite a published hotspot list with a 'nearby' landmark line on each entry that has one."""
    rows = []
    for row in _read(path):
        line = describe_nearby(nearby_landmarks(row["lat"], row["lon"], landmarks, NEARBY_MAX_M, NEARBY_LIMIT))
        rows.append({**row, "nearby": line} if line else row)
    _write_json(path, rows)


def _hotspot_files(entry: dict[str, Any]) -> list[str]:
    files = [e["hotspots"] for e in entry["events"]]
    files += [entry[k]["hotspots"] for k in ("frequency", "standing") if entry.get(k)]
    if entry.get("suspects"):
        files.append(entry["suspects"]["list"])
    return files


def build_lga_entry(lga_dir: Path, name: str, web_data: Path) -> dict[str, Any]:
    slug = lga_dir.name
    stage2 = _latest(lga_dir, "stage2_*")
    stage3 = _latest(lga_dir, "stage3_*")
    stage4 = _latest(lga_dir, "stage4_*")
    stage5 = _latest(lga_dir, "stage5_*")
    standing = _latest(lga_dir, "standing_*")
    stage7 = lga_dir / "stage7_3d"
    if stage2 is None and stage3 is None and standing is None:
        raise ValueError(f"No finished outputs in {lga_dir}")

    boundary_source = (stage3 or stage2 or standing) / "lga_boundary.geojson"
    _publish_geojson(boundary_source, web_data / slug / "boundary.geojson")
    entry = {
        "slug": slug,
        "name": DISPLAY_NAMES.get(name, name),
        "boundary": f"{slug}/boundary.geojson",
        "events": [_event_entry(stage2, slug, web_data)] if stage2 else [],
        "frequency": _frequency_entry(stage3, slug, web_data) if stage3 else None,
        "terrain": _terrain_entry(stage4, slug, web_data) if stage4 else None,
        "suspects": _suspects_entry(stage5, slug, web_data, standing) if stage5 else None,
        "standing": _standing_entry(standing, slug, web_data) if standing else None,
        "view3d": _view3d_entry(stage7, slug, web_data) if (stage7 / "summary.json").exists() else None,
    }
    landmarks, landmarks_path = _publish_landmarks(lga_dir, slug, web_data)
    for path in _hotspot_files(entry) if landmarks else []:
        _add_nearby(web_data / path, landmarks)
    return {**entry, "landmarks": landmarks_path}


def write_manifest(entries: list[dict[str, Any]], web_data: Path) -> Path:
    path = web_data / "manifest.json"
    _write_json(path, {"generated": datetime.now(timezone.utc).isoformat(timespec="seconds"), "lgas": entries})
    return path


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    entries = []
    for name in config.LGA_ORDER:
        lga_dir = DATA_DIR / slugify(name)
        if not lga_dir.exists():
            continue
        try:
            entries.append(build_lga_entry(lga_dir, name, WEB_DATA_DIR))
        except ValueError as exc:
            log.warning("Skipped %s: %s", name, exc)
            continue
        log.info("Published %s", name)
    log.info("Manifest: %s", write_manifest(entries, WEB_DATA_DIR))


if __name__ == "__main__":
    main()
