// Local terrain around a tapped spot: which way the ground falls and where water
// would pond. Pure functions over a small height grid (row-major, row 0 north),
// decoded from the published Terrarium tiles (about 19 m per pixel at zoom 13).

const OFFSET_M = 32768;
const NEIGHBOURS = [[-1, -1], [-1, 0], [-1, 1], [0, -1], [0, 1], [1, -1], [1, 0], [1, 1]];
const COMPASS = ["north", "north-east", "east", "south-east", "south", "south-west", "west", "north-west"];
export const POOL_MIN_DEPTH_M = 0.3; // shallower than this is within the elevation data's noise
const FLAT_DROP_M = 0.3; // a route dropping less than this is over nearly flat ground
const DISTANCE_STEP_M = 50;

export function decodeTerrarium(rgba) {
  const out = new Float64Array(rgba.length / 4);
  for (let i = 0; i < out.length; i++) {
    out[i] = rgba[i * 4] * 256 + rgba[i * 4 + 1] + rgba[i * 4 + 2] / 256 - OFFSET_M;
  }
  return out;
}

// Minimal binary min-heap of [height, index]
function heap() {
  const items = [];
  const swap = (a, b) => ([items[a], items[b]] = [items[b], items[a]]);
  return {
    get size() { return items.length; },
    push(item) {
      items.push(item);
      let i = items.length - 1;
      while (i > 0) {
        const p = (i - 1) >> 1;
        if (items[p][0] <= items[i][0]) break;
        swap(i, p);
        i = p;
      }
    },
    pop() {
      const top = items[0];
      const last = items.pop();
      if (items.length) {
        items[0] = last;
        let i = 0;
        for (;;) {
          const l = 2 * i + 1, r = l + 1;
          let m = i;
          if (l < items.length && items[l][0] < items[m][0]) m = l;
          if (r < items.length && items[r][0] < items[m][0]) m = r;
          if (m === i) break;
          swap(i, m);
          i = m;
        }
      }
      return top;
    },
  };
}

/** Copy of heights with hollows filled to their pour point; the window edge drains out. */
export function priorityFlood(heights, w, h, eps) {
  const filled = Float64Array.from(heights);
  const seen = new Uint8Array(w * h);
  const queue = heap();
  for (let r = 0; r < h; r++) {
    for (let c = 0; c < w; c++) {
      if (r === 0 || c === 0 || r === h - 1 || c === w - 1) {
        seen[r * w + c] = 1;
        queue.push([filled[r * w + c], r * w + c]);
      }
    }
  }
  while (queue.size) {
    const [z, i] = queue.pop();
    const r = Math.floor(i / w), c = i % w;
    for (const [dr, dc] of NEIGHBOURS) {
      const nr = r + dr, nc = c + dc;
      if (nr < 0 || nc < 0 || nr >= h || nc >= w) continue;
      const n = nr * w + nc;
      if (seen[n]) continue;
      seen[n] = 1;
      filled[n] = Math.max(filled[n], z + eps);
      queue.push([filled[n], n]);
    }
  }
  return filled;
}

/** Index of the steepest-descent neighbour for each cell, or -1 where water leaves the window. */
export function flowDirections(filled, w, h) {
  const dirs = new Int32Array(w * h).fill(-1);
  for (let r = 0; r < h; r++) {
    for (let c = 0; c < w; c++) {
      let best = 0;
      for (const [dr, dc] of NEIGHBOURS) {
        const nr = r + dr, nc = c + dc;
        if (nr < 0 || nc < 0 || nr >= h || nc >= w) continue;
        const slope = (filled[r * w + c] - filled[nr * w + nc]) / Math.hypot(dr, dc);
        if (slope > best) {
          best = slope;
          dirs[r * w + c] = nr * w + nc;
        }
      }
    }
  }
  return dirs;
}

export function compass(bearing) {
  return COMPASS[Math.round(bearing / 45) % 8];
}

const rounded = (m) => Math.max(DISTANCE_STEP_M, Math.round(m / DISTANCE_STEP_M) * DISTANCE_STEP_M);

/** Cells draining through each cell, itself included. dirs from flowDirections. */
export function accumulate(dirs) {
  const n = dirs.length;
  const acc = new Float64Array(n).fill(1);
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
  return acc;
}

const M_PER_DEG_LAT = 110574;
const M_PER_DEG_LON = 111320;

/** (north, east) metres from (lat, lon) to (lat2, lon2). */
export function offsetM(lat, lon, lat2, lon2) {
  return [(lat2 - lat) * M_PER_DEG_LAT, (lon2 - lon) * M_PER_DEG_LON * Math.cos((lat * Math.PI) / 180)];
}

function landmarkLabel(name, kind) {
  return name.toLowerCase().includes(kind.toLowerCase()) ? name : `${name} (${kind})`;
}

/** "Mile 3 Market, 100 m east · …" for the closest landmarks (rows [lat, lon, kind, name]), or null. */
export function nearbyLandmarks(lat, lon, rows, maxM, limit) {
  const found = rows
    .map(([la, lo, kind, name]) => {
      const [north, east] = offsetM(lat, lon, la, lo);
      return { kind, name, distance: Math.hypot(north, east), bearing: (Math.atan2(east, north) * 180) / Math.PI };
    })
    .filter((m) => m.distance <= maxM)
    .sort((a, b) => a.distance - b.distance)
    .slice(0, limit);
  if (!found.length) return null;
  return found
    .map((m) => {
      const where = m.distance < DISTANCE_STEP_M ? "beside it" : `${rounded(m.distance)} m ${compass((m.bearing + 360) % 360)}`;
      return `${landmarkLabel(m.name, m.kind)}, ${where}`;
    })
    .join(" · ");
}


/** Cells from start following dirs until stop(i) is true, the window edge (-1), or maxSteps. */
export function traceRoute(dirs, start, stop, maxSteps) {
  const route = [start];
  let i = start;
  for (let step = 0; step < maxSteps && !stop(i) && dirs[i] >= 0; step++) {
    i = dirs[i];
    route.push(i);
  }
  return route;
}

const ENDINGS = {
  channel: "to a natural drainage line",
  edge: "and carry on beyond the analysed area",
};

/** Plain account of the route water takes from a tapped spot. */
export function describeRoute({ pondDepth, lengthM, bearing, dropM, end }) {
  const parts = [];
  const lead = pondDepth >= POOL_MIN_DEPTH_M ? "Once it spills, it should run" : "Water from this spot should run";
  if (pondDepth >= POOL_MIN_DEPTH_M) {
    parts.push(`This spot sits in a hollow about ${pondDepth.toFixed(1)} m deep: water has to rise that much before it can flow away.`);
  }
  const fall = dropM < FLAT_DROP_M ? "over nearly flat ground" : `dropping about ${dropM.toFixed(1)} m`;
  parts.push(`${lead} about ${rounded(lengthM)} m to the ${compass(bearing)}, ${fall}, ${ENDINGS[end]}.`);
  return parts.join(" ");
}
