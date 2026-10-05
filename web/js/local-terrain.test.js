import { test } from "node:test";
import assert from "node:assert/strict";

import { accumulate, decodeTerrarium, describeRoute, flowDirections, nearbyLandmarks, priorityFlood, traceRoute } from "./local-terrain.js";

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

test("traceRoute follows directions until the stop test or the window edge", () => {
  const dirs = Int32Array.from([1, 2, 3, -1]);
  assert.deepEqual(traceRoute(dirs, 0, () => false, 10), [0, 1, 2, 3]);
  assert.deepEqual(traceRoute(dirs, 0, (i) => i === 2, 10), [0, 1, 2]);
  assert.deepEqual(traceRoute(dirs, 0, () => false, 1), [0, 1]);
});

test("describeRoute: water runs off to a drainage line", () => {
  const text = describeRoute({ pondDepth: 0, lengthM: 412, bearing: 265, dropM: 1.24, end: "channel" });
  assert.equal(text, "Water from this spot should run about 400 m to the west, dropping about 1.2 m, to a natural drainage line.");
});

test("describeRoute: spot in a hollow spills out first", () => {
  const text = describeRoute({ pondDepth: 0.46, lengthM: 180, bearing: 90, dropM: 0.3, end: "edge" });
  assert.equal(text, "This spot sits in a hollow about 0.5 m deep: water has to rise that much before it can flow away. " +
    "Once it spills, it should run about 200 m to the east, dropping about 0.3 m, and carry on beyond the analysed area.");
});

test("describeRoute: nearly flat route says so", () => {
  const text = describeRoute({ pondDepth: 0, lengthM: 300, bearing: 0, dropM: 0.1, end: "edge" });
  assert.match(text, /over nearly flat ground/);
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

