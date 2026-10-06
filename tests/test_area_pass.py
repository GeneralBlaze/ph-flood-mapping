import math

import numpy as np
import pytest
from shapely.geometry import shape

from analysis.area_pass import hollow_sites, parse_routed, parse_sites
from analysis.area_request import AreaError

PIXEL = 1 / 3600
SQUARE = [[4.80, 7.00], [4.80, 7.01], [4.81, 7.01], [4.81, 7.00]]


def grid_over_square(dem: np.ndarray) -> dict:
    # top-left of the grid at the square's north-west corner
    return {"dem": dem, "west": 7.00, "north": 4.81}


def test_hollow_sites_finds_the_deepest_hollow_inside_the_area():
    dem = np.full((36, 36), 10.0)
    dem[10:13, 10:13] = 9.0           # 3x3 hollow, 1 m deep
    dem[20, 20] = 9.9                 # 0.1 m dip: too shallow
    filled = dem.copy()
    filled[10:13, 10:13] = 10.0
    filled[20, 20] = 10.0

    sites = hollow_sites(grid_over_square(dem), filled, SQUARE, min_depth=0.3, limit=3)

    assert len(sites) == 1
    polygon = shape(sites[0]["geometry"])
    assert polygon.contains(shape({"type": "Point", "coordinates": [7.00 + 11.5 * PIXEL, 4.81 - 11.5 * PIXEL]}))
    assert sites[0]["max_depth_m"] == 1.0
    assert sites[0]["area_ha"] == pytest.approx(9 * 30.9 * 30.7 / 1e4, rel=0.05)


def test_hollow_sites_ignores_hollows_outside_the_drawn_area():
    dem = np.full((60, 60), 10.0)
    dem[50:53, 50:53] = 9.0           # beyond 0.01 degrees (36 cells) from the corner
    filled = np.full_like(dem, 10.0)
    assert hollow_sites(grid_over_square(dem), filled, SQUARE, min_depth=0.3, limit=3) == []


def site(lon=7.005, lat=4.805, d=0.0005):
    return {"geometry": {"type": "Polygon", "coordinates": [[[lon, lat], [lon + d, lat], [lon + d, lat + d],
                                                              [lon, lat + d], [lon, lat]]]}}


def test_parse_sites_accepts_up_to_five_polygons_near_the_area():
    polygons = parse_sites([site(), site(7.007)], SQUARE)
    assert len(polygons) == 2
    assert math.isclose(polygons[0].area, 0.0005 ** 2)


@pytest.mark.parametrize("sites, message", [
    ("nope", "sites"),
    ([site()] * 6, "sites"),
    ([{"geometry": {"type": "Point", "coordinates": [7.0, 4.8]}}], "polygon"),
    ([site(lon=7.5)], "outside"),
    ([{"geometry": {"type": "Polygon", "coordinates": [[[7.0, 4.8]] * 3000]}}], "too detailed"),
])
def test_parse_sites_rejects_bad_input(sites, message):
    with pytest.raises(AreaError, match=message):
        parse_sites(sites, SQUARE)


def test_parse_routed_checks_route_points_and_numbers():
    routed = parse_routed([{"route": [[7.005, 4.805], [7.006, 4.804]], "rise_m": 1.2,
                            "barrier": [7.006, 4.804], "ground": 12.0, "centres": [[7.0055, 4.8045]]}], SQUARE)
    assert routed[0]["route"] == [(7.005, 4.805), (7.006, 4.804)]
    assert routed[0]["barrier"] == (7.006, 4.804)
    assert routed[0]["centres"] == [(7.0055, 4.8045)]

    with pytest.raises(AreaError):
        parse_routed([{"route": [[7.9, 4.8]], "rise_m": 0, "barrier": None, "ground": 1, "centres": []}], SQUARE)
    with pytest.raises(AreaError):
        parse_routed([{"route": [], "rise_m": "x", "barrier": None, "ground": 1, "centres": []}], SQUARE)


def test_merge_patches_joins_overlapping_patches_and_keeps_the_largest():
    from analysis.area_pass import merge_patches

    recurrent = [site(7.001, 4.801, 0.002), site(7.008, 4.808, 0.0005)]
    latest = [site(7.002, 4.802, 0.002), site(7.005, 4.805, 0.001)]   # first overlaps recurrent[0]

    merged = merge_patches(recurrent, latest, limit=2)

    assert len(merged) == 2
    assert merged[0]["recurrent"] and merged[0]["latest"]               # the joined patch, largest
    assert merged[1]["latest"] and not merged[1]["recurrent"]
    assert merged[0]["area_ha"] > merged[1]["area_ha"] > 0
    assert merged[0]["kind"] == "flood"


def test_parse_sites_repairs_a_self_intersecting_outline():
    bowtie = {"geometry": {"type": "Polygon", "coordinates": [[[7.001, 4.801], [7.003, 4.803], [7.003, 4.801],
                                                                [7.001, 4.803], [7.001, 4.801]]]}}
    polygons = parse_sites([bowtie], SQUARE)
    assert polygons[0].is_valid and polygons[0].area > 0


def test_parse_sites_rejects_malformed_coordinates():
    with pytest.raises(AreaError):
        parse_sites([{"geometry": {"type": "Polygon", "coordinates": [[["a", "b"]]]}}], SQUARE)
