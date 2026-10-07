import { formatDate } from "./format.js";

// Every dated radar pass of an LGA (flood maps and standing-water comparisons), newest first.
// The panel shows them in one date list instead of one card each, so new passes do not grow the panel.

/** @returns {{id: string, layer: "event"|"standing", date: string, label: string, note: string, hectares: number, data: object}[]} */
export function listPasses(lga) {
  const floods = (lga.events ?? []).map((e) => ({
    id: `flood-${e.date}`,
    layer: "event",
    date: e.date,
    label: `${formatDate(e.date)} · flood`,
    note: "Standing water the morning and evening after heavy rain",
    hectares: e.flooded_ha,
    data: e,
  }));
  const standing = [lga.standing ?? []].flat().map((s) => ({
    id: `standing-${s.after}`,
    layer: "standing",
    date: s.after,
    label: `${formatDate(s.after)} · water still standing`,
    note: `Flooding from ${formatDate(s.before)} that had not drained after the dry days since`,
    hectares: s.hectares.standing,
    data: s,
  }));
  return [...floods, ...standing].sort((a, b) => b.date.localeCompare(a.date) || a.layer.localeCompare(b.layer));
}

/** The pass with this id on this layer; otherwise that layer's newest pass; null for other layers. */
export function findPass(lga, layer, id) {
  const ofLayer = listPasses(lga).filter((p) => p.layer === layer);
  return ofLayer.find((p) => p.id === id) ?? ofLayer[0] ?? null;
}
