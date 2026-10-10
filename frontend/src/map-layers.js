/** Shared base-layer definitions and persistence helpers for Leaflet maps. */

import L from 'leaflet';

const STORAGE_KEY = 'rk_mapLayer';

export const MAP_LAYER_DEFS = {
  osm: {
    label: 'Street',
    url: 'https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png',
    options: {
      attribution: '&copy; OpenStreetMap',
      maxZoom: 19,
    },
  },
  satellite: {
    label: 'Satellite',
    url: 'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',
    options: {
      attribution: 'Tiles &copy; Esri',
      maxZoom: 19,
    },
    // Imagery alone has no names; these transparent layers add roads and places.
    overlays: [
      'https://server.arcgisonline.com/ArcGIS/rest/services/Reference/World_Transportation/MapServer/tile/{z}/{y}/{x}',
      'https://server.arcgisonline.com/ArcGIS/rest/services/Reference/World_Boundaries_and_Places/MapServer/tile/{z}/{y}/{x}',
    ],
  },
};

export function sanitizeMapLayerKey(value) {
  return value === 'satellite' ? 'satellite' : 'osm';
}

export function getStoredMapLayer() {
  try {
    return sanitizeMapLayerKey(localStorage.getItem(STORAGE_KEY));
  } catch {
    return 'osm';
  }
}

export function persistMapLayer(layerKey) {
  const next = sanitizeMapLayerKey(layerKey);
  try { localStorage.setItem(STORAGE_KEY, next); } catch {}
  return next;
}

export function createBaseLayer(layerKey) {
  const def = MAP_LAYER_DEFS[sanitizeMapLayerKey(layerKey)];
  const base = L.tileLayer(def.url, def.options);
  if (!def.overlays?.length) return base;
  return L.layerGroup([
    base,
    ...def.overlays.map(url => L.tileLayer(url, { maxZoom: def.options.maxZoom })),
  ]);
}
