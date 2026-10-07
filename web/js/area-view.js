import { el } from "./dom.js";
import { formatHectares } from "./format.js";
import { STEPS, analyseArea } from "./area-runner.js";
import { polygonAreaKm2 } from "./area-analysis.js";
import { fullAnalysisEnabled, runFullAnalysis } from "./full-area.js";
import { resetFull, showFullError, showFullProgress, showFullResult } from "./full-report.js";
import { areaId, loadRuns, saveRun } from "./history-store.js";
import { nearbyLandmarks } from "./local-terrain.js";

// The drawn-area report: the instant browser analysis, the optional full (server) analysis, and saving
// both to this browser's History so an area can be reopened without running anything again.
const FULL_MAX_KM2 = 10; // the server's limit (analysis/area_request.py)
const PLACE_MAX_M = 1500;
const PNG_DATA_URI = /^data:image\/png;base64,[A-Za-z0-9+/=]+$/;
const savedTime = new Intl.DateTimeFormat("en-NG", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });
const $ = (id) => document.getElementById(id);
const isPhone = () => window.matchMedia("(max-width: 768px)").matches;

/** A saved full result is only drawn if it still has the expected shape (storage is user-editable). */
function usableSaved(full) {
  return full && Array.isArray(full.lines) && Array.isArray(full.sites) && Array.isArray(full.overlays)
    && full.overlays.every((o) => typeof o.url === "string" && PNG_DATA_URI.test(o.url));
}

function placeName(ring, landmarks) {
  const lat = ring.reduce((s, p) => s + p[0], 0) / ring.length;
  const lon = ring.reduce((s, p) => s + p[1], 0) / ring.length;
  const near = nearbyLandmarks(lat, lon, landmarks, PLACE_MAX_M, 1);
  return near ? `Near ${near.split(", ")[0]}` : `Area at ${lat.toFixed(3)}, ${lon.toFixed(3)}`;
}

export function createAreaView({ map, storage, dataRoot, fetchJson, reducedMotion, getState, setState, onSaved }) {
  let shownKey = null; // area whose report is showing
  let fullRun = null; // { controller } of the full run in progress or shown
  let context = null; // { lga, landmarks } for the area on show
  const fullIntro = $("full-intro").textContent.trim();
  $("full-run").hidden = true;
  fullAnalysisEnabled().then((enabled) => { $("full-run").hidden = !enabled; });

  const keyOf = (state) => (state.area ? areaId(state.lga, state.area) : null);

  function setProgress(step) {
    const percent = Math.round((step / STEPS.length) * 100);
    $("area-progress").hidden = false;
    $("area-progress").setAttribute("aria-valuenow", String(percent));
    $("area-progress-bar").style.setProperty("width", `${percent}%`);
    $("area-step").textContent = step < STEPS.length ? `Step ${step + 1} of ${STEPS.length}: ${STEPS[step]}…` : "Done.";
  }

  function renderHollowList(hollows) {
    $("area-hollows").replaceChildren(
      ...hollows.map((hollow, i) =>
        el("li", {}, [
          el("button", {
            class: "site-row",
            type: "button",
            "aria-label": `Hollow ${i + 1}, up to ${hollow.maxDepth.toFixed(1)} m deep. Show on map`,
            onclick: () => setState({ at: [hollow.lat, hollow.lon], area: null, site: null }),
          }, [
            el("span", { class: "hotspot__rank", text: String(i + 1) }),
            el("span", { class: "site-row__body" }, [
              el("span", { class: "site-row__place", text: `Hollow up to ${hollow.maxDepth.toFixed(1)} m deep` }),
              ...(hollow.nearby ? [el("span", { class: "site-row__near", text: hollow.nearby.split(" · ")[0] })] : []),
            ]),
            el("span", { class: "site-row__area", text: formatHectares(hollow.areaM2 / 1e4) }),
          ]),
        ])
      )
    );
  }

  function save(ring, lga, landmarks, extra) {
    saveRun(storage, {
      lga: lga.slug, lgaName: lga.name, ring, areaKm2: polygonAreaKm2(ring), place: placeName(ring, landmarks), ...extra,
    });
    onSaved();
  }

  function focusSite(result, i) {
    // On phones the sheet covers the map: lower it first so the site is in view
    if (isPhone() && $("sheet").dataset.expanded === "true") $("sheet-toggle").click();
    map.focusGeometry(result.sites[i].geometry, reducedMotion.matches);
  }

  function showFull(result, savedAt) {
    showFullResult(result, (i) => focusSite(result, i));
    if (savedAt) {
      $("full-step").textContent = `Saved result from ${savedTime.format(new Date(savedAt))}.`;
      $("full-start").hidden = false;
      $("full-start").textContent = "Run again for the latest radar";
    }
    map.hideAreaRunoff();
    map.showFull(result, reducedMotion.matches);
  }

  function stopFull() {
    fullRun?.controller.abort();
    fullRun = null;
    map.clearFull();
  }

  function prepareFull(state) {
    const km2 = polygonAreaKm2(state.area);
    const tooBig = km2 > FULL_MAX_KM2;
    $("full-start").textContent = "Run full analysis";
    resetFull({
      startable: !tooBig,
      intro: tooBig
        ? `The full analysis takes areas up to ${FULL_MAX_KM2} km²; this one is ${km2.toFixed(0)} km². Draw a smaller area to run it.`
        : fullIntro,
    });
    const saved = loadRuns(storage).find((r) => r.id === keyOf(state));
    if (usableSaved(saved?.full)) showFull(saved.full, saved.savedAt);
  }

  async function startFull() {
    const state = getState();
    if (!state.area || !context) return;
    const { lga, landmarks } = context;
    stopFull();
    const controller = new AbortController();
    fullRun = { controller };
    try {
      const result = await runFullAnalysis({ ring: state.area, onProgress: showFullProgress, signal: controller.signal });
      if (fullRun?.controller !== controller) return;
      showFull(result, null);
      save(state.area, lga, landmarks, { full: result });
    } catch (error) {
      if (controller.signal.aborted || fullRun?.controller !== controller) return;
      showFullError(error instanceof Error ? error.message : "The full analysis failed; please try again.");
    }
  }

  function showError(message) {
    $("area-progress").hidden = true;
    $("area-step").textContent = "";
    $("area-lines").replaceChildren(el("p", { class: "status status--error", role: "alert", text: message }));
  }

  /** Called on every render: runs the instant analysis once per drawn shape. */
  async function render(lga, landmarks, basemap) {
    const state = getState();
    const key = keyOf(state);
    $("area-report").hidden = !key;
    if (!key) {
      shownKey = null;
      context = null;
      stopFull();
      map.clearArea();
      return;
    }
    if (shownKey === key) return;
    shownKey = key;
    context = { lga, landmarks };
    stopFull();
    prepareFull(state);
    // On phones the report lives in the bottom sheet: open it so the progress bar is visible
    if (isPhone() && $("sheet").dataset.expanded !== "true") $("sheet-toggle").click();
    $("area-lines").replaceChildren();
    $("area-hollows").replaceChildren();
    $("sheet-content").scrollTop = 0;
    map.setBasemap(basemap);
    map.showArea({ ring: state.area }, reducedMotion.matches);
    map.focusArea(state.area, reducedMotion.matches);
    try {
      const sites = lga.suspects ? await fetchJson(lga.suspects.list) : [];
      const report = await analyseArea({
        ring: state.area, lga, dataRoot, landmarks, sites, onProgress: setProgress, reducedMotion: reducedMotion.matches,
      });
      if (keyOf(getState()) !== key) return; // a newer area or view replaced this one
      $("area-progress").hidden = true;
      $("area-step").textContent = "";
      $("area-lines").replaceChildren(...report.lines.map((line) => el("p", { text: line })));
      renderHollowList(report.hollows);
      if (!fullRun && !$("full-sites").childElementCount) map.showArea({ ring: state.area, ...report }, reducedMotion.matches);
      save(state.area, lga, landmarks, { lines: report.lines });
    } catch (error) {
      if (keyOf(getState()) !== key) return;
      showError(error instanceof Error ? error.message : "The area could not be analysed.");
      save(state.area, lga, landmarks, { lines: [] });
    }
  }

  $("full-start").addEventListener("click", startFull);
  return { render };
}
