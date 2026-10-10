/** Every matching rental on the map: fetched once per city and filter set, clustered in the browser. */

import L from 'leaflet';
import Supercluster from 'supercluster';
import { esc, escA, fmtPrice } from './utils.js';
import { refs } from './state.js';
import { isFavorite, isHidden } from './personalization.js';
import { trackMapMarkerClick } from './analytics.js';
import { bedIcon, bathIcon, areaIcon } from './icons.js';

const CLUSTER_RADIUS = 90;
// Past this zoom everything shows as its own pin or stack.
const CLUSTER_MAX_ZOOM = 14;
const PIN_Z = 600;
const ACTIVE_PIN_Z = 2000;
const VIEWED_STORAGE_KEY = 'rk_viewedListings';
const VIEWED_MAX = 400;
// From this many listings on one point (unless they are all flats) the point is
// almost always a block or society's default pin, so it is marked approximate.
const APPROX_STACK_MIN = 5;

let index = null;
let features = [];
let stackCoords = new Map(); // coordKey -> 'building' | 'block'
let pinsKey = '';
let pinsController = null;
let handlers = {};
let selectedId = null;
let hoveredId = null;
const summaries = new Map();
const renderState = new Map(); // map instance -> { layer, markers: Map<key, marker>, focus }
const loadListeners = new Set();
let viewed = loadViewed();

/** Compact price for a pin: 85K, 2.4L, 1.2Cr. */
export function shortPrice(price) {
  const p = Number(price);
  if (!p) return '—';
  const trim = n => n.toFixed(1).replace(/\.0$/, '');
  if (p >= 1e7) return `${trim(p / 1e7)}Cr`;
  if (p >= 1e5) return `${trim(p / 1e5)}L`;
  if (p >= 1e3) return `${Math.round(p / 1e3)}K`;
  return String(p);
}

function compactCount(n) {
  return n >= 1000 ? `${(n / 1000).toFixed(n >= 10000 ? 0 : 1).replace(/\.0$/, '')}k` : String(n);
}

/** The key the server uses to group listings that share one coordinate. */
export function coordKey(lat, lng) {
  return `${Number(lat).toFixed(5)},${Number(lng).toFixed(5)}`;
}

function loadViewed() {
  try { return new Set(JSON.parse(localStorage.getItem(VIEWED_STORAGE_KEY) || '[]')); } catch { return new Set(); }
}

/** Remember an opened listing so its pin shows as already seen. */
export function markListingViewed(zameenId) {
  if (!zameenId) return;
  const id = String(zameenId);
  viewed.delete(id);
  viewed.add(id);
  if (viewed.size > VIEWED_MAX) viewed = new Set([...viewed].slice(-VIEWED_MAX));
  try { localStorage.setItem(VIEWED_STORAGE_KEY, JSON.stringify([...viewed])); } catch {}
  refreshPinStates();
}

/** Handlers: onPinClick(id, map), onStackClick(stack, map). */
export function initMapPins(nextHandlers) {
  handlers = nextHandlers || {};
}

export function onPinsLoaded(fn) {
  loadListeners.add(fn);
  return () => loadListeners.delete(fn);
}

export function pinsReady() {
  return Boolean(index);
}

/** Fetch pins for this city and filter set unless they are already loaded. */
export async function loadMapPins(params) {
  const key = params.toString();
  if (key === pinsKey && index) return;
  pinsKey = key;
  pinsController?.abort();
  const controller = new AbortController();
  pinsController = controller;
  try {
    const resp = await fetch('/api/map-pins?' + key, { signal: controller.signal });
    if (!resp.ok) throw new Error(`map-pins ${resp.status}`);
    const data = await resp.json();
    if (controller.signal.aborted || pinsKey !== key) return;
    buildIndex(data);
  } catch (error) {
    if (error?.name === 'AbortError') return;
    // Keep whatever is drawn; the list still works without pins.
    if (pinsKey === key) pinsKey = '';
  } finally {
    if (pinsController === controller) pinsController = null;
  }
}

function buildIndex(data) {
  const types = data.types || [];
  features = [];
  (data.pins || []).forEach(([id, lat, lng, price, beds, typeIdx]) => {
    if (isHidden(id)) return;
    features.push({
      type: 'Feature',
      geometry: { type: 'Point', coordinates: [lng, lat] },
      properties: { k: 'p', id, price, beds, type: types[typeIdx] || '' },
    });
  });
  stackCoords = new Map();
  (data.stacks || []).forEach(([lat, lng, count, area, min, max, building]) => {
    stackCoords.set(coordKey(lat, lng), building ? 'building' : count >= APPROX_STACK_MIN ? 'block' : 'shared');
    features.push({
      type: 'Feature',
      geometry: { type: 'Point', coordinates: [lng, lat] },
      properties: { k: 's', n: count, area: area || '', min, max, building: Boolean(building), lat, lng },
    });
  });
  index = new Supercluster({
    radius: CLUSTER_RADIUS,
    maxZoom: CLUSTER_MAX_ZOOM,
    map: p => ({ n: p.k === 's' ? p.n : 1, min: p.k === 's' ? p.min : p.price }),
    reduce: (acc, p) => {
      acc.n += p.n;
      if (p.min && (!acc.min || p.min < acc.min)) acc.min = p.min;
    },
  });
  index.load(features);
  renderState.forEach((state, map) => {
    state.markers.forEach(marker => marker.remove());
    state.markers.clear();
    renderPins(map);
  });
  loadListeners.forEach(fn => fn());
}

/** 'building', 'block' (a block or society's default pin) or 'shared' when listings share this point, else null. */
export function sharedPinKind(lat, lng) {
  return stackCoords.get(coordKey(lat, lng)) || null;
}

/** Drop a listing the user just hid. */
export function removePin(zameenId) {
  const id = String(zameenId);
  const before = features.length;
  features = features.filter(f => f.properties.id !== id);
  if (features.length === before || !index) return;
  index.load(features);
  renderState.forEach((state, map) => renderPins(map));
}

/** Listings (not features) whose pins fall inside the bounds. */
export function countListingsInBounds(bounds) {
  if (!bounds) return 0;
  let total = 0;
  for (const f of features) {
    const [lng, lat] = f.geometry.coordinates;
    if (bounds.contains([lat, lng])) total += f.properties.k === 's' ? f.properties.n : 1;
  }
  return total;
}

function getState(map) {
  let state = renderState.get(map);
  if (!state) {
    state = { layer: L.layerGroup().addTo(map), markers: new Map(), focus: null };
    renderState.set(map, state);
    map.on('unload', () => renderState.delete(map));
  }
  return state;
}

function featureKey(f) {
  if (f.properties.cluster) return `c${f.id}`;
  if (f.properties.k === 's') return `s${coordKey(f.properties.lat, f.properties.lng)}`;
  return `p${f.properties.id}`;
}

function pinClasses(id) {
  return [
    'map-pin',
    id === selectedId ? 'is-selected' : '',
    id === hoveredId ? 'is-hovered' : '',
    viewed.has(id) ? 'is-viewed' : '',
    isFavorite(id) ? 'is-fav' : '',
  ].filter(Boolean).join(' ');
}

const HEART = '<svg class="map-pin-heart" viewBox="0 0 24 24" aria-hidden="true"><path fill="currentColor" d="M12 21s-7.5-4.6-9.6-9.2C.9 8.4 3 4.5 6.7 4.5c2.1 0 3.6 1.2 4.3 2.3h2c.7-1.1 2.2-2.3 4.3-2.3 3.7 0 5.8 3.9 4.3 7.3C19.5 16.4 12 21 12 21z"/></svg>';
const BUILDING = '<svg class="map-stack-icon" viewBox="0 0 24 24" aria-hidden="true"><path fill="none" stroke="currentColor" stroke-width="2" stroke-linejoin="round" d="M5 21V4h10v17M15 9h4v12M3 21h18M8 8h4M8 12h4M8 16h4"/></svg>';

function pinIcon(p) {
  return L.divIcon({
    className: 'map-pin-icon',
    html: `<span class="${pinClasses(p.id)}">${HEART}${esc(shortPrice(p.price))}</span>`,
    iconSize: [0, 0],
    iconAnchor: [0, 0],
  });
}

function stackIcon(p) {
  const label = p.area ? esc(p.area.length > 22 ? `${p.area.slice(0, 21)}…` : p.area) : '';
  return L.divIcon({
    className: 'map-pin-icon',
    html: `<span class="map-stack${p.building ? ' is-building' : ''}${isApproxStack(p) ? ' is-approx' : ''}">${p.building ? BUILDING : ''}<b>${compactCount(p.n)}</b>${label ? `<span class="map-stack-area">${label}</span>` : ''}</span>`,
    iconSize: [0, 0],
    iconAnchor: [0, 0],
  });
}

function isApproxStack(stack) {
  return !stack.building && (stack.n ?? stack.count) >= APPROX_STACK_MIN;
}

function clusterIcon(p) {
  const size = Math.round(30 + Math.min(Math.log10(p.n) * 7, 20));
  return L.divIcon({
    className: 'map-pin-icon',
    html: `<span class="map-cluster" style="width:${size}px;height:${size}px">${compactCount(p.n)}</span>`,
    iconSize: [0, 0],
    iconAnchor: [0, 0],
  });
}

function ariaLabel(f) {
  const p = f.properties;
  if (p.cluster) return `${p.n.toLocaleString()} rentals here${p.min ? `, from ${fmtPrice(p.min)}` : ''}. Zoom in`;
  if (p.k === 's') {
    return p.building
      ? `${p.n} flats in one building${p.area ? ` in ${p.area}` : ''}`
      : `${p.n} rentals at one map point${p.area ? ` in ${p.area}` : ''}`;
  }
  return [fmtPrice(p.price), p.beds ? `${p.beds} bed` : '', p.type].filter(Boolean).join(', ');
}

function createMarker(f, map) {
  const p = f.properties;
  const [lng, lat] = f.geometry.coordinates;
  const icon = p.cluster ? clusterIcon(p) : p.k === 's' ? stackIcon(p) : pinIcon(p);
  const isActive = p.k === 'p' && (p.id === selectedId || p.id === hoveredId);
  const marker = L.marker([lat, lng], {
    icon,
    keyboard: true,
    riseOnHover: true,
    zIndexOffset: isActive ? ACTIVE_PIN_Z : p.cluster ? 0 : PIN_Z,
  });
  marker._zr = p;
  marker.on('add', () => {
    const el = marker.getElement();
    if (!el) return;
    el.setAttribute('role', 'button');
    el.setAttribute('aria-label', ariaLabel(f));
  });
  marker.on('click', () => {
    if (p.cluster) {
      trackMapMarkerClick({ areaName: null, markerType: 'cluster', city: null, mode: refs.searchMode });
      const zoom = Math.min(index.getClusterExpansionZoom(f.id), map.getMaxZoom());
      map.flyTo([lat, lng], Math.max(zoom, map.getZoom() + 1), { animate: motionAllowed(), duration: 0.5 });
      return;
    }
    if (p.k === 's') {
      trackMapMarkerClick({ areaName: p.area || null, markerType: p.building ? 'building' : 'stack', city: null, mode: refs.searchMode });
      handlers.onStackClick?.({ lat: p.lat, lng: p.lng, count: p.n, area: p.area, min: p.min, max: p.max, building: p.building }, map);
      return;
    }
    trackMapMarkerClick({ areaName: null, markerType: 'listing', city: null, mode: refs.searchMode });
    handlers.onPinClick?.(p.id, map, [lat, lng]);
  });
  if (p.k === 'p') {
    marker.on('mouseover', () => {
      handlers.onPinHover?.(p.id, true);
      prefetchListingPhotos(p.id);
    });
    marker.on('mouseout', () => {
      handlers.onPinHover?.(p.id, false);
      cancelPhotoPrefetch();
    });
  }
  return marker;
}

export function motionAllowed() {
  try { return !window.matchMedia('(prefers-reduced-motion: reduce)').matches; } catch { return true; }
}

/** Draw clusters, pins and stacks for the visible part of one map. */
export function renderPins(map) {
  if (!map) return;
  const state = getState(map);
  if (!index) return;
  const bounds = map.getBounds().pad(0.2);
  const zoom = Math.round(map.getZoom());
  const visible = index.getClusters([bounds.getWest(), bounds.getSouth(), bounds.getEast(), bounds.getNorth()], zoom);
  const next = new Set();
  visible.forEach(f => {
    const key = featureKey(f);
    next.add(key);
    if (!state.markers.has(key)) {
      const marker = createMarker(f, map);
      marker.addTo(state.layer);
      state.markers.set(key, marker);
    }
  });
  state.markers.forEach((marker, key) => {
    if (!next.has(key)) {
      marker.remove();
      state.markers.delete(key);
    }
  });
  syncFocusMarker(map);
}

/** Re-apply selected / hovered / viewed / favourite styling without rebuilding. */
export function refreshPinStates() {
  renderState.forEach((state, map) => {
    state.markers.forEach(marker => {
      const p = marker._zr;
      if (!p || p.cluster || p.k !== 'p') return;
      marker.setIcon(pinIcon(p));
      marker.setZIndexOffset(p.id === selectedId || p.id === hoveredId ? ACTIVE_PIN_Z : PIN_Z);
    });
    syncFocusMarker(map);
  });
}

function syncFocusMarker(map) {
  const state = renderState.get(map);
  if (!state) return;
  const id = hoveredId || selectedId;
  const target = id ? (refs.currentResults.find(r => String(r.zameen_id) === id) || summaries.get(id)) : null;
  const drawnAlone = id && state.markers.has(`p${id}`);
  const lat = Number(target?.latitude);
  const lng = Number(target?.longitude);
  if (!id || drawnAlone || !Number.isFinite(lat) || !Number.isFinite(lng)) {
    state.focus?.remove();
    state.focus = null;
    return;
  }
  // The listing sits inside a cluster or a stack at this zoom: float its own
  // pin on top so the card you are looking at is always findable on the map.
  const icon = L.divIcon({
    className: 'map-pin-icon',
    html: `<span class="map-pin is-hovered is-focus">${esc(shortPrice(target.price))}</span>`,
    iconSize: [0, 0],
    iconAnchor: [0, 0],
  });
  if (!state.focus) {
    state.focus = L.marker([lat, lng], { icon, interactive: false, keyboard: false, zIndexOffset: ACTIVE_PIN_Z + 500 }).addTo(map);
  } else {
    state.focus.setLatLng([lat, lng]);
    state.focus.setIcon(icon);
  }
}

export function setHoveredListing(id) {
  const next = id ? String(id) : null;
  if (next === hoveredId) return;
  hoveredId = next;
  refreshPinStates();
}

export function setSelectedListing(id) {
  const next = id ? String(id) : null;
  if (next === selectedId) return;
  selectedId = next;
  refreshPinStates();
}

export function getSelectedListing() {
  return selectedId;
}

/** A listing in search-result shape: from the current list if present, else the API. */
export async function getListingSummary(id) {
  const key = String(id);
  const inList = refs.currentResults.find(r => String(r.zameen_id) === key);
  if (inList) return inList;
  if (summaries.has(key)) return summaries.get(key);
  const resp = await fetch(`/api/listings/${encodeURIComponent(key)}`);
  if (!resp.ok) throw new Error(`listing ${resp.status}`);
  const item = await resp.json();
  summaries.set(key, item);
  return item;
}

// ===== Pin preview: photo gallery =====

const photoRequests = new Map(); // listing url -> Promise<string[]>
const photoResults = new Map(); // listing url -> string[], once loaded
// Hovering a pin this long starts its photo fetch, so a click usually finds them ready.
const PHOTO_PREFETCH_DWELL_MS = 350;
let prefetchTimer = null;

function listingPhotos(item) {
  const photos = Array.isArray(item?.images) && item.images.length ? item.images : [];
  if (photos.length) return photos;
  return item?.image_url ? [item.image_url] : [];
}

/** The listing's full photo set. Crawled listings carry only a cover photo,
 *  so this asks the detail endpoint (a live Zameen fetch the first time). */
export function loadListingPhotos(item) {
  const url = item?.url;
  if (!url) return Promise.resolve(listingPhotos(item));
  if (!photoRequests.has(url)) {
    const request = fetch(`/api/listing-detail?url=${encodeURIComponent(url)}`)
      .then(resp => (resp.ok ? resp.json() : {}))
      .then(detail => {
        const photos = Array.isArray(detail?.images) ? detail.images.filter(Boolean) : [];
        const best = photos.length > listingPhotos(item).length ? photos : listingPhotos(item);
        photoResults.set(url, best);
        return best;
      })
      .catch(() => {
        photoRequests.delete(url); // let a later open retry
        return listingPhotos(item);
      });
    photoRequests.set(url, request);
  }
  return photoRequests.get(url);
}

/** Photos already fetched for this listing, or null while they are still loading. */
export function loadedListingPhotos(item) {
  return item?.url ? photoResults.get(item.url) || null : listingPhotos(item);
}

export function cancelPhotoPrefetch() {
  clearTimeout(prefetchTimer);
}

/** Start fetching a pin's photos after a short hover. */
export function prefetchListingPhotos(id) {
  clearTimeout(prefetchTimer);
  prefetchTimer = setTimeout(async () => {
    try {
      const item = await getListingSummary(id);
      loadListingPhotos(item);
    } catch {}
  }, PHOTO_PREFETCH_DWELL_MS);
}

function galleryHtml(photos, { loading = false } = {}) {
  if (!photos.length) {
    return `<div class="pin-gallery${loading ? ' is-loading' : ''}" data-gallery>
      <div class="pin-gallery-empty img-fallback"></div>
      <span class="pin-gallery-count" data-gallery-count>${loading ? 'Loading photos…' : ''}</span>
    </div>`;
  }
  const slides = photos.map((src, i) => `<img class="pin-gallery-img" src="${escA(src)}" alt="Photo ${i + 1} of ${photos.length}" ${i > 1 ? 'loading="lazy"' : ''} draggable="false">`).join('');
  const many = photos.length > 1;
  return `<div class="pin-gallery${loading ? ' is-loading' : ''}" data-gallery>
    <div class="pin-gallery-track" data-gallery-track>${slides}</div>
    ${many ? `<button type="button" class="pin-gallery-nav is-prev" data-gallery-prev aria-label="Previous photo" disabled>
      <svg viewBox="0 0 24 24" aria-hidden="true"><path fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" d="M15 19l-7-7 7-7"/></svg></button>
    <button type="button" class="pin-gallery-nav is-next" data-gallery-next aria-label="Next photo">
      <svg viewBox="0 0 24 24" aria-hidden="true"><path fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" d="M9 5l7 7-7 7"/></svg></button>` : ''}
    <span class="pin-gallery-count" data-gallery-count>${loading ? 'Loading photos…' : many ? `1 / ${photos.length}` : ''}</span>
  </div>`;
}

/** Wire arrows, swipe position and the counter for a gallery inside `root`. */
export function bindGallery(root, { onPhotoClick } = {}) {
  const gallery = root?.querySelector('[data-gallery]');
  const track = gallery?.querySelector('[data-gallery-track]');
  if (!track) return;
  const total = track.children.length;
  const prev = gallery.querySelector('[data-gallery-prev]');
  const next = gallery.querySelector('[data-gallery-next]');
  const count = gallery.querySelector('[data-gallery-count]');
  const current = () => Math.round(track.scrollLeft / Math.max(track.clientWidth, 1));
  const sync = () => {
    const i = current();
    if (prev) prev.disabled = i <= 0;
    if (next) next.disabled = i >= total - 1;
    if (count && total > 1 && !gallery.classList.contains('is-loading')) count.textContent = `${i + 1} / ${total}`;
  };
  const go = step => {
    const target = Math.min(Math.max(current() + step, 0), total - 1);
    track.scrollTo({ left: target * track.clientWidth, behavior: motionAllowed() ? 'smooth' : 'auto' });
  };
  prev?.addEventListener('click', e => { e.stopPropagation(); go(-1); });
  next?.addEventListener('click', e => { e.stopPropagation(); go(1); });
  track.addEventListener('scroll', sync, { passive: true });
  gallery.addEventListener('keydown', e => {
    if (e.key === 'ArrowLeft') { e.preventDefault(); go(-1); }
    if (e.key === 'ArrowRight') { e.preventDefault(); go(1); }
  });
  if (onPhotoClick) track.addEventListener('click', onPhotoClick);
  sync();
}

/** Swap in a fuller photo set, keeping the photo the user is looking at. */
export function replaceGallery(root, photos, opts) {
  const old = root?.querySelector('[data-gallery]');
  if (!old) return;
  const index = Math.round((old.querySelector('[data-gallery-track]')?.scrollLeft || 0) / Math.max(old.clientWidth, 1));
  old.outerHTML = galleryHtml(photos);
  bindGallery(root, opts);
  const track = root.querySelector('[data-gallery-track]');
  if (track && index) track.scrollLeft = index * track.clientWidth;
}

export function renderPreviewCard(item, { loadingPhotos = false } = {}) {
  const facts = [
    item.bedrooms ? `<span>${bedIcon('w-3.5 h-3.5')}${item.bedrooms} bed</span>` : '',
    item.bathrooms ? `<span>${bathIcon('w-3.5 h-3.5')}${item.bathrooms} bath</span>` : '',
    item.area_size ? `<span>${areaIcon('w-3.5 h-3.5')}${esc(item.area_size)}</span>` : '',
  ].filter(Boolean).join('');
  return `<div class="pin-preview" data-zameen-id="${escA(String(item.zameen_id || ''))}">
    ${galleryHtml(listingPhotos(item), { loading: loadingPhotos })}
    <div class="pin-preview-body">
      <div class="pin-preview-price">${esc(fmtPrice(item.price, item.price_text))}${item.price || item.price_text ? '<span>/mo</span>' : ''}</div>
      <div class="pin-preview-title">${esc(item.title || 'Rental')}</div>
      ${item.location ? `<div class="pin-preview-loc">${esc(item.location)}</div>` : ''}
      ${facts ? `<div class="pin-preview-facts">${facts}</div>` : ''}
      ${item.is_active === false ? '<div class="pin-preview-note">No longer listed on Zameen</div>' : ''}
      <button type="button" class="pin-preview-open" data-preview-open>View details</button>
    </div>
  </div>`;
}

export function renderStackCard(stack) {
  const range = stack.min && stack.max && stack.min !== stack.max
    ? `${shortPrice(stack.min)} – ${shortPrice(stack.max)}`
    : stack.min ? shortPrice(stack.min) : '';
  const count = stack.count.toLocaleString();
  const approx = isApproxStack(stack);
  const heading = stack.building ? `${count} flats in this building` : `${count} rentals at this point`;
  const note = stack.building
    ? 'All of these are flats listed at the same building.'
    : approx
    ? 'Zameen shows these listings at the block or society’s map pin, so the exact houses aren’t marked.'
    : 'These listings share one map point: often one building, or the same home posted more than once.';
  return `<div class="pin-stack-card">
    <div class="pin-stack-title">${esc(heading)}</div>
    ${stack.area ? `<div class="pin-stack-area">${esc(stack.area)}</div>` : ''}
    ${range ? `<div class="pin-stack-range">Rs ${esc(range)} /mo</div>` : ''}
    <p class="pin-stack-note">${esc(note)}</p>
    <button type="button" class="pin-preview-open" data-stack-search>Show these ${count} in the list</button>
  </div>`;
}
