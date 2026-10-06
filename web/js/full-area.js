// Full analysis of a drawn area on the server (Earth Engine): five requests, one per step, so each
// fits the server's time limit and the progress bar shows real progress. Rings are [lat, lon] pairs.

export const FULL_STEPS = [
  "Reading six rainy seasons of radar",
  "Reading the latest radar pass",
  "Tracing where the water should go",
  "Finding buildings in the way",
  "Naming streets and writing the report",
];

const ENDPOINT = "/api/area";
const UNAVAILABLE = "The full analysis is unavailable right now; please try again later.";

/** One request; throws an Error with the server's message (or a generic one) on failure. */
async function postStep(fetchImpl, body, signal) {
  const response = await fetchImpl(ENDPOINT, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
    signal,
  });
  let payload = null;
  try {
    payload = await response.json();
  } catch {
    payload = null;
  }
  if (!response.ok || !payload) throw new Error(payload?.error ?? UNAVAILABLE);
  return payload;
}

/** Merges the five step results into what the report and map need. */
export function combineFull({ history, latest, routes, buildings, streets }) {
  return {
    lines: [history.line, latest.line, routes.line].filter(Boolean),
    mode: history.mode,
    overlays: [history.overlay, latest.overlay].filter(Boolean),
    streetsAvailable: streets.streets_available !== false,
    sites: routes.sites.map((site, i) => ({
      ...site,
      route: routes.routed[i]?.route ?? [],
      riseM: routes.routed[i]?.rise_m ?? 0,
      buildings: buildings.buildings[i] ?? { count: 0, footprints: [] },
      story: streets.stories[i]?.story ?? [],
      nearby: streets.stories[i]?.nearby ?? null,
    })),
  };
}

/** Runs all steps for ring; onProgress(i) before step i and onProgress(FULL_STEPS.length) when done. */
export async function runFullAnalysis({ ring, onProgress, signal, fetchImpl = fetch }) {
  let token = null;
  const step = (name, extra = {}) => postStep(fetchImpl, { step: name, ring, token, ...extra }, signal);

  onProgress(0);
  const history = await step("history");
  token = history.token;
  onProgress(1);
  const latest = await step("latest");
  onProgress(2);
  const routes = await step("routes", { recurrent: history.patches, latest: latest.patches });
  onProgress(3);
  const buildings = await step("buildings", { sites: routes.sites, routed: routes.routed });
  onProgress(4);
  const routed = routes.routed.map((r, i) => ({ ...r, centres: buildings.buildings[i]?.centres ?? [] }));
  const streets = await step("streets", { sites: routes.sites, routed });
  onProgress(FULL_STEPS.length);
  return combineFull({ history, latest, routes, buildings, streets });
}

/** True when the server has the full analysis switched on; false on any failure (e.g. a static host). */
export async function fullAnalysisEnabled(fetchImpl = fetch) {
  try {
    const response = await fetchImpl(ENDPOINT, { method: "GET" });
    return response.ok && (await response.json()).enabled === true;
  } catch {
    return false;
  }
}

/** Label for a site card: what kind of water was found there. */
export function siteLabel(site) {
  if (site.kind === "hollow") return "Hollow in the ground";
  if (site.recurrent && site.latest) return "Floods most years, and wet on the latest pass";
  if (site.recurrent) return "Floods most years";
  return "Wet on the latest radar pass";
}
