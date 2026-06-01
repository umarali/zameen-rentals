/** Compare: pick up to 4 listings and view them side-by-side.
 *
 *  Stored client-side in localStorage as a list of { zameen_id, snapshot }
 *  so the tray + comparison view work even when the underlying search has
 *  moved on. Tracked separately from favorites/hidden so users can compare
 *  cards they haven't yet decided to save.
 */

import { $, $$, esc, escA, fmtPrice, fmtRelative, showToast } from './utils.js';
import { eyeIcon, callIcon, whatsappIcon, favFilledIcon, favHollowIcon, imageIcon } from './icons.js';

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
let _hooks = {};

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
    first_seen_at: item.first_seen_at || null,
    added: item.added || '',
    distance_km: item.distance_km || null,
    latitude: item.latitude || null,
    longitude: item.longitude || null,
    call_phone: item.call_phone || item.phone || '',
    whatsapp_phone: item.whatsapp_phone || '',
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

// ── Derived metrics ──────────────────────────────────────────────────────────

/** Convert a Zameen area_size string to Marla. Mirrors the backend SQL CASE in
 *  db_listings.py (1 Marla = 225 sqft = 25 Sq.Yd; 1 Kanal = 20 Marla). Returns
 *  null when the unit can't be parsed — callers must never guess a value. */
export function parseAreaToMarla(areaSize) {
  if (!areaSize) return null;
  const s = String(areaSize).trim().toLowerCase().replace(/,/g, '');
  const m = s.match(/([\d.]+)\s*(kanal|marla|sq\.?\s*yd\.?|sq\.?\s*ft\.?|sqft|sqyd|square\s*feet|square\s*yards?)?/);
  if (!m) return null;
  const num = parseFloat(m[1]);
  if (!Number.isFinite(num) || num <= 0) return null;
  const unit = (m[2] || 'marla').replace(/\./g, '').replace(/\s+/g, '');
  if (unit.startsWith('kanal')) return num * 20;
  if (unit.startsWith('marla')) return num;
  if (unit.includes('yd') || unit.includes('squareyard')) return (num * 9) / 225; // Sq.Yd → sqft → marla
  if (unit.includes('ft') || unit.includes('squarefeet')) return num / 225;        // sqft → marla
  return num; // bare number → assume Marla (matches the '% Marla' default)
}

function deriveMetrics(item) {
  const price = Number(item.price);
  const beds = Number(item.bedrooms);
  const sizeMarla = parseAreaToMarla(item.area_size);
  const iso = item.posted_at || item.first_seen_at || '';
  return {
    price,
    sizeMarla,
    rsPerMarla: Number.isFinite(price) && sizeMarla ? price / sizeMarla : null,
    rsPerBed: Number.isFinite(price) && beds > 0 ? price / beds : null,
    postedTs: iso ? Date.parse(iso) : NaN,
    postedIso: iso,
    hasContact: Boolean(item.call_phone || item.whatsapp_phone),
  };
}

function fmtRsCompact(v) {
  if (!Number.isFinite(v)) return '—';
  return fmtPrice(Math.round(v));
}

function sizeLabel(areaSize, marla) {
  if (!areaSize) return '—';
  // Return RAW text — the caller (row) escapes once. Annotate non-Marla units
  // with an approximate Marla figure so sizes are comparable at a glance.
  if (marla && !/marla/i.test(areaSize)) {
    const m = marla < 10 ? marla.toFixed(1) : String(Math.round(marla));
    return `${areaSize} (≈${m} marla)`;
  }
  return String(areaSize);
}

function trimWords(str, n) {
  const words = String(str || '').trim().split(/\s+/);
  return words.length > n ? words.slice(0, n).join(' ') + '…' : words.join(' ');
}

// ── Comparison modal ─────────────────────────────────────────────────────────

let _diffOnly = false;

export function openModal() {
  if (_items.length < 1) return;
  closeModal();
  const active = document.activeElement;
  if (active && active !== document.body) _lastTrigger = active;

  _diffOnly = _items.length >= 3; // hide identical rows by default when crowded

  _modalBackdrop = document.createElement('div');
  _modalBackdrop.className = 'compare-modal-backdrop';
  _modalBackdrop.addEventListener('click', closeModal);

  _modalEl = document.createElement('div');
  _modalEl.className = 'compare-modal';
  _modalEl.setAttribute('role', 'dialog');
  _modalEl.setAttribute('aria-modal', 'true');
  _modalEl.setAttribute('aria-labelledby', 'compareModalTitle');
  _modalEl.innerHTML = buildModalInner();

  document.body.appendChild(_modalBackdrop);
  document.body.appendChild(_modalEl);
  document.body.style.overflow = 'hidden';

  wireModal();
  document.addEventListener('keydown', _onEsc);
  _modalEl.querySelector('#compareCloseBtn')?.focus();
}

function byId(zid) {
  return _items.find(i => String(i.zameen_id) === String(zid)) || null;
}

function buildModalInner() {
  const toggle = _items.length >= 2
    ? `<button class="compare-diff-toggle ${_diffOnly ? 'is-on' : ''}" data-compare-difftoggle role="switch" aria-checked="${_diffOnly}">
        <span class="compare-diff-dot"></span>Only differences
      </button>`
    : '';
  return `
    <div class="compare-modal-header">
      <h2 id="compareModalTitle" class="text-lg font-bold text-gray-800">Compare (${_items.length})</h2>
      <div class="flex items-center gap-2 sm:gap-3">
        ${toggle}
        <button id="compareClearBtn" class="text-sm text-gray-500 hover:text-rose-600">Clear all</button>
        <button id="compareCloseBtn" class="w-8 h-8 rounded-full hover:bg-gray-100 flex items-center justify-center text-gray-400 hover:text-gray-700 text-xl" aria-label="Close">&times;</button>
      </div>
    </div>
    <div class="compare-modal-body">
      ${buildVerdict()}
      <div class="compare-table-scroll">${renderTable()}</div>
    </div>
  `;
}

function buildVerdict() {
  if (_items.length < 2) return '';
  const metrics = _items.map(deriveMetrics);
  let bestIdx = -1, best = Infinity;
  metrics.forEach((mt, i) => { if (mt.rsPerMarla != null && mt.rsPerMarla < best) { best = mt.rsPerMarla; bestIdx = i; } });
  if (bestIdx < 0) return ''; // no listing has both a price and a parseable size
  const item = _items[bestIdx];
  const where = item.location || item.title || 'This listing';
  return `<div class="compare-verdict">
    <span class="compare-verdict-star">★</span>
    <span><strong>Best value:</strong> ${esc(trimWords(where, 6))} — ${esc(fmtRsCompact(best))}/marla</span>
  </div>`;
}

/** Pick the single winning column for a numeric series. Needs ≥2 comparable
 *  values and no tie for first place; otherwise nobody is crowned. */
function winnerIndex(values, dir) {
  const valid = values.map((v, i) => ({ v: Number(v), i })).filter(o => Number.isFinite(o.v));
  if (valid.length < 2) return -1;
  let best = valid[0];
  for (const o of valid) { if (dir === 'min' ? o.v < best.v : o.v > best.v) best = o; }
  const ties = valid.filter(o => o.v === best.v).length;
  return ties > 1 ? -1 : best.i;
}

function row(label, values, winIdx = -1, badge = '') {
  const norm = values.map(v => String(v));
  const same = norm.length > 1 && norm.every(v => v === norm[0]) && norm[0] !== '—';
  const tds = values.map((v, i) => {
    const win = i === winIdx;
    const badgeHtml = win && badge ? `<span class="compare-badge">${esc(badge)}</span>` : '';
    return `<td class="compare-cell${win ? ' compare-cell--win' : ''}">${esc(String(v))}${badgeHtml}</td>`;
  }).join('');
  const samePill = same ? '<span class="compare-same-pill">Same</span>' : '';
  return { same, html: `<tr class="compare-row" data-same="${same}"><th class="compare-rlabel">${esc(label)}${samePill}</th>${tds}</tr>` };
}

function renderTable() {
  const items = _items;
  const metrics = items.map(deriveMetrics);

  const rsMarla = metrics.map(m => m.rsPerMarla);
  const rsBed = metrics.map(m => m.rsPerBed);
  const prices = items.map(i => Number(i.price));
  const dists = items.map(i => Number(i.distance_km));
  const posted = metrics.map(m => m.postedTs);
  const hasDist = dists.some(Number.isFinite);

  const winMarla = winnerIndex(rsMarla, 'min');
  const winBed = winnerIndex(rsBed, 'min');
  const winPrice = winnerIndex(prices, 'min');
  const winDist = winnerIndex(dists, 'min');
  const winPosted = winnerIndex(posted, 'max');

  const sections = [];
  sections.push({ label: 'Value', rows: [
    row('Rs / marla', items.map((it, i) => fmtRsCompact(rsMarla[i])), winMarla, 'Best value'),
    row('Rs / bedroom', items.map((it, i) => fmtRsCompact(rsBed[i])), winBed, 'Per room'),
    row('Price', items.map(it => fmtPrice(it.price, it.price_text)), winPrice, 'Lowest'),
  ] });
  sections.push({ label: 'Space', rows: [
    row('Bedrooms', items.map(it => it.bedrooms || '—')),
    row('Bathrooms', items.map(it => it.bathrooms || '—')),
    row('Size', items.map((it, i) => sizeLabel(it.area_size, metrics[i].sizeMarla))),
    row('Type', items.map(it => it.property_type || '—')),
  ] });
  const locRows = [row('Area', items.map(it => it.location ? trimWords(it.location, 8) : '—'))];
  if (hasDist) {
    locRows.push(row('Distance', items.map(it => Number.isFinite(Number(it.distance_km)) ? `${Number(it.distance_km).toFixed(1)} km` : '—'), winDist, 'Closest'));
  }
  sections.push({ label: 'Location', rows: locRows });
  sections.push({ label: 'Freshness', rows: [
    row('Posted', items.map((it, i) => Number.isFinite(posted[i]) ? (fmtRelative(metrics[i].postedIso) || '—') : '—'), winPosted, 'Newest'),
  ] });
  sections.push({ label: 'Contact', rows: [
    row('Phone / WhatsApp', items.map(it => (it.call_phone || it.whatsapp_phone) ? 'Available' : 'Not yet')),
  ] });

  let body = '';
  for (const sec of sections) {
    const allSame = sec.rows.every(r => r.same);
    body += `<tr class="compare-section" data-allsame="${allSame}"><th colspan="${items.length + 1}">${esc(sec.label)}</th></tr>`;
    body += sec.rows.map(r => r.html).join('');
  }
  const heads = items.map((it, idx) => headerCell(it, idx)).join('');
  return `<table class="compare-table${_diffOnly ? ' diff-only' : ''}">
    <thead><tr><th class="compare-corner"></th>${heads}</tr></thead>
    <tbody>${body}</tbody>
  </table>`;
}

function headerCell(item) {
  const zid = escA(String(item.zameen_id));
  const img = item.image_url
    ? `<span class="compare-hthumb" style="background-image:url('${escA(item.image_url)}')"></span>`
    : `<span class="compare-hthumb compare-hthumb-empty">${imageIcon('w-7 h-7')}</span>`;
  const fav = Boolean(_hooks.isFavorite && _hooks.isFavorite(item.zameen_id));
  return `<th class="compare-hcell">
    <button class="compare-col-remove" data-compare-col-remove="${zid}" aria-label="Remove from compare">&times;</button>
    ${img}
    <span class="compare-hprice">${esc(fmtPrice(item.price, item.price_text))}</span>
    <span class="compare-hloc">${esc(trimWords(item.location || item.title || '', 6))}</span>
    <span class="compare-hactions">
      <button class="compare-act" data-compare-open="${zid}" title="View details" aria-label="View details">${eyeIcon()}</button>
      <button class="compare-act compare-act-fav${fav ? ' is-fav' : ''}" data-compare-fav="${zid}" title="${fav ? 'Saved' : 'Save'}" aria-label="${fav ? 'Remove from favorites' : 'Save to favorites'}" aria-pressed="${fav}">${fav ? favFilledIcon() : favHollowIcon()}</button>
      <button class="compare-act" data-compare-call="${zid}" title="Call" aria-label="Call">${callIcon()}</button>
      <button class="compare-act compare-act-wa" data-compare-wa="${zid}" title="WhatsApp" aria-label="WhatsApp">${whatsappIcon()}</button>
    </span>
  </th>`;
}

function wireModal() {
  if (!_modalEl) return;
  _modalEl.querySelector('#compareCloseBtn')?.addEventListener('click', closeModal);
  _modalEl.querySelector('#compareClearBtn')?.addEventListener('click', () => { clearAll(); closeModal(); });

  const diffBtn = _modalEl.querySelector('[data-compare-difftoggle]');
  diffBtn?.addEventListener('click', () => {
    _diffOnly = !_diffOnly;
    const table = _modalEl.querySelector('.compare-table');
    if (table) table.classList.toggle('diff-only', _diffOnly);
    diffBtn.classList.toggle('is-on', _diffOnly);
    diffBtn.setAttribute('aria-checked', String(_diffOnly));
  });

  _modalEl.querySelectorAll('[data-compare-col-remove]').forEach(btn => {
    btn.addEventListener('click', () => {
      remove(btn.dataset.compareColRemove);
      if (_items.length === 0) closeModal();
      else rerender();
    });
  });

  _modalEl.querySelectorAll('[data-compare-open]').forEach(btn => {
    btn.addEventListener('click', () => {
      const item = byId(btn.dataset.compareOpen);
      if (!item) return;
      closeModal();
      _hooks.onOpenDrawer?.(item);
    });
  });

  _modalEl.querySelectorAll('[data-compare-fav]').forEach(btn => {
    btn.addEventListener('click', async () => {
      const zid = btn.dataset.compareFav;
      if (!_hooks.onFavorite) return;
      const nowFav = await _hooks.onFavorite(zid);
      btn.classList.toggle('is-fav', !!nowFav);
      btn.setAttribute('aria-pressed', String(!!nowFav));
      btn.title = nowFav ? 'Saved' : 'Save';
      btn.setAttribute('aria-label', nowFav ? 'Remove from favorites' : 'Save to favorites');
      btn.innerHTML = nowFav ? favFilledIcon() : favHollowIcon();
    });
  });

  const contact = (action, zid) => {
    const item = byId(zid);
    if (!item?.url) return;
    _hooks.onContact?.(action, item.url, { callPhone: item.call_phone, whatsappPhone: item.whatsapp_phone });
  };
  _modalEl.querySelectorAll('[data-compare-call]').forEach(btn =>
    btn.addEventListener('click', () => contact('call', btn.dataset.compareCall)));
  _modalEl.querySelectorAll('[data-compare-wa]').forEach(btn =>
    btn.addEventListener('click', () => contact('whatsapp', btn.dataset.compareWa)));
}

/** Rebuild the modal contents in place, preserving scroll — used after a
 *  column is removed so the dialog never tears down and loses position. */
function rerender() {
  if (!_modalEl) return;
  const scroller = _modalEl.querySelector('.compare-table-scroll');
  const sl = scroller ? scroller.scrollLeft : 0;
  const bodyEl = _modalEl.querySelector('.compare-modal-body');
  const st = bodyEl ? bodyEl.scrollTop : 0;
  _modalEl.innerHTML = buildModalInner();
  wireModal();
  const s2 = _modalEl.querySelector('.compare-table-scroll'); if (s2) s2.scrollLeft = sl;
  const b2 = _modalEl.querySelector('.compare-modal-body'); if (b2) b2.scrollTop = st;
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

export function init(hooks = {}) {
  _hooks = hooks || {};
  ensureTrayDom();
  renderTray();
}
