/** App entry point — wires modules together, search engine, init. */

import { $, $$, esc, TYPE_L, showToast } from './utils.js';
import { S, refs, CITY_DEFAULTS } from './state.js';
import {
  updateCityTabs, updateNlExamples, updateChips, clearFilter, selectArea,
  syncPriceChips, setToggle, initFilterListeners, closeDD,
} from './filters.js';
import { renderCard, initCarousels, handleContactAction, skeletonCard } from './cards.js';
import {
  initMap, ensureMarkers, updateMapMarkers, highlightMarker, resetMapView,
  initMobileMap, updateMobileCarousel, updateMobileMarkers, initHoverSync,
  getVisibleAreaNames, fitCityOverview,
  clearNearbyRadiusOverlays, hydrateStoredUserLocation, refreshUserLocationOverlays,
  requestUserLocation, resetExactPrefetchState,
} from './map.js';
import { openDrawer, initDrawerListeners } from './drawer.js';
import { getStoredMapLayer } from './map-layers.js';
import {
  initAnalytics, trackSearchOutcome, trackNlSearch, trackListingOpen,
  trackCitySwitch, trackFilterChange, trackMapMarkerClick, trackApiError, trackScrollDepth, trackFeedbackSubmitted,
} from './analytics.js';

function isNearbySupportedCity() {
  return S.city === 'karachi';
}

function getBrowseMode() {
  if (S.area) return 'area';
  return window.innerWidth > 768 && refs.map ? 'viewport' : 'city';
}

function getActiveMapInstance() {
  const overlay = $('#mapOverlay');
  if (overlay && !overlay.classList.contains('hidden') && refs.mobileMap) return refs.mobileMap;
  return refs.map || refs.mobileMap || null;
}

function updateNearbyControls() {
  const nearbyChip = $('#nearbyChip');
  const radiusChip = $('#radiusChip');
  if (!nearbyChip || !radiusChip) return;

  const sortDist = $('#sortDistance');
  if (refs.searchMode === 'nearby') {
    nearbyChip.innerHTML = `Near Me<span class="chip-clear" data-nearby-clear="1">&times;</span>`;
    nearbyChip.classList.add('has-value');
    radiusChip.classList.remove('hidden');
    radiusChip.innerHTML = `${refs.nearbyRadiusKm} km <svg class="w-3 h-3 ml-0.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2.5" d="M19 9l-7 7-7-7"/></svg>`;
    if (sortDist) sortDist.hidden = false;
  } else {
    nearbyChip.textContent = 'Near Me';
    nearbyChip.classList.remove('has-value');
    radiusChip.classList.add('hidden');
    if (sortDist) {
      sortDist.hidden = true;
      if ($('#sortSelect').value === 'distance') { $('#sortSelect').value = ''; S.sort = ''; }
    }
  }

  nearbyChip.classList.toggle('chip-disabled', !isNearbySupportedCity() && refs.searchMode !== 'nearby');
}

function exitNearbyMode({ silent = false } = {}) {
  if (refs.searchMode !== 'nearby') {
    updateNearbyControls();
    clearNearbyRadiusOverlays();
    return false;
  }
  refs.searchMode = getBrowseMode();
  clearNearbyRadiusOverlays();
  refreshUserLocationOverlays();
  updateNearbyControls();
  if (!silent) showToast('Returned to browse mode.');
  return true;
}

function beginSearchRequest(append) {
  const token = ++refs.searchToken;
  refs.searchController?.abort();
  const controller = new AbortController();
  refs.searchController = controller;
  refs.isLoading = true;
  if (!append) resetScrollTracking();
  showLoading(append);
  saveSearch();
  return { token, controller };
}

function isActiveSearch(token, controller) {
  return refs.searchToken === token && refs.searchController === controller;
}

function finalizeSearch(token, controller) {
  if (!isActiveSearch(token, controller)) return false;
  refs.searchController = null;
  refs.isLoading = false;
  refs.mapDriven = false;
  return true;
}

function resetViewportSearchMeta({ clearVisibleAreas = false } = {}) {
  refs.mapAreaTotals = {};
  if (clearVisibleAreas) refs.viewportAreaNames = [];
  refs.viewportVisibleAreas = 0;
  refs.viewportRanking = 'default';
  refs.viewportScope = 'area_coverage';
  refs.viewportAttemptedExactBounds = false;
  refs.viewportExactBoundsTotal = null;
}

function getViewportVisibleAreaCount(fallback = refs.viewportAreaNames.length) {
  return Number.isFinite(Number(refs.viewportVisibleAreas))
    ? Math.max(Number(refs.viewportVisibleAreas), 0)
    : fallback;
}

function selectAreaFull(name, fromMap, { search = true } = {}) {
  const prev = S.area;
  if (prev !== name) trackFilterChange({ filter: 'area', value: name, previousValue: prev, mode: refs.searchMode, city: S.city });
  if (refs.searchMode !== 'nearby') refs.searchMode = 'area';
  resetViewportSearchMeta({ clearVisibleAreas: true });
  refs.lastViewportSearchKey = '';
  refs.previewArea = null;
  refs.hoveredArea = null;
  refs._lastTriggeredBy = 'area_select';
  updateNearbyControls();
  selectArea(name, fromMap, { highlightMarker, doSearch: search ? doSearch : undefined });
}

function clearFilterFull(f) {
  const prevValues = { area: S.area, type: S.type, beds: S.beds, price: S.priceMin || S.priceMax ? `${S.priceMin}-${S.priceMax}` : '', more: S.furnished ? 'furnished' : S.sort || '' };
  if (prevValues[f]) trackFilterChange({ filter: f, value: '', previousValue: prevValues[f], mode: refs.searchMode, city: S.city });
  if (f === 'area') {
    refs.searchMode = refs.searchMode === 'nearby' ? 'nearby' : getBrowseMode();
    resetViewportSearchMeta({ clearVisibleAreas: true });
    refs.lastViewportSearchKey = '';
    refs.previewArea = null;
    refs.hoveredArea = null;
  }
  refs._lastTriggeredBy = 'filter_change';
  updateNearbyControls();
  clearFilter(f, { resetMapView, doSearch });
}

function openDrawerFull(item, position) {
  trackListingOpen({ item, position: position ?? null, mode: refs.searchMode, city: S.city, area: S.area, source: refs._lastSearchSource });
  openDrawer(item, selectAreaFull);
}

function getParams(pg, { omitArea = false } = {}) {
  const p = new URLSearchParams();
  p.set('city', S.city);
  if (!omitArea && S.area) p.set('area', S.area);
  if (S.type) p.set('property_type', S.type);
  if (S.beds) p.set('bedrooms', S.beds);
  if (S.bedsMax) p.set('bedrooms_max', S.bedsMax);
  if (S.priceMin) p.set('price_min', S.priceMin);
  if (S.priceMax) p.set('price_max', S.priceMax);
  if (S.sizeMarlaMin) p.set('size_marla_min', S.sizeMarlaMin);
  if (S.sizeMarlaMax) p.set('size_marla_max', S.sizeMarlaMax);
  if (S.furnished) p.set('furnished', 'true');
  if (S.sort) p.set('sort', S.sort);
  p.set('page', pg);
  return p;
}

function saveSearch() {
  try { localStorage.setItem('rk_s', JSON.stringify(S)); } catch {}
  const p = new URLSearchParams();
  if (S.city && S.city !== 'lahore') p.set('city', S.city);
  if (S.area) p.set('area', S.area);
  if (S.type) p.set('type', S.type);
  if (S.beds) p.set('beds', S.beds);
  if (S.priceMin) p.set('price_min', S.priceMin);
  if (S.priceMax) p.set('price_max', S.priceMax);
  if (S.furnished) p.set('furnished', '1');
  if (S.sort) p.set('sort', S.sort);
  const qs = p.toString();
  const newUrl = qs ? '?' + qs : location.pathname;
  if (location.search !== '?' + qs) history.replaceState(null, '', newUrl);
}

function loadSearch() {
  const urlParams = new URLSearchParams(location.search);
  const hasUrlState = [...urlParams.keys()].some(k => ['city', 'area', 'type', 'beds', 'price_min', 'price_max', 'furnished', 'sort'].includes(k));

  let d;
  if (hasUrlState) {
    d = {
      city: urlParams.get('city') || 'lahore',
      area: urlParams.get('area') || '',
      type: urlParams.get('type') || '',
      beds: urlParams.get('beds') || '',
      priceMin: urlParams.get('price_min') || '',
      priceMax: urlParams.get('price_max') || '',
      furnished: urlParams.get('furnished') === '1',
      sort: urlParams.get('sort') || '',
    };
  } else {
    try { d = JSON.parse(localStorage.getItem('rk_s')); } catch {}
  }
  if (!d) return;

  if (d.city && CITY_DEFAULTS[d.city]) { S.city = d.city; updateCityTabs(); updateNlExamples(); }
  if (d.area) selectAreaFull(d.area);
  if (d.type) { S.type = d.type; $$('#typeGrid .chip').forEach(c => c.classList.toggle('active', c.dataset.type === d.type)); }
  if (d.beds) { S.beds = d.beds; $$('#bedRow .chip').forEach(c => c.classList.toggle('active', c.dataset.beds === d.beds)); }
  if (d.priceMin) S.priceMin = d.priceMin;
  if (d.priceMax) S.priceMax = d.priceMax;
  if (d.priceMin || d.priceMax) syncPriceChips();
  if (d.furnished) setToggle(true);
  if (d.sort) { S.sort = d.sort; $('#sortSelect').value = d.sort; }
  updateChips();
}

function getStoredCityPreference() {
  const urlParams = new URLSearchParams(location.search);
  const urlCity = urlParams.get('city');
  if (urlCity && CITY_DEFAULTS[urlCity]) return urlCity;

  try {
    const saved = JSON.parse(localStorage.getItem('rk_s') || '{}');
    if (saved.city && CITY_DEFAULTS[saved.city]) return saved.city;
  } catch {}

  return '';
}

async function chooseInitialCity() {
  const storedCity = getStoredCityPreference();
  if (storedCity) {
    S.city = storedCity;
    return;
  }

  try {
    const cities = Object.keys(CITY_DEFAULTS);
    const stats = await Promise.all(cities.map(async city => {
      const r = await fetch('/api/crawl-status?city=' + city);
      if (!r.ok) return { city, total_listings: 0 };
      const d = await r.json();
      return { city, total_listings: d.total_listings || 0 };
    }));
    const best = stats.sort((a, b) => b.total_listings - a.total_listings)[0];
    if (best?.total_listings > 0) S.city = best.city;
  } catch {}
}

function showLoading(append) {
  if (!append) {
    $('#listingsGrid').innerHTML = Array(6).fill(skeletonCard()).join('');
    $('#listingsFooter').innerHTML = '';
  } else {
    const s = document.createElement('div');
    s.id = 'spinner';
    s.className = 'flex flex-col items-center gap-3 py-12';
    s.innerHTML = '<div class="w-8 h-8 border-3 border-gray-200 border-t-brand-500 rounded-full animate-spin"></div><p class="text-sm text-gray-400">Loading more...</p>';
    $('#listingsFooter').appendChild(s);
  }
}

function hideLoading() {
  const s = $('#spinner');
  if (s) s.remove();
}

function updateHeader({
  total = 0,
  source = '',
  mode = refs.searchMode,
  visibleAreas = 0,
  coveredAreas = 0,
  ranking = refs.viewportRanking,
  scope = refs.viewportScope,
} = {}) {
  const cityName = CITY_DEFAULTS[S.city]?.name || 'Karachi';
  const shown = refs.currentResults.length;
  const titleEl = $('#listingsTitle');
  const countEl = $('#resultsCount');
  const metaEl = $('#resultsMeta');
  const sourceEl = $('#dataSource');

  if (mode === 'nearby') {
    titleEl.textContent = 'Rentals near you';
    countEl.textContent = `${shown} shown`;
    metaEl.textContent = total
      ? `${total} exact-pin rentals within ${refs.nearbyRadiusKm} km`
      : `No exact-pin rentals found within ${refs.nearbyRadiusKm} km`;
  } else if (mode === 'viewport') {
    titleEl.textContent = 'Rentals in this map view';
    countEl.textContent = `${shown} shown`;
    const coverageMessage = getViewportCoverageMessage({ total, visibleAreas, coveredAreas });
    if (scope === 'exact_bounds') {
      metaEl.textContent = total
        ? `${total} exact-pin rentals currently visible on the map`
        : 'No exact-pin rentals are visible in this map view';
    } else if (isEmptyExactBoundsFallback(scope)) {
      metaEl.textContent = total
        ? `No exact-pin rentals visible here. ${coverageMessage}`
        : `No exact-pin rentals are visible in this map view. ${coverageMessage}`;
    } else {
      metaEl.textContent = coverageMessage;
    }
  } else if (S.area) {
    titleEl.textContent = 'Rentals in ' + S.area;
    countEl.textContent = `${shown} shown`;
    metaEl.textContent = total ? `${total} total in this area` : 'No rentals match this area right now';
  } else {
    titleEl.textContent = 'Rentals in ' + cityName;
    countEl.textContent = `${shown} shown`;
    metaEl.textContent = total ? `${total} total across current filters` : `No rentals match your filters in ${cityName}`;
  }

  if (source === 'local') {
    sourceEl.textContent = mode === 'nearby'
      ? 'Instant / Nearby'
      : mode === 'viewport' && ranking === 'map_focus'
      ? 'Instant / Nearest first'
      : 'Instant';
    sourceEl.className = 'text-xs text-brand-500 font-medium';
    sourceEl.classList.remove('hidden');
  } else if (source === 'live') {
    sourceEl.textContent = 'Live';
    sourceEl.className = 'text-xs text-amber-500 font-medium';
    sourceEl.classList.remove('hidden');
  } else if (source === 'unavailable') {
    sourceEl.textContent = 'Local only';
    sourceEl.className = 'text-xs text-gray-400 font-medium';
    sourceEl.classList.remove('hidden');
  } else {
    sourceEl.classList.add('hidden');
  }
}

function getViewportCoverageMessage({ total = 0, visibleAreas = 0, coveredAreas = 0 } = {}) {
  if (total && coveredAreas > 0) {
    return coveredAreas === visibleAreas
      ? `${total} available across ${coveredAreas} visible areas`
      : `${total} available in ${coveredAreas} covered areas within ${visibleAreas} visible areas`;
  }
  if (visibleAreas > 0) return `No local listings in ${visibleAreas} visible areas yet`;
  return 'Move the map to explore nearby areas';
}

function isEmptyExactBoundsFallback(scope = refs.viewportScope) {
  return scope !== 'exact_bounds'
    && refs.viewportAttemptedExactBounds
    && refs.viewportExactBoundsTotal === 0;
}

function getViewportEmptyStateMessage({ visibleAreas = getViewportVisibleAreaCount(), scope = refs.viewportScope } = {}) {
  if (scope === 'exact_bounds') {
    return 'No exact-pin rentals are visible here right now. Zoom out to broaden the map view.';
  }
  if (isEmptyExactBoundsFallback(scope)) {
    return visibleAreas > 0
      ? 'No exact-pin rentals are visible here right now. Pan or zoom the map to discover nearby covered areas.'
      : 'No exact-pin rentals are visible in this map view.';
  }
  return 'Pan or zoom the map to discover other areas';
}

let coverageExpanded = false;

function updateCoverageBadge() {
  const desktop = $('#mapCoverageBadge');
  const mobile = $('#mapCoverageBadgeMobile');
  const badges = [desktop, mobile].filter(Boolean);
  if (!badges.length) return;

  const visibleAreas = getViewportVisibleAreaCount();
  const coveredEntries = Object.entries(refs.mapAreaTotals || {}).sort((a, b) => b[1] - a[1]);
  const coveredAreas = coveredEntries.length;

  badges.forEach(el => {
    if (refs.searchMode !== 'viewport') {
      el.classList.add('hidden');
      el.innerHTML = '';
      return;
    }

    const topAreas = coveredEntries.slice(0, 3);
    const coveredHtml = topAreas.length
      ? topAreas.map(([name]) => `<span class="coverage-chip live">${esc(name)}</span>`).join('')
      : '<span class="coverage-chip">No covered areas here yet</span>';
    const summary = coveredAreas > 0
      ? `${coveredAreas} covered / ${visibleAreas || 0} visible`
      : `${visibleAreas || 0} visible areas, no local coverage`;
    const previewingEmpty = refs.previewArea && !coveredEntries.some(([name]) => name === refs.previewArea);
    const detail = previewingEmpty
      ? `Previewing ${refs.previewArea}. Gray dots only preview areas until local listings exist there.`
      : coveredAreas > 0
      ? 'Green dots have local listings. Gray dots are preview-only. Cards are ordered nearest to the map center.'
      : 'This part of the map has no crawled local listings yet. Gray dots are preview-only.';
    const legendHtml = `
      <div class="coverage-legend" aria-label="Map legend">
        <span class="coverage-legend-item"><span class="coverage-legend-dot live" aria-hidden="true"></span>Green: covered area</span>
        <span class="coverage-legend-item"><span class="coverage-legend-dot preview" aria-hidden="true"></span>Grey: preview only</span>
        <span class="coverage-legend-item"><span class="coverage-legend-dot exact" aria-hidden="true"></span>Red: exact listing pin</span>
      </div>
    `;
    const chevron = `<svg class="w-3.5 h-3.5 text-gray-400 transition-transform ${coverageExpanded ? 'rotate-180' : ''}" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2.5" d="M19 9l-7 7-7-7"/></svg>`;

    el.innerHTML = `
      <button class="coverage-toggle flex items-center justify-between w-full text-left">
        <div>
          <div class="text-[11px] font-semibold uppercase tracking-[0.12em] text-gray-400">Map Coverage</div>
          <div class="mt-0.5 text-sm font-semibold text-gray-800">${summary}</div>
        </div>
        ${chevron}
      </button>
      <div class="coverage-detail ${coverageExpanded ? '' : 'hidden'}" style="margin-top:8px">
        <div class="text-xs text-gray-500">${detail}</div>
        <div class="mt-2 flex flex-wrap gap-2">${coveredHtml}</div>
        ${legendHtml}
      </div>
    `;
    el.classList.remove('hidden');

    el.querySelector('.coverage-toggle').addEventListener('click', () => {
      coverageExpanded = !coverageExpanded;
      updateCoverageBadge();
    });
  });
}

refs._refreshCoverageUI = updateCoverageBadge;

function renderNoResults(message) {
  refs.lastSearchTotal = 0;
  refs.viewportTotal = 0;
  refs.viewportRanking = 'default';
  refs.currentResults = [];
  $('#resultsCount').textContent = '0 shown';
  $('#resultsMeta').textContent = message;

  const activeFilters = [];
  if (S.area) activeFilters.push({ label: 'Area: ' + S.area, filter: 'area' });
  if (S.type) activeFilters.push({ label: 'Type: ' + (TYPE_L[S.type] || S.type), filter: 'type' });
  if (S.beds) activeFilters.push({ label: S.beds + ' Bed', filter: 'beds' });
  if (S.priceMin || S.priceMax) activeFilters.push({ label: 'Price range', filter: 'price' });
  if (S.furnished) activeFilters.push({ label: 'Furnished', filter: 'more' });
  const filterHtml = activeFilters.length
    ? `<div class="flex flex-wrap justify-center gap-2 mt-4">${activeFilters.map(f => `<button class="text-xs px-3 py-1.5 rounded-full border border-gray-200 text-gray-500 hover:border-red-300 hover:text-red-500 transition-colors" data-remove-filter="${f.filter}">Remove ${esc(f.label)} &times;</button>`).join('')}</div>`
    : '';

  $('#listingsGrid').innerHTML = `<div class="col-span-full text-center py-12"><div class="text-5xl mb-3">&#x1f3e0;</div><h3 class="text-base font-semibold text-gray-600">No rentals found</h3><p class="text-sm text-gray-400 mt-1">${esc(message)}</p>${filterHtml}</div>`;
  $$('[data-remove-filter]').forEach(btn => btn.addEventListener('click', () => clearFilterFull(btn.dataset.removeFilter)));
}

function renderFooter(total) {
  const footer = $('#listingsFooter');
  footer.innerHTML = '';
  if (total > refs.currentResults.length) {
    const btn = document.createElement('button');
    btn.className = 'w-full py-3 mt-4 border-2 border-brand-500 rounded-lg text-brand-500 text-sm font-semibold hover:bg-brand-50 transition-colors';
    btn.textContent = refs.searchMode === 'nearby'
      ? 'Load More Nearby Results'
      : refs.searchMode === 'viewport'
      ? 'Load More From This View'
      : 'Load More Results';
    btn.addEventListener('click', () => { refs._lastTriggeredBy = 'load_more'; doSearch(refs.currentPage + 1); });
    footer.appendChild(btn);
  }
}

function applyResults(data, { append = false, mode = refs.searchMode } = {}) {
  refs.lastSearchTotal = data.total || 0;
  if (mode === 'viewport') {
    refs.mapAreaTotals = data.area_totals || {};
    refs.viewportVisibleAreas = Number.isFinite(Number(data.visible_areas))
      ? Math.max(Number(data.visible_areas), 0)
      : refs.viewportAreaNames.length;
    refs.viewportTotal = data.total || 0;
    refs.viewportShown = append ? refs.currentResults.length : (data.results || []).length;
    refs.viewportRanking = data.ranking || 'default';
    refs.viewportScope = data.scope || 'area_coverage';
    refs.viewportAttemptedExactBounds = Boolean(data.attempted_exact_bounds);
    refs.viewportExactBoundsTotal = Number.isFinite(data.exact_bounds_total) ? data.exact_bounds_total : null;
  } else {
    resetViewportSearchMeta({ clearVisibleAreas: true });
  }

  if (!append) {
    refs.currentResults = data.results || [];
    if (!refs.currentResults.length) {
      const visibleAreas = mode === 'viewport'
        ? getViewportVisibleAreaCount()
        : (data.visible_areas || refs.viewportAreaNames.length);
      updateHeader({
        total: data.total || 0,
        source: data.source,
        mode,
        visibleAreas,
        coveredAreas: Object.keys(data.area_totals || {}).length,
        ranking: data.ranking,
        scope: data.scope,
      });
      renderNoResults(
        mode === 'nearby'
          ? `No exact-pin rentals were found within ${refs.nearbyRadiusKm} km.`
          : mode === 'viewport'
          ? getViewportEmptyStateMessage({ visibleAreas, scope: refs.viewportScope })
          : 'Try removing a filter to see more results'
      );
      updateMapMarkers();
      updateCoverageBadge();
      if (refs.mobileMap) updateMobileMarkers(selectAreaFull);
      updateMobileCarousel(refs.currentResults);
      return;
    }
    $('#listingsGrid').innerHTML = refs.currentResults.map((it, i) => renderCard(it, i)).join('');
  } else {
    const next = data.results || [];
    if (!next.length) {
      hideLoading();
      renderFooter(refs.currentResults.length);
      return;
    }
    const start = refs.currentResults.length;
    refs.currentResults = refs.currentResults.concat(next);
    next.forEach((it, i) => $('#listingsGrid').insertAdjacentHTML('beforeend', renderCard(it, start + i)));
  }

  updateHeader({
    total: data.total || 0,
    source: data.source,
    mode,
    visibleAreas: mode === 'viewport'
      ? getViewportVisibleAreaCount()
      : (data.visible_areas || refs.viewportAreaNames.length),
    coveredAreas: Object.keys(data.area_totals || {}).length,
    ranking: data.ranking,
    scope: data.scope,
  });
  initCarousels();
  observeCards();
  updateMapMarkers();
  updateCoverageBadge();
  if (refs.mobileMap) updateMobileMarkers(selectAreaFull);
  updateMobileCarousel(refs.currentResults);
  renderFooter(data.total || 0);
  if (!append) $('#listingsPanel').scrollTo({ top: 0, behavior: 'smooth' });
}

function shouldUseViewportSearch({ mobile = false } = {}) {
  if (refs.searchMode === 'nearby') return false;
  if (S.area) return false;
  if (mobile) return !!refs.mobileMap;
  return window.innerWidth > 768 && !!refs.map;
}

function buildViewportSearchKey({ visibleAreaNames, center, bounds, mobile = false, page = 1 }) {
  const currentBounds = bounds || (mobile ? refs.mobileMap : refs.map)?.getBounds?.();
  return JSON.stringify({
    city: S.city,
    type: S.type || '',
    beds: S.beds || '',
    priceMin: S.priceMin || '',
    priceMax: S.priceMax || '',
    furnished: S.furnished ? 1 : 0,
    sort: S.sort || '',
    mobile,
    page,
    centerLat: center.lat.toFixed(4),
    centerLng: center.lng.toFixed(4),
    south: currentBounds ? currentBounds.getSouth().toFixed(4) : '',
    west: currentBounds ? currentBounds.getWest().toFixed(4) : '',
    north: currentBounds ? currentBounds.getNorth().toFixed(4) : '',
    east: currentBounds ? currentBounds.getEast().toFixed(4) : '',
    areas: [...visibleAreaNames].sort(),
  });
}

async function doViewportSearch(page = 1, { mobile = false } = {}) {
  const mapInstance = mobile ? refs.mobileMap : refs.map;
  if (!mapInstance) return;

  const append = page > 1;
  const visibleAreaNames = getVisibleAreaNames(mapInstance);
  const center = mapInstance.getCenter();
  const bounds = mapInstance.getBounds();
  const viewportKey = append
    ? ''
    : buildViewportSearchKey({ visibleAreaNames, center, bounds, mobile, page });
  if (!append && viewportKey === refs.lastViewportSearchKey) return;

  if (!append) {
    refs.currentPage = 1;
    refs.currentResults = [];
  } else {
    refs.currentPage = page;
  }

  const { token, controller } = beginSearchRequest(append);

  try {
    refs.searchMode = 'viewport';
    updateNearbyControls();
    refs.viewportAreaNames = visibleAreaNames;
    const params = getParams(refs.currentPage, { omitArea: true });
    refs.viewportAreaNames.forEach(name => params.append('areas', name));
    params.set('center_lat', center.lat.toFixed(6));
    params.set('center_lng', center.lng.toFixed(6));
    params.set('south', bounds.getSouth().toFixed(6));
    params.set('west', bounds.getWest().toFixed(6));
    params.set('north', bounds.getNorth().toFixed(6));
    params.set('east', bounds.getEast().toFixed(6));

    const r = await fetch('/api/map-search?' + params.toString(), { signal: controller.signal });
    if (!r.ok) {
      const e = await r.json().catch(() => ({ detail: 'Map search failed' }));
      trackApiError({ endpoint: '/api/map-search', statusCode: r.status, errorMessage: e.detail, mode: 'viewport', city: S.city });
      throw new Error(e.detail || 'Map search failed');
    }
    const data = await r.json();
    if (!isActiveSearch(token, controller)) return;
    hideLoading();
    applyResults(data, { append, mode: 'viewport' });
    refs._lastSearchSource = data.source || null;
    trackSearchOutcome({ success: true, data, mode: 'viewport', page: refs.currentPage, triggeredBy: refs._lastTriggeredBy, visibleAreasCount: refs.viewportAreaNames.length });
    if (!append) refs.lastViewportSearchKey = viewportKey;
  } catch (e) {
    if (e?.name === 'AbortError' || !isActiveSearch(token, controller)) return;
    hideLoading();
    if (append) {
      showToast('Could not load more results.', { tone: 'error' });
    } else {
      refs.currentResults = [];
      resetViewportSearchMeta();
      updateHeader({ total: 0, source: 'unavailable', mode: 'viewport', visibleAreas: refs.viewportAreaNames.length, coveredAreas: 0, ranking: 'default' });
      renderNoResults(e.message || 'Could not update the map view right now');
      updateMapMarkers();
      updateCoverageBadge();
      if (refs.mobileMap) updateMobileMarkers(selectAreaFull);
    }
    trackSearchOutcome({ success: false, data: e.message, mode: 'viewport', page: refs.currentPage, triggeredBy: refs._lastTriggeredBy });
  } finally {
    finalizeSearch(token, controller);
  }
}

async function doAreaSearch(page = 1) {
  const append = page > 1;
  refs.lastViewportSearchKey = '';
  if (!append) {
    refs.currentPage = 1;
    refs.currentResults = [];
  } else {
    refs.currentPage = page;
  }

  const { token, controller } = beginSearchRequest(append);

  try {
    refs.searchMode = S.area ? 'area' : 'city';
    updateNearbyControls();
    const r = await fetch('/api/search?' + getParams(refs.currentPage).toString(), { signal: controller.signal });
    if (!r.ok) {
      const e = await r.json().catch(() => ({ detail: 'Search failed' }));
      trackApiError({ endpoint: '/api/search', statusCode: r.status, errorMessage: e.detail, mode: refs.searchMode, city: S.city });
      throw new Error(e.detail || 'Search failed');
    }
    const data = await r.json();
    if (!isActiveSearch(token, controller)) return;
    hideLoading();
    applyResults(data, { append, mode: refs.searchMode });
    refs._lastSearchSource = data.source || null;
    trackSearchOutcome({ success: true, data, mode: refs.searchMode, page: refs.currentPage, triggeredBy: refs._lastTriggeredBy });
  } catch (e) {
    if (e?.name === 'AbortError' || !isActiveSearch(token, controller)) return;
    hideLoading();
    if (append) {
      showToast('Could not load more results.', { tone: 'error' });
    } else {
      refs.currentResults = [];
      updateHeader({ total: 0, source: 'unavailable', mode: refs.searchMode });
      renderNoResults(e.message || 'Search failed');
      updateMapMarkers();
      updateCoverageBadge();
      if (refs.mobileMap) updateMobileMarkers(selectAreaFull);
    }
    trackSearchOutcome({ success: false, data: e.message, mode: refs.searchMode, page: refs.currentPage, triggeredBy: refs._lastTriggeredBy });
  } finally {
    finalizeSearch(token, controller);
  }
}

async function doNearbySearch(page = 1) {
  const append = page > 1;
  refs.lastViewportSearchKey = '';

  if (!refs.userLocation) {
    showToast('Set your location first to search nearby.', { tone: 'error' });
    refs.searchMode = getBrowseMode();
    updateNearbyControls();
    clearNearbyRadiusOverlays();
    return doAreaSearch(1);
  }
  if (!isNearbySupportedCity()) {
    showToast('Nearby search is available in Karachi for now.', { tone: 'warning' });
    refs.searchMode = getBrowseMode();
    updateNearbyControls();
    clearNearbyRadiusOverlays();
    return doAreaSearch(1);
  }

  if (!append) {
    refs.currentPage = 1;
    refs.currentResults = [];
  } else {
    refs.currentPage = page;
  }

  const { token, controller } = beginSearchRequest(append);

  try {
    refs.searchMode = 'nearby';
    updateNearbyControls();
    refreshUserLocationOverlays();
    const params = getParams(refs.currentPage);
    params.set('lat', refs.userLocation.lat.toFixed(6));
    params.set('lng', refs.userLocation.lng.toFixed(6));
    params.set('radius_km', refs.nearbyRadiusKm);

    const r = await fetch('/api/nearby-search?' + params.toString(), { signal: controller.signal });
    if (!r.ok) {
      const e = await r.json().catch(() => ({ detail: 'Nearby search failed' }));
      trackApiError({ endpoint: '/api/nearby-search', statusCode: r.status, errorMessage: e.detail, mode: 'nearby', city: S.city });
      throw new Error(e.detail || 'Nearby search failed');
    }
    const data = await r.json();
    if (!isActiveSearch(token, controller)) return;
    hideLoading();
    applyResults(data, { append, mode: 'nearby' });
    refs._lastSearchSource = data.source || null;
    trackSearchOutcome({ success: true, data, mode: 'nearby', page: refs.currentPage, triggeredBy: refs._lastTriggeredBy, radiusKm: refs.nearbyRadiusKm });
  } catch (e) {
    if (e?.name === 'AbortError' || !isActiveSearch(token, controller)) return;
    hideLoading();
    if (append) {
      showToast('Could not load more results.', { tone: 'error' });
    } else {
      refs.currentResults = [];
      updateHeader({ total: 0, source: 'unavailable', mode: 'nearby' });
      renderNoResults(e.message || `No exact-pin rentals were found within ${refs.nearbyRadiusKm} km.`);
      updateMapMarkers();
      updateCoverageBadge();
      if (refs.mobileMap) updateMobileMarkers(selectAreaFull);
    }
    trackSearchOutcome({ success: false, data: e.message, mode: 'nearby', page: refs.currentPage, triggeredBy: refs._lastTriggeredBy, radiusKm: refs.nearbyRadiusKm });
  } finally {
    finalizeSearch(token, controller);
  }
}

async function doSearch(page = 1, opts = {}) {
  if (refs.searchMode === 'nearby') return doNearbySearch(page);
  if (shouldUseViewportSearch(opts)) return doViewportSearch(page, opts);
  return doAreaSearch(page);
}

function scheduleViewportSearch(opts = {}) {
  if (S.area || refs.searchMode === 'nearby') return;
  clearTimeout(refs.mapTimer);
  refs.mapTimer = setTimeout(() => {
    refs._lastTriggeredBy = 'map_viewport';
    doSearch(1, opts);
  }, 250);
}

async function doNlSearch() {
  const q = $('#nlInput').value.trim();
  if (!q || refs.isLoading) return;
  $('#nlSearchBtn').disabled = true;
  const parsed = $('#nlParsed');
  parsed.classList.remove('hidden');
  parsed.classList.add('flex');
  parsed.innerHTML = '<span class="inline-flex items-center gap-1.5 text-gray-400"><svg class="w-3 h-3 animate-spin" fill="none" viewBox="0 0 24 24"><circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"/><path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"/></svg>Parsing filters...</span>';
  const queryLength = q.length;
  trackNlSearch({ phase: 'submitted', queryLength });
  try {
    const r = await fetch('/api/parse-query?q=' + encodeURIComponent(q) + '&city=' + S.city);
    if (!r.ok) throw 0;
    const d = await r.json();
    const f = d.filters || {};
    if (!Object.keys(f).length) { trackNlSearch({ phase: 'parsed', queryLength, parseSuccess: false, filters: f }); parsed.innerHTML = 'Could not understand. Try "2 bed flat in DHA under 50k"'; return; }
    const parts = [];
    if (f.area) parts.push('<b class="text-brand-500">' + esc(f.area) + '</b>');
    if (f.property_type) parts.push('<b class="text-brand-500">' + (TYPE_L[f.property_type] || f.property_type) + '</b>');
    if (f.bedrooms && f.bedrooms_max) parts.push('<b class="text-brand-500">' + f.bedrooms + '-' + f.bedrooms_max + ' bed</b>');
    else if (f.bedrooms) parts.push('<b class="text-brand-500">' + f.bedrooms + ' bed</b>');
    if (f.price_min || f.price_max) {
      const mn = f.price_min ? (f.price_min / 1e3 | 0) + 'K' : '';
      const mx = f.price_max ? (f.price_max / 1e3 | 0) + 'K' : '';
      parts.push('<b class="text-brand-500">' + (mn && mx ? mn + '-' + mx : mx ? '<' + mx : mn + '+') + '</b>');
    }
    if (f.size_marla_min || f.size_marla_max) {
      const toL = v => v >= 20 && v % 20 === 0 ? (v / 20) + ' kanal' : v + ' marla';
      const smn = f.size_marla_min ? toL(f.size_marla_min) : '';
      const smx = f.size_marla_max ? toL(f.size_marla_max) : '';
      parts.push('<b class="text-brand-500">' + (smn && smx ? smn + '-' + smx : smx ? '<' + smx : smn) + '</b>');
    }
    if (f.furnished) parts.push('<b class="text-brand-500">Furnished</b>');
    parsed.innerHTML = parts.join(' &middot; ');
    // City auto-switch (before area selection)
    if (f.city_hint && f.city_hint !== S.city && CITY_DEFAULTS[f.city_hint]) {
      S.city = f.city_hint;
      S.area = ''; S.type = ''; S.beds = ''; S.bedsMax = ''; S.priceMin = ''; S.priceMax = ''; S.furnished = false; S.sort = '';
      S.sizeMarlaMin = ''; S.sizeMarlaMax = '';
      refs.searchMode = window.innerWidth > 768 && refs.map ? 'viewport' : 'city';
      resetViewportSearchMeta({ clearVisibleAreas: true });
      $('#areaInput').value = ''; $('#areaClear').classList.add('hidden');
      updateCityTabs(); updateNlExamples(); updateNearbyControls();
      await loadCityData({ search: false });
    }
    if (f.area) selectAreaFull(f.area, false, { search: false });
    if (f.property_type) { S.type = f.property_type; $$('#typeGrid .chip').forEach(c => c.classList.toggle('active', c.dataset.type === f.property_type)); }
    if (f.bedrooms) { S.beds = String(f.bedrooms); $$('#bedRow .chip').forEach(c => c.classList.toggle('active', c.dataset.beds === S.beds)); }
    S.bedsMax = f.bedrooms_max ? String(f.bedrooms_max) : '';
    if (f.price_min) S.priceMin = String(f.price_min);
    if (f.price_max) S.priceMax = String(f.price_max);
    if (f.price_min || f.price_max) syncPriceChips();
    S.sizeMarlaMin = f.size_marla_min != null ? String(f.size_marla_min) : '';
    S.sizeMarlaMax = f.size_marla_max != null ? String(f.size_marla_max) : '';
    if (f.furnished) setToggle(true);
    if (f.sort) { S.sort = f.sort; $('#sortSelect').value = f.sort; }
    trackNlSearch({ phase: 'parsed', queryLength, parseSuccess: true, filters: f });
    updateChips();
    refs._lastTriggeredBy = 'nl_search';
    doSearch();
    if (f.area_approximate) {
      parsed.innerHTML = '<span class="text-amber-600">Couldn\'t find "' + esc(f.area_query) + '" specifically — showing results for <b>' + esc(f.area) + '</b></span>';
      setTimeout(() => { parsed.classList.add('hidden'); parsed.classList.remove('flex'); }, 6000);
    } else {
      parsed.classList.add('hidden');
      parsed.classList.remove('flex');
    }
  } catch {
    parsed.innerHTML = 'Something went wrong.';
  } finally {
    $('#nlSearchBtn').disabled = false;
  }
}

function initCityTabs() {
  $$('.city-tab').forEach(tab => tab.addEventListener('click', () => {
    if (tab.dataset.city === S.city) return;
    const prevCity = S.city;
    S.city = tab.dataset.city;
    trackCitySwitch({ from: prevCity, to: S.city });
    S.area = ''; S.type = ''; S.beds = ''; S.bedsMax = ''; S.priceMin = ''; S.priceMax = ''; S.furnished = false; S.sort = '';
    S.sizeMarlaMin = ''; S.sizeMarlaMax = '';
    refs.searchMode = window.innerWidth > 768 && refs.map ? 'viewport' : 'city';
    resetViewportSearchMeta({ clearVisibleAreas: true });
    refs.lastViewportSearchKey = '';
    refs.previewArea = null;
    refs.hoveredArea = null;
    clearNearbyRadiusOverlays();
    refreshUserLocationOverlays();
    $('#areaInput').value = ''; $('#areaClear').classList.add('hidden');
    $$('#typeGrid .chip').forEach(c => c.classList.remove('active'));
    $$('#bedRow .chip').forEach(c => c.classList.toggle('active', c.dataset.beds === ''));
    $$('#priceGrid .chip').forEach(c => c.classList.remove('active'));
    $('#customPrice').classList.add('hidden'); $('#priceMin').value = ''; $('#priceMax').value = '';
    setToggle(false); $('#sortSelect').value = '';
    updateCityTabs(); updateChips(); updateNlExamples(); updateNearbyControls();
    refs._lastTriggeredBy = 'city_change';
    loadCityData();
  }));
}

let _maxCardSeen = 0;
let _scrollDepthTimer = null;
const _scrollObserver = new IntersectionObserver(entries => {
  for (const entry of entries) {
    if (!entry.isIntersecting) continue;
    const idx = parseInt(entry.target.dataset.idx, 10);
    if (Number.isFinite(idx) && idx > _maxCardSeen) _maxCardSeen = idx;
  }
  clearTimeout(_scrollDepthTimer);
  _scrollDepthTimer = setTimeout(() => {
    if (_maxCardSeen > 0) {
      trackScrollDepth({ maxPosition: _maxCardSeen, totalResults: refs.lastSearchTotal || refs.currentResults.length, mode: refs.searchMode, city: S.city });
    }
  }, 2000);
}, { threshold: 0.5 });

function observeCards() {
  $$('.card-wrap').forEach(card => _scrollObserver.observe(card));
}

function resetScrollTracking() {
  _maxCardSeen = 0;
  clearTimeout(_scrollDepthTimer);
}

function initCardListeners() {
  const grid = $('#listingsGrid');

  grid.addEventListener('click', e => {
    if (e.target.closest('[data-prev]') || e.target.closest('[data-next]')) return;
    if (e.target.closest('[data-action]')) return;
    const c = e.target.closest('.card-wrap');
    if (!c) return;
    const idx = parseInt(c.dataset.idx, 10);
    if (!isNaN(idx) && refs.currentResults[idx]) openDrawerFull(refs.currentResults[idx], idx);
  });

  grid.addEventListener('click', e => {
    const btn = e.target.closest('[data-action]');
    if (!btn || btn.dataset.action === 'open') return;
    e.preventDefault();
    e.stopPropagation();
    handleContactAction(btn.dataset.action, btn.dataset.url, btn);
  });
}

function initNlListeners() {
  $('#nlSearchBtn').addEventListener('click', doNlSearch);
  $('#nlInput').addEventListener('keydown', e => { if (e.key === 'Enter') { $('#nlSuggestions').classList.add('hidden'); doNlSearch(); } });
  $('#nlInput').addEventListener('focus', () => { if (!$('#nlInput').value.trim()) $('#nlSuggestions').classList.remove('hidden'); });
  $('#nlInput').addEventListener('input', () => { $('#nlSuggestions').classList.toggle('hidden', !!$('#nlInput').value.trim()); });
  $('#nlSuggestions').addEventListener('click', e => {
    const pop = e.target.closest('.pop-search');
    if (pop) {
      S.area = pop.dataset.area || '';
      S.type = pop.dataset.type || '';
      S.beds = pop.dataset.beds || '';
      S.priceMin = '';
      S.priceMax = '';
      S.furnished = false;
      if (refs.searchMode !== 'nearby') refs.searchMode = S.area ? 'area' : refs.searchMode;
      $('#nlInput').value = '';
      $('#nlSuggestions').classList.add('hidden');
      updateChips(); updateNearbyControls();
      refs._lastTriggeredBy = 'popular_search';
      doSearch();
      return;
    }
    const ex = e.target.closest('.nl-ex');
    if (ex) {
      $('#nlInput').value = ex.textContent;
      $('#nlSuggestions').classList.add('hidden');
      doNlSearch();
    }
  });
  document.addEventListener('click', e => { if (!e.target.closest('#nlSuggestions') && !e.target.closest('#nlInput')) $('#nlSuggestions').classList.add('hidden'); });
}

function initNearbyControls() {
  $('#nearbyChip').addEventListener('click', async e => {
    if (e.target.closest('[data-nearby-clear]')) {
      e.preventDefault();
      exitNearbyMode({ silent: true });
      doSearch(1);
      return;
    }

    if (!isNearbySupportedCity()) {
      showToast('Nearby search is available in Karachi for now.', { tone: 'warning' });
      return;
    }

    try {
      if (!refs.userLocation) {
        await requestUserLocation({ mapInstance: getActiveMapInstance(), recenter: true });
      } else {
        refreshUserLocationOverlays();
      }
    } catch {
      return;
    }

    refs.searchMode = 'nearby';
    updateNearbyControls();
    refs._lastTriggeredBy = 'nearby_chip';
    doSearch(1);
  });

  $('#dd-radius').addEventListener('click', e => {
    const chip = e.target.closest('[data-radius-km]');
    if (!chip) return;
    refs.nearbyRadiusKm = Number(chip.dataset.radiusKm) || 5;
    $$('#radiusOptions .chip').forEach(el => el.classList.toggle('active', el === chip));
    updateNearbyControls();
    closeDD();
    refreshUserLocationOverlays();
    if (refs.searchMode === 'nearby') { refs._lastTriggeredBy = 'radius_change'; doSearch(1); }
  });
}

function gatherFeedbackContext() {
  const center = refs.map ? refs.map.getCenter() : null;
  const zoom = refs.map ? refs.map.getZoom() : null;
  return JSON.stringify({
    mode: refs.searchMode, city: S.city, area: S.area || null,
    type: S.type || null, beds: S.beds || null,
    query: $('#nlInput').value || null,
    results: refs.currentResults.length,
    total: refs.lastSearchTotal || 0,
    exactPins: refs.currentResults.filter(item => item.has_exact_geography).length,
    zoom: zoom, center: center ? `${center.lat.toFixed(4)},${center.lng.toFixed(4)}` : null,
  });
}

function initReportBtn() {
  const overlay = $('#feedbackOverlay');
  const modal = $('#feedbackModal');
  const msg = $('#feedbackMsg');
  const submitBtn = $('#feedbackSubmit');

  function openFeedback() {
    overlay.classList.remove('hidden');
    modal.classList.remove('hidden');
    msg.value = '';
    submitBtn.disabled = true;
    msg.focus();
  }
  function closeFeedback() {
    overlay.classList.add('hidden');
    modal.classList.add('hidden');
  }

  $('#reportBtn').addEventListener('click', openFeedback);
  $('#feedbackClose').addEventListener('click', closeFeedback);
  $('#feedbackCancel').addEventListener('click', closeFeedback);
  overlay.addEventListener('click', closeFeedback);

  msg.addEventListener('input', () => { submitBtn.disabled = !msg.value.trim(); });

  submitBtn.addEventListener('click', async () => {
    const text = msg.value.trim();
    if (!text) return;
    submitBtn.disabled = true;
    submitBtn.textContent = 'Sending...';
    try {
      const resp = await fetch('/api/feedback', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message: text, context: gatherFeedbackContext() }),
      });
      if (!resp.ok) throw new Error();
      trackFeedbackSubmitted({ messageLength: text.length });
      closeFeedback();
      showToast('Thanks for your feedback!');
    } catch {
      showToast('Could not send feedback. Please try again.', { tone: 'error' });
      submitBtn.disabled = false;
    } finally {
      submitBtn.textContent = 'Send';
    }
  });
}

async function loadCityData({ search = true } = {}) {
  try {
    const r = await fetch('/api/areas?city=' + S.city);
    refs.allAreas = await r.json();
  } catch (e) {
    console.error(e);
  }

  Object.values(refs.markers).forEach(m => { if (refs.map) refs.map.removeLayer(m); });
  refs.markers = {};
  resetViewportSearchMeta({ clearVisibleAreas: true });
  refs.viewportTotal = 0;
  refs.viewportShown = 0;
  refs.lastViewportSearchKey = '';
  refs.previewArea = null;
  refs.hoveredArea = null;
  const cd = CITY_DEFAULTS[S.city];
  if (refs.map) fitCityOverview(refs.map);
  if (refs.listingMarkerLayer) { refs.listingMarkerLayer.remove(); refs.listingMarkerLayer = null; }
  if (refs.mobileMap) {
    refs.mobileMap.remove();
    refs.mobileMap = null;
    refs.mobileMapBaseLayer = null;
    refs.mobileMarkerLayer = null;
    refs.mobileListingMarkerLayer = null;
    refs.mobileUserLocationMarker = null;
    refs.mobileUserLocationCircle = null;
    refs.mobileNearbyRadiusLayer = null;
  }
  const carousel = $('#mapCarousel');
  if (carousel) { carousel.innerHTML = ''; carousel.classList.add('hidden'); }
  updateNearbyControls();
  resetExactPrefetchState();
  ensureMarkers(selectAreaFull);
  updateMapMarkers();
  updateCoverageBadge();
  if (search) doSearch();
}

async function init() {
  initAnalytics();
  initMobileMap(selectAreaFull, openDrawerFull, () => scheduleViewportSearch({ mobile: true }));
  await chooseInitialCity();
  refs._notify = showToast;
  refs.mapLayer = getStoredMapLayer();
  hydrateStoredUserLocation();

  updateCityTabs();
  updateNlExamples();
  try {
    const r = await fetch('/api/areas?city=' + S.city);
    refs.allAreas = await r.json();
  } catch (e) {
    console.error(e);
  }

  try {
    const r = await fetch('/api/popular-searches?city=' + S.city + '&limit=5');
    const popular = await r.json();
    if (popular.length) {
      const container = $('#nlSuggestions');
      let html = '<div class="px-3 py-1.5 text-[10px] font-semibold text-gray-400 uppercase tracking-wide">Popular</div>';
      popular.forEach(p => {
        const parts = [];
        if (p.bedrooms) parts.push(p.bedrooms + ' bed');
        if (p.property_type) parts.push(TYPE_L[p.property_type] || p.property_type);
        if (p.area) parts.push('in ' + p.area);
        const label = parts.join(' ') || 'All listings';
        html += `<div class="pop-search px-3 py-2 text-sm text-gray-600 hover:bg-brand-50 hover:text-brand-500 cursor-pointer transition-colors" data-area="${p.area || ''}" data-type="${p.property_type || ''}" data-beds="${p.bedrooms || ''}">${label} <span class="text-gray-300 text-xs">(${p.count})</span></div>`;
      });
      container.insertAdjacentHTML('afterbegin', html);
    }
  } catch {}

  initCityTabs();
  initFilterListeners({ doSearch, selectAreaFull, clearFilterFull, resetMapView });
  initNearbyControls();
  initCardListeners();
  initNlListeners();
  initDrawerListeners(selectAreaFull);
  initReportBtn();
  initHoverSync();

  loadSearch();
  updateNearbyControls();
  if (window.innerWidth > 768) {
    refs.searchMode = S.area ? 'area' : 'viewport';
    initMap(selectAreaFull, () => scheduleViewportSearch(), openDrawerFull);
    if (S.area) highlightMarker(S.area, true);
  }
  refs._lastTriggeredBy = 'page_load';
  doSearch();
}

init();
