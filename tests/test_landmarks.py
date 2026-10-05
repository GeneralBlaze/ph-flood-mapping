import pytest

from analysis.landmarks import compass, describe_nearby, landmark_kind, nearby_landmarks, parse_landmarks


def test_landmark_kind_maps_osm_tags_to_plain_words():
    assert landmark_kind({"amenity": "place_of_worship", "religion": "christian"}) == "church"
    assert landmark_kind({"amenity": "place_of_worship", "religion": "muslim"}) == "mosque"
    assert landmark_kind({"amenity": "marketplace"}) == "market"
    assert landmark_kind({"amenity": "fuel"}) == "filling station"
    assert landmark_kind({"junction": "roundabout"}) == "roundabout"
    assert landmark_kind({"shop": "bakery"}) is None


def test_parse_landmarks_uses_node_position_or_way_centre_and_skips_unnamed():
    payload = {"elements": [
        {"type": "node", "lat": 4.85, "lon": 7.0, "tags": {"name": "Rumuokoro Market", "amenity": "marketplace"}},
        {"type": "way", "center": {"lat": 4.86, "lon": 7.01}, "tags": {"name": "UPTH", "amenity": "hospital"}},
        {"type": "node", "lat": 4.87, "lon": 7.02, "tags": {"amenity": "school"}},
        {"type": "node", "lat": 4.87, "lon": 7.02, "tags": {"name": "Bakery", "shop": "bakery"}},
    ]}

    assert parse_landmarks(payload) == [
        {"name": "Rumuokoro Market", "kind": "market", "lat": 4.85, "lon": 7.0},
        {"name": "UPTH", "kind": "hospital", "lat": 4.86, "lon": 7.01},
    ]


def test_parse_landmarks_drops_duplicate_names_close_together():
    tags = {"name": "Mile 1 Market", "amenity": "marketplace"}
    payload = {"elements": [{"type": "node", "lat": 4.8, "lon": 7.0, "tags": tags},
                            {"type": "node", "lat": 4.8003, "lon": 7.0, "tags": tags}]}

    assert len(parse_landmarks(payload)) == 1


@pytest.mark.parametrize(("dlat", "dlon", "word"), [(1, 0, "north"), (0, 1, "east"), (-1, -1, "south-west")])
def test_compass(dlat, dlon, word):
    assert compass(dlat, dlon) == word


def test_nearby_landmarks_sorted_by_distance_within_radius():
    marks = [
        {"name": "Far School", "kind": "school", "lat": 4.9, "lon": 7.0},
        {"name": "St Mary's", "kind": "church", "lat": 4.8018, "lon": 7.0},   # ~200 m north
        {"name": "Mile 3 Market", "kind": "market", "lat": 4.8, "lon": 7.0009},  # ~100 m east
    ]

    near = nearby_landmarks(4.8, 7.0, marks, max_m=600, limit=3)

    assert [m["name"] for m in near] == ["Mile 3 Market", "St Mary's"]
    assert near[0]["direction"] == "east"
    assert near[1]["distance_m"] == pytest.approx(200, abs=10)


def test_describe_nearby_reads_naturally():
    near = [{"name": "Mile 3 Market", "kind": "market", "distance_m": 104, "direction": "east"},
            {"name": "St Mary's", "kind": "church", "distance_m": 199, "direction": "north"}]

    assert describe_nearby(near) == "Mile 3 Market, 100 m east · St Mary's (church), 200 m north"
    assert describe_nearby([]) is None


def test_landmark_kind_infers_religion_from_name_when_untagged():
    assert landmark_kind({"amenity": "place_of_worship", "name": "Christ Chapel International"}) == "church"
    assert landmark_kind({"amenity": "place_of_worship", "name": "Central Masjid"}) == "mosque"
    assert landmark_kind({"amenity": "place_of_worship", "name": "Winners"}) == "place of worship"


def test_describe_nearby_skips_kind_already_in_name():
    near = [{"name": "Total Filling Station", "kind": "filling station", "distance_m": 210, "direction": "south"}]

    assert describe_nearby(near) == "Total Filling Station, 200 m south"
