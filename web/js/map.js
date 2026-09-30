import { el } from "./dom.js";
import { formatHectares } from "./format.js";

const PH_CENTRE = [4.82, 7.0];
const START_ZOOM = 11;
const HOTSPOT_ZOOM = 15;
const OVERVIEW_MAX_ZOOM = 12; // at or below this, markers shrink so clusters stay readable
const OVERLAY_OPACITY = 0.85;
const HAND_OPACITY = 0.6;
const BASEMAP_URL = "https://tile.openstreetmap.org/{z}/{x}/{y}.png";
const BASEMAP_ATTRIBUTION = '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors';

function cssVar(name) {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
}

function hotspotPopup(hotspot, subtitle) {
  const children = [
    el("h3", { text: `${hotspot.rank}. ${hotspot.place}` }),
    el("p", { text: `${formatHectares(hotspot.area_ha)} ${subtitle}` }),
  ];
  if (hotspot.reasons) {
    children.push(
      el("p", { class: "popup__label", text: "Why it was flagged" }),
      el("ul", { class: "popup__reasons" }, hotspot.reasons.map((r) => el("li", { text: r }))),
      el("p", {
        class: "popup__caveat",
        text: "A lead, not a verdict: it could also be a pond, a building site or smooth paving that looks like water to radar. Check on the ground.",
      })
    );
  }
  children.push(el("p", { text: `${hotspot.lat.toFixed(4)}, ${hotspot.lon.toFixed(4)}` }));
  return el("div", { class: "popup" }, children);
}

export function createMap(container) {
  const map = L.map(container, { zoomControl: false, attributionControl: true }).setView(PH_CENTRE, START_ZOOM);
  L.control.zoom({ position: "topright" }).addTo(map);
  const setOverview = () => container.classList.toggle("map--overview", map.getZoom() <= OVERVIEW_MAX_ZOOM);
  map.on("zoomend", setOverview);
  setOverview();

  // Dark mode darkens the tiles with a CSS filter (see .basemap-tiles in app.css).
  L.tileLayer(BASEMAP_URL, { attribution: BASEMAP_ATTRIBUTION, maxZoom: 19, className: "basemap-tiles" }).addTo(map);

  // Creation order sets stacking: terrain shading < flood overlay < channels < boundary < hotspots.
  const groups = {
    hand: L.layerGroup().addTo(map),
    overlay: L.layerGroup().addTo(map),
    drainage: L.layerGroup().addTo(map),
    suspects: L.layerGroup().addTo(map),
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

    showOverlay(url, bounds, alt, opacity = OVERLAY_OPACITY) {
      groups.overlay.clearLayers();
      if (url) L.imageOverlay(url, bounds, { opacity, alt }).addTo(groups.overlay);
    },

    showHand(url, bounds) {
      groups.hand.clearLayers();
      if (url) L.imageOverlay(url, bounds, { opacity: HAND_OPACITY, alt: "Height above drainage" }).addTo(groups.hand);
    },

    showDrainage(geojson) {
      groups.drainage.clearLayers();
      if (!geojson) return;
      const colour = cssVar("--channel");
      L.geoJSON(geojson, {
        style: { color: colour, weight: 1, fillColor: colour, fillOpacity: 0.85 },
        interactive: false,
      }).addTo(groups.drainage);
    },

    showSuspectAreas(geojson) {
      groups.suspects.clearLayers();
      if (!geojson) return;
      const colour = cssVar("--signal");
      L.geoJSON(geojson, {
        style: { color: colour, weight: 2, fillColor: colour, fillOpacity: 0.35 },
        interactive: false,
      }).addTo(groups.suspects);
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
          .bindPopup(() => hotspotPopup(hotspot, subtitle), { maxWidth: 320 })
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
