from shapely.geometry import LineString, Polygon

from analysis.obstructions import describe_obstruction, describe_route, nearby_paths

SITE = Polygon([(7.000, 4.800), (7.001, 4.800), (7.001, 4.801), (7.000, 4.801)])


def test_nearby_paths_keeps_only_close_segments():
    close = LineString([(7.0015, 4.8), (7.0015, 4.801)])   # ~55 m east
    far = LineString([(7.02, 4.8), (7.02, 4.801)])        # ~2 km east

    assert nearby_paths(SITE, [close, far], max_m=300) == [close]


def test_describe_obstruction_counts_buildings():
    assert describe_obstruction(12, 300) == "12 buildings stand on or beside the natural drainage path within 300 m"
    assert describe_obstruction(1, 300) == "1 building stands on or beside the natural drainage path within 300 m"
    assert describe_obstruction(0, 300) == "No buildings found on the natural drainage path within 300 m"


def test_describe_obstruction_without_paths():
    assert describe_obstruction(None, 300) is None


def test_describe_route_counts_buildings_and_length():
    assert describe_route(5, 640) == (
        "5 buildings stand on or beside the route water should take from here to the nearest "
        "drainage channel (about 640 m)"
    )
    assert describe_route(0, 180) == (
        "No buildings found on the route water should take from here to the nearest drainage channel (about 180 m)"
    )


def test_as_polygon_list_handles_one_building_or_many():
    from analysis.obstructions import as_polygon_list

    ring = [[7.0, 4.8], [7.001, 4.8], [7.001, 4.801], [7.0, 4.8]]
    assert as_polygon_list([ring]) == [[ring]]            # single Polygon: list of rings
    assert as_polygon_list([[ring], [ring]]) == [[ring], [ring]]  # MultiPolygon: list of polygons
    assert as_polygon_list([]) == []
