import { test } from "node:test";
import assert from "node:assert/strict";

import { formatHectares, formatDate, keyFigure } from "./format.js";
import { readState, writeState } from "./state.js";

const manifest = {
  lgas: [
    { slug: "obio-akpor", name: "Obio/Akpor", frequency: null, events: [{ date: "2026-09-29", flooded_ha: 1118.4 }] },
    {
      slug: "port-harcourt",
      name: "Port-Harcourt",
      frequency: { years: [2021, 2026], repeat_min_years: 3, hectares_by_years_flooded: { 1: 50, 2: 20, 3: 10, 4: 5 } },
      events: [],
    },
  ],
};

test("formatHectares groups thousands and keeps a decimal for small areas", () => {
  assert.equal(formatHectares(1118.4), "1,118 ha");
  assert.equal(formatHectares(7.62), "7.6 ha");
});

test("formatDate renders a readable day", () => {
  assert.equal(formatDate("2026-09-29"), "29 Sep 2026");
});

test("keyFigure for an event reports flooded area on the date", () => {
  const figure = keyFigure(manifest.lgas[0], "event");
  assert.equal(figure.value, "1,118 ha");
  assert.match(figure.caption, /29 Sep 2026/);
});

test("keyFigure for frequency sums hectares at or above the repeat threshold", () => {
  const figure = keyFigure(manifest.lgas[1], "frequency");
  assert.equal(figure.value, "15.0 ha");
  assert.match(figure.caption, /3 or more/);
});

test("readState defaults to first LGA and the best available layer", () => {
  assert.deepEqual(readState("", manifest), { lga: "obio-akpor", layer: "event", boundary: true });
  assert.deepEqual(readState("?lga=port-harcourt", manifest), { lga: "port-harcourt", layer: "frequency", boundary: true });
});

test("readState rejects unknown or unavailable values", () => {
  assert.deepEqual(readState("?lga=nowhere&layer=frequency", manifest), { lga: "obio-akpor", layer: "event", boundary: true });
  assert.deepEqual(readState("?layer=<script>", manifest).layer, "event");
});

test("readState honours layer=none and boundary=0", () => {
  assert.deepEqual(readState("?layer=none&boundary=0", manifest), { lga: "obio-akpor", layer: "none", boundary: false });
});

test("writeState produces a stable query string", () => {
  assert.equal(writeState({ lga: "obio-akpor", layer: "event", boundary: true }), "?lga=obio-akpor&layer=event");
  assert.equal(writeState({ lga: "obio-akpor", layer: "none", boundary: false }), "?lga=obio-akpor&layer=none&boundary=0");
});
