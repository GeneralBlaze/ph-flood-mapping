import pytest

from analysis.suspects import classify_patch, rank_suspects


def _stats(**overrides):
    base = {
        "mean_years": 4.0,
        "hand_m": 4.0,
        "hand_fab_m": 5.0,
        "dist_channel_m": 400.0,
        "hollow_m": 0.0,
        "max_upa_km2": 0.5,
        "area_ha": 3.0,
        "buildings": 12,
        "built_frac": 0.6,
    }
    return {**base, **overrides}


def test_raised_ground_is_a_suspect_when_both_models_agree():
    result = classify_patch(_stats(), crossing_dist_m=None)

    assert result["category"] == "suspect"
    assert result["kind"] == "raised_ground"
    assert result["anomaly_m"] == pytest.approx(4.0)
    assert result["score"] == pytest.approx(4.0 * 4.0)
    assert any("4.0 m above" in r for r in result["reasons"])


def test_raised_ground_needs_both_models():
    result = classify_patch(_stats(hand_m=4.0, hand_fab_m=1.5), crossing_dist_m=None)

    assert result["category"] == "unclear"


def test_major_river_is_natural_floodplain():
    result = classify_patch(_stats(max_upa_km2=120.0), crossing_dist_m=50.0)

    assert result["category"] == "natural"
    assert result["score"] == 0


def test_very_low_ground_is_natural_floodplain():
    result = classify_patch(_stats(hand_m=0.4, hand_fab_m=0.6), crossing_dist_m=None)

    assert result["category"] == "natural"


def test_channel_patch_near_road_crossing_is_a_suspect():
    result = classify_patch(_stats(hand_m=1.5, hand_fab_m=2.0, dist_channel_m=60.0), crossing_dist_m=120.0)

    assert result["category"] == "suspect"
    assert result["kind"] == "road_crossing"
    assert any("road crosses" in r for r in result["reasons"])


def test_crossing_too_far_does_not_count():
    result = classify_patch(_stats(hand_m=1.5, hand_fab_m=2.0, dist_channel_m=60.0), crossing_dist_m=900.0)

    assert result["category"] == "unclear"


def test_reasons_mention_buildings_when_present():
    result = classify_patch(_stats(buildings=40), crossing_dist_m=None)

    assert any("40 buildings" in r for r in result["reasons"])


def test_classify_does_not_mutate_input():
    stats = _stats()
    classify_patch(stats, crossing_dist_m=None)
    assert "category" not in stats


def test_rank_orders_suspects_by_score_and_numbers_them():
    patches = [
        {"id": "a", "category": "suspect", "score": 5.0, "area_ha": 1.0},
        {"id": "b", "category": "natural", "score": 0.0, "area_ha": 9.0},
        {"id": "c", "category": "suspect", "score": 9.0, "area_ha": 1.0},
    ]

    ranked = rank_suspects(patches)

    assert [p["id"] for p in ranked] == ["c", "a"]
    assert [p["rank"] for p in ranked] == [1, 2]


def test_mapped_wetland_is_natural_even_when_raised():
    result = classify_patch(_stats(wetland_frac=0.6), crossing_dist_m=None)

    assert result["category"] == "natural"
    assert "wetland" in result["reasons"][0]


def test_built_up_share_is_explained_for_suspects():
    result = classify_patch(_stats(built_frac=0.8), crossing_dist_m=None)

    assert any("paving): 80%" in r for r in result["reasons"])


def test_crossing_must_be_within_150_m():
    result = classify_patch(_stats(hand_m=1.5, hand_fab_m=2.0, dist_channel_m=60.0), crossing_dist_m=200.0)

    assert result["category"] == "unclear"


def test_open_land_is_not_a_drainage_suspect():
    result = classify_patch(_stats(built_frac=0.05), crossing_dist_m=None)

    assert result["category"] == "unclear"
    assert "not built-up" in result["reasons"][0]


def test_patch_too_small_to_measure_is_unclear():
    result = classify_patch(_stats(mean_years=0.4), crossing_dist_m=None)

    assert result["category"] == "unclear"
    assert "too small" in result["reasons"][0]


def test_airfield_paving_is_not_a_suspect():
    result = classify_patch(_stats(on_airfield=True), crossing_dist_m=None)

    assert result["category"] == "unclear"
    assert "runway" in result["reasons"][0]
