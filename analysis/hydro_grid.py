"""Water routing on a small elevation grid, in plain numpy.

Used at 30 m (FABDEM) to trace where water from a flooded site has to go, and
how high it must rise to get there. Grid cells are indexed (row, col), row 0 north.

- priority_flood: fills hollows to their pour point (Barnes et al. 2014, with a
  tiny epsilon gradient so filled flats still drain). The difference between
  the filled and raw surface is how deep water must pond before it can escape.
- d8_directions: steepest-descent neighbour on the filled surface.
- flow_accumulation: number of cells draining through each cell.
"""

import heapq

import numpy as np

NODATA_DIR = (0, 0)  # outlet: flows off the grid or into a no-data cell
NEIGHBOURS = [(-1, -1), (-1, 0), (-1, 1), (0, -1), (0, 1), (1, -1), (1, 0), (1, 1)]


def priority_flood(dem: np.ndarray, eps: float) -> np.ndarray:
    """Copy of dem with hollows filled; NaN cells act as outlets (sea, rivers, outside the data)."""
    rows, cols = dem.shape
    filled = dem.copy()
    visited = np.isnan(dem)
    heap: list[tuple[float, int, int]] = []

    def seed(r: int, c: int) -> None:
        if not visited[r, c]:
            visited[r, c] = True
            heapq.heappush(heap, (filled[r, c], r, c))

    for r in range(rows):
        for c in range(cols):
            if np.isnan(dem[r, c]):
                continue
            on_edge = r in (0, rows - 1) or c in (0, cols - 1)
            next_to_nan = any(
                0 <= r + dr < rows and 0 <= c + dc < cols and np.isnan(dem[r + dr, c + dc]) for dr, dc in NEIGHBOURS
            )
            if on_edge or next_to_nan:
                seed(r, c)

    while heap:
        z, r, c = heapq.heappop(heap)
        for dr, dc in NEIGHBOURS:
            nr, nc = r + dr, c + dc
            if 0 <= nr < rows and 0 <= nc < cols and not visited[nr, nc]:
                visited[nr, nc] = True
                filled[nr, nc] = max(filled[nr, nc], z + eps)
                heapq.heappush(heap, (filled[nr, nc], nr, nc))
    return filled


def d8_directions(filled: np.ndarray, dx: float, dy: float) -> np.ndarray:
    """(rows, cols, 2) array of (drow, dcol) to the steepest-descent neighbour; NODATA_DIR at outlets."""
    rows, cols = filled.shape
    padded = np.pad(filled, 1, constant_values=-np.inf)  # off-grid counts as lowest: edge cells drain out
    best_slope = np.zeros((rows, cols))
    dirs = np.zeros((rows, cols, 2), dtype=np.int8)
    for dr, dc in NEIGHBOURS:
        neighbour = padded[1 + dr: 1 + dr + rows, 1 + dc: 1 + dc + cols]
        distance = float(np.hypot(dr * dy, dc * dx))
        with np.errstate(invalid="ignore"):
            slope = (filled - neighbour) / distance
        off_grid = np.isneginf(neighbour) | np.isnan(neighbour)
        slope = np.where(off_grid, 0.0, np.nan_to_num(slope, nan=0.0))
        better = slope > best_slope
        best_slope = np.where(better, slope, best_slope)
        dirs[better] = (dr, dc)
    edge = np.zeros((rows, cols), dtype=bool)
    edge[[0, -1], :] = True
    edge[:, [0, -1]] = True
    nan_next = np.zeros((rows, cols), dtype=bool)
    for dr, dc in NEIGHBOURS:
        nan_next |= np.isnan(np.pad(filled, 1, constant_values=0.0)[1 + dr: 1 + dr + rows, 1 + dc: 1 + dc + cols])
    no_descent = best_slope <= 0
    dirs[(edge | nan_next) & no_descent] = NODATA_DIR
    return dirs


def flow_accumulation(dirs: np.ndarray) -> np.ndarray:
    """Cells draining through each cell, itself included (topological order by in-degree)."""
    rows, cols = dirs.shape[:2]
    acc = np.ones((rows, cols), dtype=np.int64)
    targets = {}
    indegree = np.zeros((rows, cols), dtype=np.int32)
    for r in range(rows):
        for c in range(cols):
            dr, dc = int(dirs[r, c, 0]), int(dirs[r, c, 1])
            tr, tc = r + dr, c + dc
            if (dr, dc) != NODATA_DIR and 0 <= tr < rows and 0 <= tc < cols:
                targets[(r, c)] = (tr, tc)
                indegree[tr, tc] += 1
    queue = [(r, c) for r in range(rows) for c in range(cols) if indegree[r, c] == 0]
    while queue:
        cell = queue.pop()
        target = targets.get(cell)
        if target is None:
            continue
        acc[target] += acc[cell]
        indegree[target] -= 1
        if indegree[target] == 0:
            queue.append(target)
    return acc


def trace(dirs: np.ndarray, acc: np.ndarray, start: tuple[int, int], stop_cells: int,
          max_steps: int) -> list[tuple[int, int]]:
    """Cells water follows from start until a cell drains >= stop_cells, it leaves the grid, or max_steps."""
    rows, cols = acc.shape
    route = [start]
    r, c = start
    for _ in range(max_steps):
        if acc[r, c] >= stop_cells:
            break
        dr, dc = int(dirs[r, c, 0]), int(dirs[r, c, 1])
        if (dr, dc) == NODATA_DIR:
            break
        r, c = r + dr, c + dc
        if not (0 <= r < rows and 0 <= c < cols) or (r, c) in route:
            break
        route.append((r, c))
    return route
