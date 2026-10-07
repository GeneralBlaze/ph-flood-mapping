import { listPasses } from "./passes.js";

// Drawn-area runs kept in this browser only (nothing is sent anywhere), plus the History catalogue that
// lists them next to the published radar passes. Storage can be full, blocked or wiped at any time, so
// every read and write tolerates failure and the page works without it.

export const HISTORY_KEY = "ph-flood:drawn-areas:v1";
export const MAX_RUNS = 25;

/** Stable id for an area: same LGA and corners = same run (a re-run updates it). */
export function areaId(lga, ring) {
  return `${lga}:${ring.map(([lat, lon]) => `${lat.toFixed(5)},${lon.toFixed(5)}`).join(";")}`;
}

function isRun(value) {
  return value && typeof value.id === "string" && typeof value.lga === "string" && Array.isArray(value.ring);
}

export function loadRuns(storage) {
  try {
    const parsed = JSON.parse(storage.getItem(HISTORY_KEY) ?? "[]");
    return Array.isArray(parsed) ? parsed.filter(isRun) : [];
  } catch {
    return [];
  }
}

function write(storage, runs) {
  // Full results carry overlay images: if storage is full, drop them from the oldest runs first
  let attempt = runs;
  for (let trimmed = runs.length; trimmed >= 0; trimmed--) {
    try {
      storage.setItem(HISTORY_KEY, JSON.stringify(attempt));
      return attempt;
    } catch {
      const oldestWithResult = attempt.findLastIndex((r, i) => i > 0 && r.full);
      if (oldestWithResult < 0) break;
      attempt = attempt.map((r, i) => (i === oldestWithResult ? { ...r, full: null } : r));
    }
  }
  return runs; // storage unavailable: the history simply is not kept
}

/** Adds or updates the run for this area; returns the saved list (newest first). */
export function saveRun(storage, run, now = new Date().toISOString()) {
  const id = areaId(run.lga, run.ring);
  const runs = loadRuns(storage);
  const previous = runs.find((r) => r.id === id);
  const merged = {
    full: null,
    ...previous,
    ...run,
    full: run.full ?? previous?.full ?? null,
    id,
    createdAt: previous?.createdAt ?? now,
    savedAt: now,
  };
  const next = [merged, ...runs.filter((r) => r.id !== id)]
    .sort((a, b) => b.savedAt.localeCompare(a.savedAt))
    .slice(0, MAX_RUNS);
  return write(storage, next);
}

export function removeRun(storage, id) {
  return write(storage, loadRuns(storage).filter((r) => r.id !== id));
}

/** Radar passes (from the manifest) and drawn-area runs, for one LGA or "all", newest first. */
export function catalogue({ manifest, runs, lga }) {
  const lgas = manifest.lgas.filter((l) => lga === "all" || l.slug === lga);
  const passes = lgas
    .flatMap((l) => listPasses(l).map((p) => ({ ...p, lga: l.slug, lgaName: l.name })))
    .sort((a, b) => b.date.localeCompare(a.date) || a.lgaName.localeCompare(b.lgaName));
  const areas = runs
    .filter((r) => lga === "all" || r.lga === lga)
    .sort((a, b) => b.savedAt.localeCompare(a.savedAt));
  return { passes, areas };
}
