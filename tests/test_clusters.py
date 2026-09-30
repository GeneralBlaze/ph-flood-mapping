import pytest

from analysis.clusters import describe_address, polygon_area_ha, polygon_centroid, top_clusters

# ~100 m square near Port Harcourt (1 degree lat ~ 110.6 km, lon ~ 110.9 km at 4.8 N)
SQUARE = [[7.0, 4.8], [7.0009, 4.8], [7.0009, 4.8009], [7.0, 4.8009], [7.0, 4.8]]


def _feature(ring):
    return {"type": "Feature", "properties": {}, "geometry": {"type": "Polygon", "coordinates": [ring]}}


def test_area_of_100m_square_is_about_one_hectare():
    assert polygon_area_ha(SQUARE) == pytest.approx(1.0, rel=0.03)


def test_centroid_of_square_is_its_middle():
    lon, lat = polygon_centroid(SQUARE)
    assert lon == pytest.approx(7.00045)
    assert lat == pytest.approx(4.80045)


def test_top_clusters_keeps_largest_first():
    small = [[7.1, 4.8], [7.1003, 4.8], [7.1003, 4.8003], [7.1, 4.8003], [7.1, 4.8]]
    collection = {"features": [_feature(small), _feature(SQUARE)]}

    clusters = top_clusters(collection, limit=1)

    assert len(clusters) == 1
    assert clusters[0]["area_ha"] == pytest.approx(1.0, rel=0.03)


def test_top_clusters_ignores_non_polygons():
    collection = {"features": [{"geometry": {"type": "Point", "coordinates": [7, 4.8]}}]}
    assert top_clusters(collection, limit=5) == []


def test_describe_address_prefers_neighbourhood_then_suburb():
    address = {"neighbourhood": "Rumuokoro", "suburb": "Obio/Akpor", "road": "Ikwerre Road"}
    assert describe_address(address) == "Rumuokoro (Ikwerre Road)"


def test_describe_address_falls_back_to_road_or_unknown():
    assert describe_address({"road": "East-West Road"}) == "East-West Road"
    assert describe_address({}) == "unnamed area"


def test_nearest_place_labels_unnamed_area():
    from analysis.clusters import nearest_place_label

    places = [
        {"name": "Far Village", "lat": 4.95, "lon": 7.10},
        {"name": "Rumuokwuta", "lat": 4.8605, "lon": 6.9905},
    ]

    assert nearest_place_label(4.8600, 6.9900, places, max_m=2000) == "near Rumuokwuta"


def test_nearest_place_label_none_when_too_far():
    from analysis.clusters import nearest_place_label

    assert nearest_place_label(4.86, 6.99, [{"name": "Far", "lat": 4.99, "lon": 7.2}], max_m=2000) is None


def test_site_label_prefers_nearest_road_when_no_place():
    from shapely.geometry import LineString

    from analysis.clusters import site_label

    roads = [{"name": "Trans Woji Road", "line": LineString([(7.0, 4.8), (7.01, 4.8)])},
             {"name": None, "line": LineString([(7.0, 4.8001), (7.01, 4.8001)])}]

    assert site_label({}, 4.8005, 7.005, places=[], roads=roads) == "Off Trans Woji Road"


def test_site_label_falls_back_to_coordinates():
    from analysis.clusters import site_label

    assert site_label({}, 4.81234, 7.04567, places=[], roads=[]) == "Site at 4.812, 7.046"


def test_site_label_uses_address_first():
    from analysis.clusters import site_label

    assert site_label({"suburb": "Woji"}, 4.8, 7.0, places=[{"name": "X", "lat": 4.8, "lon": 7.0}], roads=[]) == "Woji"
