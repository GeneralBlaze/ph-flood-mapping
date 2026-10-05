import { test } from "node:test";
import assert from "node:assert/strict";

import { visibleLandmarks } from "./landmark-math.js";

const rows = [
  [4.80, 7.00, "market", "Mile 3 Market"],
  [4.81, 7.01, "church", "St Mary's"],
  [4.95, 7.20, "school", "Far School"],
];
const view = { south: 4.79, west: 6.99, north: 4.82, east: 7.02 };

test("visibleLandmarks hides labels below street zoom", () => {
  assert.deepEqual(visibleLandmarks(rows, view, 14, 50), []);
});

test("visibleLandmarks keeps only rows inside the view, capped", () => {
  assert.deepEqual(visibleLandmarks(rows, view, 16, 50).map((r) => r[3]), ["Mile 3 Market", "St Mary's"]);
  assert.equal(visibleLandmarks(rows, view, 16, 1).length, 1);
});

test("visibleLandmarks ignores malformed rows", () => {
  assert.deepEqual(visibleLandmarks([[null, 7, "x", "y"], ["a", "b"]], view, 16, 50), []);
});
