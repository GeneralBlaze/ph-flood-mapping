import { test } from "node:test";
import assert from "node:assert/strict";

import {
  colourClass, findHollows, outletShares, pointInPolygon, polygonAreaKm2, summariseArea,
} from "./area-analysis.js";

// ~1.1 km square near Port Harcourt, as [lat, lon]
const SQUARE = [[4.80, 7.00], [4.80, 7.01], [4.81, 7.01], [4.81, 7.00]];

test("pointInPolygon", () => {
  assert.equal(pointInPolygon(4.805, 7.005, SQUARE), true);
  assert.equal(pointInPolygon(4.82, 7.005, SQUARE), false);
});

test("polygonAreaKm2 of a 0.01 degree square is about 1.23 km²", () => {
  assert.ok(Math.abs(polygonAreaKm2(SQUARE) - 1.226) < 0.02);
});

test("colourClass matches the nearest palette colour within tolerance", () => {
  const palette = ["c6dbef", "9ecae1", "6baed6"];
  assert.equal(colourClass(0x9e, 0xca, 0xe1, palette), 1);
  assert.equal(colourClass(0x6c, 0xae, 0xd5, palette), 2); // small resampling error
  assert.equal(colourClass(255, 0, 0, palette), -1);
});

test("findHollows groups connected ponding cells inside the area", () => {
  const w = 5, h = 3;
  const depth = Float64Array.from([
    0, 0.5, 0.6, 0, 0,
    0, 0.4, 0, 0, 0.9,
    0, 0, 0, 0, 0.8,
  ]);
  const inside = new Uint8Array(w * h).fill(1);
  inside[14] = 0; // one cell of the right-hand hollow lies outside the drawn area

  const hollows = findHollows(depth, inside, w, h, 400, 0.3);

  assert.equal(hollows.length, 2);
  assert.deepEqual(hollows.map((x) => x.cells.length), [3, 1]); // sorted by volume
  assert.equal(hollows[0].maxDepth, 0.6);
  assert.ok(Math.abs(hollows[0].volumeM3 - 1.5 * 400) < 1e-9);
  assert.equal(hollows[1].maxDepth, 0.9);
});

test("outletShares reports which side the drawn area drains out of", () => {
  // 3x3 window, centre column inside; everything drains south off the window
  const w = 3, h = 3;
  const dirs = Int32Array.from([3, 4, 5, 6, 7, 8, -1, -1, -1]);
  const inside = Uint8Array.from([0, 1, 0, 0, 1, 0, 0, 1, 0]);

  const shares = outletShares(dirs, inside, w, h);

  assert.deepEqual(shares, [{ side: "south", share: 1 }]);
});

test("summariseArea writes the headline sentences", () => {
  const lines = summariseArea({
    areaKm2: 1.23,
    hollows: [{ areaM2: 12000, maxDepth: 0.6, volumeM3: 3000, nearby: "Mile 3 Market, 100 m east" }],
    outlets: [{ side: "south-west", share: 0.72 }, { side: "east", share: 0.2 }],
    flood: { recurrentPct: 12.3, standingHa: 4.2, eventHa: 9.8, notImagedPct: 0, standingDate: "5 Oct 2026", eventDate: "29 Sep 2026" },
    sites: 2,
  });

  assert.equal(lines[0], "Drawn area: 1.2 km².");
  assert.equal(lines[1], "1 hollow where water collects: the largest is about 1.2 ha and up to 0.6 m deep, holding roughly 3,000 m³ (Mile 3 Market, 100 m east).");
  assert.equal(lines[2], "Water leaves the area mainly on the south-west side (72%), and on the east side (20%).");
  assert.equal(lines[3], "Radar: 12% of the area flooded in 3 or more rainy seasons; 9.8 ha under water on 29 Sep 2026; 4.2 ha still standing on 5 Oct 2026.");
  assert.equal(lines[4], "2 priority sites inside the area.");
});

test("summariseArea handles no hollows, no radar coverage and no sites", () => {
  const lines = summariseArea({
    areaKm2: 0.4, hollows: [], outlets: [{ side: "north", share: 1 }],
    flood: { recurrentPct: 0, standingHa: 0, eventHa: 0, notImagedPct: 100, standingDate: "5 Oct 2026", eventDate: "29 Sep 2026" },
    sites: 0,
  });
  assert.equal(lines[1], "No hollow deeper than 0.3 m in the 30 m elevation data: the ground should shed water unless drains are blocked.");
  assert.match(lines[3], /not imaged/);
  assert.equal(lines.length, 4);
});
