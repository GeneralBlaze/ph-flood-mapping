import json

import pytest

from analysis.publish import build_lga_entry, round_coordinates, write_manifest


def _write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data) if not isinstance(data, bytes) else "")


@pytest.fixture
def stage2_dir(tmp_path):
    d = tmp_path / "data" / "obio-akpor" / "stage2_2026-09-29-o22_2026-09-29-o30"
    _write(d / "summary.json", {"lga": "Obio/Akpor", "flooded_ha": 1118.4,
                                "passes": [{"date": "2026-09-29", "orbit": 22}, {"date": "2026-09-29", "orbit": 30}]})
    _write(d / "flood_overlay.bounds.json", [[4.7, 6.9], [4.95, 7.1]])
    (d / "flood_overlay.png").write_bytes(b"png")
    _write(d / "lga_boundary.geojson", {"type": "FeatureCollection", "features": []})
    _write(d / "flood_clusters.json", [{"area_ha": 10.0, "lat": 4.9, "lon": 7.0, "place": "Eneka", "address": {"x": 1}}])
    return d


def test_round_coordinates_trims_precision_without_mutating():
    geometry = {"type": "Polygon", "coordinates": [[[7.123456789, 4.987654321], [7.1, 4.9]]]}

    rounded = round_coordinates(geometry, 5)

    assert rounded["coordinates"][0][0] == [7.12346, 4.98765]
    assert geometry["coordinates"][0][0][0] == 7.123456789


def test_entry_includes_event_and_skips_missing_stage3(stage2_dir, tmp_path):
    web_data = tmp_path / "web" / "data"

    entry = build_lga_entry(stage2_dir.parent, "Obio/Akpor", web_data)

    assert entry["slug"] == "obio-akpor"
    assert entry["frequency"] is None
    assert entry["events"][0]["date"] == "2026-09-29"
    assert entry["events"][0]["flooded_ha"] == 1118.4
    assert (web_data / entry["events"][0]["overlay"]).exists()


def test_hotspots_are_stripped_to_public_fields(stage2_dir, tmp_path):
    web_data = tmp_path / "web" / "data"

    entry = build_lga_entry(stage2_dir.parent, "Obio/Akpor", web_data)
    hotspots = json.loads((web_data / entry["events"][0]["hotspots"]).read_text())

    assert hotspots == [{"rank": 1, "area_ha": 10.0, "lat": 4.9, "lon": 7.0, "place": "Eneka"}]


def test_manifest_lists_entries(tmp_path):
    path = write_manifest([{"slug": "obio-akpor"}], tmp_path)

    manifest = json.loads(path.read_text())
    assert manifest["lgas"][0]["slug"] == "obio-akpor"
    assert "generated" in manifest


def test_entry_includes_terrain_when_stage4_exists(stage2_dir, tmp_path):
    # Arrange
    stage4 = stage2_dir.parent / "stage4_terrain"
    _write(stage4 / "summary.json", {"channel_upa_km2": 1.0})
    _write(stage4 / "hand_overlay.bounds.json", [[4.7, 6.9], [4.95, 7.1]])
    (stage4 / "hand_overlay.png").write_bytes(b"png")
    _write(stage4 / "drainage_network.geojson", {"type": "FeatureCollection", "features": [
        {"type": "Feature", "properties": {"label": 1},
         "geometry": {"type": "Polygon", "coordinates": [[[7.1234567, 4.8], [7.2, 4.8], [7.2, 4.9], [7.1234567, 4.8]]]}}]})
    web_data = tmp_path / "web" / "data"

    # Act
    entry = build_lga_entry(stage2_dir.parent, "Obio/Akpor", web_data)

    # Assert
    terrain = entry["terrain"]
    assert terrain["channel_upa_km2"] == 1.0
    assert (web_data / terrain["hand_overlay"]).exists()
    network = json.loads((web_data / terrain["drainage"]).read_text())
    assert network["features"][0]["geometry"]["coordinates"][0][0] == [7.12346, 4.8]


def test_entry_terrain_is_none_without_stage4(stage2_dir, tmp_path):
    entry = build_lga_entry(stage2_dir.parent, "Obio/Akpor", tmp_path / "web" / "data")
    assert entry["terrain"] is None


def test_entry_includes_suspects_with_public_fields_only(stage2_dir, tmp_path):
    # Arrange
    stage5 = stage2_dir.parent / "stage5_suspects"
    _write(stage5 / "summary.json", {"categories": {"suspect": 1, "natural": 2, "unclear": 3}})
    _write(stage5 / "suspects.json", [{
        "rank": 1, "kind": "raised_ground", "place": "Oginigba", "area_ha": 3.5, "mean_years": 3.4,
        "anomaly_m": 9.93, "buildings": 30, "built_frac": 1.0, "lat": 4.8, "lon": 7.03,
        "reasons": ["r1"], "crossing_road": None, "score": 33.8, "address": {"secret": "x"}}])
    square = [[[7.0, 4.8], [7.001, 4.8], [7.001, 4.801], [7.0, 4.8]]]
    _write(stage5 / "patches.geojson", {"type": "FeatureCollection", "features": [
        {"type": "Feature", "properties": {"category": "suspect", "rank": 1}, "geometry": {"type": "Polygon", "coordinates": square}},
        {"type": "Feature", "properties": {"category": "natural", "rank": None}, "geometry": {"type": "Polygon", "coordinates": square}},
    ]})
    web_data = tmp_path / "web" / "data"

    # Act
    entry = build_lga_entry(stage2_dir.parent, "Obio/Akpor", web_data)

    # Assert
    suspects = entry["suspects"]
    assert suspects["counts"] == {"suspect": 1, "natural": 2, "unclear": 3}
    listed = json.loads((web_data / suspects["list"]).read_text())
    assert "address" not in listed[0] and "score" not in listed[0]
    assert listed[0]["anomaly_m"] == 9.9
    areas = json.loads((web_data / suspects["areas"]).read_text())
    assert [f["properties"] for f in areas["features"]] == [{"rank": 1}]


def test_compact_flow_rows():
    from analysis.publish import compact_flow

    collection = {"features": [{"properties": {"upa_km2": 2.345},
                                "geometry": {"coordinates": [[7.1234567, 4.8], [7.124, 4.7991666]]}}]}

    assert compact_flow(collection) == [[7.12346, 4.8, 7.124, 4.79917, 2.3]]


def test_suspects_entry_publishes_routes_and_obstructions(stage2_dir, tmp_path):
    stage5 = stage2_dir.parent / "stage5_suspects"
    _write(stage5 / "summary.json", {"categories": {"suspect": 1, "natural": 0, "unclear": 0}})
    _write(stage5 / "suspects.json", [])
    _write(stage5 / "patches.geojson", {"type": "FeatureCollection", "features": []})
    line = {"type": "LineString", "coordinates": [[7.1234567, 4.8], [7.124, 4.801]]}
    _write(stage5 / "routes.geojson", {"type": "FeatureCollection", "features": [
        {"type": "Feature", "properties": {"rank": 1}, "geometry": line}]})
    _write(stage5 / "obstructions.geojson", {"type": "FeatureCollection", "features": []})
    web_data = tmp_path / "web" / "data"

    entry = build_lga_entry(stage2_dir.parent, "Obio/Akpor", web_data)

    routes = json.loads((web_data / entry["suspects"]["routes"]).read_text())
    assert routes["features"][0]["properties"] == {"rank": 1}
    assert routes["features"][0]["geometry"]["coordinates"][0] == [7.12346, 4.8]
    assert (web_data / entry["suspects"]["obstructions"]).exists()


@pytest.fixture
def standing_dir(tmp_path):
    d = tmp_path / "data" / "ikwerre" / "standing_2026-09-29_2026-10-05-o22"
    _write(d / "summary.json", {"lga": "Ikwerre", "before": {"date": "2026-09-29", "orbit": 22},
                                "after": {"date": "2026-10-05", "orbit": 22},
                                "hectares": {"drained": 10.0, "standing": 40.0, "new": 5.0}})
    _write(d / "standing_overlay.bounds.json", [[4.9, 6.8], [5.1, 7.0]])
    (d / "standing_overlay.png").write_bytes(b"png")
    _write(d / "lga_boundary.geojson", {"type": "FeatureCollection", "features": []})
    _write(d / "standing_clusters.json", [{"area_ha": 8.0, "lat": 5.0, "lon": 6.9, "place": "Isiokpo", "address": {}}])
    return d


def test_standing_only_lga_gets_entry_with_dates_and_hectares(standing_dir, tmp_path):
    web_data = tmp_path / "web" / "data"

    entry = build_lga_entry(standing_dir.parent, "Ikwerre", web_data)

    standing = entry["standing"]
    assert (standing["before"], standing["after"]) == ("2026-09-29", "2026-10-05")
    assert standing["hectares"]["standing"] == 40.0
    assert (web_data / standing["overlay"]).exists()
    assert json.loads((web_data / standing["hotspots"]).read_text())[0]["place"] == "Isiokpo"
    assert entry["events"] == [] and entry["suspects"] is None


def test_site_status_is_merged_into_suspects():
    from analysis.publish import merge_site_status

    suspects = [{"rank": 1, "place": "A"}, {"rank": 2, "place": "B"}]
    statuses = [{"rank": 2, "status": "standing", "after_frac": 0.3, "before_frac": 0.0}]

    merged = merge_site_status(suspects, statuses)

    assert merged == [{"rank": 1, "place": "A", "water_now": None}, {"rank": 2, "place": "B", "water_now": "standing"}]
    assert "water_now" not in suspects[0]


def test_landmarks_are_published_and_hotspots_get_nearby_line(stage2_dir, tmp_path):
    payload = {"elements": [{"type": "node", "lat": 4.9009, "lon": 7.0, "tags": {"name": "Eneka Market", "amenity": "marketplace"}}]}
    _write(stage2_dir.parent / "osm_landmarks.json", payload)
    web_data = tmp_path / "web" / "data"

    entry = build_lga_entry(stage2_dir.parent, "Obio/Akpor", web_data)

    assert json.loads((web_data / entry["landmarks"]).read_text()) == [[4.9009, 7.0, "market", "Eneka Market"]]
    hotspot = json.loads((web_data / entry["events"][0]["hotspots"]).read_text())[0]
    assert hotspot["nearby"] == "Eneka Market, 100 m north"


def test_apply_stories_adds_story_and_replaces_old_route_reason():
    from analysis.publish import apply_stories

    suspects = [{"rank": 1, "reasons": ["Flooded in 4 of 6 seasons",
                                        "62 buildings stand on or beside the route water should take from here",
                                        "Built-up land (buildings, roads, paving): 80%"], "path_buildings": 62},
                {"rank": 2, "reasons": ["x"], "path_buildings": None}]
    stories = [{"rank": 1, "story": ["Line one.", "Line two."], "buildings_by_street": {"A": 3, "None": 2}}]

    out = apply_stories(suspects, stories)

    assert out[0]["story"] == ["Line one.", "Line two."]
    assert out[0]["reasons"] == ["Flooded in 4 of 6 seasons", "Built-up land (buildings, roads, paving): 80%"]
    assert out[0]["path_buildings"] == 5
    assert out[1] == {"rank": 2, "reasons": ["x"], "path_buildings": None, "story": None}
    assert suspects[0]["path_buildings"] == 62


def test_view3d_entry_copies_tiles_and_buildings(stage2_dir, tmp_path):
    d = stage2_dir.parent / "stage7_3d"
    _write(d / "summary.json", {"terrain_zooms": [11, 13], "terrain_bounds": [6.9, 4.7, 7.1, 4.9]})
    (d / "terrain" / "13" / "4300").mkdir(parents=True)
    (d / "terrain" / "13" / "4300" / "4000.png").write_bytes(b"png")
    _write(d / "buildings" / "1.geojson", {"type": "FeatureCollection", "features": []})
    web_data = tmp_path / "web" / "data"

    entry = build_lga_entry(stage2_dir.parent, "Obio/Akpor", web_data)

    view = entry["view3d"]
    assert view["terrain"] == "obio-akpor/terrain3d/{z}/{x}/{y}.png"
    assert (view["minzoom"], view["maxzoom"], view["bounds"]) == (11, 13, [6.9, 4.7, 7.1, 4.9])
    assert (web_data / "obio-akpor/terrain3d/13/4300/4000.png").exists()
    assert (web_data / view["buildings"] / "1.geojson").exists()
