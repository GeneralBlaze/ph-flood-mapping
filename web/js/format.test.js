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
  assert.deepEqual(readState("", manifest), { lga: "obio-akpor", layer: "event", boundary: true, drainage: false, hand: false, at: null, area: null, site: null, pass: null, tab: "map" });
  assert.deepEqual(readState("?lga=port-harcourt", manifest), { lga: "port-harcourt", layer: "frequency", boundary: true, drainage: false, hand: false, at: null, area: null, site: null, pass: null, tab: "map" });
});

test("readState rejects unknown or unavailable values", () => {
  assert.deepEqual(readState("?lga=nowhere&layer=frequency", manifest), { lga: "obio-akpor", layer: "event", boundary: true, drainage: false, hand: false, at: null, area: null, site: null, pass: null, tab: "map" });
  assert.deepEqual(readState("?layer=<script>", manifest).layer, "event");
});

test("readState honours layer=none and boundary=0", () => {
  assert.deepEqual(readState("?layer=none&boundary=0", manifest), { lga: "obio-akpor", layer: "none", boundary: false, drainage: false, hand: false, at: null, area: null, site: null, pass: null, tab: "map" });
});

test("writeState produces a stable query string", () => {
  assert.equal(writeState({ lga: "obio-akpor", layer: "event", boundary: true, drainage: false, hand: false, site: null }), "?lga=obio-akpor&layer=event");
  assert.equal(writeState({ lga: "obio-akpor", layer: "none", boundary: false, drainage: false, hand: false, site: null }), "?lga=obio-akpor&layer=none&boundary=0");
});

test("readState reads terrain toggles", () => {
  const state = readState("?drainage=1&hand=1", manifest);
  assert.equal(state.drainage, true);
  assert.equal(state.hand, true);
});

test("writeState includes only enabled terrain toggles", () => {
  const query = writeState({ lga: "obio-akpor", layer: "event", boundary: true, drainage: true, hand: false });
  assert.equal(query, "?lga=obio-akpor&layer=event&drainage=1");
});

const withSuspects = {
  lgas: [
    {
      slug: "obio-akpor",
      name: "Obio/Akpor",
      frequency: { years: [2021, 2026], repeat_min_years: 3, hectares_by_years_flooded: { 3: 10 } },
      events: [{ date: "2026-09-29", flooded_ha: 1118.4 }],
      suspects: { counts: { suspect: 30, natural: 86, unclear: 105 }, list: "x", areas: "y" },
    },
  ],
};

test("suspects layer is the default when available", () => {
  assert.equal(readState("", withSuspects).layer, "suspects");
  assert.equal(readState("", manifest).layer, "event");
});

test("keyFigure for suspects counts sites", () => {
  const figure = keyFigure(withSuspects.lgas[0], "suspects");
  assert.equal(figure.value, "30 sites");
  assert.match(figure.caption, /should drain/);
});

test("readState reads a site for any flood layer but not for 'none'", () => {
  assert.equal(readState("?site=2", withSuspects).site, 2);
  assert.equal(readState("?site=2&layer=event", withSuspects).site, 2);
  assert.equal(readState("?site=2&layer=none", withSuspects).site, null);
  assert.equal(readState("?site=abc", withSuspects).site, null);
});

test("writeState includes the selected site", () => {
  const query = writeState({ lga: "obio-akpor", layer: "suspects", boundary: true, drainage: false, hand: false, site: 3 });
  assert.equal(query, "?lga=obio-akpor&layer=suspects&site=3");
});

const withStanding = {
  lgas: [
    {
      slug: "ikwerre",
      name: "Ikwerre",
      frequency: null,
      events: [],
      standing: { before: "2026-09-29", after: "2026-10-05", hectares: { drained: 10, standing: 465.1, new: 5 } },
    },
  ],
};

test("keyFigure for standing water reports hectares still wet on the later date", () => {
  const figure = keyFigure(withStanding.lgas[0], "standing");
  assert.equal(figure.value, "465 ha");
  assert.match(figure.caption, /5 Oct 2026/);
  assert.match(figure.caption, /29 Sep/);
});

test("readState defaults to standing water when it is the only layer", () => {
  assert.equal(readState("", withStanding).layer, "standing");
  assert.equal(readState("?layer=standing", withStanding).layer, "standing");
});

test("readState reads a tapped spot and rejects nonsense", () => {
  assert.deepEqual(readState("?at=4.94167,7.01140", withSuspects).at, [4.94167, 7.0114]);
  assert.equal(readState("?at=abc,7", withSuspects).at, null);
  assert.equal(readState("?at=95,7", withSuspects).at, null);
  assert.equal(readState("?at=4.9,7&site=2", withSuspects).site, null); // a spot replaces a site
});

test("writeState rounds a tapped spot to about a metre", () => {
  const query = writeState({ lga: "obio-akpor", layer: "suspects", boundary: true, drainage: false, hand: false, site: null, at: [4.941674, 7.011402] });
  assert.equal(query, "?lga=obio-akpor&layer=suspects&at=4.94167%2C7.01140");
});

test("readState reads a drawn area and rejects bad ones", () => {
  const ring = readState("?area=4.80,7.00;4.80,7.01;4.81,7.01", withSuspects).area;
  assert.deepEqual(ring, [[4.8, 7.0], [4.8, 7.01], [4.81, 7.01]]);
  assert.equal(readState("?area=4.80,7.00;4.80,7.01", withSuspects).area, null); // fewer than 3 corners
  assert.equal(readState("?area=4.8,x;4.8,7;4.9,7", withSuspects).area, null);
  const both = readState("?area=4.80,7.00;4.80,7.01;4.81,7.01&site=2&at=4.8,7", withSuspects);
  assert.equal(both.site, null);
  assert.equal(both.at, null); // a drawn area replaces a site or spot
});

test("writeState encodes a drawn area", () => {
  const query = writeState({ lga: "obio-akpor", layer: "suspects", boundary: true, drainage: false, hand: false, site: null, at: null,
    area: [[4.8, 7.0], [4.8, 7.01], [4.81, 7.01]] });
  assert.equal(query, "?lga=obio-akpor&layer=suspects&area=4.80000%2C7.00000%3B4.80000%2C7.01000%3B4.81000%2C7.01000");
});

test("readState keeps a valid pass and tab, and drops unknown ones", () => {
  const twoFloods = { lgas: [{ slug: "x", name: "X", frequency: null,
    events: [{ date: "2026-09-29", flooded_ha: 1 }, { date: "2026-08-14", flooded_ha: 2 }] }] };
  assert.equal(readState("?layer=event&pass=flood-2026-08-14", twoFloods).pass, "flood-2026-08-14");
  assert.equal(readState("?layer=event&pass=flood-1999-01-01", twoFloods).pass, null);
  assert.equal(readState("?tab=history", twoFloods).tab, "history");
  assert.equal(readState("?tab=evil", twoFloods).tab, "map");
});

test("writeState includes pass and tab only when they are not the defaults", () => {
  const base = { lga: "x", layer: "event", boundary: true, drainage: false, hand: false, site: null };
  assert.equal(writeState({ ...base, pass: null, tab: "map" }), "?lga=x&layer=event");
  assert.equal(writeState({ ...base, pass: "flood-2026-08-14", tab: "sites" }), "?lga=x&layer=event&pass=flood-2026-08-14&tab=sites");
});

test("keyFigure reports the chosen pass", () => {
  const lga = { events: [{ date: "2026-09-29", flooded_ha: 923.7 }, { date: "2026-08-14", flooded_ha: 410.2 }] };
  assert.equal(keyFigure(lga, "event", "flood-2026-08-14").value, "410 ha");
  assert.equal(keyFigure(lga, "event", null).value, "924 ha");
});
