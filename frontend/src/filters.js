/** Filter bar: chips, dropdowns, area autocomplete, presets. */

import { $, $$, esc, escA, TYPE_L } from './utils.js';
import { S, refs, CITY_DEFAULTS, POPULAR_AREAS_BY_CITY, NL_EXAMPLES } from './state.js';

// ===== NL EXAMPLES (city-aware) =====

export function updateNlExamples() {
  const cfg = NL_EXAMPLES[S.city] || NL_EXAMPLES.karachi;
  $('#nlInput').placeholder = cfg.placeholder;
  const container = $('#nlExamples');
  if (container) container.innerHTML = cfg.examples.map(ex =>
    `<div class="nl-ex px-3 py-2 text-sm text-gray-600 hover:bg-brand-50 hover:text-brand-500 cursor-pointer transition-colors">${esc(ex)}</div>`
  ).join('');
}

// ===== CITY TABS =====

export function updateCityTabs() {
  $$('.city-tab').forEach(t => t.classList.toggle('active', t.dataset.city === S.city));
}

// ===== CHIP LABELS =====

function setChipVal(el, val, def) {
  const f = el.dataset.filter;
  if (val) {
    el.innerHTML = esc(val) + `<span class="chip-clear" data-chip-clear="${f}">&times;</span>`;
    el.classList.add('has-value');
  } else {
    el.innerHTML = def + ' <svg class="w-3 h-3 ml-0.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2.5" d="M19 9l-7 7-7-7"/></svg>';
    el.classList.remove('has-value');
  }
}

function countFilters() {
  let n = 0;
  if (S.area) n++; if (S.type) n++; if (S.beds) n++;
  if (S.priceMin || S.priceMax) n++; if (S.furnished) n++; if (S.sort) n++;
  return n;
}

export function updateChips() {
  setChipVal($('#areaChip'), S.area, 'Area');
  setChipVal($('#typeChip'), S.type ? TYPE_L[S.type] || S.type : '', 'Type');
  setChipVal($('#bedsChip'), S.beds ? S.beds + (S.beds === '5' ? '+' : '') + ' Bed' : '', 'Beds');

  let pl = '';
  if (S.priceMin || S.priceMax) {
    const mn = S.priceMin ? (S.priceMin / 1e3 | 0) + 'K' : '';
    const mx = S.priceMax ? (S.priceMax / 1e3 | 0) + 'K' : '';
    pl = mn && mx ? mn + '-' + mx : mx ? '<' + mx : mn + '+';
  }
  setChipVal($('#priceChip'), pl, 'Price');

  const mc = (S.furnished ? 1 : 0) + (S.sort ? 1 : 0);
  setChipVal($('#moreChip'), mc ? 'More (' + mc + ')' : '', 'More');

  $('#clearAllBtn').classList.toggle('hidden', countFilters() === 0);
}

// ===== DROPDOWNS =====

const ddMap = { area: 'dd-area', type: 'dd-type', beds: 'dd-beds', price: 'dd-price', more: 'dd-more' };

export function openDD(name) {
  if (refs.activeDD === name) { closeDD(); return; }
  closeDD();
  const el = $('#' + ddMap[name]);
  el.classList.add('open');
  refs.activeDD = name;
  if (window.innerWidth <= 768) $('#ddBackdrop').classList.remove('hidden');

  // Position dropdown under its chip button (desktop only)
  if (window.innerWidth > 768) {
    const chip = $(`[data-filter="${name}"]`);
    const bar = el.parentElement;
    const chipRect = chip.getBoundingClientRect();
    const barRect = bar.getBoundingClientRect();
    let left = chipRect.left - barRect.left;
    const maxLeft = barRect.width - el.offsetWidth;
    if (left > maxLeft) left = Math.max(0, maxLeft);
    el.style.left = left + 'px';
  }

  if (name === 'area') { $('#areaInput').focus(); renderAreaList(filterAreas($('#areaInput').value.trim())); }
}

export function closeDD() {
  Object.values(ddMap).forEach(id => $('#' + id).classList.remove('open'));
  refs.activeDD = null;
  $('#ddBackdrop').classList.add('hidden');
}

// ===== AREA AUTOCOMPLETE =====

let hlIdx = -1;

function filterAreas(q) {
  if (!q) {
    const cityPopular = POPULAR_AREAS_BY_CITY[S.city] || new Set();
    const popular = refs.allAreas.filter(a => cityPopular.has(a.name));
    const cn = CITY_DEFAULTS[S.city]?.name || 'Karachi';
    return popular.length ? popular : refs.allAreas.filter(a => a.name !== cn).slice(0, 25);
  }
  const lq = q.toLowerCase().replace(/[-]/g, ' ');
  const qTokens = lq.split(/\s+/).filter(t => t.length > 0);
  const scored = [];
  const cityName = CITY_DEFAULTS[S.city]?.name || 'Karachi';
  for (const a of refs.allAreas) {
    if (a.name === cityName) continue;
    const nl = a.name.toLowerCase();
    const nlNorm = nl.replace(/[-]/g, ' ');
    if (nl === lq) { scored.push({ a, s: 100 }); continue; }
    if (nlNorm.startsWith(lq)) { scored.push({ a, s: 90 }); continue; }
    if (nlNorm.includes(lq)) { scored.push({ a, s: 80 - a.name.length * 0.1 }); continue; }
    if (a.name_ur && a.name_ur.includes(q)) { scored.push({ a, s: 75 }); continue; }
    const aTokens = nlNorm.split(/\s+/);
    const overlap = qTokens.filter(t => aTokens.some(at => at.startsWith(t) || at.includes(t))).length;
    if (overlap > 0) scored.push({ a, s: 40 + overlap * 15 - (a.name.length * 0.05) });
  }
  scored.sort((a, b) => b.s - a.s);
  return scored.slice(0, 20).map(x => x.a);
}

function renderAreaList(items) {
  const areaList = $('#areaList');
  if (!items.length) { areaList.innerHTML = '<div class="p-3 text-sm text-gray-400">No areas found</div>'; return; }
  hlIdx = -1;
  areaList.innerHTML = items.map((a, i) =>
    `<div class="area-opt" data-i="${i}" data-name="${a.name}"><span>${esc(a.name)}</span>${a.name_ur ? `<span class="text-xs text-gray-400" dir="rtl">${a.name_ur}</span>` : ''}</div>`
  ).join('');
}

export function syncPriceChips() {
  let matched = false;
  $$('#priceGrid .chip').forEach(c => {
    if (c.dataset.custom) return;
    const m = c.dataset.pmin === S.priceMin && c.dataset.pmax === S.priceMax;
    c.classList.toggle('active', m); if (m) matched = true;
  });
  const cc = $('[data-custom="1"]');
  if (!matched && (S.priceMin || S.priceMax)) {
    cc.classList.add('active'); $('#customPrice').classList.remove('hidden');
    $('#priceMin').value = S.priceMin; $('#priceMax').value = S.priceMax;
  } else {
    cc.classList.remove('active'); if (!matched) $('#customPrice').classList.add('hidden');
  }
}

export function setToggle(on) {
  const t = $('#furnishedToggle');
  t.classList.toggle('toggle-on', on);
  t.querySelector('.toggle-knob').style.transform = on ? 'translateX(20px)' : 'translateX(0)';
  S.furnished = on;
}

// ===== CLEAR FILTER =====

export function clearFilter(f, { resetMapView, doSearch } = {}) {
  if (f === 'area') { S.area = ''; $('#areaInput').value = ''; $('#areaClear').classList.add('hidden'); resetMapView?.(); }
  if (f === 'type') { S.type = ''; $$('#typeGrid .chip').forEach(c => c.classList.remove('active')); }
  if (f === 'beds') { S.beds = ''; $$('#bedRow .chip').forEach(c => c.classList.toggle('active', c.dataset.beds === '')); }
  if (f === 'price') { S.priceMin = ''; S.priceMax = ''; $$('#priceGrid .chip').forEach(c => c.classList.remove('active')); $('#customPrice').classList.add('hidden'); $('#priceMin').value = ''; $('#priceMax').value = ''; }
  if (f === 'more') { S.furnished = false; S.sort = ''; setToggle(false); $('#sortSelect').value = ''; }
  updateChips(); doSearch?.();
}

// ===== SELECT AREA =====

export function selectArea(name, fromMap, { highlightMarker, doSearch } = {}) {
  S.area = name;
  $('#areaInput').value = name;
  $('#areaClear').classList.remove('hidden');
  closeDD();
  updateChips();
  if (!fromMap) highlightMarker?.(name, true);
  doSearch?.();
}

// ===== INIT FILTER LISTENERS =====

export function initFilterListeners({ doSearch, selectAreaFull, clearFilterFull, resetMapView }) {
  // Chip → open dropdown or clear
  $$('[data-filter]').forEach(el => el.addEventListener('click', e => {
    const clearBtn = e.target.closest('[data-chip-clear]');
    if (clearBtn) { e.stopPropagation(); clearFilterFull(clearBtn.dataset.chipClear); return; }
    openDD(el.dataset.filter);
  }));

  // Click outside closes dropdown
  document.addEventListener('click', e => {
    if (!e.target.closest('.filter-dd') && !e.target.closest('[data-filter]')) closeDD();
  });
  $('#ddBackdrop').addEventListener('click', closeDD);

  // Clear All
  $('#clearAllBtn').addEventListener('click', () => {
    S.area = ''; S.type = ''; S.beds = ''; S.priceMin = ''; S.priceMax = ''; S.furnished = false; S.sort = '';
    $('#areaInput').value = ''; $('#areaClear').classList.add('hidden');
    $$('#typeGrid .chip').forEach(c => c.classList.remove('active'));
    $$('#bedRow .chip').forEach(c => c.classList.toggle('active', c.dataset.beds === ''));
    $$('#priceGrid .chip').forEach(c => c.classList.remove('active'));
    $('#customPrice').classList.add('hidden'); $('#priceMin').value = ''; $('#priceMax').value = '';
    setToggle(false); $('#sortSelect').value = '';
    $$('#presetRow .chip').forEach(c => c.classList.remove('active'));
    updateChips(); resetMapView(); doSearch();
  });

  // Area autocomplete
  const areaInput = $('#areaInput');
  const areaClear = $('#areaClear');

  areaInput.addEventListener('input', () => {
    const q = areaInput.value.trim();
    areaClear.classList.toggle('hidden', !q);
    if (!q) { S.area = ''; updateChips(); }
    renderAreaList(filterAreas(q));
  });
  areaInput.addEventListener('focus', () => renderAreaList(filterAreas(areaInput.value.trim())));
  areaInput.addEventListener('keydown', e => {
    const opts = $('#areaList').querySelectorAll('.area-opt');
    if (e.key === 'ArrowDown') { e.preventDefault(); hlIdx = Math.min(hlIdx + 1, opts.length - 1); opts.forEach((o, i) => o.classList.toggle('hl', i === hlIdx)); }
    else if (e.key === 'ArrowUp') { e.preventDefault(); hlIdx = Math.max(hlIdx - 1, 0); opts.forEach((o, i) => o.classList.toggle('hl', i === hlIdx)); }
    else if (e.key === 'Enter') { e.preventDefault(); if (hlIdx >= 0 && opts[hlIdx]) selectAreaFull(opts[hlIdx].dataset.name); else doSearch(); }
    else if (e.key === 'Escape') closeDD();
  });
  $('#areaList').addEventListener('click', e => {
    const o = e.target.closest('.area-opt');
    if (o) selectAreaFull(o.dataset.name);
  });
  areaClear.addEventListener('click', () => {
    S.area = ''; areaInput.value = ''; areaClear.classList.add('hidden');
    refs.searchMode = window.innerWidth > 768 && refs.map ? 'viewport' : 'city';
    refs.mapAreaTotals = {};
    refs.viewportAreaNames = [];
    refs.previewArea = null;
    refs.hoveredArea = null;
    resetMapView(); updateChips(); renderAreaList(refs.allAreas.slice(0, 20)); doSearch();
  });

  // Type
  $('#typeGrid').addEventListener('click', e => {
    const c = e.target.closest('.chip'); if (!c) return;
    if (c.classList.contains('active')) { c.classList.remove('active'); S.type = ''; }
    else { $$('#typeGrid .chip').forEach(x => x.classList.remove('active')); c.classList.add('active'); S.type = c.dataset.type; }
    updateChips(); closeDD(); doSearch();
  });

  // Beds
  $('#bedRow').addEventListener('click', e => {
    const c = e.target.closest('.chip'); if (!c) return;
    $$('#bedRow .chip').forEach(x => x.classList.remove('active'));
    c.classList.add('active'); S.beds = c.dataset.beds;
    updateChips(); closeDD(); doSearch();
  });

  // Price
  $('#priceGrid').addEventListener('click', e => {
    const c = e.target.closest('.chip'); if (!c) return;
    if (c.dataset.custom) {
      $$('#priceGrid .chip').forEach(x => x.classList.remove('active'));
      c.classList.add('active'); $('#customPrice').classList.remove('hidden');
      S.priceMin = $('#priceMin').value; S.priceMax = $('#priceMax').value;
      updateChips(); return;
    }
    $('#customPrice').classList.add('hidden');
    if (c.classList.contains('active')) { c.classList.remove('active'); S.priceMin = ''; S.priceMax = ''; }
    else { $$('#priceGrid .chip').forEach(x => x.classList.remove('active')); c.classList.add('active'); S.priceMin = c.dataset.pmin; S.priceMax = c.dataset.pmax; }
    updateChips(); closeDD(); doSearch();
  });
  $('#priceMin').addEventListener('input', () => { S.priceMin = $('#priceMin').value; updateChips(); });
  $('#priceMax').addEventListener('input', () => { S.priceMax = $('#priceMax').value; updateChips(); });
  $$('#customPrice input').forEach(el => el.addEventListener('keydown', e => { if (e.key === 'Enter') { closeDD(); doSearch(); } }));
  $('#priceApply').addEventListener('click', () => { S.priceMin = $('#priceMin').value; S.priceMax = $('#priceMax').value; updateChips(); closeDD(); doSearch(); });

  // Furnished
  $('#furnishedToggle').addEventListener('click', () => { setToggle(!S.furnished); updateChips(); doSearch(); });

  // Sort
  $('#sortSelect').addEventListener('change', () => { S.sort = $('#sortSelect').value; updateChips(); closeDD(); doSearch(); });

  // Presets
  $('#presetRow').addEventListener('click', e => {
    const c = e.target.closest('.chip'); if (!c) return;
    $$('#presetRow .chip').forEach(x => x.classList.remove('active'));
    c.classList.add('active');
    S.type = c.dataset.type || ''; S.beds = c.dataset.beds || ''; S.priceMin = c.dataset.pmin || ''; S.priceMax = c.dataset.pmax || '';
    $$('#typeGrid .chip').forEach(x => x.classList.toggle('active', x.dataset.type === S.type));
    $$('#bedRow .chip').forEach(x => x.classList.toggle('active', x.dataset.beds === S.beds));
    syncPriceChips();
    updateChips(); closeDD(); doSearch();
  });

  // Escape closes dropdown
  document.addEventListener('keydown', e => { if (e.key === 'Escape') closeDD(); });
}
