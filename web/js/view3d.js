// 3D site view: satellite imagery draped over our own FABDEM terrain tiles, with
// buildings at their measured heights. MapLibre is loaded only when this opens.
const GROUND_EXAGGERATION = 4; // Port Harcourt is flat: a 2 m hollow is invisible at true scale
const PITCH = 60;
const BEARING = -20;
const MAX_ZOOM = 17.5;
const ESRI = "https://server.arcgisonline.com/ArcGIS/rest/services";
const ESRI_REFERENCE = "https://services.arcgisonline.com/ArcGIS/rest/services/Reference";
const ATTRIBUTION =
  "Imagery © Esri, Maxar, Earthstar Geographics · Terrain: FABDEM (CC BY-NC-SA 4.0) · Buildings: Google Open Buildings";

let libraryPromise = null;

function loadLibrary() {
  if (!libraryPromise) {
    const css = document.createElement("link");
    css.rel = "stylesheet";
    css.href = "vendor/maplibre/maplibre-gl.css";
    document.head.append(css);
    libraryPromise = import("../vendor/maplibre/maplibre-gl.mjs");
  }
  return libraryPromise;
}

const absolute = (path) => new URL(path, window.location.href).href;
const collection = (features) => ({ type: "FeatureCollection", features });

function sceneBounds(features) {
  let west = Infinity, south = Infinity, east = -Infinity, north = -Infinity;
  const visit = (c) => {
    if (typeof c[0] === "number") {
      west = Math.min(west, c[0]); east = Math.max(east, c[0]);
      south = Math.min(south, c[1]); north = Math.max(north, c[1]);
    } else c.forEach(visit);
  };
  features.forEach((f) => visit(f.geometry.coordinates));
  return [[west, south], [east, north]];
}

// Leaflet bounds [[south, west], [north, east]] -> MapLibre image corners, clockwise from top-left
function corners([[south, west], [north, east]]) {
  return [[west, north], [east, north], [east, south], [west, south]];
}

function style({ view3d, dataRoot, area, route, buildingsUrl, overlay, colours }) {
  const raster = (url) => ({ type: "raster", tiles: [url], tileSize: 256, maxzoom: 19 });
  return {
    version: 8,
    sources: {
      imagery: { ...raster(`${ESRI}/World_Imagery/MapServer/tile/{z}/{y}/{x}`), attribution: ATTRIBUTION },
      roads: raster(`${ESRI_REFERENCE}/World_Transportation/MapServer/tile/{z}/{y}/{x}`),
      places: raster(`${ESRI_REFERENCE}/World_Boundaries_and_Places/MapServer/tile/{z}/{y}/{x}`),
      dem: {
        type: "raster-dem",
        tiles: [absolute(dataRoot + view3d.terrain)],
        encoding: "terrarium",
        tileSize: 256,
        minzoom: view3d.minzoom,
        maxzoom: view3d.maxzoom,
        bounds: view3d.bounds,
      },
      area: { type: "geojson", data: collection(area ? [area] : []) },
      route: { type: "geojson", data: collection(route ? [route] : []), lineMetrics: true },
      buildings: { type: "geojson", data: buildingsUrl ?? collection([]) },
      ...(overlay ? { flood: { type: "image", url: overlay.url, coordinates: corners(overlay.bounds) } } : {}),
    },
    layers: [
      { id: "imagery", type: "raster", source: "imagery" },
      { id: "roads", type: "raster", source: "roads" },
      { id: "places", type: "raster", source: "places" },
      ...(overlay ? [{ id: "flood", type: "raster", source: "flood", paint: { "raster-opacity": 0.5, "raster-resampling": "nearest" } }] : []),
      { id: "area", type: "fill", source: "area", paint: { "fill-color": colours.signal, "fill-opacity": 0.4 } },
      { id: "area-edge", type: "line", source: "area", paint: { "line-color": colours.signal, "line-width": 2 } },
      {
        id: "route",
        type: "line",
        source: "route",
        layout: { "line-cap": "round", "line-join": "round" },
        // Pale at the site, strong at the channel: shows which way the water should go
        paint: {
          "line-width": 7,
          "line-gradient": ["interpolate", ["linear"], ["line-progress"], 0, "#e0fbff", 1, colours.channel],
        },
      },
      {
        id: "buildings",
        type: "fill-extrusion",
        source: "buildings",
        paint: {
          "fill-extrusion-color": ["case", ["get", "on_route"], colours.obstruction, "#d9d3c3"],
          "fill-extrusion-height": ["get", "h"],
          "fill-extrusion-opacity": 0.9,
        },
      },
    ],
    terrain: { source: "dem", exaggeration: GROUND_EXAGGERATION },
  };
}

/** Opens the 3D scene in container; returns a function that closes it. */
export async function open3d({ container, view3d, dataRoot, hotspot, area, route, overlay, withBuildings, colours, reducedMotion }) {
  const maplibre = await loadLibrary();
  const map = new maplibre.Map({
    container,
    style: style({
      view3d,
      dataRoot,
      area,
      route,
      colours,
      overlay: overlay ? { ...overlay, url: absolute(overlay.url) } : null,
      buildingsUrl: withBuildings ? absolute(`${dataRoot}${view3d.buildings}/${hotspot.rank}.geojson`) : null,
    }),
    center: [hotspot.lon, hotspot.lat],
    zoom: 16,
    pitch: PITCH,
    bearing: BEARING,
    maxZoom: MAX_ZOOM,
    maxPitch: 80,
    attributionControl: { compact: true },
  });
  map.addControl(new maplibre.NavigationControl({ visualizePitch: true }), "top-right");
  const framed = [area, route].filter(Boolean);
  map.once("load", () => {
    if (framed.length) {
      map.fitBounds(sceneBounds(framed), { padding: 80, pitch: PITCH, bearing: BEARING, maxZoom: 17, animate: !reducedMotion });
    }
  });
  return () => map.remove();
}

export const VIEW3D_EXAGGERATION = GROUND_EXAGGERATION;
