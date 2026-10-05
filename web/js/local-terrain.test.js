import { test } from "node:test";
import assert from "node:assert/strict";

import { accumulate, decodeTerrarium, describeSpot, flowDirections, keepForDisplay, nearbyLandmarks, planeFit, priorityFlood } from "./local-terrain.js";

// 5x5 bowl: centre 1 m, ring 3 m, gap of 2 m to the east, falling to 0 at the east edge.
const BOWL = Float64Array.from([
  5, 5, 5, 5, 5,
  5, 3, 3, 3, 5,
  5, 3, 1, 2, 0,
  5, 3, 3, 3, 5,
  5, 5, 5, 5, 5,
]);

test("decodeTerrarium reads RGBA pixels to metres", () => {
  const rgba = Uint8ClampedArray.from([128, 30, 128, 255]); // 32768 + 30 + 0.5 - 32768
  assert.deepEqual([...decodeTerrarium(rgba)], [30.5]);
});

test("priorityFlood fills the hollow to its 2 m pour point", () => {
  const filled = priorityFlood(BOWL, 5, 5, 0.001);
  assert.ok(Math.abs(filled[12] - 2) < 0.01);
  assert.equal(filled[0], 5);
  assert.equal(BOWL[12], 1);
});

test("flowDirections points the hollow towards its outlet", () => {
  const dirs = flowDirections(priorityFlood(BOWL, 5, 5, 0.001), 5, 5);
  assert.equal(dirs[12], 13); // centre -> east
  assert.equal(dirs[14], -1); // edge outlet
});

test("planeFit finds the downhill bearing and drop", () => {
  // Falls 1 m per cell to the east (+x), 20 m cells
  const w = 5, h = 5;
  const heights = Float64Array.from({ length: w * h }, (_, i) => 10 - (i % w));
  const fit = planeFit(heights, w, h, 20, 20);
  assert.ok(Math.abs(fit.bearing - 90) < 1);
  assert.ok(Math.abs(fit.dropPer300m - 15) < 0.01);
});

test("describeSpot reports a hollow when the spot ponds", () => {
  const text = describeSpot({ pondDepth: 0.8, nearestPool: null, bearing: 135, dropPer300m: 1.2 });
  assert.match(text, /hollow about 0\.8 m deep/);
});

test("describeSpot reports gentle slope and no hollow", () => {
  const text = describeSpot({ pondDepth: 0, nearestPool: null, bearing: 135, dropPer300m: 1.2 });
  assert.match(text, /falls gently to the south-east, about 1\.2 m over 300 m/);
  assert.match(text, /No hollow deeper than 0\.3 m/);
});

test("describeSpot calls near-flat ground flat and mentions a nearby pool", () => {
  const text = describeSpot({ pondDepth: 0, nearestPool: { depth: 0.6, distance: 180, direction: "north" }, bearing: 10, dropPer300m: 0.2 });
  assert.match(text, /nearly flat/);
  assert.match(text, /nearest hollow, about 0\.6 m deep, is about 200 m north/);
});

test("accumulate counts cells draining through each cell", () => {
  const dirs = Int32Array.from([1, 2, 3, -1]); // a row draining east
  assert.deepEqual([...accumulate(dirs)], [1, 2, 3, 4]);
});

test("nearbyLandmarks lists the closest within range with distance and direction", () => {
  const rows = [[4.8018, 7.0, "church", "St Mary's"], [4.8, 7.0009, "market", "Mile 3 Market"], [4.9, 7.0, "school", "Far"]];
  assert.equal(nearbyLandmarks(4.8, 7.0, rows, 600, 3), "Mile 3 Market, 100 m east · St Mary's (church), 200 m north");
  assert.equal(nearbyLandmarks(4.8, 7.0, [], 600, 3), null);
});

test("keepForDisplay keeps runoff lines and a sparse grid of direction arrows", () => {
  const w = 8, h = 8;
  const acc = new Float64Array(w * h).fill(1);
  acc[3 * w + 5] = 9; // a gathering runoff cell off the grid
  const keep = (i) => keepForDisplay(i, acc, w, 6, 4);
  assert.equal(keep(0), true); // grid point (0,0)
  assert.equal(keep(4 * w + 4), true); // grid point (4,4)
  assert.equal(keep(1 * w + 2), false); // ordinary cell
  assert.equal(keep(3 * w + 5), true); // runoff
});
