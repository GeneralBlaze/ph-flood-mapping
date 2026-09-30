import pytest

from analysis.flowpaths import PIXEL_DEG, flow_segments


def test_east_flow_points_one_pixel_east():
    segments = flow_segments([(7.0, 4.8, 1, 2.5)])

    (start, end), = [s["coords"] for s in segments]
    assert start == (7.0, 4.8)
    assert end == pytest.approx((7.0 + PIXEL_DEG, 4.8))
    assert segments[0]["bearing"] == pytest.approx(90)
    assert segments[0]["upa_km2"] == 2.5


@pytest.mark.parametrize(
    ("code", "bearing"),
    [(1, 90), (2, 135), (4, 180), (8, 225), (16, 270), (32, 315), (64, 0), (128, 45)],
)
def test_all_d8_codes_map_to_compass_bearings(code, bearing):
    assert flow_segments([(7.0, 4.8, code, 1.0)])[0]["bearing"] == pytest.approx(bearing)


def test_outlets_and_nodata_are_skipped():
    assert flow_segments([(7.0, 4.8, 0, 1.0), (7.0, 4.8, 247, 1.0), (7.0, 4.8, 255, 1.0)]) == []


def _grid(cells):
    """cells: {(kx, ky): (d8, upa)} keyed by pixel index."""
    return cells


def test_trace_follows_directions_until_a_channel():
    from analysis.flowpaths import pixel_key, trace_downstream

    kx, ky = pixel_key(7.0, 4.8)
    grid = _grid({
        (kx, ky): (1, 0.1),          # east
        (kx + 1, ky): (4, 0.3),      # south
        (kx + 1, ky - 1): (4, 5.0),  # channel reached (>= 1 km2)
    })

    route = trace_downstream(7.0, 4.8, grid, stop_upa_km2=1.0, max_steps=50)

    assert len(route) == 3
    assert route[-1] == pytest.approx(((kx + 1) * PIXEL_DEG, (ky - 1) * PIXEL_DEG))


def test_trace_stops_at_grid_edge_and_loops():
    from analysis.flowpaths import pixel_key, trace_downstream

    kx, ky = pixel_key(7.0, 4.8)
    loop = {(kx, ky): (1, 0.1), (kx + 1, ky): (16, 0.1)}  # east then back west

    assert len(trace_downstream(7.0, 4.8, loop, stop_upa_km2=1.0, max_steps=50)) == 2
    assert len(trace_downstream(7.0, 4.8, {}, stop_upa_km2=1.0, max_steps=50)) == 1
