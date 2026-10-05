import {
  POOL_MIN_DEPTH_M, accumulate, keepForDisplay, compass, decodeTerrarium, describeSpot, flowDirections, offsetM, planeFit, priorityFlood,
} from "./local-terrain.js";

// Reads the published Terrarium tiles around a spot (zoom 13, ~19 m per pixel) and
// works out local runoff: arrows for every pixel, hollows where water ponds, and a
// sentence about the ground. Everything runs in the browser from files we host.
const ZOOM = 13;
const TILE = 256;
const RADIUS_M = 500;
const FILL_EPS_M = 0.001;
const POOL_RGBA = [56, 130, 220]; // blue: water only
const RUNOFF_MIN_CELLS = 6; // cells gathering this much water are drawn as runoff lines
const ARROW_GRID = 4; // otherwise one direction arrow every 4 cells (~75 m)

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

/** Height window centred on (lat, lon): { heights, w, h, x0, y0, cellXm, cellYm } in world pixels. */
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
  return { heights, w: size, h: size, x0, y0, cellXm: metresPerPixel, cellYm: metresPerPixel };
}

function poolImage(depth, w, h) {
  const canvas = document.createElement("canvas");
  canvas.width = w;
  canvas.height = h;
  const ctx = canvas.getContext("2d");
  const image = ctx.createImageData(w, h);
  for (let i = 0; i < depth.length; i++) {
    if (depth[i] < POOL_MIN_DEPTH_M) continue;
    image.data.set([...POOL_RGBA, Math.min(230, 150 + depth[i] * 150)], i * 4);
  }
  ctx.putImageData(image, 0, 0);
  return canvas.toDataURL("image/png");
}

function nearestPool(depth, w, h, lat, lon, toLonLat) {
  const centre = Math.floor(h / 2) * w + Math.floor(w / 2);
  let best = null;
  for (let i = 0; i < depth.length; i++) {
    if (depth[i] < POOL_MIN_DEPTH_M || i === centre) continue;
    const [plon, plat] = toLonLat(i);
    const [north, east] = offsetM(lat, lon, plat, plon);
    const distance = Math.hypot(north, east);
    if (!best || distance < best.distance) {
      best = { distance, depth: depth[i], direction: compass((Math.atan2(east, north) * 180) / Math.PI + 360) };
    }
  }
  return best;
}

/** Local runoff around a spot, ready for the map and the panel. */
export async function analyseSpot(view3d, dataRoot, lat, lon) {
  const { heights, w, h, x0, y0, cellXm, cellYm } = await sampleWindow(view3d, dataRoot, lat, lon);
  const filled = priorityFlood(heights, w, h, FILL_EPS_M);
  const depth = filled.map((z, i) => z - heights[i]);
  const dirs = flowDirections(filled, w, h);
  const acc = accumulate(dirs);
  const toLonLat = (i) => pixelLonLat(x0 + (i % w) + 0.5, y0 + Math.floor(i / w) + 0.5);
  const segments = [];
  for (let i = 0; i < dirs.length; i++) {
    if (dirs[i] < 0 || !keepForDisplay(i, acc, w, RUNOFF_MIN_CELLS, ARROW_GRID)) continue;
    const [lon1, lat1] = toLonLat(i);
    const [lon2, lat2] = toLonLat(dirs[i]);
    segments.push([lon1, lat1, lon2, lat2, acc[i] * cellXm * cellYm / 1e6]); // km² draining through
  }
  const [west, north] = pixelLonLat(x0, y0);
  const [east, south] = pixelLonLat(x0 + w, y0 + h);
  const centre = Math.floor(h / 2) * w + Math.floor(w / 2);
  const plane = planeFit(heights, w, h, cellXm, cellYm);
  const pool = nearestPool(depth, w, h, lat, lon, toLonLat);
  return {
    segments,
    pools: { url: poolImage(depth, w, h), bounds: [[south, west], [north, east]] },
    sentence: describeSpot({
      pondDepth: depth[centre],
      nearestPool: depth[centre] >= POOL_MIN_DEPTH_M ? null : pool,
      bearing: plane.bearing,
      dropPer300m: plane.dropPer300m,
    }),
  };
}
