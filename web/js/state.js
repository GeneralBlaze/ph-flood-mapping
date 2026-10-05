// Shareable view state lives in the URL: ?lga=<slug>&layer=suspects|standing|frequency|event|none&boundary=0&drainage=1&hand=1&site=<rank>

const LAYERS = ["suspects", "standing", "frequency", "event", "none"];

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

export function readState(search, manifest) {
  const params = new URLSearchParams(search);
  const lga = manifest.lgas.find((l) => l.slug === params.get("lga")) ?? manifest.lgas[0];
  const requested = params.get("layer");
  const layer = isLayerAvailable(lga, requested) ? requested : defaultLayer(lga);
  return {
    lga: lga.slug,
    layer,
    boundary: params.get("boundary") !== "0",
    drainage: params.get("drainage") === "1",
    hand: params.get("hand") === "1",
    site: layer !== "none" ? parseSite(params.get("site")) : null,
  };
}

export function writeState(state) {
  const params = new URLSearchParams({ lga: state.lga, layer: state.layer });
  if (!state.boundary) params.set("boundary", "0");
  if (state.drainage) params.set("drainage", "1");
  if (state.hand) params.set("hand", "1");
  if (state.site) params.set("site", String(state.site));
  return `?${params.toString()}`;
}
