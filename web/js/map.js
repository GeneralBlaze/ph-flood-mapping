import { el } from "./dom.js";
import { formatHectares } from "./format.js";

const PH_CENTRE = [4.82, 7.0];
const START_ZOOM = 11;
const HOTSPOT_ZOOM = 15;
const OVERLAY_OPACITY = 0.85;
const BASEMAP_URL = "https://tile.openstreetmap.org/{z}/{x}/{y}.png";
const BASEMAP_ATTRIBUTION = '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors';

function cssVar(name) {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
}

function hotspotPopup(hotspot, subtitle) {
  return el("div", { class: "popup" }, [
    el("h3", { text: `${hotspot.rank}. ${hotspot.place}` }),
    el("p", { text: `${formatHectares(hotspot.area_ha)} ${subtitle}` }),
    el("p", { text: `${hotspot.lat.toFixed(4)}, ${hotspot.lon.toFixed(4)}` }),
  ]);
}

export function createMap(container) {
  const map = L.map(container, { zoomControl: false, attributionControl: true }).setView(PH_CENTRE, START_ZOOM);
  L.control.zoom({ position: "topright" }).addTo(map);

  // Dark mode darkens the tiles with a CSS filter (see .basemap-tiles in app.css).
  L.tileLayer(BASEMAP_URL, { attribution: BASEMAP_ATTRIBUTION, maxZoom: 19, className: "basemap-tiles" }).addTo(map);

  const groups = {
    overlay: L.layerGroup().addTo(map),
    boundary: L.layerGroup().addTo(map),
    hotspots: L.layerGroup().addTo(map),
  };
  const markers = new Map();

  return {
    // Keep the fitted area clear of the floating sheet (side panel on desktop, bottom sheet on phones).
    fitTo(bounds) {
      const sheet = document.getElementById("sheet").getBoundingClientRect();
      const isBottomSheet = window.matchMedia("(max-width: 768px)").matches;
      const margin = 24;
      map.fitBounds(bounds, {
        paddingTopLeft: isBottomSheet ? [margin, margin] : [sheet.right + margin, margin],
        paddingBottomRight: isBottomSheet ? [margin, window.innerHeight - sheet.top + margin] : [margin, margin],
      });
    },

    showOverlay(url, bounds, alt) {
      groups.overlay.clearLayers();
      if (url) L.imageOverlay(url, bounds, { opacity: OVERLAY_OPACITY, alt }).addTo(groups.overlay);
    },

    showBoundary(geojson, visible) {
      groups.boundary.clearLayers();
      if (!geojson || !visible) return;
      L.geoJSON(geojson, {
        style: { color: cssVar("--ink"), weight: 2, dashArray: "6 4", fill: false },
        interactive: false,
      }).addTo(groups.boundary);
    },

    showHotspots(hotspots, subtitle) {
      groups.hotspots.clearLayers();
      markers.clear();
      for (const hotspot of hotspots) {
        const icon = L.divIcon({
          className: "",
          html: `<span class="hotspot-marker">${Number(hotspot.rank)}</span>`,
          iconSize: [30, 30],
        });
        const marker = L.marker([hotspot.lat, hotspot.lon], {
          icon,
          title: `${hotspot.rank}. ${hotspot.place}`,
          keyboard: true,
        })
          .bindPopup(() => hotspotPopup(hotspot, subtitle))
          .addTo(groups.hotspots);
        markers.set(hotspot.rank, marker);
      }
    },

    focusHotspot(hotspot, reducedMotion) {
      const target = [hotspot.lat, hotspot.lon];
      if (reducedMotion) map.setView(target, HOTSPOT_ZOOM);
      else map.flyTo(target, HOTSPOT_ZOOM, { duration: 0.8 });
      markers.get(hotspot.rank)?.openPopup();
    },
  };
}
