import { test } from "node:test";
import assert from "node:assert/strict";

import { arrowFrame, lineWidth, phaseFor } from "./flow-math.js";

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
