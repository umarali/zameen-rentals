/** Compare: pick up to 4 listings and view them side-by-side.
 *
 *  Stored client-side in localStorage as a list of { zameen_id, snapshot }
 *  so the tray + comparison view work even when the underlying search has
 *  moved on. Tracked separately from favorites/hidden so users can compare
 *  cards they haven't yet decided to save.
 */

import { $, $$, esc, escA, fmtPrice, fmtRelative, showToast } from './utils.js';

const STORE_KEY = 'zr_compare_v1';
const MAX_ITEMS = 4;

const subscribers = new Set();

function load() {
  try {
    const raw = localStorage.getItem(STORE_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    return Array.isArray(parsed) ? parsed.slice(0, MAX_ITEMS) : [];
  } catch { return []; }
}

function save(items) {
  try { localStorage.setItem(STORE_KEY, JSON.stringify(items.slice(0, MAX_ITEMS))); }
  catch { /* storage full — silently drop */ }
}

let _items = load();
let _trayEl = null;
let _modalEl = null;
let _modalBackdrop = null;
let _lastTrigger = null;

function emit() {
  for (const fn of subscribers) {
    try { fn(getItems()); } catch (err) { console.warn('compare listener error', err); }
  }
  renderTray();
}

export function subscribe(fn) {
  subscribers.add(fn);
  fn(getItems());
  return () => subscribers.delete(fn);
}

export function getItems() { return [..._items]; }
export function getIds() { return new Set(_items.map(i => String(i.zameen_id))); }
export function has(zameenId) { return getIds().has(String(zameenId)); }
export function count() { return _items.length; }
export function isFull() { return _items.length >= MAX_ITEMS; }

export function add(listing) {
  if (!listing) return false;
  const zid = String(listing.zameen_id || extractZid(listing.url));
  if (!zid) return false;
  if (has(zid)) {
    showToast('Already in compare', { tone: 'default' });
    return false;
  }
  if (isFull()) {
    showToast(`You can compare up to ${MAX_ITEMS} listings at a time.`, { tone: 'error' });
    return false;
  }
  _items.push(snapshotListing(listing, zid));
  save(_items);
  emit();
  return true;
}

export function remove(zameenId) {
  const zid = String(zameenId);
  const before = _items.length;
  _items = _items.filter(i => String(i.zameen_id) !== zid);
  if (_items.length === before) return false;
  save(_items);
  emit();
  return true;
}

export function toggle(listing) {
  const zid = String(listing?.zameen_id || extractZid(listing?.url));
  if (!zid) return false;
  if (has(zid)) { remove(zid); return false; }
  return add(listing);
}

export function clearAll() {
  _items = [];
  save(_items);
  emit();
}

function extractZid(url) {
  if (!url) return '';
  const m = url.match(/-(\d{5,10})-\d+-\d+\.html?(?:$|\?|#)/);
  return m ? m[1] : '';
}

function snapshotListing(item, zid) {
  return {
    zameen_id: zid,
    url: item.url || '',
    title: item.title || '',
    price: item.price || null,
    price_text: item.price_text || '',
    bedrooms: item.bedrooms || null,
    bathrooms: item.bathrooms || null,
    area_size: item.area_size || '',
    location: item.location || '',
    image_url: item.image_url || '',
    images: Array.isArray(item.images) ? item.images.slice(0, 3) : [],
    property_type: item.property_type || '',
    posted_at: item.posted_at || item.first_seen_at || null,
    added: item.added || '',
    distance_km: item.distance_km || null,
    latitude: item.latitude || null,
    longitude: item.longitude || null,
    saved_at: new Date().toISOString(),
  };
}

// ── Tray ────────────────────────────────────────────────────────────────────

function ensureTrayDom() {
  if (_trayEl) return _trayEl;
  const el = document.createElement('div');
  el.className = 'compare-tray hidden';
  el.id = 'compareTray';
  el.setAttribute('role', 'region');
  el.setAttribute('aria-label', 'Compare listings tray');
  document.body.appendChild(el);
  _trayEl = el;
  return el;
}

function renderTray() {
  const el = ensureTrayDom();
  if (!_items.length) {
    el.classList.add('hidden');
    el.innerHTML = '';
    return;
  }
  const thumbs = [];
  for (let i = 0; i < MAX_ITEMS; i++) {
    const item = _items[i];
    if (item) {
      const bg = item.image_url ? `style="background-image: url('${escA(item.image_url)}')"` : '';
      thumbs.push(`<div class="compare-thumb" ${bg} title="${escA(item.title || 'Listing')}" data-compare-thumb="${escA(item.zameen_id)}">
        <button class="compare-thumb-remove" data-compare-remove="${escA(item.zameen_id)}" aria-label="Remove from compare">×</button>
      </div>`);
    } else {
      thumbs.push('<div class="compare-thumb compare-thumb-empty" aria-hidden="true"></div>');
    }
  }
  const canCompare = _items.length >= 2;
  el.innerHTML = `
    <button class="compare-tray-close" data-compare-close aria-label="Clear compare list">×</button>
    <div class="compare-tray-thumbs">${thumbs.join('')}</div>
    <button class="compare-tray-btn" data-compare-open ${canCompare ? '' : 'disabled'} title="${canCompare ? 'Compare selected listings' : 'Add at least 2 listings to compare'}">
      Compare ${_items.length}/${MAX_ITEMS}
    </button>
  `;
  el.classList.remove('hidden');

  el.querySelector('[data-compare-close]').addEventListener('click', () => clearAll());
  el.querySelector('[data-compare-open]').addEventListener('click', () => openModal());
  el.querySelectorAll('[data-compare-remove]').forEach(btn => {
    btn.addEventListener('click', e => {
      e.stopPropagation();
      remove(btn.dataset.compareRemove);
    });
  });
  el.querySelectorAll('[data-compare-thumb]').forEach(btn => {
    btn.addEventListener('click', e => {
      if (e.target.matches('[data-compare-remove]')) return;
      const zid = btn.dataset.compareThumb;
      const item = _items.find(i => String(i.zameen_id) === zid);
      if (item?.url) window.open(item.url, '_blank', 'noopener');
    });
  });
}

// ── Comparison modal ────────────────────────────────────────────────────────

export function openModal() {
  if (_items.length < 1) return;
  closeModal();
  const active = document.activeElement;
  if (active && active !== document.body) _lastTrigger = active;

  _modalBackdrop = document.createElement('div');
  _modalBackdrop.className = 'compare-modal-backdrop';
  _modalBackdrop.addEventListener('click', closeModal);

  _modalEl = document.createElement('div');
  _modalEl.className = 'compare-modal';
  _modalEl.setAttribute('role', 'dialog');
  _modalEl.setAttribute('aria-modal', 'true');
  _modalEl.setAttribute('aria-labelledby', 'compareModalTitle');

  const cols = _items.map((item, idx) => renderCol(item, idx, _items)).join('');
  const gridClass = _items.length >= 4 ? 'compare-grid-4' : _items.length === 3 ? 'compare-grid-3' : 'compare-grid-2';

  _modalEl.innerHTML = `
    <div class="compare-modal-header">
      <h2 id="compareModalTitle" class="text-lg font-bold text-gray-800">Compare listings (${_items.length})</h2>
      <div class="flex items-center gap-2">
        <button id="compareClearBtn" class="text-sm text-gray-500 hover:text-rose-600">Clear all</button>
        <button id="compareCloseBtn" class="w-8 h-8 rounded-full hover:bg-gray-100 flex items-center justify-center text-gray-400 hover:text-gray-700 text-xl" aria-label="Close">&times;</button>
      </div>
    </div>
    <div class="compare-modal-body">
      <div class="compare-grid ${gridClass}">${cols}</div>
    </div>
  `;
  document.body.appendChild(_modalBackdrop);
  document.body.appendChild(_modalEl);
  document.body.style.overflow = 'hidden';

  _modalEl.querySelector('#compareCloseBtn').addEventListener('click', closeModal);
  _modalEl.querySelector('#compareClearBtn').addEventListener('click', () => { clearAll(); closeModal(); });
  _modalEl.querySelectorAll('[data-compare-col-remove]').forEach(btn => {
    btn.addEventListener('click', () => {
      remove(btn.dataset.compareColRemove);
      if (_items.length === 0) closeModal();
      else openModal();
    });
  });
  document.addEventListener('keydown', _onEsc);
}

function _onEsc(e) {
  if (e.key === 'Escape') closeModal();
}

export function closeModal() {
  document.removeEventListener('keydown', _onEsc);
  if (_modalEl) { _modalEl.remove(); _modalEl = null; }
  if (_modalBackdrop) { _modalBackdrop.remove(); _modalBackdrop = null; }
  document.body.style.overflow = '';
  if (_lastTrigger && typeof _lastTrigger.focus === 'function') _lastTrigger.focus();
  _lastTrigger = null;
}

function renderCol(item, idx, allItems) {
  const img = item.image_url
    ? `<img src="${escA(item.image_url)}" alt="" loading="lazy">`
    : `<div class="flex items-center justify-center h-full text-4xl text-gray-300">&#x1f3e0;</div>`;

  const rows = buildComparisonRows(item, allItems);
  return `
    <div class="compare-col">
      <div class="compare-col-image">
        ${img}
        <button class="compare-col-remove" data-compare-col-remove="${escA(item.zameen_id)}" aria-label="Remove from compare">&times;</button>
      </div>
      <div class="compare-col-body">
        <div class="text-base font-bold text-gray-900">${esc(fmtPrice(item.price, item.price_text))}</div>
        <div class="text-xs text-gray-500 line-clamp-2">${esc(item.title || 'Rental property')}</div>
        ${item.location ? `<div class="text-[11px] text-gray-400 line-clamp-1">${esc(item.location)}</div>` : ''}
        <div class="mt-1 space-y-1.5">
          ${rows}
        </div>
        ${item.url ? `<div class="mt-2 flex gap-2"><a href="${escA(item.url)}" target="_blank" rel="noopener" class="text-xs font-semibold text-brand-600 hover:text-brand-700">Open on Zameen.com →</a></div>` : ''}
      </div>
    </div>
  `;
}

function buildComparisonRows(item, allItems) {
  // For numerical fields, highlight the row when this column has the BEST value.
  const rows = [];
  const priceVals = allItems.map(i => Number(i.price)).filter(Number.isFinite);
  const bedroomVals = allItems.map(i => Number(i.bedrooms)).filter(Number.isFinite);
  const bathroomVals = allItems.map(i => Number(i.bathrooms)).filter(Number.isFinite);

  rows.push(comparisonRow('Bedrooms', item.bedrooms || '—',
    Number.isFinite(Number(item.bedrooms)) && bedroomVals.length > 1 && Number(item.bedrooms) === Math.max(...bedroomVals)));
  rows.push(comparisonRow('Bathrooms', item.bathrooms || '—',
    Number.isFinite(Number(item.bathrooms)) && bathroomVals.length > 1 && Number(item.bathrooms) === Math.max(...bathroomVals)));
  rows.push(comparisonRow('Size', item.area_size || '—', false));
  rows.push(comparisonRow('Type', item.property_type || '—', false));
  rows.push(comparisonRow('Price',
    item.price ? `Rs ${Number(item.price).toLocaleString()}` : (item.price_text || '—'),
    Number.isFinite(Number(item.price)) && priceVals.length > 1 && Number(item.price) === Math.min(...priceVals)
  ));
  if (item.distance_km != null && Number.isFinite(Number(item.distance_km))) {
    const distanceVals = allItems.map(i => Number(i.distance_km)).filter(Number.isFinite);
    rows.push(comparisonRow('Distance', `${Number(item.distance_km).toFixed(1)} km`,
      distanceVals.length > 1 && Number(item.distance_km) === Math.min(...distanceVals)));
  }
  if (item.posted_at) {
    rows.push(comparisonRow('Posted', fmtRelative(item.posted_at) || '—', false));
  }
  return rows.join('');
}

function comparisonRow(label, value, highlight) {
  const cls = highlight ? 'compare-row-value compare-row-highlight' : 'compare-row-value';
  return `<div class="compare-row"><span class="compare-row-label">${esc(label)}</span><span class="${cls}">${esc(value)}</span></div>`;
}

export function init() {
  ensureTrayDom();
  renderTray();
}
