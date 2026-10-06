from datetime import datetime, timezone


from analysis.area_radar import (
    hectares_by_value, history_line, latest_line, latest_passes, scene_thresholds, traced_line,
)


def ms(day: str, hour: int = 5) -> int:
    return int(datetime.fromisoformat(day).replace(hour=hour, tzinfo=timezone.utc).timestamp() * 1000)


def test_latest_passes_keeps_the_newest_day_and_other_orbits_on_it():
    rows = [
        [ms("2026-09-29"), 22], [ms("2026-09-29", 17), 30],
        [ms("2026-10-05"), 22], [ms("2026-10-05", 17), 124],
        [ms("2026-10-05", 5), 22],                          # second tile of the same pass
    ]
    assert latest_passes(rows) == [("2026-10-05", 22), ("2026-10-05", 124)]


def test_latest_passes_leaves_out_other_days():
    rows = [[ms("2026-10-04", 17), 30], [ms("2026-10-05"), 22], [ms("2026-09-20"), 124]]
    assert latest_passes(rows) == [("2026-10-05", 22)]


def test_latest_passes_with_no_scenes():
    assert latest_passes([]) == []


def test_hectares_by_value_converts_pixel_counts():
    # 10 m pixels: 100 pixels = 1 ha; frequencyHistogram keys arrive as strings
    assert hectares_by_value({"0": 5000, "1": 250, "3": 120.5, "null": 4}, cell_m=10) == {0: 50.0, 1: 2.5, 3: 1.2}


def test_history_line_published_and_estimate():
    assert history_line(120, 6.4, "published", "2021–2026") == (
        "Radar flood history 2021–2026: 6.4 ha (5% of the area) flooded in 3 or more rainy seasons.")
    assert history_line(80, 0, "estimate", "2021–2026") == (
        "Radar flood history 2021–2026 (thresholds set for this area): no ground flooded in 3 or more rainy seasons.")
    assert "under 0.1 ha" in history_line(50, 0.04, "published", "2021–2026")


def test_latest_line():
    assert latest_line({"date": "2026-10-05", "flooded_ha": 3.2}) == "Latest radar pass, 5 Oct 2026: 3.2 ha under water."
    assert latest_line({"date": "2026-10-05", "flooded_ha": 0}) == "Latest radar pass, 5 Oct 2026: no flooding seen."
    assert latest_line(None) == "No radar pass over the area in the last 3 weeks."


def test_traced_line():
    assert traced_line(2, "flood") == "2 flooded patches inside the area are traced."
    assert traced_line(1, "flood") == "1 flooded patch inside the area is traced."
    assert traced_line(1, "hollow") == (
        "No flooded patch large enough to trace; the deepest hollow in the ground is traced instead.")
    assert traced_line(3, "hollow").startswith("No flooded patch large enough to trace; the deepest 3 hollows")
    assert traced_line(0, "hollow").startswith("Nothing large enough to trace")


def test_scene_thresholds_skips_empty_scenes_and_caps():
    bimodal = {"histogram": [10, 50, 10, 0, 0, 10, 50, 10], "bucketMeans": [-24, -23, -22, -21, -20, -19, -18, -17]}
    found = scene_thresholds([bimodal, None, {"histogram": []}])
    assert -22 < found[0] < -19
    assert found[1:] == [None, None]
    assert scene_thresholds([bimodal], cap=-21.5) == [-21.5]
