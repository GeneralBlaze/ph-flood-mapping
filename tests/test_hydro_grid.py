import numpy as np
import pytest

from analysis.hydro_grid import NODATA_DIR, d8_directions, flow_accumulation, priority_flood, trace

# A 5x5 bowl: a hollow at the centre (1 m) ringed by 3 m ground, with the
# lowest gap in the rim (2 m) on the east side, then falling away to 0 at the edge.
BOWL = np.array([
    [5, 5, 5, 5, 5],
    [5, 3, 3, 3, 5],
    [5, 3, 1, 2, 0],
    [5, 3, 3, 3, 5],
    [5, 5, 5, 5, 5],
], dtype=float)


def test_priority_flood_fills_hollow_to_its_pour_point():
    filled = priority_flood(BOWL, eps=0.001)

    assert filled[2, 2] == pytest.approx(2.0, abs=0.01)  # water rises to the 2 m gap
    assert filled[2, 2] > filled[2, 3]                     # and still drains towards it
    assert filled[0, 0] == 5                               # untouched where already draining
    assert BOWL[2, 2] == 1                                 # input not modified


def test_priority_flood_leaves_nan_cells_as_outlets():
    dem = np.array([[3, 3, 3], [3, 1, np.nan], [3, 3, 3]], dtype=float)
    filled = priority_flood(dem, eps=0.001)

    assert filled[1, 1] == pytest.approx(1.0)  # drains straight into the no-data (sea/river) cell


def test_d8_points_downhill_and_marks_edges_as_outlets():
    dirs = d8_directions(priority_flood(BOWL, eps=0.001), dx=30, dy=30)

    assert tuple(dirs[2, 2]) == (0, 1)     # centre flows east, towards the gap
    assert tuple(dirs[2, 3]) == (0, 1)     # gap flows east to the edge
    assert tuple(dirs[2, 4]) == NODATA_DIR  # edge cell: leaves the grid


def test_flow_accumulation_counts_upstream_cells():
    dem = np.array([[3, 2, 1, 0]], dtype=float)  # a 1-row slope to the east
    dirs = d8_directions(priority_flood(dem, eps=0.001), dx=30, dy=30)

    assert list(flow_accumulation(dirs)[0]) == [1, 2, 3, 4]


def test_trace_follows_directions_until_accumulation_threshold():
    dem = np.array([[3, 2, 1, 0]], dtype=float)
    dirs = d8_directions(priority_flood(dem, eps=0.001), dx=30, dy=30)
    acc = flow_accumulation(dirs)

    assert trace(dirs, acc, (0, 0), stop_cells=3, max_steps=10) == [(0, 0), (0, 1), (0, 2)]
    assert trace(dirs, acc, (0, 0), stop_cells=99, max_steps=10) == [(0, 0), (0, 1), (0, 2), (0, 3)]
    assert len(trace(dirs, acc, (0, 0), stop_cells=99, max_steps=1)) == 2
