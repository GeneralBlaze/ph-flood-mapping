import { findHollows, outletShares, pointInPolygon, polygonAreaKm2, colourClass, summariseArea } from "./area-analysis.js";
import { POOL_MIN_DEPTH_M, accumulate, flowDirections, nearbyLandmarks, priorityFlood } from "./local-terrain.js";
import { formatDate } from "./format.js";
import { poolImage } from "./spot-terrain.js";
import { sampleBox } from "./terrain-sampler.js";

// Drawn-area report, run in the browser from published data: terrain tiles for
// hollows and outlets, the flood-layer images for radar figures, and the site lists.
const MARGIN_M = 300; // routing room around the drawn area
const FILL_EPS_M = 0.001;
const RUNOFF_MIN_CELLS = 40; // main runoff lines only: where ~1.5 ha of the area's water gathers
const NEARBY_M = 600;
const YEARS_PALETTE = ["c6dbef", "9ecae1", "6baed6", "3182bd", "08519c", "08306b"]; // run_stage3.py
const STANDING_PALETTE = ["a9c8f0", "0b3fa8", "3d8fd9", "8a8a8a"]; // run_standing.py: drained, standing, new, not imaged
const EVENT_PALETTE = ["1f6fff"]; // outputs.py
export const MAX_AREA_KM2 = 25;
export const STEPS = ["Loading terrain", "Finding hollows", "Tracing where water leaves", "Reading radar layers", "Writing the report"];

const MIN_STEP_MS = 280; // small areas finish in a blink; hold each step long enough to read

const nextFrame = () => new Promise((resolve) => requestAnimationFrame(() => resolve()));
const pause = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

/** Reports a step, lets the progress bar paint, and keeps the previous step visible for MIN_STEP_MS. */
function stepper(onProgress, reducedMotion) {
  let shownAt = 0;
  return async (step) => {
    const wait = reducedMotion ? 0 : MIN_STEP_MS - (performance.now() - shownAt);
    if (shownAt && wait > 0) await pause(wait);
    onProgress(step);
    shownAt = performance.now();
    await nextFrame();
  };
}

function box(ring) {
  const lats = ring.map((p) => p[0]), lons = ring.map((p) => p[1]);
  const midLat = (Math.min(...lats) + Math.max(...lats)) / 2;
  const dLat = MARGIN_M / 110574, dLon = MARGIN_M / (111320 * Math.cos((midLat * Math.PI) / 180));
  return { south: Math.min(...lats) - dLat, north: Math.max(...lats) + dLat, west: Math.min(...lons) - dLon, east: Math.max(...lons) + dLon };
}

const imageCache = new Map();

async function overlayPixels(url) {
  if (!imageCache.has(url)) {
    imageCache.set(url, new Promise((resolve, reject) => {
      const img = new Image();
      img.onload = () => {
        const canvas = document.createElement("canvas");
        canvas.width = img.naturalWidth;
        canvas.height = img.naturalHeight;
        const ctx = canvas.getContext("2d", { willReadFrequently: true });
        ctx.drawImage(img, 0, 0);
        resolve({ data: ctx.getImageData(0, 0, canvas.width, canvas.height).data, w: canvas.width, h: canvas.height });
      };
      img.onerror = () => reject(new Error(`Flood layer not available: ${url}`));
      img.src = url;
    }));
  }
  return imageCache.get(url);
}

const mercY = (lat) => Math.log(Math.tan(Math.PI / 4 + (lat * Math.PI) / 360));

/** Palette class of an EPSG:3857 overlay at (lat, lon), or -1 (transparent, outside or unmatched). */
function classAt(px, [[south, west], [north, east]], lat, lon, palette) {
  const x = Math.floor(((lon - west) / (east - west)) * px.w);
  const y = Math.floor(((mercY(north) - mercY(lat)) / (mercY(north) - mercY(south))) * px.h);
  if (x < 0 || y < 0 || x >= px.w || y >= px.h) return -1;
  const k = (y * px.w + x) * 4;
  return px.data[k + 3] < 128 ? -1 : colourClass(px.data[k], px.data[k + 1], px.data[k + 2], palette);
}

async function radarFigures(lga, dataRoot, insideCells, toLonLat, cellHa) {
  const layers = [
    lga.frequency && ["frequency", lga.frequency, YEARS_PALETTE],
    lga.standing && ["standing", lga.standing, STANDING_PALETTE],
    lga.events[0] && ["event", lga.events[0], EVENT_PALETTE],
  ].filter(Boolean);
  if (!layers.length) return null;
  const counts = { recurrent: 0, standing: 0, notImaged: 0, event: 0 };
  for (const [kind, layer, palette] of layers) {
    const px = await overlayPixels(dataRoot + layer.overlay);
    for (const i of insideCells) {
      const [lon, lat] = toLonLat(i);
      const cls = classAt(px, layer.bounds, lat, lon, palette);
      if (kind === "frequency" && cls + 1 >= lga.frequency.repeat_min_years) counts.recurrent++;
      if (kind === "standing" && cls === 1) counts.standing++;
      if (kind === "standing" && cls === 3) counts.notImaged++;
      if (kind === "event" && cls === 0) counts.event++;
    }
  }
  const n = insideCells.length;
  return {
    recurrentPct: (counts.recurrent / n) * 100,
    standingHa: counts.standing * cellHa,
    notImagedPct: lga.standing ? (counts.notImaged / n) * 100 : 100,
    eventHa: counts.event * cellHa,
    standingDate: lga.standing ? formatDate(lga.standing.after) : "the latest date",
    eventDate: lga.events[0] ? formatDate(lga.events[0].date) : "the flood date",
  };
}

/**
 * Runs the report for ring ([lat, lon] corners). onProgress(stepIndex) is called before each step.
 * Returns { lines, hollowsImage, runoff, hollows }.
 */
export async function analyseArea({ ring, lga, dataRoot, landmarks, sites, onProgress, reducedMotion = false }) {
  const step = stepper(onProgress, reducedMotion);
  const areaKm2 = polygonAreaKm2(ring);
  if (areaKm2 > MAX_AREA_KM2) throw new Error(`Please draw a smaller area (up to ${MAX_AREA_KM2} km²; this one is ${areaKm2.toFixed(0)} km²).`);
  if (!lga.view3d) throw new Error("Terrain data is not available for this local government area yet.");

  await step(0);
  const grid = await sampleBox(lga.view3d, dataRoot, box(ring));
  const { heights, w, h, toLonLat, metresPerPixel } = grid;
  const cellM2 = metresPerPixel ** 2;

  await step(1);
  const inside = new Uint8Array(w * h);
  const insideCells = [];
  for (let i = 0; i < inside.length; i++) {
    const [lon, lat] = toLonLat(i);
    if (pointInPolygon(lat, lon, ring)) {
      inside[i] = 1;
      insideCells.push(i);
    }
  }
  if (!insideCells.length) throw new Error("The drawn area is too small to analyse.");
  const filled = priorityFlood(heights, w, h, FILL_EPS_M);
  const depth = filled.map((z, i) => z - heights[i]);
  const hollows = findHollows(depth, inside, w, h, cellM2, POOL_MIN_DEPTH_M).map((hollow) => {
    const [lon, lat] = toLonLat(hollow.deepest);
    return { ...hollow, lat, lon, nearby: nearbyLandmarks(lat, lon, landmarks, NEARBY_M, 1) };
  });

  await step(2);
  const dirs = flowDirections(filled, w, h);
  const outlets = outletShares(dirs, inside, w, h);
  const acc = accumulate(dirs.map((t, i) => (inside[i] ? t : -1)));
  const runoff = [];
  for (const i of insideCells) {
    if (dirs[i] < 0 || acc[i] < RUNOFF_MIN_CELLS) continue;
    const [lon1, lat1] = toLonLat(i);
    const [lon2, lat2] = toLonLat(dirs[i]);
    runoff.push([lon1, lat1, lon2, lat2, (acc[i] * cellM2) / 1e6]);
  }

  await step(3);
  const flood = await radarFigures(lga, dataRoot, insideCells, toLonLat, cellM2 / 1e4);

  await step(4);
  const sitesInside = sites.filter((s) => pointInPolygon(s.lat, s.lon, ring));
  const hollowCellsAll = hollows.flatMap((x) => x.cells);
  await step(STEPS.length); // keep "Writing the report" on screen briefly, then show 100%
  if (!reducedMotion) await pause(MIN_STEP_MS);
  return {
    lines: summariseArea({ areaKm2, hollows, outlets, flood, sites: sitesInside.length }),
    hollows: hollows.slice(0, 5).map(({ lat, lon, maxDepth, areaM2, volumeM3, nearby }) => ({ lat, lon, maxDepth, areaM2, volumeM3, nearby })),
    hollowsImage: hollowCellsAll.length ? { url: poolImage(hollowCellsAll, depth, w, h), bounds: grid.bounds } : null,
    runoff,
  };
}
