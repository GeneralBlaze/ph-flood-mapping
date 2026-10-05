// Which landmark labels to draw (see landmark-layer.js). Rows are [lat, lon, kind, name].

export const LANDMARK_MIN_ZOOM = 15;

export function visibleLandmarks(rows, view, zoom, limit) {
  if (zoom < LANDMARK_MIN_ZOOM) return [];
  return rows
    .filter(
      (r) =>
        Array.isArray(r) &&
        typeof r[0] === "number" &&
        typeof r[1] === "number" &&
        typeof r[3] === "string" &&
        r[0] >= view.south && r[0] <= view.north && r[1] >= view.west && r[1] <= view.east
    )
    .slice(0, limit);
}
