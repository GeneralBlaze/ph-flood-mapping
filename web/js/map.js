import { el } from "./dom.js";
import { createFlowLayer } from "./flow-layer.js";
import { createLandmarkLayer } from "./landmark-layer.js";
import { formatHectares } from "./format.js";

const PH_CENTRE = [4.82, 7.0];
const START_ZOOM = 11;
const HOTSPOT_ZOOM = 15;
const OVERVIEW_MAX_ZOOM = 12; // at or below this, markers shrink so clusters stay readable
const OVERLAY_OPACITY = 0.85;
const HAND_OPACITY = 0.6;
const BASEMAP_URL = "https://tile.openstreetmap.org/{z}/{x}/{y}.png";
const BASEMAP_ATTRIBUTION = '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors';
const ESRI = "https://server.arcgisonline.com/ArcGIS/rest/services";
const ESRI_REFERENCE = "https://services.arcgisonline.com/ArcGIS/rest/services/Reference";
const SATELLITE_ATTRIBUTION =
  "Imagery &copy; Esri, Maxar, Earthstar Geographics and the GIS User Community &middot; Powered by Esri";
const SITE_ZOOM = 17;
const SITE_PADDING = 60;
const POPUP_PAD_TOP_LEFT = [16, 170]; // keeps opened popups below the site bar
const ROUTE_UPSTREAM_KM2 = 50; // draws route lines at full width

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
        text: "An indication, not a confirmed blockage. The water may instead be a pond, a construction site or paving that appears as water on radar. Verify on site.",
      })
    );
  }
  if (hotspot.nearby) {
    children.push(el("p", { class: "popup__label", text: "Landmarks nearby" }), el("p", { text: hotspot.nearby }));
  }
  children.push(el("p", { text: `${hotspot.lat.toFixed(4)}, ${hotspot.lon.toFixed(4)}` }));
  return el("div", { class: "popup" }, children);
}

// Padding that keeps fitted areas clear of the floating panels: the side sheet
// (or bottom sheet on phones) and the site bar when it is showing.
function clearOfPanels(margin) {
  const sheet = document.getElementById("sheet").getBoundingClientRect();
  const siteBar = document.getElementById("site-bar");
  const barBottom = siteBar && !siteBar.hidden ? siteBar.getBoundingClientRect().bottom : 0;
  const isBottomSheet = window.matchMedia("(max-width: 768px)").matches;
  const collapsed = document.body.classList.contains("sheet-collapsed");
  const left = isBottomSheet || collapsed ? margin : sheet.right + margin;
  const bottom = isBottomSheet ? window.innerHeight - sheet.top + margin : margin;
  return { paddingTopLeft: [left, Math.max(margin, barBottom + margin)], paddingBottomRight: [margin, bottom] };
}

// Open a marker's popup once the map has stopped moving, panned clear of the panels.
function openPopupClear(map, marker, animated) {
  if (!marker) return;
  const open = () => {
    const { paddingTopLeft, paddingBottomRight } = clearOfPanels(16);
    const popup = marker.getPopup();
    if (popup) {
      popup.options.autoPanPaddingTopLeft = L.point(paddingTopLeft);
      popup.options.autoPanPaddingBottomRight = L.point(paddingBottomRight);
    }
    marker.openPopup();
  };
  if (animated) map.once("moveend", open);
  else open();
}

export function createMap(container) {
  const map = L.map(container, { zoomControl: false, attributionControl: true }).setView(PH_CENTRE, START_ZOOM);
  L.control.zoom({ position: "topright" }).addTo(map);
  const setOverview = () => container.classList.toggle("map--overview", map.getZoom() <= OVERVIEW_MAX_ZOOM);
  map.on("zoomend", setOverview);
  setOverview();
  const landmarks = createLandmarkLayer(map);

  // Dark mode darkens the street tiles with a CSS filter (see .basemap-tiles in app.css).
  const streetLayer = L.tileLayer(BASEMAP_URL, { attribution: BASEMAP_ATTRIBUTION, maxZoom: 19, className: "basemap-tiles" }).addTo(map);
  let satelliteLayer = null; // created on first use so overview visitors never load imagery
  const satellite = () =>
    (satelliteLayer ??= L.layerGroup([
      L.tileLayer(`${ESRI}/World_Imagery/MapServer/tile/{z}/{y}/{x}`, { attribution: SATELLITE_ATTRIBUTION, maxZoom: 19 }),
      L.tileLayer(`${ESRI_REFERENCE}/World_Transportation/MapServer/tile/{z}/{y}/{x}`, { maxZoom: 19 }),
      L.tileLayer(`${ESRI_REFERENCE}/World_Boundaries_and_Places/MapServer/tile/{z}/{y}/{x}`, { maxZoom: 19 }),
    ]));

  // Creation order sets stacking: terrain shading < flood overlay < channels < boundary < hotspots.
  const groups = {
    hand: L.layerGroup().addTo(map),
    overlay: L.layerGroup().addTo(map),
    drainage: L.layerGroup().addTo(map),
    suspects: L.layerGroup().addTo(map),
    site: L.layerGroup().addTo(map),
    boundary: L.layerGroup().addTo(map),
    hotspots: L.layerGroup().addTo(map),
  };
  const markers = new Map();
  let flowLayer = null;
  let routeLayer = null;
  let localFlowLayer = null; // runoff arrows around the open site or tapped spot
  const local = L.layerGroup().addTo(map); // pools and the spot pin

  return {
    fitTo(bounds) {
      map.fitBounds(bounds, clearOfPanels(24));
    },

    showOverlay(url, bounds, alt, opacity = OVERLAY_OPACITY) {
      groups.overlay.clearLayers();
      if (url) L.imageOverlay(url, bounds, { opacity, alt }).addTo(groups.overlay);
    },

    showHand(url, bounds) {
      groups.hand.clearLayers();
      if (url) L.imageOverlay(url, bounds, { opacity: HAND_OPACITY, alt: "Height above drainage" }).addTo(groups.hand);
    },

    showFlow(rows) {
      if (!rows) {
        flowLayer?.remove();
        flowLayer = null;
        return;
      }
      if (!flowLayer) {
        const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
        flowLayer = createFlowLayer({ colour: cssVar("--channel"), reducedMotion: reduced }).addTo(map);
      }
      flowLayer.setData(rows);
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

    setBasemap(kind) {
      const useSatellite = kind === "satellite";
      if (useSatellite) {
        streetLayer.remove();
        satellite().addTo(map);
      } else {
        satelliteLayer?.remove();
        streetLayer.addTo(map);
      }
      streetLayer.bringToBack();
      container.classList.toggle("map--satellite", useSatellite);
    },

    showSite({ route, buildings, reducedMotion }) {
      groups.site.clearLayers();
      routeLayer?.remove();
      routeLayer = null;
      if (buildings) {
        L.geoJSON(buildings, {
          style: { color: cssVar("--obstruction"), weight: 2, fillColor: cssVar("--obstruction"), fillOpacity: 0.35 },
          interactive: false,
        }).addTo(groups.site);
      }
      if (route) {
        const coords = route.geometry.coordinates;
        L.polyline(coords.map(([lon, lat]) => [lat, lon]), { color: "#ffffff", weight: 7, opacity: 0.85, interactive: false })
          .addTo(groups.site);
        const rows = coords.slice(1).map(([lon, lat], i) => [coords[i][0], coords[i][1], lon, lat, ROUTE_UPSTREAM_KM2]);
        routeLayer = createFlowLayer({
          colour: cssVar("--channel"), reducedMotion, arrowPx: 4, lineAlpha: 1, widthScale: 1,
          pane: "routePane", zIndex: 460,
        }).addTo(map);
        routeLayer.setData(rows);
      }
    },

    clearSite() {
      groups.site.clearLayers();
      routeLayer?.remove();
      routeLayer = null;
      this.clearLocal();
    },

    onMapClick(handler) {
      map.on("click", (e) => handler(e.latlng.lat, e.latlng.lng));
    },

    showSpot(lat, lon) {
      L.marker([lat, lon], {
        icon: L.divIcon({ className: "", html: '<span class="spot-pin" aria-hidden="true"></span>', iconSize: [22, 22] }),
        title: "Selected spot",
        keyboard: false,
        interactive: false,
      }).addTo(local);
    },

    showLocal({ segments, pools }, reducedMotion) {
      if (pools) L.imageOverlay(pools.url, pools.bounds, { opacity: 0.75, alt: "Hollows where water ponds" }).addTo(local);
      localFlowLayer?.remove();
      localFlowLayer = createFlowLayer({
        colour: cssVar("--channel"), reducedMotion, arrowPx: 2.5, lineAlpha: 0.8, widthScale: 0.7,
        pane: "localFlowPane", zIndex: 455, casing: false,
      }).addTo(map);
      localFlowLayer.setData(segments);
    },

    clearLocal() {
      local.clearLayers();
      localFlowLayer?.remove();
      localFlowLayer = null;
    },

    focusSpot(lat, lon, reducedMotion) {
      const bounds = L.latLng(lat, lon).toBounds(350);
      const options = { maxZoom: SITE_ZOOM, ...clearOfPanels(SITE_PADDING) };
      map.closePopup();
      if (reducedMotion) map.fitBounds(bounds, options);
      else map.flyToBounds(bounds, { ...options, duration: 0.8 });
    },

    focusSite(hotspot, route, reducedMotion) {
      const points = [[hotspot.lat, hotspot.lon], ...(route?.geometry.coordinates ?? []).map(([lon, lat]) => [lat, lon])];
      const bounds = L.latLngBounds(points);
      const options = { maxZoom: SITE_ZOOM, ...clearOfPanels(SITE_PADDING) };
      if (reducedMotion) map.fitBounds(bounds, options);
      else map.flyToBounds(bounds, { ...options, duration: 0.8 });
      // No automatic popup here: the site bar already names the site, and on short
      // screens the popup would cover it. Tapping the marker still opens it.
      map.closePopup();
    },

    showHotspots(hotspots, subtitle, onSelect) {
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
          .bindPopup(() => hotspotPopup(hotspot, subtitle), { maxWidth: 320, autoPanPaddingTopLeft: POPUP_PAD_TOP_LEFT })
          .addTo(groups.hotspots);
        if (onSelect) marker.on("click", () => onSelect(hotspot));
        markers.set(hotspot.rank, marker);
      }
    },

    showLandmarks(rows) {
      landmarks.setData(rows);
    },

    focusHotspot(hotspot, reducedMotion) {
      const target = [hotspot.lat, hotspot.lon];
      if (reducedMotion) map.setView(target, HOTSPOT_ZOOM);
      else map.flyTo(target, HOTSPOT_ZOOM, { duration: 0.8 });
      openPopupClear(map, markers.get(hotspot.rank), !reducedMotion);
    },
  };
}
