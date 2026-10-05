// Pure functions for the drawn-area report: geometry, hollows, outlets and the
// summary text. Grids are row-major with row 0 north; rings are [lat, lon] pairs.

import { compass } from "./local-terrain.js";

const M_PER_DEG_LAT = 110574;
const M_PER_DEG_LON = 111320;
const COLOUR_TOLERANCE = 24; // EE thumbnails are exact, but browsers may resample overlays slightly
const MINOR_OUTLET_SHARE = 0.1;
const numberFormat = new Intl.NumberFormat("en-NG", { maximumFractionDigits: 0 });

export function pointInPolygon(lat, lon, ring) {
  let inside = false;
  for (let i = 0, j = ring.length - 1; i < ring.length; j = i++) {
    const [yi, xi] = ring[i];
    const [yj, xj] = ring[j];
    if (yi > lat !== yj > lat && lon < ((xj - xi) * (lat - yi)) / (yj - yi) + xi) inside = !inside;
  }
  return inside;
}

export function polygonAreaKm2(ring) {
  const lat0 = ring.reduce((s, p) => s + p[0], 0) / ring.length;
  const kx = M_PER_DEG_LON * Math.cos((lat0 * Math.PI) / 180);
  let sum = 0;
  for (let i = 0, j = ring.length - 1; i < ring.length; j = i++) {
    sum += ring[j][1] * kx * ring[i][0] * M_PER_DEG_LAT - ring[i][1] * kx * ring[j][0] * M_PER_DEG_LAT;
  }
  return Math.abs(sum) / 2 / 1e6;
}

/** Index of the palette colour (hex strings) nearest to r,g,b, or -1 if none is close. */
export function colourClass(r, g, b, palette) {
  let best = -1, bestDistance = COLOUR_TOLERANCE;
  palette.forEach((hex, i) => {
    const n = Number.parseInt(hex, 16);
    const distance = Math.hypot(r - (n >> 16), g - ((n >> 8) & 255), b - (n & 255));
    if (distance <= bestDistance) {
      best = i;
      bestDistance = distance;
    }
  });
  return best;
}

/** Connected groups of cells inside the area ponding at least minDepth, largest volume first. */
export function findHollows(depth, inside, w, h, cellM2, minDepth) {
  const seen = new Uint8Array(w * h);
  const hollows = [];
  for (let start = 0; start < depth.length; start++) {
    if (seen[start] || !inside[start] || depth[start] < minDepth) continue;
    const cells = [];
    const stack = [start];
    seen[start] = 1;
    while (stack.length) {
      const i = stack.pop();
      cells.push(i);
      const r = Math.floor(i / w), c = i % w;
      for (let dr = -1; dr <= 1; dr++) {
        for (let dc = -1; dc <= 1; dc++) {
          const nr = r + dr, nc = c + dc, n = nr * w + nc;
          if (nr < 0 || nc < 0 || nr >= h || nc >= w || seen[n] || !inside[n] || depth[n] < minDepth) continue;
          seen[n] = 1;
          stack.push(n);
        }
      }
    }
    const deepest = cells.reduce((a, b) => (depth[b] > depth[a] ? b : a));
    hollows.push({
      cells,
      deepest,
      maxDepth: depth[deepest],
      areaM2: cells.length * cellM2,
      volumeM3: cells.reduce((s, i) => s + depth[i], 0) * cellM2,
    });
  }
  return hollows.sort((a, b) => b.volumeM3 - a.volumeM3);
}

/** Share of the area's runoff leaving on each side (compass from the area's centre), largest first. */
export function outletShares(dirs, inside, w, h) {
  const n = dirs.length;
  const acc = Float64Array.from(inside);
  const indegree = new Int32Array(n);
  for (let i = 0; i < n; i++) if (dirs[i] >= 0) indegree[dirs[i]]++;
  const stack = [];
  for (let i = 0; i < n; i++) if (indegree[i] === 0) stack.push(i);
  while (stack.length) {
    const i = stack.pop();
    const t = dirs[i];
    if (t < 0) continue;
    acc[t] += acc[i];
    if (--indegree[t] === 0) stack.push(t);
  }
  let cr = 0, cc = 0, count = 0;
  for (let i = 0; i < n; i++) if (inside[i]) { cr += Math.floor(i / w); cc += i % w; count++; }
  cr /= count; cc /= count;
  const bySide = new Map();
  let total = 0;
  for (let i = 0; i < n; i++) {
    if (!inside[i] || (dirs[i] >= 0 && inside[dirs[i]])) continue;
    const bearing = ((Math.atan2(i % w - cc, cr - Math.floor(i / w)) * 180) / Math.PI + 360) % 360;
    const side = compass(bearing);
    bySide.set(side, (bySide.get(side) ?? 0) + acc[i]);
    total += acc[i];
  }
  return [...bySide.entries()]
    .map(([side, amount]) => ({ side, share: Math.round((amount / total) * 100) / 100 }))
    .sort((a, b) => b.share - a.share);
}

function roughly(m3) {
  const step = m3 >= 1000 ? 100 : 10;
  return numberFormat.format(Math.max(step, Math.round(m3 / step) * step));
}

function hollowsLine(hollows) {
  if (!hollows.length) {
    return "No hollow deeper than 0.3 m in the 30 m elevation data: the ground should shed water unless drains are blocked.";
  }
  const top = hollows[0];
  const count = hollows.length === 1 ? "1 hollow" : `${hollows.length} hollows`;
  const near = top.nearby ? ` (${top.nearby})` : "";
  return `${count} where water collects: the largest is about ${(top.areaM2 / 1e4).toFixed(1)} ha and up to ` +
    `${top.maxDepth.toFixed(1)} m deep, holding roughly ${roughly(top.volumeM3)} m³${near}.`;
}

function outletsLine(outlets) {
  if (!outlets.length) return null;
  const [main, ...rest] = outlets;
  if (main.share >= 0.95) return `Water leaves the area on the ${main.side} side.`;
  const minor = rest.filter((o) => o.share >= MINOR_OUTLET_SHARE)
    .map((o) => `, and on the ${o.side} side (${Math.round(o.share * 100)}%)`).join("");
  return `Water leaves the area mainly on the ${main.side} side (${Math.round(main.share * 100)}%)${minor}.`;
}

function radarLine(flood) {
  if (!flood) return null;
  const standing = flood.notImagedPct >= 50
    ? `${Math.round(flood.notImagedPct)}% not imaged on ${flood.standingDate}`
    : `${flood.standingHa.toFixed(1)} ha still standing on ${flood.standingDate}`;
  return `Radar: ${Math.round(flood.recurrentPct)}% of the area flooded in 3 or more rainy seasons; ` +
    `${flood.eventHa.toFixed(1)} ha under water on ${flood.eventDate}; ${standing}.`;
}

/** Headline sentences for the drawn-area report. */
export function summariseArea({ areaKm2, hollows, outlets, flood, sites }) {
  const lines = [`Drawn area: ${areaKm2.toFixed(1)} km².`, hollowsLine(hollows), outletsLine(outlets), radarLine(flood)];
  if (sites > 0) lines.push(`${sites} priority ${sites === 1 ? "site" : "sites"} inside the area.`);
  return lines.filter(Boolean);
}
