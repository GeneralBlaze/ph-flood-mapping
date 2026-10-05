import { decodeTerrarium } from "./local-terrain.js";

// Loads published Terrarium tiles (zoom 13, ~19 m per pixel) into a height grid
// covering a box, row 0 north. Shared by the spot route and the drawn-area report.
const ZOOM = 13;
const TILE = 256;
const WORLD_PX = TILE * 2 ** ZOOM;

export function worldPixel(lat, lon) {
  const s = Math.sin((lat * Math.PI) / 180);
  return [((lon + 180) / 360) * WORLD_PX, (0.5 - Math.log((1 + s) / (1 - s)) / (4 * Math.PI)) * WORLD_PX];
}

export function pixelLonLat(x, y) {
  const lon = (x / WORLD_PX) * 360 - 180;
  const lat = (Math.atan(Math.sinh(Math.PI * (1 - (2 * y) / WORLD_PX))) * 180) / Math.PI;
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

/** Height grid covering { south, west, north, east }. */
export async function sampleBox(view3d, dataRoot, { south, west, north, east }) {
  const [xa, ya] = worldPixel(north, west);
  const [xb, yb] = worldPixel(south, east);
  const x0 = Math.floor(xa), y0 = Math.floor(ya);
  const w = Math.ceil(xb) - x0 + 1, h = Math.ceil(yb) - y0 + 1;
  const canvas = document.createElement("canvas");
  canvas.width = w;
  canvas.height = h;
  const ctx = canvas.getContext("2d", { willReadFrequently: true });
  const tiles = [];
  for (let tx = Math.floor(x0 / TILE); tx <= Math.floor((x0 + w) / TILE); tx++) {
    for (let ty = Math.floor(y0 / TILE); ty <= Math.floor((y0 + h) / TILE); ty++) tiles.push([tx, ty]);
  }
  const path = dataRoot + view3d.terrain;
  const images = await Promise.all(
    tiles.map(([tx, ty]) => loadImage(path.replace("{z}", ZOOM).replace("{x}", tx).replace("{y}", ty)))
  );
  images.forEach((img, i) => ctx.drawImage(img, tiles[i][0] * TILE - x0, tiles[i][1] * TILE - y0));
  const midLat = (south + north) / 2;
  return {
    heights: decodeTerrarium(ctx.getImageData(0, 0, w, h).data),
    w,
    h,
    metresPerPixel: (40075016.7 * Math.cos((midLat * Math.PI) / 180)) / WORLD_PX,
    toLonLat: (i) => pixelLonLat(x0 + (i % w) + 0.5, y0 + Math.floor(i / w) + 0.5),
    bounds: (() => {
      const [wl, nt] = pixelLonLat(x0, y0);
      const [el, sb] = pixelLonLat(x0 + w, y0 + h);
      return [[sb, wl], [nt, el]];
    })(),
  };
}

/** Square height grid of about ±radiusM around (lat, lon); the spot is the centre cell. */
export function sampleAround(view3d, dataRoot, lat, lon, radiusM) {
  const dLat = radiusM / 110574;
  const dLon = radiusM / (111320 * Math.cos((lat * Math.PI) / 180));
  return sampleBox(view3d, dataRoot, { south: lat - dLat, west: lon - dLon, north: lat + dLat, east: lon + dLon });
}
