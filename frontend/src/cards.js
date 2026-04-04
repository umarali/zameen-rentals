/** Listing card rendering, carousels, contact actions. */

import { $, $$, esc, escA, TYPE_L, fmtPrice } from './utils.js';
import { S, refs, CITY_DEFAULTS } from './state.js';
import { trackContactIntent } from './analytics.js';

// ===== AREA MATCHING FOR CARDS =====

export function getAreaForListing(item) {
  if (!item.location) return S.area ? refs.allAreas.find(a => a.name === S.area) || null : null;
  const loc = item.location.toLowerCase().replace(/[-,]/g, ' ');
  const locTokens = new Set(loc.split(/\s+/).filter(t => t.length > 1));
  let best = null, bestScore = 0;
  const cityN = CITY_DEFAULTS[S.city]?.name || 'Karachi';
  for (const a of refs.allAreas) {
    if (a.name === cityN) continue;
    const nl = a.name.toLowerCase().replace(/[-,]/g, ' ');
    if (loc.includes(nl)) {
      const score = nl.length + 100;
      if (score > bestScore) { bestScore = score; best = a; }
      continue;
    }
    const areaTokens = nl.split(/\s+/).filter(t => t.length > 1);
    const overlap = areaTokens.filter(t => locTokens.has(t)).length;
    if (overlap >= 2 || (areaTokens.length === 1 && overlap === 1)) {
      const score = overlap * 10 + (overlap === areaTokens.length ? 50 : 0);
      if (score > bestScore) { bestScore = score; best = a; }
    }
  }
  if (best) return best;
  if (S.area) return refs.allAreas.find(a => a.name === S.area) || null;
  return null;
}

export function formatDistance(distanceKm, { approximate = false } = {}) {
  const distance = Number(distanceKm);
  if (!Number.isFinite(distance)) return '';
  const prefix = approximate ? '~' : '';
  if (distance < 1) {
    const meters = Math.max(50, Math.round((distance * 1000) / 50) * 50);
    return `${prefix}${meters} m away`;
  }
  return `${prefix}${distance.toFixed(distance < 10 ? 1 : 0)} km away`;
}

// ===== RENDER CARD =====

export function renderCard(item, idx) {
  const area = getAreaForListing(item);
  const areaAttr = area ? `data-area="${escA(area.name)}"` : '';
  const imgs = item.images || [];
  const hasMulti = imgs.length > 1;
  const mainImg = item.image_url;

  let imgHtml;
  if (mainImg) {
    if (hasMulti) {
      imgHtml = `<div class="relative aspect-[4/3] overflow-hidden bg-gray-100 group" data-carousel>
        <div class="flex h-full transition-transform duration-300" data-slides>${imgs.slice(0, 5).map(u => `<img class="w-full h-full object-cover shrink-0 card-img-zoom" src="${escA(u)}" alt="" loading="lazy" onerror="this.src=''">`).join('')}</div>
        <button data-prev class="absolute left-2 top-1/2 -translate-y-1/2 w-7 h-7 rounded-full bg-white/80 hover:bg-white flex items-center justify-center text-gray-700 opacity-0 group-hover:opacity-100 transition-opacity shadow"><svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2.5" d="M15 19l-7-7 7-7"/></svg></button>
        <button data-next class="absolute right-2 top-1/2 -translate-y-1/2 w-7 h-7 rounded-full bg-white/80 hover:bg-white flex items-center justify-center text-gray-700 opacity-0 group-hover:opacity-100 transition-opacity shadow"><svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2.5" d="M9 5l7 7-7 7"/></svg></button>
        <div class="absolute bottom-2 left-1/2 -translate-x-1/2 flex gap-1">${imgs.slice(0, 5).map((_, i) => `<span class="carousel-dot w-1.5 h-1.5 rounded-full bg-white/60 ${i === 0 ? 'active' : ''}"></span>`).join('')}</div>
      </div>`;
    } else {
      imgHtml = `<div class="relative aspect-[4/3] overflow-hidden bg-gray-100"><img class="w-full h-full object-cover card-img-zoom" src="${escA(mainImg)}" alt="" loading="lazy" onerror="this.parentElement.innerHTML='<div class=\\'flex items-center justify-center h-full text-4xl text-gray-300\\'>&#x1f3e0;</div>'"></div>`;
    }
  } else {
    imgHtml = `<div class="aspect-[4/3] bg-gray-100 flex items-center justify-center text-4xl text-gray-300">&#x1f3e0;</div>`;
  }

  const badges = [];
  if (item.bedrooms) badges.push(`<span class="flex items-center gap-1"><svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M3 12l2-2m0 0l7-7 7 7M5 10v10a1 1 0 001 1h3m10-11l2 2m-2-2v10a1 1 0 01-1 1h-3m-4 0h4"/></svg>${item.bedrooms} bed</span>`);
  if (item.bathrooms) badges.push(`<span class="flex items-center gap-1"><svg class="w-3.5 h-3.5" fill="currentColor" viewBox="0 0 20 20"><path fill-rule="evenodd" d="M5 2a2 2 0 00-2 2v14l3.5-2 3.5 2 3.5-2 3.5 2V4a2 2 0 00-2-2H5zm2.5 3a1.5 1.5 0 100 3 1.5 1.5 0 000-3zm6.207.293a1 1 0 00-1.414 0l-6 6a1 1 0 101.414 1.414l6-6a1 1 0 000-1.414zM12.5 10a1.5 1.5 0 100 3 1.5 1.5 0 000-3z" clip-rule="evenodd"/></svg>${item.bathrooms} bath</span>`);
  if (item.area_size) badges.push(`<span class="flex items-center gap-1"><svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 8V4m0 0h4M4 4l5 5m11-1V4m0 0h-4m4 0l-5 5M4 16v4m0 0h4m-4 0l5-5m11 5l-5-5m5 5v-4m0 4h-4"/></svg>${esc(item.area_size)}</span>`);

  const typeLabel = item.property_type ? `<span class="text-[10px] font-semibold uppercase tracking-wide text-brand-500 bg-brand-50 px-2 py-0.5 rounded-full">${esc(item.property_type)}</span>` : '';
  const callPhone = item.call_phone || item.phone || '';
  const whatsappPhone = item.whatsapp_phone || '';
  const distanceLabel = formatDistance(item.distance_km, { approximate: item.is_distance_approximate });
  const contactAttrs = [
    callPhone ? `data-call-phone="${escA(callPhone)}"` : '',
    whatsappPhone ? `data-whatsapp-phone="${escA(whatsappPhone)}"` : '',
  ].filter(Boolean).join(' ');

  return `<div class="card-wrap rounded-xl overflow-hidden bg-white border border-gray-100 cursor-pointer transition-all hover:shadow-lg hover:border-gray-200 active:scale-[0.99]" data-idx="${idx}" data-url="${escA(item.url || '')}" ${areaAttr}>
    ${imgHtml}
    <div class="p-3">
      <div class="flex items-center justify-between gap-2 mb-1">
        <div class="text-base font-bold text-gray-800">${esc(fmtPrice(item.price, item.price_text))}</div>
        ${typeLabel}
      </div>
      <div class="text-sm text-gray-600 line-clamp-1 mb-1">${esc(item.title || 'Rental Property')}</div>
      ${item.location ? `<div class="flex items-center gap-1 text-xs text-gray-400 mb-2"><svg class="w-3 h-3 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M17.657 16.657L13.414 20.9a1.998 1.998 0 01-2.827 0l-4.244-4.243a8 8 0 1111.314 0z"/><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 11a3 3 0 11-6 0 3 3 0 016 0z"/></svg>${esc(item.location)}</div>` : ''}
      ${distanceLabel ? `<div class="text-xs font-semibold text-brand-600 mb-2">${esc(distanceLabel)}</div>` : ''}
      ${badges.length ? `<div class="flex flex-wrap gap-3 text-xs text-gray-500">${badges.join('')}</div>` : ''}
      ${item.added ? `<div class="text-[11px] text-gray-400 mt-2">${esc(item.added)}</div>` : ''}
      ${item.url ? `<div class="flex items-center justify-end gap-1 pt-2 mt-2 border-t border-gray-100">
        <a data-action="open" href="${escA(item.url)}" target="_blank" rel="noopener" class="action-btn w-9 h-9 rounded-full text-gray-400 hover:text-brand-500 hover:bg-brand-50 active:bg-brand-100 transition-colors" title="Open on Zameen.com"><svg class="w-4 h-4" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M18 13v6a2 2 0 01-2 2H5a2 2 0 01-2-2V8a2 2 0 012-2h6M15 3h6v6M10 14L21 3"/></svg></a>
        <button data-action="call" data-url="${escA(item.url)}" ${contactAttrs} class="action-btn w-9 h-9 rounded-full text-gray-400 hover:text-brand-500 hover:bg-brand-50 active:bg-brand-100 transition-colors" title="Call"><svg class="w-4 h-4" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" d="M3 5a2 2 0 012-2h3.28a1 1 0 01.948.684l1.498 4.493a1 1 0 01-.502 1.21l-2.257 1.13a11.042 11.042 0 005.516 5.516l1.13-2.257a1 1 0 011.21-.502l4.493 1.498a1 1 0 01.684.949V19a2 2 0 01-2 2h-1C9.716 21 3 14.284 3 6V5z"/></svg></button>
        <button data-action="whatsapp" data-url="${escA(item.url)}" ${contactAttrs} class="action-btn w-9 h-9 rounded-full text-gray-400 hover:text-green-600 hover:bg-green-50 active:bg-green-100 transition-colors" title="WhatsApp"><svg class="w-4 h-4" fill="currentColor" viewBox="0 0 24 24"><path d="M17.472 14.382c-.297-.149-1.758-.867-2.03-.967-.273-.099-.471-.148-.67.15-.197.297-.767.966-.94 1.164-.173.199-.347.223-.644.075-.297-.15-1.255-.463-2.39-1.475-.883-.788-1.48-1.761-1.653-2.059-.173-.297-.018-.458.13-.606.134-.133.298-.347.446-.52.149-.174.198-.298.298-.497.099-.198.05-.371-.025-.52-.075-.149-.669-1.612-.916-2.207-.242-.579-.487-.5-.669-.51-.173-.008-.371-.01-.57-.01-.198 0-.52.074-.792.372-.272.297-1.04 1.016-1.04 2.479 0 1.462 1.065 2.875 1.213 3.074.149.198 2.096 3.2 5.077 4.487.709.306 1.262.489 1.694.625.712.227 1.36.195 1.871.118.571-.085 1.758-.719 2.006-1.413.248-.694.248-1.289.173-1.413-.074-.124-.272-.198-.57-.347m-5.421 7.403h-.004a9.87 9.87 0 01-5.031-1.378l-.361-.214-3.741.982.998-3.648-.235-.374a9.86 9.86 0 01-1.51-5.26c.001-5.45 4.436-9.884 9.888-9.884 2.64 0 5.122 1.03 6.988 2.898a9.825 9.825 0 012.893 6.994c-.003 5.45-4.437 9.884-9.885 9.884m8.413-18.297A11.815 11.815 0 0012.05 0C5.495 0 .16 5.335.157 11.892c0 2.096.547 4.142 1.588 5.945L.057 24l6.305-1.654a11.882 11.882 0 005.683 1.448h.005c6.554 0 11.89-5.335 11.893-11.893a11.821 11.821 0 00-3.48-8.413z"/></svg></button>
      </div>` : ''}
    </div>
  </div>`;
}

// ===== CAROUSELS =====

export function initCarousels() {
  $$('[data-carousel]').forEach(el => {
    if (el.dataset.carouselReady === '1') return;
    let idx = 0;
    const slides = el.querySelector('[data-slides]');
    const dots = el.querySelectorAll('.carousel-dot');
    const n = slides.children.length;
    if (n <= 1) return;
    function go(i) {
      idx = Math.max(0, Math.min(i, n - 1));
      slides.style.transform = `translateX(-${idx * 100}%)`;
      dots.forEach((d, j) => d.classList.toggle('active', j === idx));
    }
    el.querySelector('[data-prev]')?.addEventListener('click', e => { e.stopPropagation(); go(idx - 1); });
    el.querySelector('[data-next]')?.addEventListener('click', e => { e.stopPropagation(); go(idx + 1); });
    // Touch swipe support for mobile
    let touchX = 0;
    let touchY = 0;
    let swiping = false;
    el.addEventListener('touchstart', e => { touchX = e.touches[0].clientX; touchY = e.touches[0].clientY; swiping = false; }, { passive: true });
    el.addEventListener('touchmove', e => {
      const dx = Math.abs(e.touches[0].clientX - touchX);
      const dy = Math.abs(e.touches[0].clientY - touchY);
      if (dx > dy && dx > 10) swiping = true;
    }, { passive: true });
    el.addEventListener('touchend', e => {
      if (!swiping) return;
      const dx = e.changedTouches[0].clientX - touchX;
      if (Math.abs(dx) > 40) {
        e.stopPropagation();
        go(dx < 0 ? idx + 1 : idx - 1);
      }
    }, { passive: false });
    el.dataset.carouselReady = '1';
  });
}

// ===== CONTACT ACTIONS =====

function getDatasetContact(btn) {
  return {
    callPhone: btn.dataset.callPhone || btn.dataset.phone || '',
    whatsappPhone: btn.dataset.whatsappPhone || '',
  };
}

function syncContactButtons(listingUrl, data) {
  if (!listingUrl || !window.CSS?.escape || !data) return;
  const selector = `[data-url="${window.CSS.escape(listingUrl)}"]`;
  document.querySelectorAll(selector).forEach(el => {
    if (data.call_phone || data.phone) {
      el.dataset.callPhone = data.call_phone || data.phone;
      el.dataset.phone = data.call_phone || data.phone;
    }
    if (data.whatsapp_phone) {
      el.dataset.whatsappPhone = data.whatsapp_phone;
    } else {
      delete el.dataset.whatsappPhone;
    }
  });
}

function openContact(action, listingUrl, contact) {
  const callPhone = contact.callPhone;
  const whatsappPhone = contact.whatsappPhone;
  if (action === 'call' && callPhone) {
    window.open(`tel:${callPhone}`, '_self');
    return true;
  }
  if (action === 'whatsapp' && whatsappPhone) {
    const waNum = whatsappPhone.replace(/^0/, '92').replace(/[^0-9]/g, '');
    window.open(`https://wa.me/${waNum}?text=${encodeURIComponent('Hi, I am interested in this property: ' + listingUrl)}`, '_blank');
    return true;
  }
  return false;
}

export async function handleContactAction(action, listingUrl, btn) {
  const card = btn.closest('.card-wrap');
  const pos = card ? parseInt(card.dataset.idx, 10) : null;
  trackContactIntent({ channel: action, listingUrl, position: Number.isFinite(pos) ? pos : null, mode: refs.searchMode, city: S.city, source: refs._lastSearchSource });
  if (openContact(action, listingUrl, getDatasetContact(btn))) return;
  btn.classList.add('animate-pulse');
  try {
    const resp = await fetch(`/api/listing-contact?url=${encodeURIComponent(listingUrl)}`);
    const data = await resp.json();
    btn.classList.remove('animate-pulse');
    syncContactButtons(listingUrl, data);
    if (!openContact(action, listingUrl, getDatasetContact(btn))) window.open(listingUrl, '_blank', 'noopener');
  } catch {
    btn.classList.remove('animate-pulse');
    window.open(listingUrl, '_blank', 'noopener');
  }
}

// ===== SKELETON CARDS =====

export function skeletonCard() {
  return `<div class="rounded-xl overflow-hidden bg-white border border-gray-100">
    <div class="aspect-[4/3] skeleton sm:aspect-[4/3]"></div>
    <div class="p-3 space-y-2.5">
      <div class="skeleton h-5 w-1/2 rounded-md"></div>
      <div class="skeleton h-4 w-3/4 rounded-md"></div>
      <div class="skeleton h-3.5 w-2/3 rounded-md"></div>
      <div class="flex gap-3 mt-2"><div class="skeleton h-3.5 w-14 rounded-md"></div><div class="skeleton h-3.5 w-14 rounded-md"></div><div class="skeleton h-3.5 w-16 rounded-md"></div></div>
    </div>
  </div>`;
}
