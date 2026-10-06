import { el } from "./dom.js";
import { formatDate, formatHectares } from "./format.js";
import { createMap } from "./map.js";
import { renderFigure, renderHotspots, renderLayerControls, renderLgaSelect, renderTerrainControls } from "./panel.js";
import { defaultLayer, isLayerAvailable, readState, writeState } from "./state.js";
import { nearbyLandmarks } from "./local-terrain.js";
import { analyseSpot } from "./spot-terrain.js";
import { STEPS, analyseArea } from "./area-runner.js";
import { open3d } from "./view3d.js";

const DATA_ROOT = "data/";
const NEARBY_MAX_M = 600;
const NEARBY_LIMIT = 3;
const SITE_OVERLAY_OPACITY = 0.45; // at street zoom the imagery under the flood shading must stay visible
const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)");
const cache = new Map();

const $ = (id) => document.getElementById(id);

async function fetchJson(path) {
  if (cache.has(path)) return cache.get(path);
  const response = await fetch(DATA_ROOT + path);
  if (!response.ok) throw new Error(`Could not load ${path} (HTTP ${response.status})`);
  const data = await response.json();
  cache.set(path, data);
  return data;
}

function validateManifest(manifest) {
  const ok =
    manifest &&
    Array.isArray(manifest.lgas) &&
    manifest.lgas.length > 0 &&
    manifest.lgas.every((l) => typeof l.slug === "string" && typeof l.name === "string" && Array.isArray(l.events));
  if (!ok) throw new Error("The map data is in an unexpected format.");
  return manifest;
}

function showError(message) {
  $("figure").replaceChildren(el("p", { class: "status status--error", role: "alert", text: message }));
}

function layerData(lga, layer) {
  if (layer === "suspects" && lga.suspects) {
    const base = lga.frequency;
    return {
      overlay: base?.overlay,
      bounds: base?.bounds,
      hotspots: lga.suspects.list,
      areas: lga.suspects.areas,
      subtitle: "that floods where it should drain",
      alt: "Suspected drainage problems over years flooded",
      overlayOpacity: 0.35,
    };
  }
  if (layer === "standing" && lga.standing) {
    const w = lga.standing;
    return { ...w, subtitle: `still under water on ${formatDate(w.after)}`, alt: `Water still standing on ${formatDate(w.after)}` };
  }
  if (layer === "frequency" && lga.frequency) {
    return { ...lga.frequency, subtitle: `flooded in ${lga.frequency.repeat_min_years}+ seasons`, alt: "Years flooded" };
  }
  if (layer === "event" && lga.events[0]) {
    const e = lga.events[0];
    return { ...e, subtitle: `under water on ${formatDate(e.date)}`, alt: `Flooding on ${formatDate(e.date)}` };
  }
  return null;
}

// Show only the key items that this site view actually draws
function renderSiteKey({ area, route }) {
  $("key-area").hidden = !area;
  $("key-route").hidden = !route;
  $("key-buildings").hidden = !route;
  $("site-key").hidden = !area && !route;
}

const siteTitle = (site) => (site.rank ? `${site.rank}. ${site.place}` : site.place);

// Drainage assessment (priority sites) plus the local-ground sentence (any site or spot)
function renderSiteReport(site, groundSentence) {
  const lines = [...(site?.story ?? [])];
  if (groundSentence) lines.push(groundSentence);
  $("site-report").hidden = !lines.length;
  if (!lines.length) return;
  $("site-report-place").textContent = siteTitle(site);
  $("site-report-story").replaceChildren(...lines.map((line) => el("p", { text: line })));
  $("sheet-content").scrollTop = 0;
}

const cssVar = (name) => getComputedStyle(document.documentElement).getPropertyValue(name).trim();

// The 3D view is a modal over the map; currentSite holds what it needs for the open site.
function setup3d(getSite) {
  const dialog = $("view3d");
  const opener = $("site-3d");
  let close = null;

  async function show() {
    const site = getSite();
    if (!site) return;
    dialog.hidden = false;
    $("view3d-title").textContent = `3D view · ${siteTitle(site.hotspot)}`;
    $("view3d-close").focus();
    dialog.querySelectorAll("[data-for]").forEach((li) => {
      li.hidden = li.dataset.for !== (site.isSuspect ? "suspect" : "layer");
    });
    try {
      const areas = site.isSuspect ? await fetchJson(site.lga.suspects.areas) : { features: [] };
      close = await open3d({
        container: $("view3d-map"),
        view3d: site.lga.view3d,
        dataRoot: DATA_ROOT,
        hotspot: site.hotspot,
        area: areas.features.find((f) => f.properties.rank === site.hotspot.rank) ?? null,
        route: site.route,
        overlay: site.isSuspect ? null : site.overlay,
        withBuildings: site.isSuspect,
        colours: { signal: cssVar("--signal"), channel: cssVar("--channel"), obstruction: cssVar("--obstruction") },
        reducedMotion: reducedMotion.matches,
      });
    } catch (error) {
      $("view3d-map").replaceChildren(
        el("p", { class: "status status--error", role: "alert", text: "The 3D view could not be loaded on this device." })
      );
    }
  }

  function hide() {
    close?.();
    close = null;
    $("view3d-map").replaceChildren();
    dialog.hidden = true;
    opener.focus();
  }

  opener.addEventListener("click", show);
  $("view3d-close").addEventListener("click", hide);
  dialog.addEventListener("keydown", (e) => {
    if (e.key === "Escape") hide();
  });
}

function setupSheetCollapse() {
  const button = $("sheet-collapse");
  const sheet = $("sheet");
  button.addEventListener("click", () => {
    const collapsed = document.body.classList.toggle("sheet-collapsed");
    button.setAttribute("aria-expanded", String(!collapsed));
    button.setAttribute("aria-label", collapsed ? "Show panel" : "Hide panel");
    sheet.inert = collapsed; // hidden panel must not take keyboard focus
  });
}

function setupSheetToggle() {
  const sheet = $("sheet");
  const toggle = $("sheet-toggle");
  toggle.addEventListener("click", () => {
    const expanded = sheet.dataset.expanded !== "true";
    sheet.dataset.expanded = String(expanded);
    toggle.setAttribute("aria-expanded", String(expanded));
    toggle.textContent = expanded ? "Show map" : "Details";
  });
}

async function start() {
  setupSheetToggle();
  setupSheetCollapse();
  const map = createMap($("map"));

  let manifest;
  try {
    manifest = validateManifest(await fetchJson("manifest.json"));
  } catch (error) {
    $("lga-title").textContent = "Map data unavailable";
    showError(error instanceof Error ? error.message : "Could not load the map data.");
    return;
  }

  $("generated").textContent = `Data updated ${formatDate(manifest.generated.slice(0, 10))}.`;
  let state = readState(window.location.search, manifest);
  let renderToken = 0;
  let focusedSite = null; // avoids re-flying to the same site on unrelated re-renders
  let basemap = "satellite";
  let keepView = false; // set by deselect: stay at this zoom and imagery
  let currentSite = null; // { lga, hotspot, route } while a site is open
  let ground = { key: null, sentence: null }; // local-terrain sentence for the open site or spot

  const setBasemap = (kind) => {
    basemap = kind;
    $("basemap-satellite").setAttribute("aria-pressed", String(kind === "satellite"));
    $("basemap-street").setAttribute("aria-pressed", String(kind === "street"));
    if (state.site || state.at || state.area) map.setBasemap(kind);
  };

  // A tapped spot behaves like a site without analysis of its own
  function spotSite(landmarks) {
    const [lat, lon] = state.at;
    return { rank: null, lat, lon, place: `Selected spot (${lat.toFixed(4)}, ${lon.toFixed(4)})`,
             nearby: nearbyLandmarks(lat, lon, landmarks, NEARBY_MAX_M, NEARBY_LIMIT) };
  }

  async function showGround(lga, site, key, token) {
    // Priority sites already have their street-level route; trace one for any other point or spot
    if (!lga.view3d || currentSite?.route) return;
    try {
      const local = await analyseSpot(lga.view3d, DATA_ROOT, site.lat, site.lon);
      if (token !== renderToken) return;
      map.showLocal(local, reducedMotion.matches);
      ground = { key, sentence: local.sentence };
      renderSiteReport(site, ground.sentence);
    } catch {
      // Outside the terrain tiles (beyond the analysed LGAs): the satellite view still works
    }
  }

  async function renderSite(lga, hotspots, data, landmarks, token) {
    const hotspot = state.at ? spotSite(landmarks) : state.site ? hotspots.find((h) => h.rank === state.site) : null;
    $("site-bar").hidden = !hotspot;
    $("site-rank").hidden = !hotspot?.rank;
    renderSiteReport(hotspot);
    $("site-3d").hidden = !(hotspot && lga.view3d);  // terrain exists for analysed LGAs; any point can use it
    if (!hotspot) {
      currentSite = null;
      focusedSite = null;
      map.clearSite();
      map.setBasemap(state.area || keepView ? basemap : "street");
      keepView = false;
      return;
    }
    $("site-rank").textContent = hotspot.rank ? String(hotspot.rank) : "";
    $("site-name").textContent = hotspot.place;
    $("site-nearby").hidden = !hotspot.nearby;
    $("site-nearby").textContent = hotspot.nearby ? `Near ${hotspot.nearby}` : "";
    // Drainage routes and route buildings exist only for priority sites
    const suspects = state.layer === "suspects" && hotspot.rank ? lga.suspects : null;
    const [routes, obstructions] = await Promise.all([
      suspects?.routes ? fetchJson(suspects.routes) : Promise.resolve(null),
      suspects?.obstructions ? fetchJson(suspects.obstructions) : Promise.resolve(null),
    ]);
    const route = routes?.features.find((f) => f.properties.rank === hotspot.rank) ?? null;
    renderSiteKey({ area: Boolean(suspects), route: Boolean(route) });
    currentSite = {
      lga,
      hotspot,
      route,
      isSuspect: Boolean(suspects),
      overlay: data?.overlay ? { url: DATA_ROOT + data.overlay, bounds: data.bounds } : null,
    };
    const buildings = obstructions
      ? { ...obstructions, features: obstructions.features.filter((f) => f.properties.rank === hotspot.rank) }
      : null;
    map.setBasemap(basemap);
    map.showSite({ route, buildings, reducedMotion: reducedMotion.matches });
    const key = state.at ? `at:${state.at.join(",")}` : `${lga.slug}:${state.layer}:${hotspot.rank}`;
    if (ground.key === key) renderSiteReport(hotspot, ground.sentence); // unrelated re-render: keep it
    if (focusedSite === key) return;
    focusedSite = key;
    map.clearLocal();
    if (state.at) {
      map.showSpot(hotspot.lat, hotspot.lon, deselect);
      map.focusSpot(hotspot.lat, hotspot.lon, reducedMotion.matches);
    } else {
      map.focusSite(hotspot, route, reducedMotion.matches);
    }
    await showGround(lga, hotspot, key, token);
  }

  // Drawn-area report: runs once per drawn shape, with a progress bar while it works
  let areaDone = null; // key of the area whose report is showing
  function areaKey() {
    return state.area ? `${state.lga}:${state.area.map((c) => c.join(",")).join(";")}` : null;
  }

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
            class: "hotspot",
            type: "button",
            "aria-label": `Hollow ${i + 1}, up to ${hollow.maxDepth.toFixed(1)} m deep. Show on map`,
            onclick: () => setState({ at: [hollow.lat, hollow.lon], area: null, site: null }),
          }, [
            el("span", { class: "hotspot__rank", text: String(i + 1) }),
            el("span", { class: "hotspot__place" }, [
              `Hollow up to ${hollow.maxDepth.toFixed(1)} m deep`,
              ...(hollow.nearby ? [el("span", { class: "hotspot__nearby", text: `Near ${hollow.nearby}` })] : []),
            ]),
            el("span", { class: "hotspot__area", text: formatHectares(hollow.areaM2 / 1e4) }),
          ]),
        ])
      )
    );
  }

  async function renderArea(lga, landmarks) {
    const key = areaKey();
    $("area-report").hidden = !key;
    $("draw-start").hidden = Boolean(key) || drawTool.active;
    if (!key) {
      areaDone = null;
      map.clearArea();
      return;
    }
    if (areaDone === key) return;
    areaDone = key;
    // On phones the report lives in the bottom sheet: open it so the progress bar is visible
    if (window.matchMedia("(max-width: 768px)").matches && $("sheet").dataset.expanded !== "true") $("sheet-toggle").click();
    $("area-lines").replaceChildren();
    $("area-hollows").replaceChildren();
    $("sheet-content").scrollTop = 0;
    map.setBasemap(basemap);
    map.showArea({ ring: state.area }, reducedMotion.matches);
    map.focusArea(state.area, reducedMotion.matches);
    try {
      const sites = lga.suspects ? await fetchJson(lga.suspects.list) : [];
      const report = await analyseArea({
        ring: state.area, lga, dataRoot: DATA_ROOT, landmarks, sites, onProgress: setProgress,
        reducedMotion: reducedMotion.matches,
      });
      if (areaKey() !== key) return; // a newer area or view replaced this one
      $("area-progress").hidden = true;
      $("area-step").textContent = "";
      $("area-lines").replaceChildren(...report.lines.map((line) => el("p", { text: line })));
      renderHollowList(report.hollows);
      map.showArea({ ring: state.area, ...report }, reducedMotion.matches);
    } catch (error) {
      if (areaKey() !== key) return;
      $("area-progress").hidden = true;
      $("area-step").textContent = "";
      $("area-lines").replaceChildren(
        el("p", { class: "status status--error", role: "alert", text: error instanceof Error ? error.message : "The area could not be analysed." })
      );
    }
  }

  const drawTool = map.createDrawTool(({ active, count, canFinish }) => {
    $("draw-bar").hidden = !active;
    $("draw-undo").disabled = count === 0;
    $("draw-finish").disabled = !canFinish;
    $("draw-hint").textContent = count === 0
      ? "Tap the map to add corners around the area (at least 3)."
      : `${count} ${count === 1 ? "corner" : "corners"}. Keep tapping, then choose Analyse area.`;
  });

  const setState = (patch, { refit = false } = {}) => {
    state = { ...state, ...patch };
    window.history.replaceState(null, "", writeState(state));
    render(refit);
  };

  /** Drops the tapped spot or open site but leaves the map where it is. */
  function deselect() {
    keepView = true;
    setState({ site: null, at: null });
  }

  async function render(refit) {
    const token = ++renderToken;
    const lga = manifest.lgas.find((l) => l.slug === state.lga);
    const data = layerData(lga, state.layer);

    $("lga-title").textContent = lga.name;
    $("lga-meta").textContent = "Local Government Area · Rivers State";
    renderLgaSelect($("lga-select"), manifest, lga.slug, (slug) => {
      const next = manifest.lgas.find((l) => l.slug === slug);
      const layer = isLayerAvailable(next, state.layer) ? state.layer : defaultLayer(next);
      setState({ lga: slug, layer, site: null, at: null, area: null }, { refit: true });
    });
    renderLayerControls($("layer-controls"), lga, state.layer, (layer) => setState({ layer, site: null, at: state.at }));
    renderFigure($("figure"), $("legend"), lga, state.layer);
    renderTerrainControls($("drainage-toggle"), $("hand-toggle"), $("terrain-legend"), lga, state);
    const terrain = lga.terrain;
    map.showHand(terrain && state.hand ? DATA_ROOT + terrain.hand_overlay : null, terrain?.hand_bounds);
    const overlayOpacity = state.site || state.at || state.area ? Math.min(data?.overlayOpacity ?? 1, SITE_OVERLAY_OPACITY) : data?.overlayOpacity;
    map.showOverlay(data?.overlay ? DATA_ROOT + data.overlay : null, data?.bounds, data?.alt, overlayOpacity);
    if (refit && (data?.bounds || lga.events[0]?.bounds)) map.fitTo(data?.bounds ?? lga.events[0].bounds);

    try {
      const [boundary, hotspots, drainage, suspectAreas, landmarks] = await Promise.all([
        fetchJson(lga.boundary),
        data ? fetchJson(data.hotspots) : Promise.resolve([]),
        terrain && state.drainage ? fetchJson(terrain.flow ?? terrain.drainage) : Promise.resolve(null),
        data?.areas ? fetchJson(data.areas) : Promise.resolve(null),
        lga.landmarks ? fetchJson(lga.landmarks).catch(() => []) : Promise.resolve([]),
      ]);
      if (token !== renderToken) return;
      // Directed flow paths when available; older data falls back to channel outlines.
      map.showFlow(terrain?.flow && drainage ? drainage : null);
      map.showDrainage(terrain?.flow ? null : drainage);
      map.showSuspectAreas(suspectAreas);
      map.showLandmarks(landmarks);
      map.showBoundary(boundary, state.boundary);
      // Every point, in every layer, opens the zoomed satellite site view
      const select = (h) => setState({ site: h.rank, at: null, area: null });
      map.showHotspots(hotspots, data?.subtitle ?? "", select);
      renderHotspots($("hotspots"), $("hotspots-heading"), hotspots, state.layer, select, lga);
      await renderSite(lga, hotspots, data, landmarks, token);
      renderArea(lga, landmarks);
    } catch (error) {
      if (token === renderToken) showError(error instanceof Error ? error.message : "Could not load layer data.");
    }
  }

  setup3d(() => currentSite);
  $("site-back").addEventListener("click", () => setState({ site: null, at: null }, { refit: true }));
  $("site-close").addEventListener("click", deselect);
  document.addEventListener("keydown", (e) => {
    if (e.key !== "Escape" || !$("view3d").hidden) return; // the 3D dialog handles its own Escape
    if (drawTool.active) $("draw-cancel").click();
    else if (state.at || state.site) deselect();
  });
  // Tap anywhere on the map: zoom into the satellite view of that spot
  map.onMapClick((lat, lon) => {
    if (!$("view3d").hidden || drawTool.active) return; // taps while drawing add corners instead
    setState({ site: null, area: null, at: [lat, lon] });
  });
  $("draw-start").addEventListener("click", () => {
    setState({ site: null, at: null, area: null });
    drawTool.start();
    $("draw-start").hidden = true;
  });
  $("draw-undo").addEventListener("click", () => drawTool.undo());
  $("draw-cancel").addEventListener("click", () => {
    drawTool.stop();
    $("draw-start").hidden = false;
  });
  $("draw-finish").addEventListener("click", () => {
    const ring = drawTool.stop();
    if (ring) setState({ area: ring, site: null, at: null });
  });
  $("area-clear").addEventListener("click", () => setState({ area: null }, { refit: true }));
  $("basemap-satellite").addEventListener("click", () => setBasemap("satellite"));
  $("basemap-street").addEventListener("click", () => setBasemap("street"));
  $("boundary-toggle").checked = state.boundary;
  $("boundary-toggle").addEventListener("change", (e) => setState({ boundary: e.target.checked }));
  $("drainage-toggle").addEventListener("change", (e) => setState({ drainage: e.target.checked }));
  $("hand-toggle").addEventListener("change", (e) => setState({ hand: e.target.checked }));
  render(true);
}

start();
