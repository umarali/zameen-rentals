/** Filter bar: chips, dropdowns, area autocomplete, presets. */

import { $, $$, esc, escA, TYPE_L } from './utils.js';
import { S, refs, CITY_DEFAULTS, POPULAR_AREAS_BY_CITY, NL_EXAMPLES } from './state.js';
import { trackFilterChange } from './analytics.js';

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
  if (S.priceMin || S.priceMax) n++; if (S.sizeMarlaMin || S.sizeMarlaMax) n++;
  if (S.furnished) n++; if (S.sort) n++;
  return n;
}

// ===== Property size: city-aware units =====
// Size is stored canonically in MARLA (S.sizeMarlaMin/Max) and always sent to the
// API as marla. The unit is a display-only preference — Marla for Lahore/Islamabad,
// Square Yards for Karachi — switchable per the user. 1 Marla = 25 Sq Yd, matching
// the backend's area_size conversion.
const SQYD_PER_MARLA = 25;

export function cityDefaultSizeUnit(city = S.city) {
  return city === 'karachi' ? 'sqyd' : 'marla';
}
function currentSizeUnit() {
  return S.sizeUnit || cityDefaultSizeUnit();
}
function marlaToUnit(marla, unit) {
  const v = Number(marla);
  return unit === 'sqyd' ? Math.round(v * SQYD_PER_MARLA) : v;
}
function unitToMarla(val, unit) {
  if (val === '' || val == null) return '';
  const v = Number(val);
  if (!Number.isFinite(v)) return '';
  return String(unit === 'sqyd' ? v / SQYD_PER_MARLA : v);
}

// Preset buckets per unit. min/max are CANONICAL MARLA (so search params and chip
// matching stay unit-agnostic); the label is shown in the unit.
const SIZE_PRESETS = {
  // Max-only buckets use min:'' (not '0') — a sent size_marla_min=0 is an ACTIVE
  // backend filter (gate is `if size_marla_min:`), which would drop NULL/unparseable
  // sizes; '' means "no lower bound" and is omitted from the query.
  marla: [
    { min: '',   max: '5',  label: '≤ 5 Marla' },
    { min: '5',  max: '10', label: '5–10 Marla' },
    { min: '10', max: '20', label: '10–20 Marla' },
    { min: '20', max: '',   label: '1 Kanal+' },
  ],
  sqyd: [
    { min: '',    max: '4.8', label: '≤ 120 sq yd' },
    { min: '4.8', max: '9.6', label: '120–240 sq yd' },
    { min: '9.6', max: '20',  label: '240–500 sq yd' },
    { min: '20',  max: '',    label: '500+ sq yd' },
  ],
};

function _fmtSizeBound(marla, unit) {
  if (unit === 'sqyd') return `${marlaToUnit(marla, 'sqyd')} sq yd`;
  const v = Number(marla);
  return (v >= 20 && v % 20 === 0) ? `${v / 20} Kanal` : `${v} Marla`;
}

// Human label for a canonical marla range, rendered in the current display unit.
export function sizeChipLabel(min, max, unit = currentSizeUnit()) {
  const mn = (min && Number(min) > 0) ? Number(min) : null;
  const mx = (max && Number(max) > 0) ? Number(max) : null;
  if (mn != null && mx != null) {
    return unit === 'sqyd'
      ? `${marlaToUnit(mn, 'sqyd')}–${marlaToUnit(mx, 'sqyd')} sq yd`
      : `${mn}–${mx} Marla`;
  }
  if (mx != null) return `≤ ${_fmtSizeBound(mx, unit)}`;
  if (mn != null) return unit === 'sqyd' ? `${marlaToUnit(mn, 'sqyd')}+ sq yd` : `${_fmtSizeBound(mn, unit)}+`;
  return '';
}

// (Re)render the size dropdown's unit toggle + preset chips for the active unit,
// then reflect the current selection. Call on init, city change, and unit switch.
export function renderSizeFilter() {
  const grid = $('#sizeGrid');
  if (!grid) return;
  const unit = currentSizeUnit();
  grid.innerHTML = SIZE_PRESETS[unit].map(p =>
    `<span class="chip" data-smin="${p.min}" data-smax="${p.max}">${p.label}</span>`
  ).join('') + '<span class="chip" data-custom="1">Custom</span>';
  $$('#sizeUnitToggle [data-unit]').forEach(b => {
    const on = b.dataset.unit === unit;
    b.classList.toggle('active', on);
    b.setAttribute('aria-pressed', String(on));
  });
  const hint = $('#sizeUnitHint');
  if (hint) hint.textContent = unit === 'sqyd' ? '1 Marla ≈ 25 sq yd' : '1 Kanal = 20 Marla';
  const unitLabel = unit === 'sqyd' ? 'Sq Yd' : 'Marla';
  if ($('#sizeMin')) $('#sizeMin').placeholder = `Min (${unitLabel})`;
  if ($('#sizeMax')) $('#sizeMax').placeholder = `Max (${unitLabel})`;
  syncSizeChips();
}

export function syncSizeChips() {
  const unit = currentSizeUnit();
  let matched = false;
  $$('#sizeGrid .chip').forEach(c => {
    if (c.dataset.custom) return;
    const m = (c.dataset.smin || '') === (S.sizeMarlaMin || '') && (c.dataset.smax || '') === (S.sizeMarlaMax || '');
    c.classList.toggle('active', m); if (m) matched = true;
  });
  const cc = $('#sizeGrid [data-custom="1"]');
  if (!cc) return;
  if (!matched && (S.sizeMarlaMin || S.sizeMarlaMax)) {
    cc.classList.add('active'); $('#customSize').classList.remove('hidden');
    $('#sizeMin').value = S.sizeMarlaMin ? marlaToUnit(S.sizeMarlaMin, unit) : '';
    $('#sizeMax').value = S.sizeMarlaMax ? marlaToUnit(S.sizeMarlaMax, unit) : '';
  } else {
    cc.classList.remove('active'); if (!matched) $('#customSize').classList.add('hidden');
  }
}

export function setSizeUnit(unit) {
  if (unit !== 'marla' && unit !== 'sqyd') return;
  S.sizeUnit = unit;
  renderSizeFilter();
  updateChips();
}

// #nlInput follows a clear-on-apply model: it represents the next NL query
// the user might type, not a record of what's currently filtered. Any action
// that submits a new search should clear it so it never lies about state.
function clearNlInput() {
  const el = $('#nlInput');
  if (el) el.value = '';
  $('#nlSuggestions')?.classList.add('hidden');
}

export function updateChips() {
  const hasActiveFilters = countFilters() > 0;
  setChipVal($('#areaChip'), S.area, 'Area');
  setChipVal($('#typeChip'), S.type ? TYPE_L[S.type] || S.type : '', 'Type');
  const bedLabel = S.beds
    ? (S.bedsMax && S.bedsMax !== S.beds ? S.beds + '-' + S.bedsMax + ' Bed' : S.beds + (S.beds === '5' ? '+' : '') + ' Bed')
    : '';
  setChipVal($('#bedsChip'), bedLabel, 'Beds');

  let pl = '';
  if (S.priceMin || S.priceMax) {
    const mn = S.priceMin ? (S.priceMin / 1e3 | 0) + 'K' : '';
    const mx = S.priceMax ? (S.priceMax / 1e3 | 0) + 'K' : '';
    pl = mn && mx ? mn + '-' + mx : mx ? '<' + mx : mn + '+';
  }
  setChipVal($('#priceChip'), pl, 'Price');

  setChipVal($('#sizeChip'), sizeChipLabel(S.sizeMarlaMin, S.sizeMarlaMax), 'Size');

  const mc = (S.furnished ? 1 : 0) + (S.sort ? 1 : 0);
  setChipVal($('#moreChip'), mc ? 'More (' + mc + ')' : '', 'More');

  $('#clearAllBtn').classList.toggle('hidden', !hasActiveFilters);
  $('#appHeader')?.classList.toggle('header-has-clear', hasActiveFilters);

  // Keep the "Understood:" chip row (if showing) consistent with filter changes.
  refs._refreshUnderstood?.();
}

// ===== DROPDOWNS =====

const ddMap = { area: 'dd-area', type: 'dd-type', beds: 'dd-beds', size: 'dd-size', price: 'dd-price', more: 'dd-more', radius: 'dd-radius' };

// Element to restore focus to when the active dropdown closes. Captured on
// open so Esc / click-outside / Apply all return keyboard users to the chip.
let _ddTrigger = null;

export function openDD(name) {
  if (refs.activeDD === name) { closeDD(); return; }
  // Switching dropdowns: skip focus restore on the previous trigger so it
  // doesn't briefly steal focus while we're opening the new one.
  closeDD({ restoreFocus: false });
  const el = $('#' + ddMap[name]);
  el.classList.add('open');
  refs.activeDD = name;
  _ddTrigger = $(`[data-filter="${name}"]`) || null;
  if (window.innerWidth < 1024) $('#ddBackdrop').classList.remove('hidden');

  // Position dropdown under its chip button (desktop only)
  if (window.innerWidth >= 1024) {
    const chip = _ddTrigger;
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

export function closeDD({ restoreFocus = true } = {}) {
  const wasOpen = refs.activeDD !== null;
  Object.values(ddMap).forEach(id => $('#' + id).classList.remove('open'));
  refs.activeDD = null;
  $('#ddBackdrop').classList.add('hidden');
  // Restore focus to the triggering chip on Esc / Apply / chip-select close.
  // Click-outside callers pass restoreFocus:false so focus follows the click.
  // Defer to the next tick so an in-flight Enter keypress can't fire a
  // synthetic click on the newly-focused chip and reopen the dropdown.
  if (wasOpen && restoreFocus && _ddTrigger && typeof _ddTrigger.focus === 'function') {
    const t = _ddTrigger;
    setTimeout(() => t.focus(), 0);
  }
  _ddTrigger = null;
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
  const cc = $('#priceGrid [data-custom="1"]');
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
  if (f === 'area') {
    S.area = '';
    $('#areaInput').value = '';
    $('#areaClear').classList.add('hidden');
    if (refs.searchMode !== 'nearby') resetMapView?.();
  }
  if (f === 'type') { S.type = ''; $$('#typeGrid .chip').forEach(c => c.classList.remove('active')); }
  if (f === 'beds') { S.beds = ''; S.bedsMax = ''; $$('#bedRow .chip').forEach(c => c.classList.toggle('active', c.dataset.beds === '')); }
  if (f === 'price') { S.priceMin = ''; S.priceMax = ''; $$('#priceGrid .chip').forEach(c => c.classList.remove('active')); $('#customPrice').classList.add('hidden'); $('#priceMin').value = ''; $('#priceMax').value = ''; }
  if (f === 'size') { S.sizeMarlaMin = ''; S.sizeMarlaMax = ''; $$('#sizeGrid .chip').forEach(c => c.classList.remove('active')); $('#customSize').classList.add('hidden'); $('#sizeMin').value = ''; $('#sizeMax').value = ''; }
  if (f === 'more') { S.furnished = false; S.sort = ''; setToggle(false); $('#sortSelect').value = ''; }
  clearNlInput();
  updateChips(); doSearch?.();
}

// ===== SELECT AREA =====

export function selectArea(name, fromMap, { highlightMarker, doSearch } = {}) {
  S.area = name;
  $('#areaInput').value = name;
  $('#areaClear').classList.remove('hidden');
  clearNlInput();
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

  // Click outside closes dropdown — don't yank focus back to the chip; let
  // it follow whatever the user actually clicked on.
  document.addEventListener('click', e => {
    if (!e.target.closest('.filter-dd') && !e.target.closest('[data-filter]')) {
      closeDD({ restoreFocus: false });
    }
  });
  // Mobile backdrop is a deliberate dismiss gesture, more like Esc — restore.
  $('#ddBackdrop').addEventListener('click', () => closeDD());

  // Clear All
  $('#clearAllBtn').addEventListener('click', () => {
    S.area = ''; S.type = ''; S.beds = ''; S.bedsMax = ''; S.priceMin = ''; S.priceMax = ''; S.furnished = false; S.sort = '';
    S.sizeMarlaMin = ''; S.sizeMarlaMax = '';
    $('#areaInput').value = ''; $('#areaClear').classList.add('hidden');
    $$('#typeGrid .chip').forEach(c => c.classList.remove('active'));
    $$('#bedRow .chip').forEach(c => c.classList.toggle('active', c.dataset.beds === ''));
    $$('#priceGrid .chip').forEach(c => c.classList.remove('active'));
    $('#customPrice').classList.add('hidden'); $('#priceMin').value = ''; $('#priceMax').value = '';
    $$('#sizeGrid .chip').forEach(c => c.classList.remove('active'));
    $('#customSize').classList.add('hidden'); $('#sizeMin').value = ''; $('#sizeMax').value = '';
    setToggle(false); $('#sortSelect').value = '';
    $$('#presetRow .chip').forEach(c => c.classList.remove('active'));
    clearNlInput();
    updateChips();
    if (refs.searchMode !== 'nearby') resetMapView();
    doSearch();
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
    if (refs.searchMode !== 'nearby') {
      refs.searchMode = 'city';
    }
    refs.mapAreaTotals = {};
    refs.viewportAreaNames = [];
    refs.viewportRanking = 'default';
    refs.viewportScope = 'area_coverage';
    refs.viewportAttemptedExactBounds = false;
    refs.viewportExactBoundsTotal = null;
    refs.previewArea = null;
    refs.hoveredArea = null;
    if (refs.searchMode !== 'nearby') resetMapView();
    clearNlInput();
    updateChips(); renderAreaList(refs.allAreas.slice(0, 20)); doSearch();
  });

  // Type
  $('#typeGrid').addEventListener('click', e => {
    const c = e.target.closest('.chip'); if (!c) return;
    const prev = S.type;
    if (c.classList.contains('active')) { c.classList.remove('active'); S.type = ''; }
    else { $$('#typeGrid .chip').forEach(x => x.classList.remove('active')); c.classList.add('active'); S.type = c.dataset.type; }
    if (prev !== S.type) trackFilterChange({ filter: 'type', value: S.type, previousValue: prev, mode: refs.searchMode, city: S.city });
    clearNlInput();
    updateChips(); closeDD(); doSearch();
  });

  // Beds
  $('#bedRow').addEventListener('click', e => {
    const c = e.target.closest('.chip'); if (!c) return;
    const prev = S.beds;
    $$('#bedRow .chip').forEach(x => x.classList.remove('active'));
    c.classList.add('active'); S.beds = c.dataset.beds; S.bedsMax = '';
    if (prev !== S.beds) trackFilterChange({ filter: 'beds', value: S.beds, previousValue: prev, mode: refs.searchMode, city: S.city });
    clearNlInput();
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
    const prevPrice = `${S.priceMin}-${S.priceMax}`;
    if (c.classList.contains('active')) { c.classList.remove('active'); S.priceMin = ''; S.priceMax = ''; }
    else { $$('#priceGrid .chip').forEach(x => x.classList.remove('active')); c.classList.add('active'); S.priceMin = c.dataset.pmin; S.priceMax = c.dataset.pmax; }
    const newPrice = `${S.priceMin}-${S.priceMax}`;
    if (prevPrice !== newPrice) trackFilterChange({ filter: 'price', value: newPrice, previousValue: prevPrice, mode: refs.searchMode, city: S.city });
    clearNlInput();
    updateChips(); closeDD(); doSearch();
  });
  $('#priceMin').addEventListener('input', () => { S.priceMin = $('#priceMin').value; updateChips(); });
  $('#priceMax').addEventListener('input', () => { S.priceMax = $('#priceMax').value; updateChips(); });
  $$('#customPrice input').forEach(el => el.addEventListener('keydown', e => { if (e.key === 'Enter') { clearNlInput(); closeDD(); doSearch(); } }));
  $('#priceApply').addEventListener('click', () => { S.priceMin = $('#priceMin').value; S.priceMax = $('#priceMax').value; clearNlInput(); updateChips(); closeDD(); doSearch(); });

  // Size — presets are JS-rendered per unit (see renderSizeFilter); chips carry
  // canonical marla in data-smin/smax so this handler stays unit-agnostic.
  $('#sizeUnitToggle').addEventListener('click', e => {
    const b = e.target.closest('[data-unit]');
    if (b) setSizeUnit(b.dataset.unit);
  });
  $('#sizeGrid').addEventListener('click', e => {
    const c = e.target.closest('.chip'); if (!c) return;
    if (c.dataset.custom) {
      $$('#sizeGrid .chip').forEach(x => x.classList.remove('active'));
      c.classList.add('active'); $('#customSize').classList.remove('hidden');
      S.sizeMarlaMin = unitToMarla($('#sizeMin').value, currentSizeUnit());
      S.sizeMarlaMax = unitToMarla($('#sizeMax').value, currentSizeUnit());
      updateChips(); return;
    }
    $('#customSize').classList.add('hidden');
    const prevSize = `${S.sizeMarlaMin}-${S.sizeMarlaMax}`;
    if (c.classList.contains('active')) { c.classList.remove('active'); S.sizeMarlaMin = ''; S.sizeMarlaMax = ''; }
    else { $$('#sizeGrid .chip').forEach(x => x.classList.remove('active')); c.classList.add('active'); S.sizeMarlaMin = c.dataset.smin; S.sizeMarlaMax = c.dataset.smax; }
    const newSize = `${S.sizeMarlaMin}-${S.sizeMarlaMax}`;
    if (prevSize !== newSize) trackFilterChange({ filter: 'size', value: newSize, previousValue: prevSize, mode: refs.searchMode, city: S.city });
    clearNlInput();
    updateChips(); closeDD(); doSearch();
  });
  $('#sizeMin').addEventListener('input', () => { S.sizeMarlaMin = unitToMarla($('#sizeMin').value, currentSizeUnit()); updateChips(); });
  $('#sizeMax').addEventListener('input', () => { S.sizeMarlaMax = unitToMarla($('#sizeMax').value, currentSizeUnit()); updateChips(); });
  $$('#customSize input').forEach(el => el.addEventListener('keydown', e => { if (e.key === 'Enter') { clearNlInput(); closeDD(); doSearch(); } }));
  $('#sizeApply').addEventListener('click', () => { S.sizeMarlaMin = unitToMarla($('#sizeMin').value, currentSizeUnit()); S.sizeMarlaMax = unitToMarla($('#sizeMax').value, currentSizeUnit()); clearNlInput(); updateChips(); closeDD(); doSearch(); });

  // Furnished
  $('#furnishedToggle').addEventListener('click', () => {
    const prev = S.furnished;
    setToggle(!S.furnished);
    trackFilterChange({ filter: 'furnished', value: String(S.furnished), previousValue: String(prev), mode: refs.searchMode, city: S.city });
    clearNlInput();
    updateChips(); doSearch();
  });

  // Sort
  $('#sortSelect').addEventListener('change', () => {
    const prev = S.sort;
    S.sort = $('#sortSelect').value;
    if (prev !== S.sort) trackFilterChange({ filter: 'sort', value: S.sort, previousValue: prev, mode: refs.searchMode, city: S.city });
    clearNlInput();
    updateChips(); closeDD(); doSearch();
  });

  // Presets
  $('#presetRow').addEventListener('click', e => {
    const c = e.target.closest('.chip'); if (!c) return;
    $$('#presetRow .chip').forEach(x => x.classList.remove('active'));
    c.classList.add('active');
    S.type = c.dataset.type || ''; S.beds = c.dataset.beds || ''; S.bedsMax = ''; S.priceMin = c.dataset.pmin || ''; S.priceMax = c.dataset.pmax || '';
    S.sizeMarlaMin = ''; S.sizeMarlaMax = '';
    $$('#typeGrid .chip').forEach(x => x.classList.toggle('active', x.dataset.type === S.type));
    $$('#bedRow .chip').forEach(x => x.classList.toggle('active', x.dataset.beds === S.beds));
    syncPriceChips();
    syncSizeChips();
    clearNlInput();
    updateChips(); closeDD(); doSearch();
  });

  // Escape closes dropdown
  document.addEventListener('keydown', e => { if (e.key === 'Escape') closeDD(); });
}
