/** Leaflet map: desktop viewport browsing, markers, and mobile map overlay. */

import { $, $$, esc, escA, fmtPrice, showToast } from './utils.js';
import { S, refs, CITY_DEFAULTS } from './state.js';
import { track } from './analytics.js';
import { formatDistance, getAreaForListing } from './cards.js';
import {
  createBaseLayer,
  getStoredMapLayer,
  persistMapLayer,
  sanitizeMapLayerKey,
} from './map-layers.js';

const EXACT_MARKER_MIN_ZOOM = 11;
const EXACT_MARKER_MIN_ZOOM_MOBILE = 12;
const EXACT_PREFETCH_LIMIT = 10;
const EXACT_PREFETCH_CONCURRENCY = 3;
const EXACT_PREFETCH_COOLDOWN_MS = 30000;
const USER_LOCATION_STORAGE_KEY = 'rk_userLocation';
const USER_LOCATION_TTL_MS = 30 * 60 * 1000;
const AREA_LABEL_Z_INDEX = 1400;
const AREA_LABEL_HIDE_ZOOM = 13;

let exactPrefetchTimer = null;
let exactPrefetchController = null;
let exactPrefetchSession = 0;
const exactPrefetchPending = new Set();
const exactPrefetchMissing = new Set();
const exactPrefetchCooldown = new Map();

function notify(message, options) {
  if (refs._notify) refs._notify(message, options);
  else showToast(message, options);
}

function ensureMapLayerState() {
  refs.mapLayer = sanitizeMapLayerKey(refs.mapLayer || getStoredMapLayer());
  return refs.mapLayer;
}

function createUserLocationIcon() {
  return L.divIcon({
    className: 'user-location-icon',
    html: `
      <div class="user-location-marker">
        <span class="user-location-pulse"></span>
        <span class="user-location-dot"></span>
      </div>
    `,
    iconSize: [24, 24],
    iconAnchor: [12, 12],
  });
}

function persistUserLocation(location) {
  try { sessionStorage.setItem(USER_LOCATION_STORAGE_KEY, JSON.stringify(location)); } catch {}
}

export function hydrateStoredUserLocation() {
  try {
    const raw = JSON.parse(sessionStorage.getItem(USER_LOCATION_STORAGE_KEY) || 'null');
    if (!raw?.ts || Date.now() - raw.ts > USER_LOCATION_TTL_MS) {
      sessionStorage.removeItem(USER_LOCATION_STORAGE_KEY);
      refs.userLocation = null;
      return null;
    }
    if (!Number.isFinite(Number(raw.lat)) || !Number.isFinite(Number(raw.lng))) return null;
    refs.userLocation = {
      lat: Number(raw.lat),
      lng: Number(raw.lng),
      accuracy: Number(raw.accuracy) || 0,
      ts: Number(raw.ts),
    };
    return refs.userLocation;
  } catch {
    refs.userLocation = null;
    return null;
  }
}

function clearLayerRef(key) {
  if (!refs[key]) return;
  refs[key].remove();
  refs[key] = null;
}

function applyBaseLayer(mapInstance, layerRefKey, layerKey = refs.mapLayer) {
  if (!mapInstance) return;
  clearLayerRef(layerRefKey);
  refs[layerRefKey] = createBaseLayer(layerKey).addTo(mapInstance);
}

function syncLayerToggleButtons() {
  document.querySelectorAll('[data-map-layer]').forEach(btn => {
    const active = btn.dataset.mapLayer === refs.mapLayer;
    btn.classList.toggle('active', active);
    btn.setAttribute('aria-pressed', String(active));
  });
}

function syncGpsButtons() {
  document.querySelectorAll('.map-gps-btn').forEach(btn => {
    const active = Boolean(refs.userLocation);
    btn.classList.toggle('is-active', active);
    btn.setAttribute('aria-pressed', String(active));
    btn.title = active ? 'Center on my location' : 'Use my location';
  });
}

export function setActiveMapLayer(layerKey) {
  refs.mapLayer = persistMapLayer(layerKey);
  if (refs.map) applyBaseLayer(refs.map, 'mapBaseLayer', refs.mapLayer);
  if (refs.mobileMap) applyBaseLayer(refs.mobileMap, 'mobileMapBaseLayer', refs.mapLayer);
  if (refs.miniMap) applyBaseLayer(refs.miniMap, 'miniMapBaseLayer', refs.mapLayer);
  syncLayerToggleButtons();
}

function createLayerToggleControl() {
  return L.Control.extend({
    options: { position: 'topright' },
    onAdd() {
      const container = L.DomUtil.create('div', 'map-layer-control');
      container.innerHTML = `
        <button type="button" class="map-layer-btn" data-map-layer="osm" aria-pressed="false">Map</button>
        <button type="button" class="map-layer-btn" data-map-layer="satellite" aria-pressed="false">Satellite</button>
      `;
      L.DomEvent.disableClickPropagation(container);
      L.DomEvent.disableScrollPropagation(container);
      container.querySelectorAll('[data-map-layer]').forEach(btn => {
        btn.addEventListener('click', e => {
          e.preventDefault();
          setActiveMapLayer(btn.dataset.mapLayer);
        });
      });
      window.setTimeout(syncLayerToggleButtons, 0);
      return container;
    },
  });
}

function updateLocationOverlay(mapInstance, markerKey, circleKey) {
  if (!mapInstance) return;
  if (!refs.userLocation) {
    clearLayerRef(markerKey);
    clearLayerRef(circleKey);
    return;
  }

  const point = [refs.userLocation.lat, refs.userLocation.lng];
  if (!refs[markerKey]) {
    refs[markerKey] = L.marker(point, {
      icon: createUserLocationIcon(),
      interactive: false,
      keyboard: false,
      zIndexOffset: 900,
    }).addTo(mapInstance);
  } else {
    refs[markerKey].setLatLng(point);
  }

  const accuracy = Math.max(refs.userLocation.accuracy || 0, 0);
  if (!refs[circleKey]) {
    refs[circleKey] = L.circle(point, {
      radius: accuracy,
      color: '#2563eb',
      weight: 1,
      opacity: 0.5,
      fillColor: '#60a5fa',
      fillOpacity: 0.14,
      interactive: false,
    }).addTo(mapInstance);
  } else {
    refs[circleKey].setLatLng(point);
    refs[circleKey].setRadius(accuracy);
  }
}

function updateNearbyRadiusOverlay(mapInstance, layerKey) {
  if (!mapInstance) return;
  if (refs.searchMode !== 'nearby' || !refs.userLocation) {
    clearLayerRef(layerKey);
    return;
  }

  const point = [refs.userLocation.lat, refs.userLocation.lng];
  const radiusMeters = refs.nearbyRadiusKm * 1000;
  if (!refs[layerKey]) {
    refs[layerKey] = L.circle(point, {
      radius: radiusMeters,
      color: '#0a8f3c',
      weight: 1.5,
      opacity: 0.75,
      fillColor: '#0a8f3c',
      fillOpacity: 0.06,
      interactive: false,
    }).addTo(mapInstance);
  } else {
    refs[layerKey].setLatLng(point);
    refs[layerKey].setRadius(radiusMeters);
  }
}

export function refreshUserLocationOverlays({ recenter = false, mapInstance = null } = {}) {
  if (refs.map) {
    updateLocationOverlay(refs.map, 'userLocationMarker', 'userLocationCircle');
    updateNearbyRadiusOverlay(refs.map, 'nearbyRadiusLayer');
  }
  if (refs.mobileMap) {
    updateLocationOverlay(refs.mobileMap, 'mobileUserLocationMarker', 'mobileUserLocationCircle');
    updateNearbyRadiusOverlay(refs.mobileMap, 'mobileNearbyRadiusLayer');
  }
  if (recenter && refs.userLocation && mapInstance) {
    const targetZoom = Math.max(mapInstance.getZoom?.() || 0, 14);
    mapInstance.flyTo([refs.userLocation.lat, refs.userLocation.lng], targetZoom, { duration: 0.8 });
  }
  syncGpsButtons();
}

export function clearNearbyRadiusOverlays() {
  clearLayerRef('nearbyRadiusLayer');
  clearLayerRef('mobileNearbyRadiusLayer');
}

function geolocationErrorMessage(error) {
  if (!error) return 'Could not get your location right now.';
  if (error.code === 1) return 'Location permission was denied.';
  if (error.code === 2) return 'Your location is unavailable right now.';
  if (error.code === 3) return 'Getting your location timed out.';
  return 'Could not get your location right now.';
}

export async function requestUserLocation({ mapInstance = refs.map || refs.mobileMap, recenter = true } = {}) {
  if (!navigator.geolocation) {
    track('location_permission_result', { outcome: 'error' });
    notify('Your browser does not support location services.', { tone: 'error' });
    throw new Error('unsupported');
  }

  const location = await new Promise((resolve, reject) => {
    navigator.geolocation.getCurrentPosition(
      pos => resolve({
        lat: pos.coords.latitude,
        lng: pos.coords.longitude,
        accuracy: pos.coords.accuracy || 0,
        ts: Date.now(),
      }),
      err => reject(err),
      { enableHighAccuracy: true, timeout: 12000, maximumAge: 120000 },
    );
  }).catch(error => {
    track('location_permission_result', { outcome: error?.code === 1 ? 'denied' : 'error' });
    notify(geolocationErrorMessage(error), { tone: 'error' });
    throw error;
  });

  track('location_permission_result', { outcome: 'granted' });
  refs.userLocation = location;
  persistUserLocation(location);
  refreshUserLocationOverlays({ recenter, mapInstance });
  return location;
}

function createGpsControl(mapInstance) {
  return L.Control.extend({
    options: { position: 'topright' },
    onAdd() {
      const container = L.DomUtil.create('div', 'map-gps-control');
      const button = L.DomUtil.create('button', 'map-gps-btn', container);
      button.type = 'button';
      button.title = 'Use my location';
      button.setAttribute('aria-label', 'Use my location');
      button.innerHTML = `
        <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2.15" d="M12 2.75V5.25M12 18.75v2.5M21.25 12h-2.5M5.25 12h-2.5"/>
          <circle cx="12" cy="12" r="6.6" stroke-width="2.15"/>
          <circle cx="12" cy="12" r="2.8" fill="currentColor" stroke="none"/>
        </svg>
      `;
      L.DomEvent.disableClickPropagation(container);
      L.DomEvent.disableScrollPropagation(container);
      button.addEventListener('click', async e => {
        e.preventDefault();
        if (button.disabled) return;
        button.disabled = true;
        button.classList.add('is-loading');
        try {
          await requestUserLocation({ mapInstance, recenter: true });
        } finally {
          button.disabled = false;
          button.classList.remove('is-loading');
        }
      });
      window.setTimeout(syncGpsButtons, 0);
      return container;
    },
  });
}

function getAreaCounts() {
  if (refs.searchMode === 'viewport' && refs.mapAreaTotals && Object.keys(refs.mapAreaTotals).length) {
    return { ...refs.mapAreaTotals };
  }

  const counts = {};
  const cityName = CITY_DEFAULTS[S.city]?.name || 'Karachi';
  refs.currentResults.forEach(r => {
    const area = getAreaForListing(r);
    if (area && area.name !== cityName) counts[area.name] = (counts[area.name] || 0) + 1;
  });
  return counts;
}

function clearTransientAreaFocus() {
  refs.hoveredArea = null;
  if (!S.area) refs.previewArea = null;
}

function getCityBounds() {
  const cityName = CITY_DEFAULTS[S.city]?.name || 'Karachi';
  const points = refs.allAreas
    .filter(area => area.name !== cityName && area.lat && area.lng)
    .map(area => L.latLng(area.lat, area.lng));
  return points.length ? L.latLngBounds(points) : null;
}

function showAreaPreview(areaName) {
  refs.previewArea = areaName;
  refs.hoveredArea = null;
}

function isMobileOverlayVisible() {
  const overlay = $('#mapOverlay');
  return Boolean(overlay && !overlay.classList.contains('hidden'));
}

function cancelExactLocationPrefetch() {
  clearTimeout(exactPrefetchTimer);
  if (exactPrefetchController) {
    exactPrefetchController.abort();
    exactPrefetchController = null;
  }
  exactPrefetchSession += 1;
}

function canPrefetchExactLocation(item) {
  if (!item?.url || hasExactLocation(item)) return false;
  if (exactPrefetchPending.has(item.url) || exactPrefetchMissing.has(item.url)) return false;
  const lastAttempt = exactPrefetchCooldown.get(item.url) || 0;
  return Date.now() - lastAttempt > EXACT_PREFETCH_COOLDOWN_MS;
}

async function hydrateExactLocation(item, signal) {
  if (!canPrefetchExactLocation(item)) return false;

  exactPrefetchPending.add(item.url);
  exactPrefetchCooldown.set(item.url, Date.now());
  try {
    const resp = await fetch(`/api/listing-detail?url=${encodeURIComponent(item.url)}`, { signal });
    if (!resp.ok) return false;
    const data = await resp.json();
    if (data?.has_exact_geography && Number.isFinite(Number(data.latitude)) && Number.isFinite(Number(data.longitude))) {
      Object.assign(item, {
        latitude: Number(data.latitude),
        longitude: Number(data.longitude),
        location_source: data.location_source || 'listing_exact',
        has_exact_geography: true,
      });
      return true;
    }
    if (data?.source === 'live') exactPrefetchMissing.add(item.url);
    return false;
  } catch (error) {
    if (error?.name === 'AbortError') return false;
    return false;
  } finally {
    exactPrefetchPending.delete(item.url);
  }
}

function scheduleExactLocationPrefetch(mapInstance = refs.map, { mobile = false } = {}) {
  cancelExactLocationPrefetch();
  if (!mapInstance || refs.isLoading) return;
  if (mobile && !isMobileOverlayVisible()) return;

  const minZoom = mobile ? EXACT_MARKER_MIN_ZOOM_MOBILE : EXACT_MARKER_MIN_ZOOM;
  if (mapInstance.getZoom() < minZoom || !refs.currentResults.length) return;

  exactPrefetchTimer = setTimeout(async () => {
    const candidates = refs.currentResults
      .filter(canPrefetchExactLocation)
      .slice(0, EXACT_PREFETCH_LIMIT);
    if (!candidates.length) return;

    const controller = new AbortController();
    const session = exactPrefetchSession;
    const resultSet = refs.currentResults;
    exactPrefetchController = controller;
    let anyUpdated = false;
    try {
      for (let i = 0; i < candidates.length; i += EXACT_PREFETCH_CONCURRENCY) {
        const batch = candidates.slice(i, i + EXACT_PREFETCH_CONCURRENCY);
        const results = await Promise.all(batch.map(item => hydrateExactLocation(item, controller.signal)));
        if (controller.signal.aborted || refs.currentResults !== resultSet || session !== exactPrefetchSession) return;
        if (results.some(Boolean)) anyUpdated = true;
      }

      if (anyUpdated && refs.currentResults === resultSet && session === exactPrefetchSession) {
        if (exactPrefetchController === controller) exactPrefetchController = null;
        updateMapMarkers();
        if (refs.mobileMap) updateMobileMarkers(refs._selectAreaFull);
      }
    } finally {
      if (exactPrefetchController === controller) exactPrefetchController = null;
    }
  }, 250);
}

function hasExactLocation(item) {
  return Boolean(
    item?.has_exact_geography
    && Number.isFinite(Number(item.latitude))
    && Number.isFinite(Number(item.longitude))
  );
}

function clearListingLayer(layerKey) {
  if (refs[layerKey]) {
    refs[layerKey].remove();
    refs[layerKey] = null;
  }
}

function getMarkerOffset(lat, lng, index) {
  if (!index) return [lat, lng];
  const angle = (index * 55) * (Math.PI / 180);
  const distance = 0.00008 * Math.ceil(index / 6);
  return [lat + (Math.sin(angle) * distance), lng + (Math.cos(angle) * distance)];
}

function syncListingCardHighlight(listingUrl, active) {
  if (!listingUrl || !window.CSS?.escape) return;
  const card = document.querySelector(`.card-wrap[data-url="${window.CSS.escape(listingUrl)}"]`);
  if (card) card.classList.toggle('card-map-active', active);
}

function handleAreaMarkerClick(area, selectAreaFull, mapInstance = refs.map, { mobile = false } = {}) {
  const count = refs.areaCounts[area.name] || 0;
  const hasResults = count > 0 || area.name === S.area;

  if (hasResults) {
    refs.previewArea = null;
    refs.hoveredArea = null;
    if (mobile) {
      selectAreaFull(area.name, true);
    } else {
      selectAreaFull(area.name);
    }
    return;
  }

  showAreaPreview(area.name);
  updateMapMarkers();
  refs._refreshCoverageUI?.();
  if (mobile) updateMobileMarkers(selectAreaFull);

  const targetZoom = Math.max(mapInstance?.getZoom?.() ?? 11, 13);
  mapInstance?.flyTo([area.lat, area.lng], targetZoom, { duration: 0.6 });
}

function updateListingMarkers(mapInstance = refs.map, { mobile = false } = {}) {
  const layerKey = mobile ? 'mobileListingMarkerLayer' : 'listingMarkerLayer';
  clearListingLayer(layerKey);
  if (!mapInstance) return;
  if (!['viewport', 'nearby'].includes(refs.searchMode)) return;

  const minZoom = mobile ? EXACT_MARKER_MIN_ZOOM_MOBILE : EXACT_MARKER_MIN_ZOOM;
  if (mapInstance.getZoom() < minZoom) return;

  const bounds = mapInstance.getBounds();
  const exactListings = refs.currentResults.filter(item => {
    if (!hasExactLocation(item)) return false;
    return bounds.contains(L.latLng(Number(item.latitude), Number(item.longitude)));
  });
  if (!exactListings.length) return;

  const layer = L.layerGroup();
  const duplicateCounts = new Map();

  exactListings.forEach(item => {
    const lat = Number(item.latitude);
    const lng = Number(item.longitude);
    const key = `${lat.toFixed(6)},${lng.toFixed(6)}`;
    const duplicateIndex = duplicateCounts.get(key) || 0;
    duplicateCounts.set(key, duplicateIndex + 1);
    const [markerLat, markerLng] = getMarkerOffset(lat, lng, duplicateIndex);
    const radius = mobile ? 5.5 : 6.5;
    const marker = L.circleMarker([markerLat, markerLng], {
      radius,
      className: 'listing-exact-marker',
      color: '#ffffff',
      weight: 2,
      opacity: 1,
      fillColor: '#ef4444',
      fillOpacity: 0.95,
      bubblingMouseEvents: true,
    });

    marker.on('click', () => {
      if (mobile) {
        cancelExactLocationPrefetch();
        $('#mapOverlay').classList.add('hidden');
      }
      refs._openDrawer?.(item);
    });
    marker.on('mouseover', () => {
      marker.setStyle({ radius: radius + 1.5, fillColor: '#dc2626' });
      syncListingCardHighlight(item.url, true);
    });
    marker.on('mouseout', () => {
      marker.setStyle({ radius, fillColor: '#ef4444' });
      syncListingCardHighlight(item.url, false);
    });

    if (!mobile) {
      marker.bindTooltip(
        `<div class="text-[11px] font-semibold text-gray-800">${esc(item.title || 'Rental')}</div><div class="text-[10px] text-gray-500">${esc(fmtPrice(item.price, item.price_text))}</div>`,
        { direction: 'top', offset: [0, -8], opacity: 0.96 },
      );
    }

    marker.addTo(layer);
  });

  layer.addTo(mapInstance);
  refs[layerKey] = layer;
}

function createIcon(name, active, count, mapInstance = refs.map || refs.mobileMap, variant = 'covered', showLabel = active) {
  if (showLabel) {
    const cls = active ? 'area-label area-label-active' : 'area-label';
    const badge = count ? `<span class="area-badge">${count}</span>` : '';
    return L.divIcon({
      className: 'area-marker',
      html: `<div class="${cls}" style="transform:translate(-50%,-50%)">${esc(name)}${badge}</div>`,
      iconSize: [0, 0],
      iconAnchor: [0, 0],
    });
  }

  if (variant === 'coverage') {
    return L.divIcon({
      className: 'area-marker',
      html: '<div class="coverage-dot"></div>',
      iconSize: [6, 6],
      iconAnchor: [3, 3],
    });
  }
  return L.divIcon({
    className: 'area-marker',
    html: `<div class="${active ? 'area-dot area-dot-active' : 'area-dot area-dot-live'}"></div>`,
    iconSize: [10, 10],
    iconAnchor: [5, 5],
  });
}

function isSubArea(childName, parentName) {
  if (!parentName) return false;
  const cl = childName.toLowerCase();
  const pl = parentName.toLowerCase();
  return cl !== pl && (cl.startsWith(pl + ' ') || cl.startsWith(pl + ' - '));
}

function shouldShowAreaLabel(mapInstance, { active = false, hovered = false, preview = false } = {}) {
  if (!active && !hovered && !preview) return false;
  const zoom = mapInstance?.getZoom?.() ?? 0;
  return zoom < AREA_LABEL_HIDE_ZOOM;
}

export function getVisibleAreaNames(mapInstance = refs.map) {
  if (!mapInstance || !refs.allAreas.length) return [];
  const bounds = mapInstance.getBounds();
  const cityName = CITY_DEFAULTS[S.city]?.name || 'Karachi';
  return refs.allAreas
    .filter(a => a.name !== cityName && a.lat && a.lng && bounds.contains(L.latLng(a.lat, a.lng)))
    .map(a => a.name);
}

export function fitCityOverview(mapInstance = refs.map, { animate = false } = {}) {
  if (!mapInstance) return;
  const bounds = getCityBounds();
  if (!bounds) {
    const cd = CITY_DEFAULTS[S.city];
    mapInstance.setView([cd.lat, cd.lng], cd.zoom, { animate });
    return;
  }
  mapInstance.fitBounds(bounds, {
    animate,
    maxZoom: CITY_DEFAULTS[S.city]?.zoom || 11,
    padding: [24, 24],
  });
}

export function updateMapMarkers() {
  const map = refs.map;
  if (!map) return;

  refs.areaCounts = getAreaCounts();
  const bounds = map.getBounds();
  const active = S.area;

  Object.entries(refs.markers).forEach(([name, marker]) => {
    const count = refs.areaCounts[name] || 0;
    const hasResults = count > 0;
    const isActive = name === active;
    const isHovered = refs.hoveredArea === name;
    const isPreview = refs.previewArea === name;
    const inView = bounds.contains(marker.getLatLng());
    const showLabel = shouldShowAreaLabel(map, {
      active: isActive,
      hovered: isHovered,
      preview: isPreview,
    });
    const variant = hasResults || isActive ? 'covered' : 'coverage';
    marker.setZIndexOffset(showLabel ? AREA_LABEL_Z_INDEX : 0);

    if (isActive) {
      const activeCount = refs.lastSearchTotal || count || 0;
      marker.setIcon(createIcon(name, true, showLabel ? activeCount : 0, map, 'covered', showLabel));
      if (!map.hasLayer(marker)) marker.addTo(map);
      return;
    }

    if (!inView) {
      if (map.hasLayer(marker)) map.removeLayer(marker);
      return;
    }

    marker.setIcon(createIcon(name, false, showLabel ? count : 0, map, variant, showLabel));
    if (!map.hasLayer(marker)) marker.addTo(map);
  });

  updateListingMarkers(map);
  scheduleExactLocationPrefetch(map);
}

export function ensureMarkers(selectAreaFull) {
  const map = refs.map;
  if (!map || !refs.allAreas.length) return;

  refs.allAreas.forEach(area => {
    const cityName = CITY_DEFAULTS[S.city]?.name || 'Karachi';
    if (!area.lat || !area.lng || area.name === cityName || refs.markers[area.name]) return;

    const marker = L.marker([area.lat, area.lng], { icon: createIcon(area.name, false, 0, map, 'coverage', false) });
    marker._areaName = area.name;
    marker.on('click', () => {
      handleAreaMarkerClick(area, selectAreaFull, map);
    });
    marker.on('mouseover', () => {
      refs.hoveredArea = area.name;
      updateMapMarkers();
      $$(`[data-area="${area.name}"]`).forEach(card => card.classList.add('card-map-active'));
    });
    marker.on('mouseout', () => {
      if (refs.hoveredArea === area.name) {
        refs.hoveredArea = null;
        updateMapMarkers();
      }
      $$(`[data-area="${area.name}"]`).forEach(card => card.classList.remove('card-map-active'));
    });
    refs.markers[area.name] = marker;
  });

  updateMapMarkers();
}

export function highlightMarker(name, flyTo) {
  const map = refs.map;
  if (!map) return;
  refs.previewArea = null;
  refs.hoveredArea = null;
  updateMapMarkers();
  if (name && refs.markers[name] && flyTo) {
    const hasSubs = refs.allAreas.some(a => isSubArea(a.name, name));
    map.flyTo(refs.markers[name].getLatLng(), hasSubs ? 13 : 14, { duration: 0.8 });
  }
}

export function resetMapView() {
  const map = refs.map;
  if (!map) return;
  fitCityOverview(map, { animate: true });
}

function syncDesktopViewport() {
  refs.hoveredArea = null;
  updateMapMarkers();
  refs._onViewportChange?.();
}

export function initMap(selectAreaFull, onViewportChange, openDrawer) {
  refs._selectAreaFull = selectAreaFull;
  refs._onViewportChange = onViewportChange;
  refs._openDrawer = openDrawer;

  const cd = CITY_DEFAULTS[S.city];
  ensureMapLayerState();
  refs.map = L.map('mapContainer', { zoomControl: false }).setView([cd.lat, cd.lng], cd.zoom);
  applyBaseLayer(refs.map, 'mapBaseLayer', refs.mapLayer);
  refs.map.addControl(new (createLayerToggleControl())());
  refs.map.addControl(new (createGpsControl(refs.map))());
  L.control.zoom({ position: 'topright' }).addTo(refs.map);

  setTimeout(() => refs.map?.invalidateSize(), 100);
  fitCityOverview(refs.map);
  ensureMarkers(selectAreaFull);
  refreshUserLocationOverlays();
  syncLayerToggleButtons();

  refs.map.on('moveend', syncDesktopViewport);
  refs.map.on('zoomend', syncDesktopViewport);

  if (window.ResizeObserver) {
    new ResizeObserver(() => { if (refs.map) refs.map.invalidateSize(); }).observe($('#mapPanel'));
  }
}

function renderMobileMapCard(item) {
  const img = item.image_url;
  const distanceLabel = formatDistance(item.distance_km, { approximate: item.is_distance_approximate });
  return `<div class="shrink-0 w-64 bg-white rounded-xl shadow-lg border border-gray-100 overflow-hidden cursor-pointer" style="scroll-snap-align:start" data-mobile-card-url="${escA(item.url || '')}">
    ${img ? `<img class="w-full h-32 object-cover" src="${escA(img)}" alt="" loading="lazy">` : `<div class="w-full h-32 bg-gray-100 flex items-center justify-center text-3xl text-gray-300">&#x1f3e0;</div>`}
    <div class="p-2.5">
      <div class="text-sm font-bold text-gray-800">${esc(fmtPrice(item.price, item.price_text))}</div>
      <div class="text-xs text-gray-500 line-clamp-1">${esc(item.title || 'Rental')}</div>
      ${distanceLabel ? `<div class="mt-1 text-[11px] font-semibold text-brand-600">${esc(distanceLabel)}</div>` : ''}
      <div class="flex gap-2 mt-1 text-[11px] text-gray-400">
        ${item.bedrooms ? `<span>${item.bedrooms} bed</span>` : ''}
        ${item.bathrooms ? `<span>${item.bathrooms} bath</span>` : ''}
        ${item.area_size ? `<span>${esc(item.area_size)}</span>` : ''}
      </div>
    </div>
  </div>`;
}

export function updateMobileCarousel(items = refs.currentResults) {
  const carousel = $('#mapCarousel');
  if (!carousel) return;
  if (!items.length) {
    carousel.classList.add('hidden');
    carousel.innerHTML = '';
    return;
  }
  carousel.innerHTML = items.slice(0, 10).map(renderMobileMapCard).join('');
  carousel.classList.remove('hidden');
  carousel.classList.add('flex');
}

export function updateMobileMarkers(selectAreaFull) {
  const map = refs.mobileMap;
  if (!map) return;
  if (refs.mobileMarkerLayer) refs.mobileMarkerLayer.remove();

  const layer = L.layerGroup();
  const counts = getAreaCounts();
  const cityName = CITY_DEFAULTS[S.city]?.name || 'Karachi';
  const bounds = map.getBounds();

  refs.allAreas.forEach(area => {
    if (!area.lat || !area.lng || area.name === cityName || !bounds.contains(L.latLng(area.lat, area.lng))) return;
    const count = counts[area.name] || 0;
    const isActive = area.name === S.area;
    const showLabel = shouldShowAreaLabel(map, {
      active: isActive,
      preview: refs.previewArea === area.name,
    });
    const variant = count || isActive ? 'covered' : 'coverage';
    const icon = createIcon(area.name, isActive, showLabel ? count : 0, map, variant, showLabel);
    L.marker([area.lat, area.lng], { icon, zIndexOffset: showLabel ? AREA_LABEL_Z_INDEX : 0 }).on('click', () => {
      handleAreaMarkerClick(area, selectAreaFull, map, { mobile: true });
    }).addTo(layer);
  });

  layer.addTo(map);
  refs.mobileMarkerLayer = layer;
  updateListingMarkers(map, { mobile: true });
  scheduleExactLocationPrefetch(map, { mobile: true });
}

export function initMobileMap(selectAreaFull, openDrawer, onViewportChange) {
  refs._onMobileViewportChange = onViewportChange;
  refs._openDrawer = openDrawer;
  refs._selectAreaFull = selectAreaFull;

  $('#mapFab').addEventListener('click', () => {
    $('#mapOverlay').classList.remove('hidden');

    if (!refs.mobileMap) {
      const cd = CITY_DEFAULTS[S.city];
      ensureMapLayerState();
      refs.mobileMap = L.map('mapContainerMobile', { zoomControl: false }).setView([cd.lat, cd.lng], cd.zoom);
      applyBaseLayer(refs.mobileMap, 'mobileMapBaseLayer', refs.mapLayer);
      refs.mobileMap.addControl(new (createLayerToggleControl())());
      refs.mobileMap.addControl(new (createGpsControl(refs.mobileMap))());
      L.control.zoom({ position: 'topright' }).addTo(refs.mobileMap);
      fitCityOverview(refs.mobileMap);
      refreshUserLocationOverlays();
      syncLayerToggleButtons();
      refs.mobileMap.on('moveend', () => {
        if (!isMobileOverlayVisible()) return;
        refs._onMobileViewportChange?.();
      });
      refs.mobileMap.on('zoomend', () => {
        updateMobileMarkers(selectAreaFull);
        if (isMobileOverlayVisible()) refs._onMobileViewportChange?.();
      });
    }

    setTimeout(() => refs.mobileMap?.invalidateSize(), 100);
    if (S.area && refs.markers[S.area]) refs.mobileMap.setView(refs.markers[S.area].getLatLng(), 14);
    updateMobileMarkers(selectAreaFull);
    updateMobileCarousel(refs.currentResults);
    if (!S.area && isMobileOverlayVisible()) refs._onMobileViewportChange?.();
  });

  $('#mapCarousel').addEventListener('click', e => {
    const card = e.target.closest('[data-mobile-card-url]');
    if (!card) return;
    const idx = [...$('#mapCarousel').children].indexOf(card);
    if (refs.currentResults[idx]) {
      cancelExactLocationPrefetch();
      $('#mapOverlay').classList.add('hidden');
      openDrawer(refs.currentResults[idx]);
    }
  });

  $('#mapOverlayClose').addEventListener('click', () => {
    cancelExactLocationPrefetch();
    $('#mapOverlay').classList.add('hidden');
  });
}

export function initHoverSync() {
  const grid = $('#listingsGrid');
  grid.addEventListener('mouseover', e => {
    const card = e.target.closest('[data-area]');
    if (!card || !refs.map) return;
    refs.hoveredArea = card.dataset.area;
    updateMapMarkers();
  });

  grid.addEventListener('mouseout', e => {
    const card = e.target.closest('[data-area]');
    if (!card || !refs.map) return;
    if (refs.hoveredArea === card.dataset.area) {
      refs.hoveredArea = null;
      updateMapMarkers();
    }
  });
}
