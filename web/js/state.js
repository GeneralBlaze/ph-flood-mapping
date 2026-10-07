// Shareable view state lives in the URL: ?lga=<slug>&layer=suspects|standing|frequency|event|none&pass=<id>&tab=map|sites|history
// &boundary=0&drainage=1&hand=1&site=<rank>&at=<lat>,<lon>&area=<lat>,<lon>;…

import { listPasses } from "./passes.js";

const LAYERS = ["suspects", "standing", "frequency", "event", "none"];
export const TABS = ["map", "sites", "history"];

function availableLayers(lga) {
  return LAYERS.filter((layer) => {
    if (layer === "suspects") return Boolean(lga.suspects);
    if (layer === "standing") return Boolean(lga.standing);
    if (layer === "frequency") return Boolean(lga.frequency);
    if (layer === "event") return lga.events.length > 0;
    return true;
  });
}

export function defaultLayer(lga) {
  return availableLayers(lga)[0];
}

export function isLayerAvailable(lga, layer) {
  return availableLayers(lga).includes(layer);
}

function parseSite(value) {
  const rank = Number.parseInt(value ?? "", 10);
  return Number.isInteger(rank) && rank > 0 ? rank : null;
}

const SPOT_DECIMALS = 5; // about a metre

function parseSpot(value) {
  const parts = (value ?? "").split(",").map(Number);
  if (parts.length !== 2 || parts.some((n) => !Number.isFinite(n))) return null;
  const [lat, lon] = parts;
  return Math.abs(lat) <= 90 && Math.abs(lon) <= 180 ? [lat, lon] : null;
}

const MAX_AREA_CORNERS = 60;

function parseArea(value) {
  if (!value) return null;
  const corners = value.split(";").map(parseSpot);
  if (corners.length < 3 || corners.length > MAX_AREA_CORNERS || corners.some((c) => c === null)) return null;
  return corners;
}

export function readState(search, manifest) {
  const params = new URLSearchParams(search);
  const lga = manifest.lgas.find((l) => l.slug === params.get("lga")) ?? manifest.lgas[0];
  const requested = params.get("layer");
  const layer = isLayerAvailable(lga, requested) ? requested : defaultLayer(lga);
  const area = parseArea(params.get("area"));
  const at = area ? null : parseSpot(params.get("at"));
  const pass = listPasses(lga).find((p) => p.id === params.get("pass") && p.layer === layer)?.id ?? null;
  const tab = TABS.includes(params.get("tab")) ? params.get("tab") : "map";
  return {
    lga: lga.slug,
    layer,
    boundary: params.get("boundary") !== "0",
    drainage: params.get("drainage") === "1",
    hand: params.get("hand") === "1",
    at,
    area,
    site: !at && !area && layer !== "none" ? parseSite(params.get("site")) : null,
    pass,
    tab,
  };
}

export function writeState(state) {
  const params = new URLSearchParams({ lga: state.lga, layer: state.layer });
  if (state.pass) params.set("pass", state.pass);
  if (state.tab && state.tab !== "map") params.set("tab", state.tab);
  if (!state.boundary) params.set("boundary", "0");
  if (state.drainage) params.set("drainage", "1");
  if (state.hand) params.set("hand", "1");
  if (state.site) params.set("site", String(state.site));
  if (state.at) params.set("at", state.at.map((n) => n.toFixed(SPOT_DECIMALS)).join(","));
  if (state.area) params.set("area", state.area.map((c) => c.map((n) => n.toFixed(SPOT_DECIMALS)).join(",")).join(";"));
  return `?${params.toString()}`;
}
