"""Terrain tiles for the 3D view, made from our own 30 m FABDEM grid.

Writes standard XYZ tiles in Terrarium encoding (height = R*256 + G + B/256 - 32768),
which MapLibre reads as a raster-dem source. Plain numpy + zlib: no imaging library.
Heights are rounded to 0.1 m, which keeps tiles small and is finer than the data.
"""

import math
import struct
import zlib
from pathlib import Path

import numpy as np

TILE_PX = 256
OFFSET_M = 32768.0
HEIGHT_STEP_M = 0.1


def lonlat_to_tile(lon: float, lat: float, zoom: int) -> tuple[int, int]:
    n = 2 ** zoom
    x = int((lon + 180.0) / 360.0 * n)
    y = int((1.0 - math.asinh(math.tan(math.radians(lat))) / math.pi) / 2.0 * n)
    return x, y


def _tile_lat(y: float, zoom: int) -> float:
    return math.degrees(math.atan(math.sinh(math.pi * (1 - 2 * y / 2 ** zoom))))


def tile_bounds(x: int, y: int, zoom: int) -> tuple[float, float, float, float]:
    """(west, south, east, north) of a tile."""
    n = 2 ** zoom
    return x / n * 360.0 - 180.0, _tile_lat(y + 1, zoom), (x + 1) / n * 360.0 - 180.0, _tile_lat(y, zoom)


def tiles_covering(box: tuple[float, float, float, float], zoom: int) -> list[tuple[int, int]]:
    """Tiles covering (west, south, east, north)."""
    west, south, east, north = box
    x0, y0 = lonlat_to_tile(west, north, zoom)
    x1, y1 = lonlat_to_tile(east, south, zoom)
    return [(x, y) for x in range(x0, x1 + 1) for y in range(y0, y1 + 1)]


def terrarium_encode(heights: np.ndarray) -> np.ndarray:
    """(rows, cols) metres -> (rows, cols, 3) uint8; NaN (open water) becomes 0 m."""
    h = np.round(np.nan_to_num(heights, nan=0.0) / HEIGHT_STEP_M) * HEIGHT_STEP_M + OFFSET_M
    r = np.floor(h / 256.0)
    g = np.floor(h - r * 256.0)
    b = np.round((h - r * 256.0 - g) * 256.0)
    return np.stack([r, g, np.minimum(b, 255)], axis=-1).astype(np.uint8)


def terrarium_decode(rgb: np.ndarray) -> np.ndarray:
    rgb = rgb.astype(float)
    return rgb[..., 0] * 256.0 + rgb[..., 1] + rgb[..., 2] / 256.0 - OFFSET_M


def _chunk(kind: bytes, data: bytes) -> bytes:
    return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)


def png_bytes(rgb: np.ndarray) -> bytes:
    """Minimal 8-bit RGB PNG."""
    height, width = rgb.shape[:2]
    raw = b"".join(b"\x00" + rgb[row].tobytes() for row in range(height))
    header = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    return b"\x89PNG\r\n\x1a\n" + _chunk(b"IHDR", header) + _chunk(b"IDAT", zlib.compress(raw, 9)) + _chunk(b"IEND", b"")


def sample_tile(grid: dict, pixel_deg: float, x: int, y: int, zoom: int) -> np.ndarray:
    """Bilinear heights for each pixel of a tile from a north-up lon/lat grid (NaN and outside -> 0 m)."""
    west, _, east, _ = tile_bounds(x, y, zoom)
    cols = west + (np.arange(TILE_PX) + 0.5) / TILE_PX * (east - west)
    rows = np.array([_tile_lat(y + (i + 0.5) / TILE_PX, zoom) for i in range(TILE_PX)])
    dem = np.nan_to_num(grid["dem"], nan=0.0)
    fc = (cols - grid["west"]) / pixel_deg - 0.5
    fr = (grid["north"] - rows) / pixel_deg - 0.5
    c0 = np.clip(np.floor(fc).astype(int), 0, dem.shape[1] - 2)
    r0 = np.clip(np.floor(fr).astype(int), 0, dem.shape[0] - 2)
    tc = np.clip(fc - c0, 0, 1)[None, :]
    tr = np.clip(fr - r0, 0, 1)[:, None]
    R, C = np.meshgrid(r0, c0, indexing="ij")
    top = dem[R, C] * (1 - tc) + dem[R, C + 1] * tc
    bottom = dem[R + 1, C] * (1 - tc) + dem[R + 1, C + 1] * tc
    heights = top * (1 - tr) + bottom * tr
    outside = (fc[None, :] < 0) | (fc[None, :] > dem.shape[1] - 1) | (fr[:, None] < 0) | (fr[:, None] > dem.shape[0] - 1)
    return np.where(outside, 0.0, heights)


def write_tiles(grid: dict, pixel_deg: float, zooms: range, out_dir: Path) -> int:
    rows, cols = grid["dem"].shape
    box = (grid["west"], grid["north"] - rows * pixel_deg, grid["west"] + cols * pixel_deg, grid["north"])
    count = 0
    for zoom in zooms:
        for x, y in tiles_covering(box, zoom):
            path = out_dir / str(zoom) / str(x) / f"{y}.png"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(png_bytes(terrarium_encode(sample_tile(grid, pixel_deg, x, y, zoom))))
            count += 1
    return count
