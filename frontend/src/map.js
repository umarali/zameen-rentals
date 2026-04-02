/** Leaflet map: desktop viewport browsing, markers, and mobile map overlay. */

import { $, $$, esc, escA, fmtPrice } from './utils.js';
import { S, refs, CITY_DEFAULTS } from './state.js';
import { getAreaForListing } from './cards.js';

const EXACT_MARKER_MIN_ZOOM = 11;
const EXACT_MARKER_MIN_ZOOM_MOBILE = 12;
const EXACT_PREFETCH_LIMIT = 10;
const EXACT_PREFETCH_CONCURRENCY = 3;
const EXACT_PREFETCH_COOLDOWN_MS = 30000;

let exactPrefetchTimer = null;
let exactPrefetchController = null;
let exactPrefetchSession = 0;
const exactPrefetchPending = new Set();
const exactPrefetchMissing = new Set();
const exactPrefetchCooldown = new Map();

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
    const showLabel = isActive || isHovered || isPreview;
    const variant = hasResults || isActive ? 'covered' : 'coverage';

    if (isActive) {
      const activeCount = refs.lastSearchTotal || count || 0;
      marker.setIcon(createIcon(name, true, activeCount, map, 'covered', true));
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
  refs.map = L.map('mapContainer', { zoomControl: true }).setView([cd.lat, cd.lng], cd.zoom);
  L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
    attribution: '&copy; OpenStreetMap',
    maxZoom: 18,
  }).addTo(refs.map);

  setTimeout(() => refs.map?.invalidateSize(), 100);
  fitCityOverview(refs.map);
  ensureMarkers(selectAreaFull);

  refs.map.on('moveend', syncDesktopViewport);
  refs.map.on('zoomend', syncDesktopViewport);

  if (window.ResizeObserver) {
    new ResizeObserver(() => { if (refs.map) refs.map.invalidateSize(); }).observe($('#mapPanel'));
  }
}

function renderMobileMapCard(item) {
  const img = item.image_url;
  return `<div class="shrink-0 w-64 bg-white rounded-xl shadow-lg border border-gray-100 overflow-hidden cursor-pointer" style="scroll-snap-align:start" data-mobile-card-url="${escA(item.url || '')}">
    ${img ? `<img class="w-full h-32 object-cover" src="${escA(img)}" alt="" loading="lazy">` : `<div class="w-full h-32 bg-gray-100 flex items-center justify-center text-3xl text-gray-300">&#x1f3e0;</div>`}
    <div class="p-2.5">
      <div class="text-sm font-bold text-gray-800">${esc(fmtPrice(item.price, item.price_text))}</div>
      <div class="text-xs text-gray-500 line-clamp-1">${esc(item.title || 'Rental')}</div>
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
    const showLabel = isActive || refs.previewArea === area.name;
    const variant = count || isActive ? 'covered' : 'coverage';
    const icon = createIcon(area.name, isActive, showLabel ? count : 0, map, variant, showLabel);
    L.marker([area.lat, area.lng], { icon }).on('click', () => {
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
      refs.mobileMap = L.map('mapContainerMobile', { zoomControl: true }).setView([cd.lat, cd.lng], cd.zoom);
      L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
        attribution: '&copy; OpenStreetMap',
        maxZoom: 18,
      }).addTo(refs.mobileMap);
      fitCityOverview(refs.mobileMap);
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
