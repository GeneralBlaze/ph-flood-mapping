// Tap-to-draw polygon tool: each tap adds a corner; Finish closes the shape.
// Works the same with a mouse or a finger, with no extra library.
const MIN_CORNERS = 3;

export function createDrawTool(map, { colour, onChange }) {
  let active = false;
  let corners = [];
  const layer = L.layerGroup().addTo(map);

  function redraw() {
    layer.clearLayers();
    if (corners.length > 1) {
      L.polyline(corners, { color: colour, weight: 3, dashArray: "6 6", interactive: false }).addTo(layer);
    }
    if (corners.length > 2) {
      L.polygon(corners, { color: colour, weight: 0, fillColor: colour, fillOpacity: 0.12, interactive: false }).addTo(layer);
    }
    corners.forEach((c) =>
      L.circleMarker(c, { radius: 5, color: "#fff", weight: 2, fillColor: colour, fillOpacity: 1, interactive: false }).addTo(layer)
    );
    onChange({ active, count: corners.length, canFinish: corners.length >= MIN_CORNERS });
  }

  const add = (e) => {
    corners = [...corners, [e.latlng.lat, e.latlng.lng]];
    redraw();
  };

  return {
    get active() {
      return active;
    },
    start() {
      active = true;
      corners = [];
      map.doubleClickZoom.disable();
      map.getContainer().classList.add("map--drawing");
      map.on("click", add);
      redraw();
    },
    undo() {
      corners = corners.slice(0, -1);
      redraw();
    },
    /** Ends drawing; returns the corners ([lat, lon]) if there are enough, else null. */
    stop() {
      const result = corners.length >= MIN_CORNERS ? corners : null;
      active = false;
      corners = [];
      map.off("click", add);
      map.doubleClickZoom.enable();
      map.getContainer().classList.remove("map--drawing");
      layer.clearLayers();
      onChange({ active, count: 0, canFinish: false });
      return result;
    },
  };
}
