import pytest
from shapely.geometry import Polygon

from analysis.crossings import crossing_points, nearest_distance_m, parse_roads

# A channel strip running north–south at lon 7.000–7.001
CHANNEL = Polygon([(7.000, 4.80), (7.001, 4.80), (7.001, 4.82), (7.000, 4.82)])


def test_parse_roads_keeps_ways_with_geometry():
    payload = {
        "elements": [
            {"type": "way", "tags": {"highway": "primary", "name": "Ikwerre Road"},
             "geometry": [{"lat": 4.81, "lon": 6.99}, {"lat": 4.81, "lon": 7.01}]},
            {"type": "way", "tags": {"highway": "residential"}, "geometry": [{"lat": 4.8, "lon": 7.0}]},
            {"type": "node", "lat": 4.8, "lon": 7.0},
        ]
    }

    roads = parse_roads(payload)

    assert len(roads) == 1
    assert roads[0]["name"] == "Ikwerre Road"
    assert roads[0]["line"].length > 0


def test_road_across_channel_gives_one_crossing():
    roads = parse_roads({"elements": [
        {"type": "way", "tags": {"highway": "tertiary"},
         "geometry": [{"lat": 4.81, "lon": 6.99}, {"lat": 4.81, "lon": 7.01}]}]})

    points = crossing_points(roads, [CHANNEL])

    assert len(points) == 1
    assert points[0]["point"].x == pytest.approx(7.0005, abs=1e-4)


def test_road_beside_channel_gives_no_crossing():
    roads = parse_roads({"elements": [
        {"type": "way", "tags": {"highway": "tertiary"},
         "geometry": [{"lat": 4.80, "lon": 7.01}, {"lat": 4.82, "lon": 7.01}]}]})

    assert crossing_points(roads, [CHANNEL]) == []


def test_nearest_distance_in_metres():
    # ~0.001 degrees of longitude at 4.8 N is ~111 m
    target = Polygon([(7.002, 4.81), (7.003, 4.81), (7.003, 4.811), (7.002, 4.811)])
    points = [{"point": CHANNEL.centroid, "road": "x"}]

    distance, _ = nearest_distance_m(target, points)

    assert distance == pytest.approx(166, rel=0.1)


def test_nearest_distance_none_without_points():
    assert nearest_distance_m(CHANNEL, []) == (None, None)


def test_only_major_roads_are_kept_for_crossings():
    from analysis.crossings import major_roads

    roads = parse_roads({"elements": [
        {"type": "way", "tags": {"highway": "residential"}, "geometry": [{"lat": 4.81, "lon": 6.99}, {"lat": 4.81, "lon": 7.01}]},
        {"type": "way", "tags": {"highway": "secondary"}, "geometry": [{"lat": 4.81, "lon": 6.99}, {"lat": 4.81, "lon": 7.01}]},
    ]})

    assert [r["highway"] for r in major_roads(roads)] == ["secondary"]


def test_parse_aeroways_keeps_lines_and_areas():
    from analysis.crossings import parse_aeroways

    payload = {"elements": [
        {"type": "way", "tags": {"aeroway": "runway"}, "geometry": [{"lat": 4.84, "lon": 7.01}, {"lat": 4.83, "lon": 7.02}]},
        {"type": "way", "tags": {"aeroway": "apron"},
         "geometry": [{"lat": 4.8, "lon": 7.0}, {"lat": 4.8, "lon": 7.001}, {"lat": 4.801, "lon": 7.001}, {"lat": 4.8, "lon": 7.0}]},
        {"type": "node", "tags": {"aeroway": "windsock"}, "lat": 4.8, "lon": 7.0},
    ]}

    shapes = parse_aeroways(payload)

    assert [s.geom_type for s in shapes] == ["LineString", "Polygon"]
