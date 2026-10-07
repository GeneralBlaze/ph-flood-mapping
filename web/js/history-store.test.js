import { test } from "node:test";
import assert from "node:assert/strict";

import { MAX_RUNS, areaId, catalogue, loadRuns, removeRun, saveRun } from "./history-store.js";

function memoryStorage({ quotaBytes = Infinity } = {}) {
  const data = new Map();
  return {
    getItem: (k) => (data.has(k) ? data.get(k) : null),
    setItem: (k, v) => {
      if (v.length > quotaBytes) throw Object.assign(new Error("full"), { name: "QuotaExceededError" });
      data.set(k, v);
    },
    removeItem: (k) => data.delete(k),
  };
}

const RING = [[4.80, 7.00], [4.80, 7.01], [4.81, 7.01]];
const run = (over = {}) => ({ lga: "obio-akpor", lgaName: "Obio/Akpor", ring: RING, areaKm2: 0.6, place: "Near Mile 3",
                              lines: ["Drawn area: 0.6 km²."], ...over });

test("saveRun adds a run and loadRuns reads it back, newest first", () => {
  const storage = memoryStorage();
  saveRun(storage, run(), "2026-10-07T09:00:00Z");
  saveRun(storage, run({ ring: [[4.9, 7.0], [4.9, 7.1], [4.95, 7.1]] }), "2026-10-07T10:00:00Z");
  const runs = loadRuns(storage);
  assert.equal(runs.length, 2);
  assert.equal(runs[0].savedAt, "2026-10-07T10:00:00Z");
  assert.equal(runs[1].id, areaId("obio-akpor", RING));
});

test("saving the same area again updates it and keeps an earlier full result unless replaced", () => {
  const storage = memoryStorage();
  saveRun(storage, run({ full: { lines: ["Radar…"] } }), "2026-10-07T09:00:00Z");
  saveRun(storage, run({ lines: ["Drawn area: 0.6 km².", "2 hollows."] }), "2026-10-07T11:00:00Z");
  const [only] = loadRuns(storage);
  assert.equal(loadRuns(storage).length, 1);
  assert.deepEqual(only.lines, ["Drawn area: 0.6 km².", "2 hollows."]);
  assert.deepEqual(only.full, { lines: ["Radar…"] });
  assert.equal(only.createdAt, "2026-10-07T09:00:00Z");
});

test("the list is capped, dropping the oldest", () => {
  const storage = memoryStorage();
  for (let i = 0; i < MAX_RUNS + 3; i++) {
    saveRun(storage, run({ ring: [[4.8 + i / 1000, 7.0], [4.8, 7.01], [4.81, 7.01]] }), `2026-10-07T00:${String(i).padStart(2, "0")}:00Z`);
  }
  const runs = loadRuns(storage);
  assert.equal(runs.length, MAX_RUNS);
  assert.equal(runs.at(-1).savedAt, "2026-10-07T00:03:00Z");
});

test("when storage is full, older saved full results are dropped before giving up", () => {
  const storage = memoryStorage({ quotaBytes: 2000 })   // both results ~2,400 bytes; one ~1,500;
  saveRun(storage, run({ full: { overlay: "x".repeat(900) } }), "2026-10-07T09:00:00Z");
  saveRun(storage, run({ ring: [[4.9, 7.0], [4.9, 7.1], [4.95, 7.1]], full: { overlay: "y".repeat(900) } }), "2026-10-07T10:00:00Z");
  const runs = loadRuns(storage);
  assert.equal(runs.length, 2);
  assert.ok(runs[0].full);              // the newest keeps its result
  assert.equal(runs[1].full, null);     // the older one was trimmed to make room
});

test("unreadable or blocked storage gives an empty history instead of an error", () => {
  const broken = { getItem: () => { throw new Error("blocked"); }, setItem: () => { throw new Error("blocked"); } };
  assert.deepEqual(loadRuns(broken), []);
  assert.doesNotThrow(() => saveRun(broken, run(), "2026-10-07T09:00:00Z"));
  const junk = memoryStorage();
  junk.setItem("ph-flood:drawn-areas:v1", "{not json");
  assert.deepEqual(loadRuns(junk), []);
});

test("removeRun deletes one run", () => {
  const storage = memoryStorage();
  saveRun(storage, run(), "2026-10-07T09:00:00Z");
  removeRun(storage, areaId("obio-akpor", RING));
  assert.deepEqual(loadRuns(storage), []);
});

test("catalogue filters radar passes and drawn areas by LGA, newest first", () => {
  const manifest = { lgas: [
    { slug: "obio-akpor", name: "Obio/Akpor", events: [{ date: "2026-09-29", flooded_ha: 923.7 }],
      standing: { before: "2026-09-29", after: "2026-10-05", hectares: { standing: 465.1 } } },
    { slug: "ikwerre", name: "Ikwerre", events: [{ date: "2026-09-30", flooded_ha: 12 }], standing: null },
  ] };
  const runs = [{ id: "a", lga: "ikwerre", savedAt: "2026-10-07T10:00:00Z" }, { id: "b", lga: "obio-akpor", savedAt: "2026-10-06T10:00:00Z" }];

  const all = catalogue({ manifest, runs, lga: "all" });
  assert.deepEqual(all.passes.map((p) => `${p.lgaName} ${p.id}`),
    ["Obio/Akpor standing-2026-10-05", "Ikwerre flood-2026-09-30", "Obio/Akpor flood-2026-09-29"]);
  assert.deepEqual(all.areas.map((r) => r.id), ["a", "b"]);

  const one = catalogue({ manifest, runs, lga: "ikwerre" });
  assert.deepEqual(one.passes.map((p) => p.id), ["flood-2026-09-30"]);
  assert.deepEqual(one.areas.map((r) => r.id), ["a"]);
});
