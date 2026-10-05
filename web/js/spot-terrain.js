import {
  POOL_MIN_DEPTH_M, accumulate, describeRoute, flowDirections, offsetM, priorityFlood, traceRoute,
} from "./local-terrain.js";
import { sampleAround } from "./terrain-sampler.js";

// The path water takes from one tapped spot, worked out in the browser from the
// published Terrarium tiles (zoom 13, ~19 m per pixel): fill hollows, follow the
// steepest way down from the spot, and stop at a natural drainage line.
const RADIUS_M = 1500;
const FILL_EPS_M = 0.001;
const CHANNEL_KM2 = 1; // same threshold as the pipeline's drainage channels
const MAX_STEPS = 150; // ~3 km
const SAME_LEVEL_M = 0.05; // cells within this of the spot's water level belong to its hollow
const POOL_RGBA = [56, 130, 220]; // blue: water only

/** Cells of the hollow the spot sits in: connected, still under water at the spot's water level. */
function hollowCells(start, filled, depth, w, h) {
  const level = filled[start];
  const seen = new Set([start]);
  const stack = [start];
  while (stack.length) {
    const i = stack.pop();
    const r = Math.floor(i / w), c = i % w;
    for (let dr = -1; dr <= 1; dr++) {
      for (let dc = -1; dc <= 1; dc++) {
        const nr = r + dr, nc = c + dc, n = nr * w + nc;
        if (nr < 0 || nc < 0 || nr >= h || nc >= w || seen.has(n)) continue;
        if (depth[n] > SAME_LEVEL_M && Math.abs(filled[n] - level) < SAME_LEVEL_M) {
          seen.add(n);
          stack.push(n);
        }
      }
    }
  }
  return seen;
}

export function poolImage(cells, depth, w, h) {
  const canvas = document.createElement("canvas");
  canvas.width = w;
  canvas.height = h;
  const ctx = canvas.getContext("2d");
  const image = ctx.createImageData(w, h);
  for (const i of cells) image.data.set([...POOL_RGBA, Math.min(230, 150 + depth[i] * 150)], i * 4);
  ctx.putImageData(image, 0, 0);
  return canvas.toDataURL("image/png");
}

/** Route water takes from the spot, the hollow it sits in (if any) and a sentence about it. */
export async function analyseSpot(view3d, dataRoot, lat, lon) {
  const { heights, w, h, metresPerPixel, toLonLat, bounds } = await sampleAround(view3d, dataRoot, lat, lon, RADIUS_M);
  const filled = priorityFlood(heights, w, h, FILL_EPS_M);
  const depth = filled.map((z, i) => z - heights[i]);
  const dirs = flowDirections(filled, w, h);
  const acc = accumulate(dirs);
  const channelCells = (CHANNEL_KM2 * 1e6) / metresPerPixel ** 2;
  const start = Math.floor(h / 2) * w + Math.floor(w / 2);
  const cells = traceRoute(dirs, start, (i) => acc[i] >= channelCells, MAX_STEPS);
  const route = cells.map(toLonLat);

  const last = cells[cells.length - 1];
  const [endLon, endLat] = route[route.length - 1];
  const [north, east] = offsetM(lat, lon, endLat, endLon);
  const lengthM = route.slice(1).reduce((sum, [lo, la], i) => {
    const [n, e] = offsetM(route[i][1], route[i][0], la, lo);
    return sum + Math.hypot(n, e);
  }, 0);
  const pondDepth = depth[start];
  let pool = null;
  if (pondDepth >= POOL_MIN_DEPTH_M) {
    pool = { url: poolImage(hollowCells(start, filled, depth, w, h), depth, w, h), bounds };
  }
  return {
    route: route.length > 1 ? route : null,
    pool,
    sentence: describeRoute({
      pondDepth,
      lengthM,
      bearing: ((Math.atan2(east, north) * 180) / Math.PI + 360) % 360,
      dropM: Math.max(0, filled[start] - heights[last]),
      end: acc[last] >= channelCells ? "channel" : "edge",
    }),
  };
}
