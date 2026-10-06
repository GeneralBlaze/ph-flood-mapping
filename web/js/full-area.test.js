import { test } from "node:test";
import assert from "node:assert/strict";

import { FULL_STEPS, fullAnalysisEnabled, runFullAnalysis, siteLabel } from "./full-area.js";

const RING = [[4.80, 7.00], [4.80, 7.01], [4.81, 7.01]];

function fakeServer(responses) {
  const requests = [];
  const fetchImpl = async (url, options) => {
    const body = JSON.parse(options.body);
    requests.push({ url, body });
    const [status, payload] = responses[body.step];
    return { ok: status === 200, json: async () => payload };
  };
  return { requests, fetchImpl };
}

const OK = {
  history: [200, { token: "t1", line: "History.", mode: "published", overlay: { kind: "history" }, patches: [{ geometry: 1 }] }],
  latest: [200, { line: "Latest.", overlay: null, patches: [] }],
  routes: [200, { line: "Traced.", sites: [{ kind: "flood", recurrent: true }], routed: [{ route: [[7, 4.8]], rise_m: 0.4 }] }],
  buildings: [200, { buildings: [{ count: 2, footprints: [], centres: [[7.001, 4.801]] }] }],
  streets: [200, { stories: [{ story: ["Story."], nearby: "Market" }], streets_available: true }],
};

test("runs the five steps in order, carrying the token and each step's output", async () => {
  const { requests, fetchImpl } = fakeServer(OK);
  const progress = [];

  const result = await runFullAnalysis({ ring: RING, onProgress: (i) => progress.push(i), fetchImpl });

  assert.deepEqual(requests.map((r) => r.body.step), ["history", "latest", "routes", "buildings", "streets"]);
  assert.equal(requests[0].body.token, null);
  assert.ok(requests.slice(1).every((r) => r.body.token === "t1"));
  assert.deepEqual(requests[2].body.recurrent, [{ geometry: 1 }]);
  assert.deepEqual(requests[4].body.routed[0].centres, [[7.001, 4.801]]);
  assert.deepEqual(progress, [0, 1, 2, 3, 4, FULL_STEPS.length]);
  assert.deepEqual(result.lines, ["History.", "Latest.", "Traced."]);
  assert.equal(result.overlays.length, 1);
  assert.equal(result.sites[0].buildings.count, 2);
  assert.deepEqual(result.sites[0].story, ["Story."]);
  assert.equal(result.sites[0].nearby, "Market");
  assert.equal(result.sites[0].riseM, 0.4);
});

test("stops at a failed step with the server's message", async () => {
  const { requests, fetchImpl } = fakeServer({ ...OK, latest: [429, { error: "Too many full analyses." }] });
  await assert.rejects(runFullAnalysis({ ring: RING, onProgress: () => {}, fetchImpl }), /Too many full analyses/);
  assert.equal(requests.length, 2);
});

test("a response that is not JSON gives a generic message", async () => {
  const fetchImpl = async () => ({ ok: false, json: async () => { throw new SyntaxError("x"); } });
  await assert.rejects(runFullAnalysis({ ring: RING, onProgress: () => {}, fetchImpl }), /unavailable right now/);
});

test("siteLabel describes each kind of site", () => {
  assert.equal(siteLabel({ kind: "hollow" }), "Hollow in the ground");
  assert.equal(siteLabel({ kind: "flood", recurrent: true, latest: true }), "Floods most years, and wet on the latest pass");
  assert.equal(siteLabel({ kind: "flood", recurrent: true }), "Floods most years");
  assert.equal(siteLabel({ kind: "flood", latest: true }), "Wet on the latest radar pass");
});

test("fullAnalysisEnabled is true only when the server says so", async () => {
  assert.equal(await fullAnalysisEnabled(async () => ({ ok: true, json: async () => ({ enabled: true }) })), true);
  assert.equal(await fullAnalysisEnabled(async () => ({ ok: true, json: async () => ({ enabled: false }) })), false);
  assert.equal(await fullAnalysisEnabled(async () => ({ ok: false, json: async () => ({}) })), false);
  assert.equal(await fullAnalysisEnabled(async () => { throw new TypeError("offline"); }), false);
});
