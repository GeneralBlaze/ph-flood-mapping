import { el } from "./dom.js";
import { formatDate } from "./format.js";
import { createMap } from "./map.js";
import { renderFigure, renderHotspots, renderLayerControls, renderLgaSelect, renderTerrainControls } from "./panel.js";
import { defaultLayer, isLayerAvailable, readState, writeState } from "./state.js";

const DATA_ROOT = "data/";
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
  if (layer === "frequency" && lga.frequency) {
    return { ...lga.frequency, subtitle: `flooded in ${lga.frequency.repeat_min_years}+ seasons`, alt: "Years flooded" };
  }
  if (layer === "event" && lga.events[0]) {
    const e = lga.events[0];
    return { ...e, subtitle: `under water on ${formatDate(e.date)}`, alt: `Flooding on ${formatDate(e.date)}` };
  }
  return null;
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
  const map = createMap($("map"));

  let manifest;
  try {
    manifest = validateManifest(await fetchJson("manifest.json"));
  } catch (error) {
    $("lga-title").textContent = "Map data unavailable";
    showError(error instanceof Error ? error.message : "Could not load the map data.");
    return;
  }

  $("generated").textContent = `Data published ${manifest.generated.slice(0, 10)}.`;
  let state = readState(window.location.search, manifest);
  let renderToken = 0;

  const setState = (patch, { refit = false } = {}) => {
    state = { ...state, ...patch };
    window.history.replaceState(null, "", writeState(state));
    render(refit);
  };

  async function render(refit) {
    const token = ++renderToken;
    const lga = manifest.lgas.find((l) => l.slug === state.lga);
    const data = layerData(lga, state.layer);

    $("lga-title").textContent = lga.name;
    $("lga-meta").textContent = `Sheet ${manifest.lgas.indexOf(lga) + 1} · Local Government Area`;
    renderLgaSelect($("lga-select"), manifest, lga.slug, (slug) => {
      const next = manifest.lgas.find((l) => l.slug === slug);
      const layer = isLayerAvailable(next, state.layer) ? state.layer : defaultLayer(next);
      setState({ lga: slug, layer }, { refit: true });
    });
    renderLayerControls($("layer-controls"), lga, state.layer, (layer) => setState({ layer }));
    renderFigure($("figure"), $("legend"), lga, state.layer);
    renderTerrainControls($("drainage-toggle"), $("hand-toggle"), $("terrain-legend"), lga, state);
    const terrain = lga.terrain;
    map.showHand(terrain && state.hand ? DATA_ROOT + terrain.hand_overlay : null, terrain?.hand_bounds);
    map.showOverlay(data?.overlay ? DATA_ROOT + data.overlay : null, data?.bounds, data?.alt, data?.overlayOpacity);
    if (refit && (data?.bounds || lga.events[0]?.bounds)) map.fitTo(data?.bounds ?? lga.events[0].bounds);

    try {
      const [boundary, hotspots, drainage, suspectAreas] = await Promise.all([
        fetchJson(lga.boundary),
        data ? fetchJson(data.hotspots) : Promise.resolve([]),
        terrain && state.drainage ? fetchJson(terrain.drainage) : Promise.resolve(null),
        data?.areas ? fetchJson(data.areas) : Promise.resolve(null),
      ]);
      if (token !== renderToken) return;
      map.showDrainage(drainage);
      map.showSuspectAreas(suspectAreas);
      map.showBoundary(boundary, state.boundary);
      map.showHotspots(hotspots, data?.subtitle ?? "");
      renderHotspots($("hotspots"), $("hotspots-heading"), hotspots, state.layer, (h) =>
        map.focusHotspot(h, reducedMotion.matches)
      );
    } catch (error) {
      if (token === renderToken) showError(error instanceof Error ? error.message : "Could not load layer data.");
    }
  }

  $("boundary-toggle").checked = state.boundary;
  $("boundary-toggle").addEventListener("change", (e) => setState({ boundary: e.target.checked }));
  $("drainage-toggle").addEventListener("change", (e) => setState({ drainage: e.target.checked }));
  $("hand-toggle").addEventListener("change", (e) => setState({ hand: e.target.checked }));
  render(true);
}

start();
