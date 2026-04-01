/** Leaflet map: markers, visibility, search-here button, mobile map. */

import { $, $$, esc, escA, fmtPrice } from './utils.js';
import { S, refs, CITY_DEFAULTS } from './state.js';
import { getAreaForListing } from './cards.js';

// ===== AREA COUNTS =====

function getAreaCounts() {
  const counts = {};
  const cityName = CITY_DEFAULTS[S.city]?.name || 'Karachi';
  refs.currentResults.forEach(r => {
    const area = getAreaForListing(r);
    if (area && area.name !== cityName) {
      counts[area.name] = (counts[area.name] || 0) + 1;
    }
  });
  return counts;
}

// ===== MARKER ICONS =====

function createIcon(name, active, count) {
  const map = refs.map;
  if (map && map.getZoom() < 10) {
    return L.divIcon({
      className: 'area-marker',
      html: `<div class="w-2.5 h-2.5 rounded-full ${active ? 'bg-brand-500 ring-2 ring-white ring-offset-1 ring-offset-brand-500' : 'bg-brand-500 ring-2 ring-white'} shadow"></div>`,
      iconSize: [10, 10], iconAnchor: [5, 5],
    });
  }
  const cls = active ? 'area-label area-label-active' : 'area-label';
  const badge = count ? `<span class="area-badge">${count}</span>` : '';
  return L.divIcon({
    className: 'area-marker',
    html: `<div class="${cls}" style="transform:translate(-50%,-50%)">${esc(name)}${badge}</div>`,
    iconSize: [0, 0], iconAnchor: [0, 0],
  });
}

// ===== SUB-AREA DETECTION =====

function isSubArea(childName, parentName) {
  if (!parentName) return false;
  const cl = childName.toLowerCase(), pl = parentName.toLowerCase();
  return cl !== pl && (cl.startsWith(pl + ' ') || cl.startsWith(pl + ' - '));
}

// ===== MAP MARKERS =====

const MAX_LABELS = 15;

export function updateMapMarkers() {
  const map = refs.map;
  if (!map) return;
  refs.areaCounts = getAreaCounts();
  const zoom = map.getZoom();
  const bounds = map.getBounds();
  const active = S.area;

  let candidates = [];
  Object.entries(refs.markers).forEach(([name, m]) => {
    const hasResults = refs.areaCounts[name] > 0;
    const isActive = name === active;
    const isSub = isSubArea(name, active);
    const inView = bounds.contains(m.getLatLng());

    if (isActive) {
      const count = refs.lastSearchTotal || refs.areaCounts[name] || 0;
      m.setIcon(createIcon(name, true, count));
      if (!map.hasLayer(m)) m.addTo(map);
    } else if (isSub && inView) {
      candidates.push({ name, m, count: refs.areaCounts[name] || 0, priority: 1 });
    } else if (hasResults && inView && zoom >= 11) {
      candidates.push({ name, m, count: refs.areaCounts[name], priority: 0 });
    } else {
      if (map.hasLayer(m)) map.removeLayer(m);
    }
  });

  candidates.sort((a, b) => b.priority - a.priority || b.count - a.count);
  candidates.forEach((c, i) => {
    if (i < MAX_LABELS) {
      c.m.setIcon(createIcon(c.name, false, c.count));
      if (!map.hasLayer(c.m)) c.m.addTo(map);
    } else {
      if (map.hasLayer(c.m)) map.removeLayer(c.m);
    }
  });
}

// ===== MARKER MANAGEMENT =====

export function ensureMarkers(selectAreaFull) {
  const map = refs.map;
  if (!map || !refs.allAreas.length) return;
  refs.allAreas.forEach(a => {
    const cn = CITY_DEFAULTS[S.city]?.name || 'Karachi';
    if (!a.lat || !a.lng || a.name === cn || refs.markers[a.name]) return;
    const m = L.marker([a.lat, a.lng], { icon: createIcon(a.name, false, 0) });
    m._areaName = a.name;
    m.on('click', () => { refs.mapDriven = true; selectAreaFull(a.name, true); });
    m.on('mouseover', () => {
      $$(`[data-area="${a.name}"]`).forEach(c => c.classList.add('card-map-active'));
      const first = $(`[data-area="${a.name}"]`);
      if (first) first.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    });
    m.on('mouseout', () => {
      $$(`[data-area="${a.name}"]`).forEach(c => c.classList.remove('card-map-active'));
    });
    refs.markers[a.name] = m;
  });
  updateMapMarkers();
}

// ===== HIGHLIGHT & NAV =====

export function highlightMarker(name, flyTo) {
  const map = refs.map;
  if (!map) return;
  updateMapMarkers();
  if (name && refs.markers[name]) {
    const hasSubs = refs.allAreas.some(a => isSubArea(a.name, name));
    const zoomLevel = hasSubs ? 13 : 14;
    if (flyTo) map.flyTo(refs.markers[name].getLatLng(), zoomLevel, { duration: 0.8 });
  }
}

export function resetMapView() {
  const map = refs.map;
  if (!map) return;
  updateMapMarkers();
  const cd = CITY_DEFAULTS[S.city];
  map.setView([cd.lat, cd.lng], cd.zoom, { animate: true });
}

// ===== SEARCH HERE BUTTON =====

function showSearchHereBtn(areaName) {
  let btn = $('#searchHereBtn');
  if (!btn) {
    btn = document.createElement('button');
    btn.id = 'searchHereBtn';
    btn.className = 'absolute top-3 left-1/2 -translate-x-1/2 z-[10] px-4 py-2 rounded-full bg-white border border-gray-200 shadow-lg text-sm font-semibold text-gray-700 hover:bg-gray-50 transition-colors';
    btn.addEventListener('click', () => {
      if (refs.pendingMapArea && refs._selectAreaFull) {
        refs.mapDriven = true;
        refs._selectAreaFull(refs.pendingMapArea, true);
      }
      hideSearchHereBtn();
    });
    $('#mapPanel').appendChild(btn);
  }
  btn.textContent = 'Search in ' + areaName;
  btn.classList.remove('hidden');
}

function hideSearchHereBtn() {
  const btn = $('#searchHereBtn');
  if (btn) btn.classList.add('hidden');
  refs.pendingMapArea = null;
}

function onMapMove() {
  clearTimeout(refs.mapTimer);
  refs.mapTimer = setTimeout(() => {
    const map = refs.map;
    if (!map || map.getZoom() < 12) { hideSearchHereBtn(); return; }
    const bounds = map.getBounds(), center = map.getCenter();
    let closest = null, minDist = Infinity;
    Object.entries(refs.markers).forEach(([name, m]) => {
      if (bounds.contains(m.getLatLng())) {
        const d = center.distanceTo(m.getLatLng());
        if (d < minDist) { minDist = d; closest = name; }
      }
    });
    if (closest && closest !== S.area) {
      refs.pendingMapArea = closest;
      showSearchHereBtn(closest);
    } else {
      hideSearchHereBtn();
    }
  }, 500);
}

// ===== INIT MAP =====

export function initMap(selectAreaFull) {
  // Store reference for search-here button
  refs._selectAreaFull = selectAreaFull;

  const cd = CITY_DEFAULTS[S.city];
  refs.map = L.map('mapContainer', { zoomControl: true }).setView([cd.lat, cd.lng], cd.zoom);
  L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', { attribution: '&copy; OpenStreetMap', maxZoom: 18 }).addTo(refs.map);
  setTimeout(() => refs.map.invalidateSize(), 100);
  ensureMarkers(selectAreaFull);

  refs.map.on('moveend', onMapMove);
  refs.map.on('zoomend', updateMapMarkers);

  if (window.ResizeObserver) new ResizeObserver(() => { if (refs.map) refs.map.invalidateSize(); }).observe($('#mapPanel'));
}

// ===== MOBILE MAP =====

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

export function updateMobileCarousel() {
  const carousel = $('#mapCarousel');
  if (!carousel) return;
  if (!refs.currentResults.length) { carousel.classList.add('hidden'); return; }
  const cards = refs.currentResults.slice(0, 10).map(renderMobileMapCard).join('');
  carousel.innerHTML = cards;
  carousel.classList.remove('hidden');
  carousel.classList.add('flex');
}

export function initMobileMap(selectAreaFull, openDrawer) {
  $('#mapFab').addEventListener('click', () => {
    $('#mapOverlay').classList.remove('hidden');
    if (!refs.mobileMap) {
      const cd = CITY_DEFAULTS[S.city];
      refs.mobileMap = L.map('mapContainerMobile', { zoomControl: true }).setView([cd.lat, cd.lng], cd.zoom);
      L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', { attribution: '&copy; OpenStreetMap', maxZoom: 18 }).addTo(refs.mobileMap);
      refs.areaCounts = getAreaCounts();
      refs.allAreas.forEach(a => {
        const cn2 = CITY_DEFAULTS[S.city]?.name || 'Karachi';
        if (!a.lat || !a.lng || a.name === cn2) return;
        const count = refs.areaCounts[a.name] || 0;
        if (!count && a.name !== S.area) return;
        const icon = createIcon(a.name, a.name === S.area, count);
        L.marker([a.lat, a.lng], { icon }).addTo(refs.mobileMap).on('click', () => {
          refs.mapDriven = true;
          selectAreaFull(a.name, true);
          updateMobileCarousel();
        });
      });
    }
    setTimeout(() => refs.mobileMap.invalidateSize(), 100);
    if (S.area && refs.markers[S.area]) refs.mobileMap.setView(refs.markers[S.area].getLatLng(), 14);
    updateMobileCarousel();

    // Mobile card click → drawer
    $('#mapCarousel').addEventListener('click', e => {
      const card = e.target.closest('[data-mobile-card-url]');
      if (!card) return;
      const idx = [...$('#mapCarousel').children].indexOf(card);
      if (refs.currentResults[idx]) { $('#mapOverlay').classList.add('hidden'); openDrawer(refs.currentResults[idx]); }
    });
  });

  $('#mapOverlayClose').addEventListener('click', () => $('#mapOverlay').classList.add('hidden'));
}

// ===== HOVER SYNC (cards → markers) =====

export function initHoverSync() {
  const grid = $('#listingsGrid');
  grid.addEventListener('mouseover', e => {
    const card = e.target.closest('[data-area]');
    if (!card || !refs.map) return;
    const m = refs.markers[card.dataset.area];
    if (m && m._icon) m._icon.querySelector('.area-label')?.classList.add('area-label-active');
  });
  grid.addEventListener('mouseout', e => {
    const card = e.target.closest('[data-area]');
    if (!card || !refs.map) return;
    const areaName = card.dataset.area;
    if (areaName === S.area) return;
    const m = refs.markers[areaName];
    if (m && m._icon) m._icon.querySelector('.area-label')?.classList.remove('area-label-active');
  });
}
