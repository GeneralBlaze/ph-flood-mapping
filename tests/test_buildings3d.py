import pytest
from shapely.geometry import LineString

from analysis.buildings3d import DEFAULT_HEIGHT_M, building_feature

SQUARE = [[[7.0, 4.8], [7.0001, 4.8], [7.0001, 4.8001], [7.0, 4.8001], [7.0, 4.8]]]


def test_building_feature_uses_measured_height_and_rounds_coordinates():
    geometry = {"type": "Polygon", "coordinates": [[[7.0000004, 4.8000004], *SQUARE[0][1:]]]}

    feature = building_feature({"mean": 7.46}, geometry, route_zone=None)

    assert feature["properties"] == {"h": 7.5, "on_route": False}
    assert feature["geometry"]["coordinates"][0][0] == [7.0, 4.8]


@pytest.mark.parametrize("measured", [None, 0.4])
def test_building_feature_falls_back_to_one_storey(measured):
    feature = building_feature({"mean": measured}, {"type": "Polygon", "coordinates": SQUARE}, route_zone=None)

    assert feature["properties"]["h"] == DEFAULT_HEIGHT_M


def test_building_feature_flags_buildings_on_the_route():
    near = LineString([(7.00005, 4.79), (7.00005, 4.81)]).buffer(0.0002)
    far = LineString([(7.1, 4.79), (7.1, 4.81)]).buffer(0.0002)
    geometry = {"type": "Polygon", "coordinates": SQUARE}

    assert building_feature({"mean": 5}, geometry, route_zone=near)["properties"]["on_route"] is True
    assert building_feature({"mean": 5}, geometry, route_zone=far)["properties"]["on_route"] is False
