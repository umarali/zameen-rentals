/** Shared base-layer definitions and persistence helpers for Leaflet maps. */

const STORAGE_KEY = 'rk_mapLayer';

export const MAP_LAYER_DEFS = {
  osm: {
    label: 'Street',
    url: 'https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png',
    options: {
      attribution: '&copy; OpenStreetMap',
      maxZoom: 18,
    },
  },
  satellite: {
    label: 'Satellite',
    url: 'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',
    options: {
      attribution: 'Tiles &copy; Esri',
      maxZoom: 18,
    },
  },
};

export function sanitizeMapLayerKey(value) {
  return value === 'satellite' ? 'satellite' : 'osm';
}

export function getStoredMapLayer() {
  try {
    return sanitizeMapLayerKey(localStorage.getItem(STORAGE_KEY));
  } catch {
    return 'satellite';
  }
}

export function persistMapLayer(layerKey) {
  const next = sanitizeMapLayerKey(layerKey);
  try { localStorage.setItem(STORAGE_KEY, next); } catch {}
  return next;
}

export function createBaseLayer(layerKey) {
  const def = MAP_LAYER_DEFS[sanitizeMapLayerKey(layerKey)];
  return L.tileLayer(def.url, def.options);
}

