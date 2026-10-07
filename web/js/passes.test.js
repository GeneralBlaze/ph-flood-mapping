import { test } from "node:test";
import assert from "node:assert/strict";

import { findPass, listPasses } from "./passes.js";

const LGA = {
  slug: "obio-akpor",
  events: [
    { date: "2026-09-29", flooded_ha: 923.7, overlay: "e1.png" },
    { date: "2026-08-14", flooded_ha: 410.2, overlay: "e0.png" },
  ],
  standing: { before: "2026-09-29", after: "2026-10-05", hectares: { standing: 465.1 }, overlay: "s.png" },
};

test("listPasses lists every flood and standing-water pass, newest first", () => {
  const passes = listPasses(LGA);
  assert.deepEqual(passes.map((p) => p.id), ["standing-2026-10-05", "flood-2026-09-29", "flood-2026-08-14"]);
  assert.deepEqual(passes.map((p) => p.layer), ["standing", "event", "event"]);
  assert.equal(passes[0].label, "5 Oct 2026 · water still standing");
  assert.equal(passes[1].label, "29 Sep 2026 · flood");
  assert.equal(passes[0].hectares, 465.1);
  assert.equal(passes[2].data.overlay, "e0.png");
});

test("listPasses accepts several standing-water comparisons and none at all", () => {
  const many = { ...LGA, standing: [LGA.standing, { ...LGA.standing, after: "2026-10-11", hectares: { standing: 12 } }] };
  assert.equal(listPasses(many)[0].id, "standing-2026-10-11");
  assert.deepEqual(listPasses({ events: [], standing: null }), []);
});

test("findPass picks the requested pass of the layer, else the newest of it", () => {
  assert.equal(findPass(LGA, "event", "flood-2026-08-14").date, "2026-08-14");
  assert.equal(findPass(LGA, "event", null).date, "2026-09-29");
  assert.equal(findPass(LGA, "event", "standing-2026-10-05").date, "2026-09-29"); // wrong layer: newest flood
  assert.equal(findPass(LGA, "standing", "nope").id, "standing-2026-10-05");
  assert.equal(findPass(LGA, "frequency", null), null);
});
