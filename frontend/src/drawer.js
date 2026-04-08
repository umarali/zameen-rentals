/** Detail drawer, photo gallery, contact bar. */

import { $, $$, esc, escA, fmtPrice } from './utils.js';
import { S, refs, CITY_DEFAULTS } from './state.js';
import { getAreaForListing, handleContactAction } from './cards.js';
import { createBaseLayer } from './map-layers.js';

let drawerDetailController = null;
let drawerDetailRequestId = 0;

// ===== NEARBY AREAS =====

function getNearby(name, n) {
  const t = refs.allAreas.find(a => a.name === name);
  if (!t || !t.lat) return [];
  const cn = CITY_DEFAULTS[S.city]?.name || 'Karachi';
  return refs.allAreas.filter(a => a.name !== name && a.name !== cn && a.lat && a.lng)
    .map(a => ({ name: a.name, d: Math.hypot(a.lat - t.lat, a.lng - t.lng) }))
    .sort((a, b) => a.d - b.d).slice(0, n);
}

// ===== DRAWER IMAGES =====

function renderDrawerImages(imgs) {
  const di = $('#drawerImgArea');
  refs.drawerImages = imgs;
  if (!imgs.length) {
    di.innerHTML = `<div class="h-[280px] bg-gray-100 flex items-center justify-center text-5xl text-gray-300">&#x1f3e0;</div>`;
    return;
  }
  if (imgs.length === 1) {
    di.innerHTML = `<div class="drawer-img-single" data-gallery><img src="${escA(imgs[0])}" alt="" onerror="this.parentElement.innerHTML='<div class=\\'h-full bg-gray-100 flex items-center justify-center text-5xl text-gray-300\\'>&#x1f3e0;</div>'">
      <div class="absolute bottom-3 right-3 px-3 py-1.5 rounded-lg bg-black/60 text-white text-xs font-medium backdrop-blur-sm">1 photo</div></div>`;
  } else {
    const grid = imgs.slice(0, 5);
    di.innerHTML = `<div class="drawer-img-grid" data-gallery>
      <div class="img-main"><img src="${escA(grid[0])}" alt="" onerror="this.src=''"></div>
      ${grid.slice(1).map(u => `<div><img src="${escA(u)}" alt="" onerror="this.src=''"></div>`).join('')}
      ${imgs.length > 5 ? `<div class="absolute bottom-3 right-3 px-3 py-1.5 rounded-lg bg-black/60 text-white text-xs font-medium backdrop-blur-sm cursor-pointer">${imgs.length} photos</div>` : ''}
    </div>`;
  }
}

function getDrawerMapTarget(item, area) {
  if (
    item?.has_exact_geography
    && Number.isFinite(Number(item.latitude))
    && Number.isFinite(Number(item.longitude))
  ) {
    return {
      lat: Number(item.latitude),
      lng: Number(item.longitude),
      zoom: 16,
      exact: true,
    };
  }
  if (area?.lat && area?.lng) {
    return {
      lat: area.lat,
      lng: area.lng,
      zoom: 14,
      exact: false,
    };
  }
  return null;
}

function renderDrawerMiniMap(target) {
  const el = document.getElementById('drawerMiniMap');
  if (!el || !target) return;
  if (refs.miniMap) { refs.miniMap.remove(); refs.miniMap = null; refs.miniMapBaseLayer = null; }
  refs.miniMap = L.map(el, {
    zoomControl: false,
    dragging: false,
    scrollWheelZoom: false,
    doubleClickZoom: false,
    touchZoom: false,
    attributionControl: false,
  }).setView([target.lat, target.lng], target.zoom);
  refs.miniMapBaseLayer = createBaseLayer(refs.mapLayer).addTo(refs.miniMap);
  L.marker([target.lat, target.lng]).addTo(refs.miniMap);
}

// ===== OPEN DRAWER =====

export function openDrawer(item, selectAreaFull) {
  const imgs = item.images || (item.image_url ? [item.image_url] : []);
  const callPhone = item.call_phone || item.phone || '';
  const whatsappPhone = item.whatsapp_phone || '';
  const contactAttrs = [
    callPhone ? `data-call-phone="${escA(callPhone)}"` : '',
    whatsappPhone ? `data-whatsapp-phone="${escA(whatsappPhone)}"` : '',
  ].filter(Boolean).join(' ');
  // Show shimmer placeholder while detail fetch may return more images
  if (item.url && imgs.length <= 1) {
    $('#drawerImgArea').innerHTML = `<div class="drawer-img-single skeleton"></div>`;
    refs.drawerImages = imgs;
  } else {
    renderDrawerImages(imgs);
  }

  const highlights = [];
  if (item.bedrooms) highlights.push(`<div class="flex items-center gap-2"><svg class="w-5 h-5 text-gray-500" fill="none" stroke="currentColor" stroke-width="1.5" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M2 17V7a2 2 0 012-2h16a2 2 0 012 2v10M2 17h20M6 17v2m12-2v2M6 11h.01M6 7h12v4H6V7z"/></svg><span class="text-sm text-gray-700">${item.bedrooms} bedroom${item.bedrooms > 1 ? 's' : ''}</span></div>`);
  if (item.bathrooms) highlights.push(`<div class="flex items-center gap-2"><svg class="w-5 h-5 text-gray-500" fill="none" stroke="currentColor" stroke-width="1.5" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M3 13h18v2a4 4 0 01-4 4H7a4 4 0 01-4-4v-2zM5 13V6a2 2 0 012-2h1a2 2 0 012 2v1"/></svg><span class="text-sm text-gray-700">${item.bathrooms} bathroom${item.bathrooms > 1 ? 's' : ''}</span></div>`);
  if (item.area_size) highlights.push(`<div class="flex items-center gap-2"><svg class="w-5 h-5 text-gray-500" fill="none" stroke="currentColor" stroke-width="1.5" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M4 8V4m0 0h4M4 4l5 5m11-1V4m0 0h-4m4 0l-5 5M4 16v4m0 0h4m-4 0l5-5m11 5l-5-5m5 5v-4m0 4h-4"/></svg><span class="text-sm text-gray-700">${esc(item.area_size)}</span></div>`);
  if (item.property_type) highlights.push(`<div class="flex items-center gap-2"><svg class="w-5 h-5 text-brand-500" fill="none" stroke="currentColor" stroke-width="1.5" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M2 22h20M3 22V9l9-7 9 7v13M9 22v-6h6v6"/></svg><span class="text-sm font-medium text-brand-600">${esc(item.property_type)}</span></div>`);

  const area = getAreaForListing(item);
  const mapTarget = getDrawerMapTarget(item, area);
  let nearbyHtml = '';
  if (area) {
    const nb = getNearby(area.name, 5);
    if (nb.length) nearbyHtml = `<div><div class="text-sm font-semibold text-gray-800 mb-3">Nearby areas</div><div class="flex flex-wrap gap-2">${nb.map(n => `<span class="amenity-pill cursor-pointer hover:border-gray-400 transition-colors" data-nearby="${escA(n.name)}">${esc(n.name)}</span>`).join('')}</div></div>`;
  }

  $('#drawerContent').innerHTML = `
    <div class="drawer-summary mt-5 mb-1">
      ${item.property_type ? `<div class="text-xs font-semibold uppercase tracking-wider text-brand-500 mb-1">${esc(item.property_type)} for Rent</div>` : ''}
      <h2 class="text-xl font-bold text-gray-900 leading-snug">${esc(item.title || 'Rental Property')}</h2>
      ${item.location ? `<div class="flex items-center gap-1.5 text-sm text-gray-500 mt-1"><svg class="w-3.5 h-3.5 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M17.657 16.657L13.414 20.9a1.998 1.998 0 01-2.827 0l-4.244-4.243a8 8 0 1111.314 0z"/><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 11a3 3 0 11-6 0 3 3 0 016 0z"/></svg>${esc(item.location)}</div>` : ''}
    </div>
    <div class="drawer-divider"></div>
    <div class="flex items-baseline gap-2 mb-1">
      <span class="text-2xl font-extrabold text-gray-900">${esc(fmtPrice(item.price, item.price_text))}</span>
      <span class="text-sm text-gray-400">/ month</span>
    </div>
    ${item.added ? `<div class="text-xs text-gray-400 mb-2">${esc(item.added)}</div>` : ''}
    ${highlights.length ? `<div class="drawer-divider"></div><div class="grid grid-cols-2 gap-3 mb-1">${highlights.join('')}</div>` : ''}
    <div id="drawerEnriched">
      <div class="drawer-divider"></div>
      <div class="space-y-3">
        <div class="skeleton h-4 w-3/4"></div>
        <div class="skeleton h-4 w-full"></div>
        <div class="skeleton h-4 w-5/6"></div>
        <div class="skeleton h-10 w-full mt-4"></div>
      </div>
    </div>
    ${mapTarget ? `<div class="drawer-divider"></div><div class="mb-3"><div class="text-sm font-semibold text-gray-800">Location</div><div id="drawerLocationMeta" class="text-xs text-gray-400 mt-1">${mapTarget.exact ? 'Exact listing pin' : 'Approximate area location'}</div></div><div id="drawerMiniMap" class="w-full h-44 rounded-xl overflow-hidden mb-1"></div>` : ''}
    ${nearbyHtml ? `<div class="drawer-divider"></div>${nearbyHtml}` : ''}
    <div class="h-20"></div>
    <div class="drawer-contact-bar">
      <div class="flex-1 min-w-0">
        <div class="text-lg font-bold text-gray-900 truncate">${esc(fmtPrice(item.price, item.price_text))}</div>
        <div class="text-xs text-gray-400">per month</div>
      </div>
      ${item.url ? `
      <a href="${escA(item.url)}" target="_blank" rel="noopener" class="w-10 h-10 rounded-full border border-gray-200 flex items-center justify-center text-gray-500 hover:text-brand-500 hover:border-brand-200 transition-colors" title="View on Zameen.com"><svg class="w-4.5 h-4.5" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M18 13v6a2 2 0 01-2 2H5a2 2 0 01-2-2V8a2 2 0 012-2h6M15 3h6v6M10 14L21 3"/></svg></a>
      <button data-contact="call" data-url="${escA(item.url)}" ${contactAttrs} class="w-10 h-10 rounded-full border border-gray-200 flex items-center justify-center text-gray-500 hover:text-brand-500 hover:border-brand-200 transition-colors" title="Call"><svg class="w-4.5 h-4.5" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M3 5a2 2 0 012-2h3.28a1 1 0 01.948.684l1.498 4.493a1 1 0 01-.502 1.21l-2.257 1.13a11.042 11.042 0 005.516 5.516l1.13-2.257a1 1 0 011.21-.502l4.493 1.498a1 1 0 01.684.949V19a2 2 0 01-2 2h-1C9.716 21 3 14.284 3 6V5z"/></svg></button>
      <button data-contact="whatsapp" data-url="${escA(item.url)}" ${contactAttrs} class="w-10 h-10 rounded-full bg-green-500 hover:bg-green-600 flex items-center justify-center text-white transition-colors shadow-sm" title="WhatsApp"><svg class="w-5 h-5" fill="currentColor" viewBox="0 0 24 24"><path d="M17.472 14.382c-.297-.149-1.758-.867-2.03-.967-.273-.099-.471-.148-.67.15-.197.297-.767.966-.94 1.164-.173.199-.347.223-.644.075-.297-.15-1.255-.463-2.39-1.475-.883-.788-1.48-1.761-1.653-2.059-.173-.297-.018-.458.13-.606.134-.133.298-.347.446-.52.149-.174.198-.298.298-.497.099-.198.05-.371-.025-.52-.075-.149-.669-1.612-.916-2.207-.242-.579-.487-.5-.669-.51-.173-.008-.371-.01-.57-.01-.198 0-.52.074-.792.372-.272.297-1.04 1.016-1.04 2.479 0 1.462 1.065 2.875 1.213 3.074.149.198 2.096 3.2 5.077 4.487.709.306 1.262.489 1.694.625.712.227 1.36.195 1.871.118.571-.085 1.758-.719 2.006-1.413.248-.694.248-1.289.173-1.413-.074-.124-.272-.198-.57-.347m-5.421 7.403h-.004a9.87 9.87 0 01-5.031-1.378l-.361-.214-3.741.982.998-3.648-.235-.374a9.86 9.86 0 01-1.51-5.26c.001-5.45 4.436-9.884 9.888-9.884 2.64 0 5.122 1.03 6.988 2.898a9.825 9.825 0 012.893 6.994c-.003 5.45-4.437 9.884-9.885 9.884m8.413-18.297A11.815 11.815 0 0012.05 0C5.495 0 .16 5.335.157 11.892c0 2.096.547 4.142 1.588 5.945L.057 24l6.305-1.654a11.882 11.882 0 005.683 1.448h.005c6.554 0 11.89-5.335 11.893-11.893a11.821 11.821 0 00-3.48-8.413z"/></svg></button>
      ` : ''}
    </div>
  `;

  // Mini map
  if (mapTarget) {
    setTimeout(() => renderDrawerMiniMap(mapTarget), 150);
  }

  // Show drawer
  $('#drawer').classList.add('drawer-open');
  $('#drawerOverlay').classList.add('overlay-open');
  document.body.style.overflow = 'hidden';
  // Push history so back button can close drawer
  try { refs._drawerHistoryPushed = true; history.pushState({ drawer: true }, '', ''); } catch { refs._drawerHistoryPushed = false; }

  // Progressive enrichment
  if (item.url) fetchDrawerDetail(item, imgs);

}

// ===== FETCH DETAIL =====

async function fetchDrawerDetail(item, existingImgs) {
  const el = $('#drawerEnriched');
  if (!el) return;
  const listingUrl = item.url;
  drawerDetailController?.abort();
  const controller = new AbortController();
  const requestId = ++drawerDetailRequestId;
  drawerDetailController = controller;
  try {
    const resp = await fetch(`/api/listing-detail?url=${encodeURIComponent(listingUrl)}`, { signal: controller.signal });
    if (!resp.ok) throw new Error('detail-fetch-failed');
    const d = await resp.json();
    if (controller.signal.aborted || requestId !== drawerDetailRequestId) return;
    if (!d || !Object.keys(d).length) { el.innerHTML = ''; return; }

    const resolvedItem = { ...item, ...d };
    const area = getAreaForListing(resolvedItem);
    const mapTarget = getDrawerMapTarget(resolvedItem, area);

    // Always render images from detail (replaces shimmer or updates with more photos)
    if (d.images && d.images.length) renderDrawerImages(d.images);
    else if (existingImgs.length) renderDrawerImages(existingImgs);
    const contactBtns = $('#drawerContent')?.querySelectorAll('[data-contact]') || [];
    contactBtns.forEach(btn => {
      if (d.call_phone || d.phone) {
        btn.dataset.callPhone = d.call_phone || d.phone;
        btn.dataset.phone = d.call_phone || d.phone;
      }
      if (d.whatsapp_phone) {
        btn.dataset.whatsappPhone = d.whatsapp_phone;
      } else {
        delete btn.dataset.whatsappPhone;
      }
    });
    const locationMeta = document.getElementById('drawerLocationMeta');
    if (locationMeta && mapTarget) {
      locationMeta.textContent = mapTarget.exact ? 'Exact listing pin' : 'Approximate area location';
      setTimeout(() => renderDrawerMiniMap(mapTarget), 60);
    }

    let html = '';
    if (d.description) {
      const short = d.description.length > 200;
      html += `<div class="drawer-divider"></div>
        <div class="text-sm font-semibold text-gray-800 mb-2">About this property</div>
        <div id="drawerDesc" class="text-sm text-gray-600 leading-relaxed ${short ? 'line-clamp-4' : ''}">${esc(d.description).replace(/\n/g, '<br>')}</div>
        ${short ? `<button id="descToggle" class="text-sm font-semibold text-gray-900 underline underline-offset-4 mt-2 hover:text-brand-600 transition-colors">Show more</button>` : ''}`;
    }
    if (d.agent_name) {
      html += `<div class="drawer-divider"></div>
        <div class="flex items-center gap-3">
          <div class="w-11 h-11 rounded-full bg-gray-200 flex items-center justify-center text-gray-500"><svg class="w-6 h-6" fill="none" stroke="currentColor" stroke-width="1.5" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M15.75 6a3.75 3.75 0 11-7.5 0 3.75 3.75 0 017.5 0zM4.501 20.118a7.5 7.5 0 0114.998 0"/></svg></div>
          <div>
            <div class="text-sm font-semibold text-gray-800">${esc(d.agent_name)}</div>
            ${d.agent_agency ? `<div class="text-xs text-gray-400">${esc(d.agent_agency)}</div>` : ''}
          </div>
        </div>`;
    }
    if (d.amenities && d.amenities.length) {
      const shown = d.amenities.slice(0, 8);
      const rest = d.amenities.length - shown.length;
      html += `<div class="drawer-divider"></div>
        <div class="text-sm font-semibold text-gray-800 mb-3">What this place offers</div>
        <div class="flex flex-wrap gap-2" id="amenitiesList">${shown.map(a => `<span class="amenity-pill">${esc(a)}</span>`).join('')}</div>
        ${rest > 0 ? `<button id="amenitiesToggle" class="text-sm font-semibold text-gray-900 underline underline-offset-4 mt-3 hover:text-brand-600 transition-colors">Show all ${d.amenities.length} amenities</button>
        <div id="amenitiesAll" class="hidden flex-wrap gap-2 mt-2">${d.amenities.slice(8).map(a => `<span class="amenity-pill">${esc(a)}</span>`).join('')}</div>` : ''}`;
    }
    if (d.features && d.features.length) {
      html += `<div class="drawer-divider"></div>
        <div class="text-sm font-semibold text-gray-800 mb-3">Property details</div>
        <div class="grid grid-cols-1 gap-2">${d.features.slice(0, 10).map(f => `<div class="flex items-center gap-2 text-sm text-gray-600"><svg class="w-4 h-4 text-brand-500 shrink-0" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M5 13l4 4L19 7"/></svg>${esc(f)}</div>`).join('')}</div>`;
    }
    const detailKeys = Object.keys(d.details || {});
    if (detailKeys.length) {
      html += `<div class="drawer-divider"></div>
        <div class="text-sm font-semibold text-gray-800 mb-3">Details</div>
        <div class="grid grid-cols-2 gap-x-4 gap-y-2">${detailKeys.slice(0, 12).map(k => `<div class="text-xs text-gray-400">${esc(k)}</div><div class="text-sm text-gray-700">${esc(d.details[k])}</div>`).join('')}</div>`;
    }
    el.innerHTML = html || '';

    const descToggle = document.getElementById('descToggle');
    if (descToggle) descToggle.addEventListener('click', () => {
      const desc = document.getElementById('drawerDesc');
      desc.classList.toggle('line-clamp-4');
      descToggle.textContent = desc.classList.contains('line-clamp-4') ? 'Show more' : 'Show less';
    });
    const amToggle = document.getElementById('amenitiesToggle');
    if (amToggle) amToggle.addEventListener('click', () => {
      const all = document.getElementById('amenitiesAll');
      all.classList.toggle('hidden'); all.classList.toggle('flex');
      amToggle.textContent = all.classList.contains('hidden') ? `Show all ${d.amenities.length} amenities` : 'Show less';
    });
  } catch (error) {
    if (error?.name === 'AbortError' || requestId !== drawerDetailRequestId) return;
    el.innerHTML = '<p class="text-xs text-gray-400 text-center py-2">Could not load details</p>';
  } finally {
    if (drawerDetailController === controller) drawerDetailController = null;
  }
}

// ===== CLOSE DRAWER =====

export function closeDrawer(fromPopState) {
  if (!$('#drawer').classList.contains('drawer-open')) return;
  drawerDetailRequestId += 1;
  drawerDetailController?.abort();
  drawerDetailController = null;
  $('#drawer').classList.remove('drawer-open');
  $('#drawerOverlay').classList.remove('overlay-open');
  document.body.style.overflow = '';
  if (refs.miniMap) { refs.miniMap.remove(); refs.miniMap = null; refs.miniMapBaseLayer = null; }
  refs.drawerImages = [];
  if (!fromPopState && refs._drawerHistoryPushed) {
    refs._drawerHistoryPushed = false;
    history.back();
  } else {
    refs._drawerHistoryPushed = false;
  }
}

// ===== GALLERY =====

function openGallery(idx) {
  refs.galleryIdx = idx;
  $('#galleryModal').classList.remove('hidden');
  updateGalleryImg();
  document.body.style.overflow = 'hidden';
}

function closeGallery() { $('#galleryModal').classList.add('hidden'); }

function updateGalleryImg() {
  const img = $('#galleryImg').querySelector('img');
  img.src = refs.drawerImages[refs.galleryIdx] || '';
  $('#galleryCounter').textContent = `${refs.galleryIdx + 1} / ${refs.drawerImages.length}`;
}

export function initDrawerListeners(selectAreaFull) {
  $('#drawerClose').addEventListener('click', () => closeDrawer());
  $('#drawerOverlay').addEventListener('click', () => closeDrawer());
  $('#drawerContent').addEventListener('click', e => {
    const nearby = e.target.closest('[data-nearby]');
    if (nearby) {
      closeDrawer();
      selectAreaFull?.(nearby.dataset.nearby);
      return;
    }

    const btn = e.target.closest('[data-contact]');
    if (!btn) return;
    e.preventDefault();
    handleContactAction(btn.dataset.contact, btn.dataset.url, btn);
  });
  $('#drawerImgArea').addEventListener('click', e => {
    if (e.target.closest('[data-gallery]') && refs.drawerImages.length) openGallery(0);
  });

  // Back button closes drawer
  window.addEventListener('popstate', () => {
    if ($('#drawer').classList.contains('drawer-open')) closeDrawer(true);
  });

  // Gallery controls
  $('#galleryClose').addEventListener('click', closeGallery);
  $('#galleryPrev').addEventListener('click', () => { refs.galleryIdx = Math.max(0, refs.galleryIdx - 1); updateGalleryImg(); });
  $('#galleryNext').addEventListener('click', () => { refs.galleryIdx = Math.min(refs.drawerImages.length - 1, refs.galleryIdx + 1); updateGalleryImg(); });
  $('#galleryModal').addEventListener('click', e => {
    if (e.target === $('#galleryModal') || e.target === $('#galleryImg')) closeGallery();
  });

  // Gallery keyboard
  document.addEventListener('keydown', e => {
    if ($('#galleryModal').classList.contains('hidden')) return;
    if (e.key === 'ArrowLeft') { refs.galleryIdx = Math.max(0, refs.galleryIdx - 1); updateGalleryImg(); }
    if (e.key === 'ArrowRight') { refs.galleryIdx = Math.min(refs.drawerImages.length - 1, refs.galleryIdx + 1); updateGalleryImg(); }
  });

  // Gallery touch swipe
  let touchStartX = 0;
  const gm = $('#galleryModal');
  gm.addEventListener('touchstart', e => { touchStartX = e.touches[0].clientX; }, { passive: true });
  gm.addEventListener('touchend', e => {
    const dx = e.changedTouches[0].clientX - touchStartX;
    if (Math.abs(dx) > 50) {
      if (dx < 0) { refs.galleryIdx = Math.min(refs.drawerImages.length - 1, refs.galleryIdx + 1); updateGalleryImg(); }
      else { refs.galleryIdx = Math.max(0, refs.galleryIdx - 1); updateGalleryImg(); }
    }
  }, { passive: true });

  // Escape closes everything
  document.addEventListener('keydown', e => {
    if (e.key === 'Escape') { closeDrawer(); closeGallery(); }
  });
}
