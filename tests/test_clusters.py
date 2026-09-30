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
