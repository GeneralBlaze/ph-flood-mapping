import {
  POOL_MIN_DEPTH_M, accumulate, decodeTerrarium, describeRoute, flowDirections, offsetM, priorityFlood, traceRoute,
} from "./local-terrain.js";

// The path water takes from one tapped spot, worked out in the browser from the
// published Terrarium tiles (zoom 13, ~19 m per pixel): fill hollows, follow the
// steepest way down from the spot, and stop at a natural drainage line.
const ZOOM = 13;
const TILE = 256;
const RADIUS_M = 1500;
const FILL_EPS_M = 0.001;
const CHANNEL_KM2 = 1; // same threshold as the pipeline's drainage channels
const MAX_STEPS = 150; // ~3 km
const SAME_LEVEL_M = 0.05; // cells within this of the spot's water level belong to its hollow
const POOL_RGBA = [56, 130, 220]; // blue: water only

function worldPixel(lat, lon) {
  const n = TILE * 2 ** ZOOM;
  const x = ((lon + 180) / 360) * n;
  const s = Math.sin((lat * Math.PI) / 180);
  const y = (0.5 - Math.log((1 + s) / (1 - s)) / (4 * Math.PI)) * n;
  return [x, y];
}

function pixelLonLat(x, y) {
  const n = TILE * 2 ** ZOOM;
  const lon = (x / n) * 360 - 180;
  const lat = (Math.atan(Math.sinh(Math.PI * (1 - (2 * y) / n))) * 180) / Math.PI;
  return [lon, lat];
}

function loadImage(url) {
  return new Promise((resolve, reject) => {
    const img = new Image();
    img.onload = () => resolve(img);
    img.onerror = () => reject(new Error(`Terrain tile not available: ${url}`));
    img.src = url;
  });
}

/** Height window centred on (lat, lon), in world pixels at ZOOM. */
async function sampleWindow(view3d, dataRoot, lat, lon) {
  const [cx, cy] = worldPixel(lat, lon);
  const metresPerPixel = (40075016.7 * Math.cos((lat * Math.PI) / 180)) / (TILE * 2 ** ZOOM);
  const k = Math.ceil(RADIUS_M / metresPerPixel);
  const x0 = Math.floor(cx) - k, y0 = Math.floor(cy) - k, size = 2 * k + 1;
  const canvas = document.createElement("canvas");
  canvas.width = size;
  canvas.height = size;
  const ctx = canvas.getContext("2d", { willReadFrequently: true });
  const tiles = [];
  for (let tx = Math.floor(x0 / TILE); tx <= Math.floor((x0 + size) / TILE); tx++) {
    for (let ty = Math.floor(y0 / TILE); ty <= Math.floor((y0 + size) / TILE); ty++) tiles.push([tx, ty]);
  }
  const path = dataRoot + view3d.terrain;
  const images = await Promise.all(
    tiles.map(([tx, ty]) => loadImage(path.replace("{z}", ZOOM).replace("{x}", tx).replace("{y}", ty)))
  );
  images.forEach((img, i) => ctx.drawImage(img, tiles[i][0] * TILE - x0, tiles[i][1] * TILE - y0));
  const heights = decodeTerrarium(ctx.getImageData(0, 0, size, size).data);
  return { heights, size, x0, y0, metresPerPixel };
}

/** Cells of the hollow the spot sits in: connected, still under water at the spot's water level. */
function hollowCells(start, filled, depth, size) {
  const level = filled[start];
  const seen = new Set([start]);
  const stack = [start];
  while (stack.length) {
    const i = stack.pop();
    const r = Math.floor(i / size), c = i % size;
    for (let dr = -1; dr <= 1; dr++) {
      for (let dc = -1; dc <= 1; dc++) {
        const nr = r + dr, nc = c + dc, n = nr * size + nc;
        if (nr < 0 || nc < 0 || nr >= size || nc >= size || seen.has(n)) continue;
        if (depth[n] > SAME_LEVEL_M && Math.abs(filled[n] - level) < SAME_LEVEL_M) {
          seen.add(n);
          stack.push(n);
        }
      }
    }
  }
  return seen;
}

function poolImage(cells, depth, size) {
  const canvas = document.createElement("canvas");
  canvas.width = size;
  canvas.height = size;
  const ctx = canvas.getContext("2d");
  const image = ctx.createImageData(size, size);
  for (const i of cells) image.data.set([...POOL_RGBA, Math.min(230, 150 + depth[i] * 150)], i * 4);
  ctx.putImageData(image, 0, 0);
  return canvas.toDataURL("image/png");
}

/** Route water takes from the spot, the hollow it sits in (if any) and a sentence about it. */
export async function analyseSpot(view3d, dataRoot, lat, lon) {
  const { heights, size, x0, y0, metresPerPixel } = await sampleWindow(view3d, dataRoot, lat, lon);
  const filled = priorityFlood(heights, size, size, FILL_EPS_M);
  const depth = filled.map((z, i) => z - heights[i]);
  const dirs = flowDirections(filled, size, size);
  const acc = accumulate(dirs);
  const channelCells = (CHANNEL_KM2 * 1e6) / metresPerPixel ** 2;
  const start = Math.floor(size / 2) * size + Math.floor(size / 2);
  const cells = traceRoute(dirs, start, (i) => acc[i] >= channelCells, MAX_STEPS);
  const toLonLat = (i) => pixelLonLat(x0 + (i % size) + 0.5, y0 + Math.floor(i / size) + 0.5);
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
    const [west, top] = pixelLonLat(x0, y0);
    const [eastEdge, bottom] = pixelLonLat(x0 + size, y0 + size);
    pool = { url: poolImage(hollowCells(start, filled, depth, size), depth, size), bounds: [[bottom, west], [top, eastEdge]] };
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
