/** Leaflet maps (desktop panel and mobile overlay): every matching rental as a pin, list↔map sync, Near Me. */

import L from 'leaflet';
import 'leaflet/dist/leaflet.css';
import { $, $$, esc, escA, fmtPrice, showToast } from './utils.js';
import { S, refs, CITY_DEFAULTS } from './state.js';
import { track } from './analytics.js';
import {
  createBaseLayer,
  getStoredMapLayer,
  persistMapLayer,
  sanitizeMapLayerKey,
} from './map-layers.js';
import {
  initMapPins, renderPins, refreshPinStates, setHoveredListing, setSelectedListing,
  getSelectedListing, getListingSummary, renderPreviewCard, renderStackCard,
  countListingsInBounds, pinsReady, onPinsLoaded, motionAllowed,
} from './map-pins.js';
import { bedIcon, bathIcon } from './icons.js';

const USER_LOCATION_STORAGE_KEY = 'rk_userLocation';
const USER_LOCATION_TTL_MS = 30 * 60 * 1000;
const AREA_LABEL_Z_INDEX = 1400;
const AREA_LABEL_HIDE_ZOOM = 13;
const AUTOSEARCH_STORAGE_KEY = 'rk_mapAutoSearch';
// A move we caused ourselves is "programmatic" (no "Search this area" pill)
// or "quiet" (no search at all, e.g. a popup nudging the map into view).
const QUIET_MOVE_MS = 1200;
const PROGRAMMATIC_MOVE_MS = 2500;
// Share of area centroids dropped from each edge when framing a city: a few
// outlying societies otherwise leave the city itself small in one corner.
const CITY_FRAME_TRIM = 0.08;

refs.mapAutoSearch = loadAutoSearch();

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

function applyBaseLayerAfterPageLoad(mapInstance, layerRefKey) {
  if (document.readyState === 'complete') {
    applyBaseLayer(mapInstance, layerRefKey, refs.mapLayer);
    return;
  }
  window.addEventListener(
    'load',
    () => applyBaseLayer(mapInstance, layerRefKey, refs.mapLayer),
    { once: true },
  );
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
        <button type="button" class="map-layer-btn" data-map-layer="osm" aria-pressed="false">Street</button>
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
    flagMove(mapInstance, 'programmatic');
    mapInstance.flyTo([refs.userLocation.lat, refs.userLocation.lng], targetZoom, { duration: 0.8, animate: motionAllowed() });
  }
  syncGpsButtons();
}

export function clearNearbyRadiusOverlays() {
  clearLayerRef('nearbyRadiusLayer');
  clearLayerRef('mobileNearbyRadiusLayer');
}

export function getNearestCity(location) {
  return getNearestCityWithDistance(location).city;
}

// Beyond this distance from every city centre, Near Me has nothing to show:
// the furthest covered suburbs (Bahria Town Karachi, DHA City) sit well inside it.
export const NEAR_ME_MAX_CITY_KM = 75;

export function getNearestCityWithDistance(location) {
  const point = L.latLng(location.lat, location.lng);
  let best = null;
  for (const city of Object.keys(CITY_DEFAULTS)) {
    const km = point.distanceTo(CITY_DEFAULTS[city]) / 1000;
    if (!best || km < best.km) best = { city, km };
  }
  return best;
}

// The TTL is checked when a stored location is loaded, but an app left open
// for hours (an installed PWA) keeps its in-memory location; check it again.
export function isUserLocationFresh(location = refs.userLocation) {
  return !!location?.ts && Date.now() - location.ts <= USER_LOCATION_TTL_MS;
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

// ===== Who moved the map =====

function flagMove(map, kind) {
  if (!map) return;
  map._zrMove = { kind, until: Date.now() + (kind === 'quiet' ? QUIET_MOVE_MS : PROGRAMMATIC_MOVE_MS) };
}

function consumeMoveKind(map) {
  const flag = map._zrMove;
  map._zrMove = null;
  return flag && Date.now() <= flag.until ? flag.kind : 'user';
}

function watchMoves(map, onMoveEnd) {
  map.on('dragstart', () => { map._zrMove = null; });
  map.on('moveend', () => onMoveEnd(consumeMoveKind(map)));
}

// ===== "Search as I move the map" =====

function loadAutoSearch() {
  try { return localStorage.getItem(AUTOSEARCH_STORAGE_KEY) !== '0'; } catch { return true; }
}

export function isMapAutoSearch() {
  return refs.mapAutoSearch !== false;
}

export function setMapAutoSearch(on) {
  refs.mapAutoSearch = Boolean(on);
  try { localStorage.setItem(AUTOSEARCH_STORAGE_KEY, on ? '1' : '0'); } catch {}
  track('map_autosearch_toggle', { on: Boolean(on) });
  $$('[data-map-autosearch]').forEach(box => { box.checked = Boolean(on); });
  refs._onAutoSearchChange?.(Boolean(on));
}

export function showSearchAreaPill(show, label = 'Search this area') {
  $$('.map-search-area').forEach(btn => {
    btn.classList.toggle('hidden', !show);
    if (show) btn.textContent = label;
  });
}

export function isSearchAreaPillVisible() {
  return $$('.map-search-area').some(btn => !btn.classList.contains('hidden'));
}

// ===== Summary and map key =====

function summaryText(map) {
  if (!map || !pinsReady()) return null;
  const n = countListingsInBounds(map.getBounds());
  return { count: n.toLocaleString(), label: n === 1 ? 'rental in this view' : 'rentals in this view', empty: n === 0 };
}

export function updateMapSummary() {
  const desktop = summaryText(refs.map);
  const mobile = summaryText(refs.mobileMap);
  $$('#mapCoverageBadge [data-map-count], #mapCoverageBadge [data-map-count-label], #mapSheetBar [data-map-count], #mapSheetBar [data-map-count-label]')
    .forEach(el => {
      const inMobile = Boolean(el.closest('#mapSheetBar'));
      const summary = inMobile ? mobile : desktop;
      if (el.hasAttribute('data-map-count')) el.textContent = summary ? summary.count : '…';
      else el.textContent = summary ? (summary.empty ? 'No matching rentals in this view' : summary.label) : 'Loading rentals';
      el.closest('[data-map-summary]')?.classList.toggle('is-empty', Boolean(summary?.empty));
    });
}

function initMapChrome() {
  $$('[data-map-autosearch]').forEach(box => {
    box.checked = isMapAutoSearch();
    box.addEventListener('change', () => setMapAutoSearch(box.checked));
  });
  $$('[data-map-key-toggle]').forEach(btn => {
    btn.addEventListener('click', () => {
      const panel = btn.parentElement.querySelector('[data-map-key]');
      const open = panel.classList.toggle('hidden') === false;
      btn.setAttribute('aria-expanded', String(open));
    });
  });
  $$('.map-search-area').forEach(btn => {
    btn.addEventListener('click', () => refs._searchThisArea?.({ mobile: Boolean(btn.closest('#mapOverlay')) }));
  });
  onPinsLoaded(() => {
    updateMapSummary();
    if (refs.mobileMap && isMobileOverlayVisible()) updateMobileCarousel();
  });
}

// ===== Pins: clicks, popups, list sync =====

function cardFor(id) {
  if (!id || !window.CSS?.escape) return null;
  return document.querySelector(`#listingsGrid .card-wrap[data-zameen-id="${window.CSS.escape(String(id))}"]`);
}

function highlightCard(id, { scroll = false } = {}) {
  $$('#listingsGrid .card-map-selected').forEach(card => card.classList.remove('card-map-selected'));
  const card = cardFor(id);
  if (!card) return;
  card.classList.add('card-map-selected');
  if (scroll) card.scrollIntoView({ block: 'nearest', behavior: motionAllowed() ? 'smooth' : 'auto' });
}

function bindPopupAction(popup, selector, handler) {
  const el = popup.getElement()?.querySelector(selector);
  if (el) el.addEventListener('click', handler);
}

function openPopup(map, latlng, html) {
  const popup = L.popup({
    className: 'pin-popup',
    maxWidth: 300,
    minWidth: 250,
    offset: [0, -32],
    // Clear the summary card and the layer, GPS and zoom controls.
    autoPanPaddingTopLeft: [24, 150],
    autoPanPaddingBottomRight: [72, 24],
  }).setLatLng(latlng).setContent(html);
  flagMove(map, 'quiet');
  popup.openOn(map);
  return popup;
}

async function openPinPopup(id, map, latlng) {
  setSelectedListing(id);
  highlightCard(id, { scroll: true });
  const popup = openPopup(map, latlng, '<div class="pin-preview-loading">Loading…</div>');
  popup.on('remove', () => {
    if (getSelectedListing() === id) setSelectedListing(null);
    highlightCard(null);
  });
  try {
    const item = await getListingSummary(id);
    if (!map.hasLayer(popup)) return;
    flagMove(map, 'quiet');
    popup.setContent(renderPreviewCard(item));
    bindPopupAction(popup, '[data-preview-open]', () => {
      map.closePopup(popup);
      refs._openDrawer?.(item);
    });
  } catch {
    if (map.hasLayer(popup)) popup.setContent('<div class="pin-preview-loading">Could not load this listing.</div>');
  }
}

function openStackPopup(stack, map) {
  const popup = openPopup(map, [stack.lat, stack.lng], renderStackCard(stack));
  bindPopupAction(popup, '[data-stack-search]', () => {
    map.closePopup(popup);
    refs._searchStack?.(stack, { mobile: map === refs.mobileMap });
  });
}

function onPinHover(id, on) {
  const card = cardFor(id);
  if (card) card.classList.toggle('card-map-active', on);
}

initMapPins({
  onPinClick: (id, map, latlng) => {
    if (map === refs.mobileMap) selectMobileListing(id);
    else openPinPopup(id, map, latlng);
  },
  onStackClick: openStackPopup,
  onPinHover,
});

export function initHoverSync() {
  const grid = $('#listingsGrid');
  let current = null;
  grid.addEventListener('mouseover', e => {
    const card = e.target.closest('.card-wrap[data-zameen-id]');
    const id = card?.dataset.zameenId || null;
    if (id === current) return;
    current = id;
    setHoveredListing(id);
  });
  grid.addEventListener('mouseleave', () => {
    current = null;
    setHoveredListing(null);
  });
}

// ===== Active area label =====

function createAreaLabelIcon(name, count) {
  const badge = count ? `<span class="area-badge">${count.toLocaleString()}</span>` : '';
  return L.divIcon({
    className: 'area-marker',
    html: `<div class="area-label area-label-active" style="transform:translate(-50%,-50%)">${esc(name)}${badge}</div>`,
    iconSize: [0, 0],
    iconAnchor: [0, 0],
  });
}

function updateAreaLabel(map, refKey) {
  if (!map) return;
  const area = S.area ? refs.allAreas.find(a => a.name === S.area) : null;
  if (!area?.lat || !area?.lng || map.getZoom() >= AREA_LABEL_HIDE_ZOOM) {
    clearLayerRef(refKey);
    return;
  }
  const icon = createAreaLabelIcon(area.name, refs.lastSearchTotal || 0);
  if (!refs[refKey]) {
    refs[refKey] = L.marker([area.lat, area.lng], {
      icon, interactive: false, keyboard: false, zIndexOffset: AREA_LABEL_Z_INDEX,
    }).addTo(map);
  } else {
    refs[refKey].setLatLng([area.lat, area.lng]);
    refs[refKey].setIcon(icon);
  }
}

function isSubArea(childName, parentName) {
  if (!parentName) return false;
  const cl = childName.toLowerCase();
  const pl = parentName.toLowerCase();
  return cl !== pl && (cl.startsWith(pl + ' ') || cl.startsWith(pl + ' - '));
}

// ===== Framing =====

function cityAreaPoints() {
  const cityName = CITY_DEFAULTS[S.city]?.name || 'Karachi';
  return refs.allAreas.filter(area => area.name !== cityName && area.lat && area.lng);
}

function getCityBounds() {
  const points = cityAreaPoints();
  if (!points.length) return null;
  const lats = points.map(a => a.lat).sort((a, b) => a - b);
  const lngs = points.map(a => a.lng).sort((a, b) => a - b);
  const cut = Math.floor(points.length * CITY_FRAME_TRIM);
  const last = points.length - 1 - cut;
  return L.latLngBounds([lats[cut], lngs[cut]], [lats[last], lngs[last]]);
}

export function getVisibleAreaNames(mapInstance = refs.map) {
  if (!mapInstance || !refs.allAreas.length) return [];
  const bounds = mapInstance.getBounds();
  return cityAreaPoints()
    .filter(a => bounds.contains(L.latLng(a.lat, a.lng)))
    .map(a => a.name);
}

export function fitCityOverview(mapInstance = refs.map, { animate = false } = {}) {
  if (!mapInstance) return;
  flagMove(mapInstance, 'programmatic');
  const bounds = getCityBounds();
  if (!bounds) {
    const cd = CITY_DEFAULTS[S.city];
    mapInstance.setView([cd.lat, cd.lng], cd.zoom, { animate });
    return;
  }
  mapInstance.fitBounds(bounds, { animate: animate && motionAllowed(), maxZoom: 13, padding: [16, 16] });
}

export function highlightMarker(name, flyTo) {
  const map = refs.map;
  if (!map) return;
  updateMapMarkers();
  const area = name ? refs.allAreas.find(a => a.name === name) : null;
  if (area?.lat && area?.lng && flyTo) {
    const hasSubs = refs.allAreas.some(a => isSubArea(a.name, name));
    flagMove(map, 'programmatic');
    map.flyTo([area.lat, area.lng], hasSubs ? 13 : 14, { duration: 0.8, animate: motionAllowed() });
  }
}

export function resetMapView() {
  if (refs.map) fitCityOverview(refs.map, { animate: true });
}

/** City switch: drop the old city's label, popup and selection, then frame the new city. */
export function resetMapsForCity() {
  [refs.map, refs.mobileMap].forEach(map => map?.closePopup());
  clearLayerRef('areaLabelMarker');
  clearLayerRef('mobileAreaLabelMarker');
  setSelectedListing(null);
  setHoveredListing(null);
  mobileExtraItem = null;
  if (refs.map) fitCityOverview(refs.map);
  if (refs.mobileMap) fitCityOverview(refs.mobileMap);
}

// ===== Desktop map =====

export function updateMapMarkers() {
  if (!refs.map) return;
  updateAreaLabel(refs.map, 'areaLabelMarker');
  renderPins(refs.map);
  updateMapSummary();
}

// Kept for callers that predate pins: area markers are now just the active label.
export function ensureMarkers() {
  updateMapMarkers();
}

export function initMap(selectAreaFull, onViewportChange, openDrawer) {
  refs._selectAreaFull = selectAreaFull;
  refs._onViewportChange = onViewportChange;
  refs._openDrawer = openDrawer;

  const cd = CITY_DEFAULTS[S.city];
  ensureMapLayerState();
  refs.map = L.map('mapContainer', { zoomControl: false, maxZoom: 19 }).setView([cd.lat, cd.lng], cd.zoom);
  applyBaseLayerAfterPageLoad(refs.map, 'mapBaseLayer');
  refs.map.addControl(new (createLayerToggleControl())());
  refs.map.addControl(new (createGpsControl(refs.map))());
  L.control.zoom({ position: 'topright' }).addTo(refs.map);

  setTimeout(() => refs.map?.invalidateSize(), 100);
  watchMoves(refs.map, kind => {
    updateMapMarkers();
    refs._onViewportChange?.({ kind });
  });
  fitCityOverview(refs.map);
  updateMapMarkers();
  refreshUserLocationOverlays();
  syncLayerToggleButtons();

  if (window.ResizeObserver) {
    new ResizeObserver(() => { if (refs.map) refs.map.invalidateSize(); }).observe($('#mapPanel'));
  }
}

// ===== Mobile map overlay =====

let mobileExtraItem = null;
let mobileHistoryPushed = false;
let carouselObserver = null;

function isMobileOverlayVisible() {
  const overlay = $('#mapOverlay');
  return Boolean(overlay && !overlay.classList.contains('hidden'));
}

export function isMobileMapOpen() {
  return isMobileOverlayVisible();
}

function syncOverlayTop() {
  const shell = $('#filtersShell');
  const top = shell ? Math.max(0, Math.round(shell.getBoundingClientRect().bottom)) : 0;
  document.documentElement.style.setProperty('--map-overlay-top', `${top}px`);
}

function itemId(item) {
  return item?.zameen_id ? String(item.zameen_id) : '';
}

function renderMobileMapCard(item, { extra = false } = {}) {
  const id = itemId(item);
  const img = item.image_url;
  const facts = [
    item.bedrooms ? `<span>${bedIcon('w-3 h-3')}${item.bedrooms}</span>` : '',
    item.bathrooms ? `<span>${bathIcon('w-3 h-3')}${item.bathrooms}</span>` : '',
    item.area_size ? `<span>${esc(item.area_size)}</span>` : '',
  ].filter(Boolean).join('');
  return `<div class="map-card${extra ? ' is-extra' : ''}${id && id === getSelectedListing() ? ' is-selected' : ''}" role="button" tabindex="0" data-mobile-card-id="${escA(id)}" data-mobile-card-url="${escA(item.url || '')}">
    ${img ? `<img class="map-card-img" src="${escA(img)}" alt="" loading="lazy">` : '<div class="map-card-img img-fallback"></div>'}
    <div class="map-card-body">
      <div class="map-card-price">${esc(fmtPrice(item.price, item.price_text))}</div>
      <div class="map-card-title">${esc(item.title || 'Rental')}</div>
      ${item.location ? `<div class="map-card-loc">${esc(item.location)}</div>` : ''}
      ${facts ? `<div class="map-card-facts">${facts}</div>` : ''}
    </div>
  </div>`;
}

function carouselItems() {
  const items = refs.currentResults.slice();
  if (mobileExtraItem && !items.some(r => itemId(r) === itemId(mobileExtraItem))) items.unshift(mobileExtraItem);
  return items;
}

export function updateMobileCarousel() {
  const carousel = $('#mapCarousel');
  if (!carousel) return;
  const items = carouselItems();
  if (!items.length) {
    carousel.innerHTML = '';
    carousel.classList.add('hidden');
    carousel.classList.remove('flex');
    return;
  }
  const more = refs.lastSearchTotal > refs.currentResults.length
    ? '<button type="button" class="map-card map-card-more" data-carousel-more>Load more</button>'
    : '';
  carousel.innerHTML = items.map(item => renderMobileMapCard(item, { extra: item === mobileExtraItem })).join('') + more;
  carousel.classList.remove('hidden');
  carousel.classList.add('flex');
  observeCarousel(carousel);
}

function observeCarousel(carousel) {
  carouselObserver?.disconnect();
  if (!window.IntersectionObserver) return;
  carouselObserver = new IntersectionObserver(entries => {
    const visible = entries.filter(e => e.isIntersecting && e.intersectionRatio >= 0.6);
    if (!visible.length || !isMobileOverlayVisible()) return;
    const id = visible[0].target.dataset.mobileCardId;
    if (!id || id === getSelectedListing()) return;
    selectCarouselCard(id);
  }, { root: carousel, threshold: [0.6] });
  carousel.querySelectorAll('[data-mobile-card-id]').forEach(card => carouselObserver.observe(card));
}

function selectCarouselCard(id) {
  setSelectedListing(id);
  $$('#mapCarousel .map-card').forEach(card => card.classList.toggle('is-selected', card.dataset.mobileCardId === id));
  const map = refs.mobileMap;
  const item = carouselItems().find(r => itemId(r) === id);
  const lat = Number(item?.latitude);
  const lng = Number(item?.longitude);
  if (!map || !Number.isFinite(lat) || !Number.isFinite(lng)) return;
  if (!map.getBounds().pad(-0.15).contains([lat, lng])) {
    flagMove(map, 'quiet');
    map.panTo([lat, lng], { animate: motionAllowed() });
  }
}

function scrollCarouselTo(id) {
  const carousel = $('#mapCarousel');
  const card = carousel && window.CSS?.escape
    ? carousel.querySelector(`[data-mobile-card-id="${window.CSS.escape(id)}"]`)
    : null;
  if (!card) return;
  carousel.scrollTo({ left: card.offsetLeft - 12, behavior: motionAllowed() ? 'smooth' : 'auto' });
}

async function selectMobileListing(id) {
  setCarouselCollapsed(false);
  if (!refs.currentResults.some(r => itemId(r) === id)) {
    try {
      mobileExtraItem = await getListingSummary(id);
    } catch {
      showToast('Could not load this listing.', { tone: 'error' });
      return;
    }
    updateMobileCarousel();
  }
  selectCarouselCard(id);
  scrollCarouselTo(id);
}

function setCarouselCollapsed(collapsed) {
  const overlay = $('#mapOverlay');
  overlay?.classList.toggle('cards-collapsed', collapsed);
  const btn = $('#mapCardsToggle');
  if (btn) {
    btn.setAttribute('aria-expanded', String(!collapsed));
    btn.setAttribute('aria-label', collapsed ? 'Show listing cards' : 'Hide listing cards');
  }
}

export function updateMobileMarkers() {
  const map = refs.mobileMap;
  if (!map) return;
  updateAreaLabel(map, 'mobileAreaLabelMarker');
  renderPins(map);
  updateMapSummary();
}

function ensureMobileMap() {
  if (refs.mobileMap) return refs.mobileMap;
  const cd = CITY_DEFAULTS[S.city];
  ensureMapLayerState();
  const map = L.map('mapContainerMobile', { zoomControl: false, maxZoom: 19 }).setView([cd.lat, cd.lng], cd.zoom);
  refs.mobileMap = map;
  applyBaseLayer(map, 'mobileMapBaseLayer', refs.mapLayer);
  map.addControl(new (createLayerToggleControl())());
  map.addControl(new (createGpsControl(map))());
  L.control.zoom({ position: 'topright' }).addTo(map);
  watchMoves(map, kind => {
    updateMobileMarkers();
    if (isMobileOverlayVisible()) refs._onMobileViewportChange?.({ kind, mobile: true });
  });
  fitCityOverview(map);
  refreshUserLocationOverlays();
  syncLayerToggleButtons();
  return map;
}

function openMapOverlay() {
  refs._closeOtherOverlays?.('mapOverlay');
  syncOverlayTop();
  document.body.classList.add('map-open');
  $('#mapOverlay').classList.remove('hidden');
  try {
    history.pushState({ ...(history.state || {}), zrMap: true }, '');
    mobileHistoryPushed = true;
  } catch {
    mobileHistoryPushed = false;
  }
  track('map_opened', { surface: 'mobile', mode: refs.searchMode });

  const map = ensureMobileMap();
  const area = S.area ? refs.allAreas.find(a => a.name === S.area) : null;
  if (area?.lat && area?.lng) {
    flagMove(map, 'programmatic');
    map.setView([area.lat, area.lng], 14);
  } else if (refs.searchMode === 'nearby' && refs.userLocation) {
    flagMove(map, 'programmatic');
    map.setView([refs.userLocation.lat, refs.userLocation.lng], 14);
  }
  setTimeout(() => {
    map.invalidateSize();
    updateMobileMarkers();
    updateMobileCarousel();
    if (!S.area && refs.searchMode !== 'nearby') refs._onMobileViewportChange?.({ kind: 'programmatic', mobile: true });
  }, 100);
}

function closeMapOverlay({ fromPopState = false } = {}) {
  if (!isMobileOverlayVisible()) return;
  refs.mobileMap?.closePopup();
  $('#mapOverlay').classList.add('hidden');
  document.body.classList.remove('map-open');
  showSearchAreaPill(false);
  setSelectedListing(null);
  mobileExtraItem = null;
  if (!fromPopState && mobileHistoryPushed) {
    mobileHistoryPushed = false;
    history.back();
  } else {
    mobileHistoryPushed = false;
  }
}

export function initMobileMap(selectAreaFull, openDrawer, onViewportChange) {
  refs._onMobileViewportChange = onViewportChange;
  refs._openDrawer = openDrawer;
  refs._selectAreaFull = selectAreaFull;
  initMapChrome();

  $('#mapFab').addEventListener('click', openMapOverlay);
  $('#mapOverlayClose').addEventListener('click', () => closeMapOverlay());
  $('#mapCardsToggle')?.addEventListener('click', () => {
    setCarouselCollapsed(!$('#mapOverlay').classList.contains('cards-collapsed'));
  });

  const carousel = $('#mapCarousel');
  const openCard = target => {
    if (target.closest('[data-carousel-more]')) {
      refs._loadMoreResults?.({ mobile: true });
      return;
    }
    const card = target.closest('[data-mobile-card-id]');
    if (!card) return;
    const item = carouselItems().find(r => itemId(r) === card.dataset.mobileCardId)
      || refs.currentResults.find(r => (r.url || '') === card.dataset.mobileCardUrl);
    // The drawer opens over the map, so Back returns here.
    if (item) openDrawer(item);
  };
  carousel.addEventListener('click', e => openCard(e.target));
  carousel.addEventListener('keydown', e => {
    if (e.key === 'Enter' || e.key === ' ') {
      e.preventDefault();
      openCard(e.target);
    }
  });

  window.addEventListener('popstate', e => {
    if (isMobileOverlayVisible() && !e.state?.zrMap) closeMapOverlay({ fromPopState: true });
  });
  window.addEventListener('resize', () => { if (isMobileOverlayVisible()) syncOverlayTop(); });

  refs._registerOverlay?.({
    name: 'mapOverlay',
    isOpen: isMobileOverlayVisible,
    close: () => closeMapOverlay(),
  });
  document.addEventListener('keydown', e => {
    if (e.key === 'Escape' && isMobileOverlayVisible() && !$('#drawer').classList.contains('drawer-open')) closeMapOverlay();
  });
}

/** After a search: refresh the pins' view of the list, labels and the mobile cards. */
export function syncMapsWithResults() {
  mobileExtraItem = mobileExtraItem && refs.currentResults.some(r => itemId(r) === itemId(mobileExtraItem))
    ? null
    : mobileExtraItem;
  refreshPinStates();
  updateMapMarkers();
  if (refs.mobileMap) updateMobileMarkers();
  if (isMobileOverlayVisible()) updateMobileCarousel();
}

