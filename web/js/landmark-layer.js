import { el } from "./dom.js";
import { visibleLandmarks } from "./landmark-math.js";

// Labelled points for schools, churches, markets and the like, shown from street
// zoom so a site can be found by the places people give directions by.
const MAX_LABELS = 60;

export function createLandmarkLayer(map) {
  const group = L.layerGroup().addTo(map);
  let rows = [];

  function render() {
    group.clearLayers();
    const b = map.getBounds();
    const view = { south: b.getSouth(), west: b.getWest(), north: b.getNorth(), east: b.getEast() };
    for (const [lat, lon, kind, name] of visibleLandmarks(rows, view, map.getZoom(), MAX_LABELS)) {
      const html = el("span", { class: "landmark" }, [
        el("span", { class: "landmark__dot", "aria-hidden": "true" }),
        el("span", { class: "landmark__name", text: name }),
      ]);
      L.marker([lat, lon], {
        icon: L.divIcon({ className: "", html, iconSize: null }),
        title: `${name} (${kind})`,
        interactive: false,
        keyboard: false,
        pane: "landmarkPane",
      }).addTo(group);
    }
  }

  if (!map.getPane("landmarkPane")) map.createPane("landmarkPane").style.zIndex = 620;
  map.on("moveend zoomend", render);

  return {
    setData(data) {
      rows = Array.isArray(data) ? data : [];
      render();
    },
  };
}
