import { test } from "node:test";
import assert from "node:assert/strict";

import { arrowCount, arrowFrame, lineWidth, phaseFor, zoomScale } from "./flow-math.js";

test("arrowFrame moves from start to end and fades at both ends", () => {
  const a = arrowFrame({ x: 0, y: 0 }, { x: 10, y: 0 }, 0.5);
  assert.deepEqual([a.x, a.y], [5, 0]);
  assert.equal(a.alpha, 1);
  assert.equal(arrowFrame({ x: 0, y: 0 }, { x: 10, y: 0 }, 0).alpha, 0);
});

test("arrowFrame angle follows the segment direction", () => {
  const down = arrowFrame({ x: 0, y: 0 }, { x: 0, y: 10 }, 0.5);
  assert.ok(Math.abs(down.angle - Math.PI / 2) < 1e-9);
});

test("phaseFor is deterministic and within [0, 1)", () => {
  assert.equal(phaseFor(42), phaseFor(42));
  for (let i = 0; i < 100; i++) {
    const p = phaseFor(i);
    assert.ok(p >= 0 && p < 1);
  }
});

test("lineWidth grows with drained area but stays bounded", () => {
  assert.ok(lineWidth(100) > lineWidth(1));
  assert.ok(lineWidth(1e6) <= 4);
  assert.ok(lineWidth(1) >= 1);
});

test("zoomScale is 1 at city scale and grows, bounded, at street level", () => {
  assert.equal(zoomScale(12), 1);
  assert.equal(zoomScale(13), 1);
  assert.ok(zoomScale(16) > zoomScale(15));
  assert.ok(zoomScale(16) >= 2);
  assert.ok(zoomScale(22) <= 3.5);
});

test("arrowCount spaces several arrows along long segments", () => {
  assert.equal(arrowCount(10, 60), 0);   // too short for any arrow
  assert.equal(arrowCount(40, 60), 1);
  assert.equal(arrowCount(200, 60), 3);
  assert.equal(arrowCount(10_000, 60), 6); // capped
});
