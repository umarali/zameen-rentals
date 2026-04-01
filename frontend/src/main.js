/** App entry point — wires modules together, search engine, init. */

import '../src/style.css';
import { $, $$, esc, TYPE_L } from './utils.js';
import { S, refs, CITY_DEFAULTS } from './state.js';
import { updateCityTabs, updateNlExamples, updateChips, closeDD, clearFilter, selectArea, syncPriceChips, setToggle, initFilterListeners } from './filters.js';
import { renderCard, initCarousels, handleContactAction, skeletonCard } from './cards.js';
import { initMap, ensureMarkers, updateMapMarkers, highlightMarker, resetMapView, initMobileMap, updateMobileCarousel, initHoverSync } from './map.js';
import { openDrawer, closeDrawer, initDrawerListeners } from './drawer.js';

// ===== WIRED HELPERS =====
// These close over module functions so we can pass them as callbacks

function selectAreaFull(name, fromMap) {
  selectArea(name, fromMap, { highlightMarker, doSearch });
}

function clearFilterFull(f) {
  clearFilter(f, { resetMapView, doSearch });
}

function openDrawerFull(item) {
  openDrawer(item, selectAreaFull);
}

// ===== SEARCH ENGINE =====

function getParams(pg) {
  const p = new URLSearchParams();
  p.set('city', S.city);
  if (S.area) p.set('area', S.area);
  if (S.type) p.set('property_type', S.type);
  if (S.beds) p.set('bedrooms', S.beds);
  if (S.priceMin) p.set('price_min', S.priceMin);
  if (S.priceMax) p.set('price_max', S.priceMax);
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

function hideLoading() { const s = $('#spinner'); if (s) s.remove(); }

async function doSearch(page) {
  if (refs.isLoading) return;
  const append = page && page > 1;
  if (!append) { refs.currentPage = 1; refs.currentResults = []; }
  else refs.currentPage = page;

  refs.isLoading = true; showLoading(append); saveSearch();

  try {
    const r = await fetch('/api/search?' + getParams(refs.currentPage).toString());
    if (!r.ok) { const e = await r.json().catch(() => ({ detail: 'Search failed' })); throw new Error(e.detail || 'Search failed'); }
    const d = await r.json();
    hideLoading();

    const cityName = CITY_DEFAULTS[S.city]?.name || 'Karachi';
    $('#listingsTitle').textContent = S.area ? 'Rentals in ' + S.area : 'Rentals in ' + cityName;

    refs.lastSearchTotal = d.total || 0;
    if (!append) {
      refs.currentResults = d.results || [];
      if (!refs.currentResults.length) {
        refs.lastSearchTotal = 0;
        $('#resultsCount').textContent = '0 results';
        const activeFilters = [];
        if (S.area) activeFilters.push({ label: 'Area: ' + S.area, filter: 'area' });
        if (S.type) activeFilters.push({ label: 'Type: ' + (TYPE_L[S.type] || S.type), filter: 'type' });
        if (S.beds) activeFilters.push({ label: S.beds + ' Bed', filter: 'beds' });
        if (S.priceMin || S.priceMax) activeFilters.push({ label: 'Price range', filter: 'price' });
        if (S.furnished) activeFilters.push({ label: 'Furnished', filter: 'more' });
        const filterHtml = activeFilters.length ? `<div class="flex flex-wrap justify-center gap-2 mt-4">${activeFilters.map(f => `<button class="text-xs px-3 py-1.5 rounded-full border border-gray-200 text-gray-500 hover:border-red-300 hover:text-red-500 transition-colors" data-remove-filter="${f.filter}">Remove ${esc(f.label)} &times;</button>`).join('')}</div>` : '';
        $('#listingsGrid').innerHTML = `<div class="col-span-full text-center py-12"><div class="text-5xl mb-3">&#x1f3e0;</div><h3 class="text-base font-semibold text-gray-600">No rentals found</h3><p class="text-sm text-gray-400 mt-1">Try removing a filter to see more results</p>${filterHtml}</div>`;
        $$('[data-remove-filter]').forEach(btn => btn.addEventListener('click', () => clearFilterFull(btn.dataset.removeFilter)));
        updateMapMarkers(); return;
      }
      $('#listingsGrid').innerHTML = refs.currentResults.map((it, i) => renderCard(it, i)).join('');
    } else {
      const nr = d.results || [], si = refs.currentResults.length;
      refs.currentResults = refs.currentResults.concat(nr);
      nr.forEach((it, i) => $('#listingsGrid').insertAdjacentHTML('beforeend', renderCard(it, si + i)));
    }
    $('#reportBtn').classList.remove('hidden');
    if (d.total && d.total > refs.currentResults.length) {
      $('#resultsCount').textContent = 'Showing ' + refs.currentResults.length + ' of ' + d.total + ' results';
    } else {
      $('#resultsCount').textContent = refs.currentResults.length + ' results';
    }
    const srcEl = $('#dataSource');
    if (d.source === 'local') {
      srcEl.textContent = 'Instant'; srcEl.className = 'text-xs text-brand-500 font-medium'; srcEl.classList.remove('hidden');
    } else if (d.source === 'live') {
      srcEl.textContent = 'Live'; srcEl.className = 'text-xs text-amber-500 font-medium'; srcEl.classList.remove('hidden');
    } else { srcEl.classList.add('hidden'); }

    initCarousels();
    updateMapMarkers();

    const ft = $('#listingsFooter'); ft.innerHTML = '';
    if ((d.results || []).length >= 15) {
      const b = document.createElement('button');
      b.className = 'w-full py-3 mt-4 border-2 border-brand-500 rounded-lg text-brand-500 text-sm font-semibold hover:bg-brand-50 transition-colors';
      b.textContent = 'Load More Results';
      b.addEventListener('click', () => doSearch(refs.currentPage + 1));
      ft.appendChild(b);
    }
    if (!append) $('#listingsPanel').scrollTo({ top: 0, behavior: 'smooth' });
  } catch (e) {
    hideLoading();
    refs.currentResults = [];
    updateMapMarkers();
    $('#listingsFooter').innerHTML = `<div class="text-center py-6 bg-red-50 rounded-lg mt-4"><p class="text-sm text-red-600">${esc(e.message)}</p></div>`;
  } finally { refs.isLoading = false; refs.mapDriven = false; }
}

// ===== NL SEARCH =====

async function doNlSearch() {
  const q = $('#nlInput').value.trim();
  if (!q || refs.isLoading) return;
  $('#nlSearchBtn').disabled = true;
  const parsed = $('#nlParsed');
  parsed.classList.remove('hidden'); parsed.classList.add('flex');
  parsed.innerHTML = '<span class="inline-flex items-center gap-1.5 text-gray-400"><svg class="w-3 h-3 animate-spin" fill="none" viewBox="0 0 24 24"><circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"/><path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"/></svg>Parsing filters...</span>';
  try {
    const r = await fetch('/api/parse-query?q=' + encodeURIComponent(q) + '&city=' + S.city);
    if (!r.ok) throw 0;
    const d = await r.json(), f = d.filters || {};
    if (!Object.keys(f).length) { parsed.innerHTML = 'Could not understand. Try "2 bed flat in DHA under 50k"'; return; }
    const parts = [];
    if (f.area) parts.push('<b class="text-brand-500">' + esc(f.area) + '</b>');
    if (f.property_type) parts.push('<b class="text-brand-500">' + (TYPE_L[f.property_type] || f.property_type) + '</b>');
    if (f.bedrooms) parts.push('<b class="text-brand-500">' + f.bedrooms + ' bed</b>');
    if (f.price_min || f.price_max) { const mn = f.price_min ? (f.price_min / 1e3 | 0) + 'K' : '', mx = f.price_max ? (f.price_max / 1e3 | 0) + 'K' : ''; parts.push('<b class="text-brand-500">' + (mn && mx ? mn + '-' + mx : mx ? '<' + mx : mn + '+') + '</b>'); }
    if (f.furnished) parts.push('<b class="text-brand-500">Furnished</b>');
    parsed.innerHTML = parts.join(' &middot; ');
    if (f.area) selectAreaFull(f.area);
    if (f.property_type) { S.type = f.property_type; $$('#typeGrid .chip').forEach(c => c.classList.toggle('active', c.dataset.type === f.property_type)); }
    if (f.bedrooms) { S.beds = String(f.bedrooms); $$('#bedRow .chip').forEach(c => c.classList.toggle('active', c.dataset.beds === S.beds)); }
    if (f.price_min) S.priceMin = String(f.price_min);
    if (f.price_max) S.priceMax = String(f.price_max);
    if (f.price_min || f.price_max) syncPriceChips();
    if (f.furnished) setToggle(true);
    if (f.sort) { S.sort = f.sort; $('#sortSelect').value = f.sort; }
    updateChips(); doSearch();
    if (f.area_approximate) {
      parsed.innerHTML = '<span class="text-amber-600">Couldn\'t find "' + esc(f.area_query) + '" specifically — showing results for <b>' + esc(f.area) + '</b></span>';
      setTimeout(() => { parsed.classList.add('hidden'); parsed.classList.remove('flex'); }, 6000);
    } else { parsed.classList.add('hidden'); parsed.classList.remove('flex'); }
  } catch { parsed.innerHTML = 'Something went wrong.'; }
  finally { $('#nlSearchBtn').disabled = false; }
}

// ===== CITY TAB SWITCHING =====

function initCityTabs() {
  $$('.city-tab').forEach(tab => tab.addEventListener('click', () => {
    if (tab.dataset.city === S.city) return;
    S.city = tab.dataset.city;
    S.area = ''; S.type = ''; S.beds = ''; S.priceMin = ''; S.priceMax = ''; S.furnished = false; S.sort = '';
    $('#areaInput').value = ''; $('#areaClear').classList.add('hidden');
    $$('#typeGrid .chip').forEach(c => c.classList.remove('active'));
    $$('#bedRow .chip').forEach(c => c.classList.toggle('active', c.dataset.beds === ''));
    $$('#priceGrid .chip').forEach(c => c.classList.remove('active'));
    $('#customPrice').classList.add('hidden'); $('#priceMin').value = ''; $('#priceMax').value = '';
    setToggle(false); $('#sortSelect').value = '';
    updateCityTabs(); updateChips(); updateNlExamples();
    loadCityData();
  }));
}

// ===== CARD CLICK HANDLERS =====

function initCardListeners() {
  const grid = $('#listingsGrid');

  // Card click → drawer
  grid.addEventListener('click', e => {
    if (e.target.closest('[data-prev]') || e.target.closest('[data-next]')) return;
    if (e.target.closest('[data-action]')) return;
    const c = e.target.closest('.card-wrap');
    if (!c) return;
    const idx = parseInt(c.dataset.idx, 10);
    if (!isNaN(idx) && refs.currentResults[idx]) openDrawerFull(refs.currentResults[idx]);
  });

  // Action buttons (call/whatsapp)
  grid.addEventListener('click', e => {
    const btn = e.target.closest('[data-action]');
    if (!btn || btn.dataset.action === 'open') return;
    e.preventDefault(); e.stopPropagation();
    if (btn.dataset.phone) {
      const phone = btn.dataset.phone;
      if (btn.dataset.action === 'call') { window.open(`tel:${phone}`, '_self'); }
      else { const waNum = phone.replace(/^0/, '92').replace(/[^0-9]/g, ''); window.open(`https://wa.me/${waNum}?text=${encodeURIComponent('Hi, I am interested in this property: ' + btn.dataset.url)}`, '_blank'); }
    } else {
      handleContactAction(btn.dataset.action, btn.dataset.url, btn);
    }
  });
}

// ===== NL SEARCH LISTENERS =====

function initNlListeners() {
  $('#nlSearchBtn').addEventListener('click', doNlSearch);
  $('#nlInput').addEventListener('keydown', e => { if (e.key === 'Enter') { $('#nlSuggestions').classList.add('hidden'); doNlSearch(); } });
  $('#nlInput').addEventListener('focus', () => { if (!$('#nlInput').value.trim()) $('#nlSuggestions').classList.remove('hidden'); });
  $('#nlInput').addEventListener('input', () => { $('#nlSuggestions').classList.toggle('hidden', !!$('#nlInput').value.trim()); });
  $('#nlSuggestions').addEventListener('click', e => {
    const pop = e.target.closest('.pop-search');
    if (pop) {
      S.area = pop.dataset.area || ''; S.type = pop.dataset.type || ''; S.beds = pop.dataset.beds || '';
      S.priceMin = ''; S.priceMax = ''; S.furnished = false;
      $('#nlInput').value = ''; $('#nlSuggestions').classList.add('hidden');
      updateChips(); doSearch(); return;
    }
    const ex = e.target.closest('.nl-ex');
    if (ex) { $('#nlInput').value = ex.textContent; $('#nlSuggestions').classList.add('hidden'); doNlSearch(); }
  });
  document.addEventListener('click', e => { if (!e.target.closest('#nlSuggestions') && !e.target.closest('#nlInput')) $('#nlSuggestions').classList.add('hidden'); });
}

// ===== REPORT ISSUE =====

function initReportBtn() {
  $('#reportBtn').addEventListener('click', () => {
    const params = new URLSearchParams();
    const body = ['**What went wrong?**\n', '<!-- Describe the issue briefly -->\n', '**Search context** (auto-filled):', `- Area: ${S.area || 'Any'}`, `- Type: ${S.type || 'Any'}`, `- Beds: ${S.beds || 'Any'}`, `- Query: ${$('#nlInput').value || '(none)'}`, `- Results shown: ${refs.currentResults.length}`].join('\n');
    params.set('title', '[Feedback] ');
    params.set('body', body);
    params.set('labels', 'feedback');
    window.open('https://github.com/umarali/zameen-rentals/issues/new?' + params.toString(), '_blank');
  });
}

// ===== LOAD CITY DATA =====

async function loadCityData() {
  try { const r = await fetch('/api/areas?city=' + S.city); refs.allAreas = await r.json(); } catch (e) { console.error(e); }
  Object.values(refs.markers).forEach(m => { if (refs.map) refs.map.removeLayer(m); });
  refs.markers = {};
  const cd = CITY_DEFAULTS[S.city];
  if (refs.map) refs.map.setView([cd.lat, cd.lng], cd.zoom);
  if (refs.mobileMap) { refs.mobileMap.remove(); refs.mobileMap = null; }
  ensureMarkers(selectAreaFull);
  updateMapMarkers();
  doSearch();
}

// ===== INIT =====

async function init() {
  try { const saved = JSON.parse(localStorage.getItem('rk_s') || '{}'); if (saved.city) S.city = saved.city; } catch {}
  updateCityTabs(); updateNlExamples();
  try { const r = await fetch('/api/areas?city=' + S.city); refs.allAreas = await r.json(); } catch (e) { console.error(e); }

  // Load popular searches
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

  // Init all listeners
  initCityTabs();
  initFilterListeners({ doSearch, selectAreaFull, clearFilterFull, resetMapView });
  initCardListeners();
  initNlListeners();
  initDrawerListeners(selectAreaFull);
  initReportBtn();
  initHoverSync();

  loadSearch();
  if (window.innerWidth > 768) initMap(selectAreaFull);
  initMobileMap(selectAreaFull, openDrawerFull);
  doSearch();
}

init();
