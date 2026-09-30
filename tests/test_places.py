import pytest

from analysis.places import parse_overpass_places, rank_places


def test_parse_keeps_named_nodes_only():
    # Arrange
    payload = {
        "elements": [
            {"type": "node", "lat": 4.85, "lon": 6.99, "tags": {"name": "Rumuokoro", "place": "suburb"}},
            {"type": "node", "lat": 4.80, "lon": 7.00, "tags": {"place": "hamlet"}},
            {"type": "way", "tags": {"name": "Ikwerre Road"}},
        ]
    }

    # Act
    places = parse_overpass_places(payload)

    # Assert
    assert places == [{"name": "Rumuokoro", "place": "suburb", "lat": 4.85, "lon": 6.99}]


def test_parse_drops_duplicate_names():
    payload = {
        "elements": [
            {"type": "node", "lat": 4.85, "lon": 6.99, "tags": {"name": "Woji", "place": "village"}},
            {"type": "node", "lat": 4.86, "lon": 6.98, "tags": {"name": "Woji", "place": "suburb"}},
        ]
    }

    assert len(parse_overpass_places(payload)) == 1


def test_rank_orders_by_flooded_fraction_and_drops_dry():
    rows = [
        {"name": "A", "flooded_ha": 2.0, "area_ha": 100.0},
        {"name": "B", "flooded_ha": 0.0, "area_ha": 100.0},
        {"name": "C", "flooded_ha": 10.0, "area_ha": 100.0},
    ]

    ranked = rank_places(rows, min_flooded_ha=0.5)

    assert [r["name"] for r in ranked] == ["C", "A"]
    assert ranked[0]["flooded_pct"] == pytest.approx(10.0)


def test_rank_does_not_mutate_input():
    rows = [{"name": "A", "flooded_ha": 2.0, "area_ha": 100.0}]

    rank_places(rows, min_flooded_ha=0.5)

    assert "flooded_pct" not in rows[0]


def test_fetch_falls_back_to_next_mirror(monkeypatch):
    # Arrange: first mirror times out, second answers
    from analysis import places

    calls = []

    def fake_post(url, query):
        calls.append(url)
        if len(calls) == 1:
            raise OSError("504 Gateway Timeout")
        return {"elements": [{"type": "node", "lat": 4.8, "lon": 7.0, "tags": {"name": "Eliozu", "place": "suburb"}}]}

    monkeypatch.setattr(places, "_post_overpass", fake_post)

    # Act
    result = places.fetch_places((4.7, 6.9, 4.9, 7.1))

    # Assert
    assert [p["name"] for p in result] == ["Eliozu"]
    assert calls == places.OVERPASS_URLS[:2]


def test_fetch_raises_when_all_mirrors_fail(monkeypatch):
    from analysis import places

    def always_fail(url, query):
        raise OSError("down")

    monkeypatch.setattr(places, "_post_overpass", always_fail)

    with pytest.raises(RuntimeError, match="All Overpass mirrors failed"):
        places.fetch_places((4.7, 6.9, 4.9, 7.1))
