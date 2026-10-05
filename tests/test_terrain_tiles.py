import struct
import zlib

import numpy as np
import pytest

from analysis.terrain_tiles import lonlat_to_tile, png_bytes, terrarium_decode, terrarium_encode, tile_bounds, tiles_covering


def test_tile_round_trip_contains_the_point():
    x, y = lonlat_to_tile(7.0, 4.85, 13)
    west, south, east, north = tile_bounds(x, y, 13)

    assert west <= 7.0 <= east and south <= 4.85 <= north
    assert east - west == pytest.approx(360 / 2 ** 13)


def test_tiles_covering_spans_the_box():
    tiles = tiles_covering((6.95, 4.80, 7.05, 4.90), 13)
    xs, ys = {t[0] for t in tiles}, {t[1] for t in tiles}

    assert len(tiles) == len(xs) * len(ys)
    assert lonlat_to_tile(6.95, 4.90, 13) in tiles and lonlat_to_tile(7.05, 4.80, 13) in tiles


def test_terrarium_encode_round_trips_to_a_tenth_of_a_metre():
    heights = np.array([[0.0, 7.25], [-1.5, 123.4]])

    decoded = terrarium_decode(terrarium_encode(heights))

    assert decoded == pytest.approx(heights, abs=0.06)


def test_terrarium_treats_nan_as_sea_level():
    assert terrarium_decode(terrarium_encode(np.array([[np.nan]])))[0, 0] == pytest.approx(0.0, abs=0.01)


def test_png_bytes_is_a_valid_rgb_png():
    rgb = np.zeros((4, 3, 3), dtype=np.uint8)
    rgb[0, 0] = (255, 0, 0)

    data = png_bytes(rgb)

    assert data[:8] == b"\x89PNG\r\n\x1a\n"
    width, height, depth, colour = struct.unpack(">IIBB", data[16:26])
    assert (width, height, depth, colour) == (3, 4, 8, 2)
    idat = data[data.index(b"IDAT") + 4: data.index(b"IEND") - 8]
    raw = zlib.decompress(idat)
    assert raw[:4] == b"\x00\xff\x00\x00"  # filter byte 0, then the red pixel


def test_fill_gaps_uses_surrounding_ground_not_sea_level():
    from analysis.terrain_tiles import fill_gaps

    dem = np.array([[30.0, 30.0, 30.0], [30.0, np.nan, 31.0], [np.nan, np.nan, 32.0]])

    filled = fill_gaps(dem)

    assert not np.isnan(filled).any()
    assert 29.5 <= filled[1, 1] <= 31.5
    assert filled[2, 0] >= 29.5
    assert np.isnan(dem[1, 1])  # input untouched


def test_sample_tile_extends_edge_heights_outside_the_grid():
    from analysis.terrain_tiles import sample_tile, tile_bounds

    west, south, east, north = tile_bounds(4250, 4000, 13)
    grid = {"dem": np.full((4, 4), 25.0), "west": west, "north": north}  # covers only the tile's corner

    heights = sample_tile(grid, 1 / 3600, 4250, 4000, 13)

    assert heights.min() == pytest.approx(25.0)
