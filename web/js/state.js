// Shareable view state lives in the URL: ?lga=<slug>&layer=frequency|event|none&boundary=0

const LAYERS = ["frequency", "event", "none"];

function availableLayers(lga) {
  return LAYERS.filter((layer) => {
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

export function readState(search, manifest) {
  const params = new URLSearchParams(search);
  const lga = manifest.lgas.find((l) => l.slug === params.get("lga")) ?? manifest.lgas[0];
  const requested = params.get("layer");
  const layer = isLayerAvailable(lga, requested) ? requested : defaultLayer(lga);
  return { lga: lga.slug, layer, boundary: params.get("boundary") !== "0" };
}

export function writeState(state) {
  const params = new URLSearchParams({ lga: state.lga, layer: state.layer });
  if (!state.boundary) params.set("boundary", "0");
  return `?${params.toString()}`;
}
