/** Listing preview popup for a map pin: price, facts and a swipeable photo gallery. */

import L from 'leaflet';
import { esc, escA, fmtPrice } from './utils.js';
import { bedIcon, bathIcon, areaIcon } from './icons.js';

// Hovering a pin this long starts its photo fetch, so a click usually finds them ready.
const PHOTO_PREFETCH_DWELL_MS = 350;

const photoRequests = new Map(); // listing url -> Promise<string[]>
const photoResults = new Map(); // listing url -> string[], once loaded
let prefetchTimer = null;

function motionAllowed() {
  try { return !window.matchMedia('(prefers-reduced-motion: reduce)').matches; } catch { return true; }
}

function listingPhotos(item) {
  if (Array.isArray(item?.images) && item.images.length) return item.images;
  return item?.image_url ? [item.image_url] : [];
}

/** The listing's full photo set. Crawled listings carry only a cover photo,
 *  so this asks the detail endpoint (a live Zameen fetch the first time). */
function loadListingPhotos(item) {
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

/** Start fetching a pin's photos after a short hover. */
export function prefetchPreviewPhotos(item) {
  clearTimeout(prefetchTimer);
  prefetchTimer = setTimeout(() => loadListingPhotos(item), PHOTO_PREFETCH_DWELL_MS);
}

export function cancelPreviewPrefetch() {
  clearTimeout(prefetchTimer);
}

function galleryHtml(photos, { loading = false, cover = '' } = {}) {
  // The cover stays visible behind the full-size photos while they download.
  const coverStyle = cover ? ` style="background-image:url('${escA(cover)}')"` : '';
  const count = `<span class="pin-gallery-count" data-gallery-count>${loading ? 'Loading photos…' : photos.length > 1 ? `1 / ${photos.length}` : ''}</span>`;
  if (!photos.length) {
    return `<div class="pin-gallery${loading ? ' is-loading' : ''}" data-gallery><div class="pin-gallery-empty img-fallback"></div>${count}</div>`;
  }
  const slides = photos.map((src, i) => `<img class="pin-gallery-img" src="${escA(src)}" alt="Photo ${i + 1} of ${photos.length}" ${i > 1 ? 'loading="lazy"' : ''} draggable="false">`).join('');
  const nav = photos.length > 1
    ? `<button type="button" class="pin-gallery-nav is-prev" data-gallery-prev aria-label="Previous photo" disabled>
        <svg viewBox="0 0 24 24" aria-hidden="true"><path fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" d="M15 19l-7-7 7-7"/></svg></button>
      <button type="button" class="pin-gallery-nav is-next" data-gallery-next aria-label="Next photo">
        <svg viewBox="0 0 24 24" aria-hidden="true"><path fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" d="M9 5l7 7-7 7"/></svg></button>`
    : '';
  return `<div class="pin-gallery${loading ? ' is-loading' : ''}" data-gallery${coverStyle}>
    <div class="pin-gallery-track" data-gallery-track>${slides}</div>${nav}${count}
  </div>`;
}

/** Wire arrows, swipe position and the counter for the gallery inside `root`. */
function bindGallery(root, onPhotoClick) {
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
  track.addEventListener('click', onPhotoClick);
  sync();
}

function previewHtml(item, photos, { loading }) {
  const facts = [
    item.bedrooms ? `<span>${bedIcon('w-3.5 h-3.5')}${item.bedrooms} bed</span>` : '',
    item.bathrooms ? `<span>${bathIcon('w-3.5 h-3.5')}${item.bathrooms} bath</span>` : '',
    item.area_size ? `<span>${areaIcon('w-3.5 h-3.5')}${esc(item.area_size)}</span>` : '',
  ].filter(Boolean).join('');
  return `<div class="pin-preview">
    ${galleryHtml(photos, { loading, cover: item.image_url || '' })}
    <div class="pin-preview-body">
      <div class="pin-preview-price">${esc(fmtPrice(item.price, item.price_text))}${item.price || item.price_text ? '<span>/mo</span>' : ''}</div>
      <div class="pin-preview-title">${esc(item.title || 'Rental')}</div>
      ${item.location ? `<div class="pin-preview-loc">${esc(item.location)}</div>` : ''}
      ${facts ? `<div class="pin-preview-facts">${facts}</div>` : ''}
      <button type="button" class="pin-preview-open" data-preview-open>View details</button>
    </div>
  </div>`;
}

/**
 * Open the preview for `item` at its pin. `padding` keeps the card clear of map
 * controls; `onOpen(item)` opens the full listing; `beforePan()` runs before the
 * popup nudges the map into view.
 */
export function openListingPreview(item, map, { padding, onOpen, beforePan, onClose } = {}) {
  const latlng = [Number(item.latitude), Number(item.longitude)];
  const ready = item.url ? photoResults.get(item.url) : listingPhotos(item);
  const popup = L.popup({
    className: 'pin-popup',
    maxWidth: 300,
    minWidth: 250,
    offset: [0, -6],
    autoPanPaddingTopLeft: padding?.topLeft || [24, 24],
    autoPanPaddingBottomRight: padding?.bottomRight || [24, 24],
  }).setLatLng(latlng);

  const open = () => {
    map.closePopup(popup);
    const photos = item.url ? photoResults.get(item.url) : null;
    onOpen?.(photos && photos.length > 1 ? { ...item, images: photos } : item);
  };
  const render = (photos, loading) => {
    popup.setContent(previewHtml(item, photos, { loading }));
    const root = popup.getElement();
    bindGallery(root, open);
    root?.querySelector('[data-preview-open]')?.addEventListener('click', open);
  };

  beforePan?.();
  popup.openOn(map);
  render(ready || listingPhotos(item), !ready);
  if (onClose) popup.on('remove', onClose);
  if (ready) return popup;

  loadListingPhotos(item).then(photos => {
    if (!map.hasLayer(popup)) return;
    const track = popup.getElement()?.querySelector('[data-gallery-track]');
    const index = track ? Math.round(track.scrollLeft / Math.max(track.clientWidth, 1)) : 0;
    beforePan?.();
    render(photos, false);
    const nextTrack = popup.getElement()?.querySelector('[data-gallery-track]');
    if (nextTrack && index) nextTrack.scrollLeft = index * nextTrack.clientWidth;
  });
  return popup;
}
