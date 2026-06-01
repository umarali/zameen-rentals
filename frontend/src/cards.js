/** Listing card rendering, carousels, contact actions. */

import { $, $$, esc, escA, TYPE_L, fmtPrice, fmtRelative } from './utils.js';
import { S, refs, CITY_DEFAULTS } from './state.js';
import { trackContactIntent } from './analytics.js';
import { isFavorite, isHidden, isNewSinceLastVisit } from './personalization.js';
import { has as compareHas } from './compare.js';
import {
  bedIcon, bathIcon, areaIcon, pinIcon, externalIcon, callIcon, whatsappIcon,
  FAV_FILLED_SVG, FAV_HOLLOW_SVG, HIDE_SVG, COMPARE_SVG,
} from './icons.js';

// Re-exported from the shared icon module so existing importers (drawer.js)
// keep working while every surface draws from one source of truth.
export { FAV_FILLED_SVG, FAV_HOLLOW_SVG, HIDE_SVG, COMPARE_SVG };

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
      imgHtml = `<div class="relative aspect-square sm:aspect-[4/3] overflow-hidden bg-gray-100 group" data-carousel>
        <div class="flex h-full transition-transform duration-300" data-slides>${imgs.slice(0, 5).map(u => `<img class="w-full h-full object-cover shrink-0 card-img-zoom" src="${escA(u)}" alt="" loading="lazy" onerror="this.src=''">`).join('')}</div>
        <button data-prev class="absolute left-1 sm:left-2 top-1/2 -translate-y-1/2 w-6 h-6 sm:w-7 sm:h-7 rounded-full bg-white/80 hover:bg-white flex items-center justify-center text-gray-700 opacity-0 group-hover:opacity-100 transition-opacity shadow"><svg class="w-3 h-3 sm:w-3.5 sm:h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2.5" d="M15 19l-7-7 7-7"/></svg></button>
        <button data-next class="absolute right-1 sm:right-2 top-1/2 -translate-y-1/2 w-6 h-6 sm:w-7 sm:h-7 rounded-full bg-white/80 hover:bg-white flex items-center justify-center text-gray-700 opacity-0 group-hover:opacity-100 transition-opacity shadow"><svg class="w-3 h-3 sm:w-3.5 sm:h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2.5" d="M9 5l7 7-7 7"/></svg></button>
        <div class="absolute bottom-1.5 sm:bottom-2 left-1/2 -translate-x-1/2 flex gap-1">${imgs.slice(0, 5).map((_, i) => `<span class="carousel-dot w-1.5 h-1.5 rounded-full bg-white/60 ${i === 0 ? 'active' : ''}"></span>`).join('')}</div>
      </div>`;
    } else {
      imgHtml = `<div class="relative aspect-square sm:aspect-[4/3] overflow-hidden bg-gray-100"><img class="w-full h-full object-cover card-img-zoom" src="${escA(mainImg)}" alt="" loading="lazy" onerror="this.parentElement.innerHTML='<div class=\\'img-fallback h-full\\'></div>'"></div>`;
    }
  } else {
    imgHtml = `<div class="img-fallback aspect-square sm:aspect-[4/3]"></div>`;
  }

  const badges = [];
  if (item.bedrooms) badges.push(`<span class="flex items-center gap-1">${bedIcon('w-3.5 h-3.5')}${item.bedrooms} bed</span>`);
  if (item.bathrooms) badges.push(`<span class="flex items-center gap-1">${bathIcon('w-3.5 h-3.5')}${item.bathrooms} bath</span>`);
  if (item.area_size) badges.push(`<span class="flex items-center gap-1">${areaIcon('w-3.5 h-3.5')}${esc(item.area_size)}</span>`);

  const typeLabel = item.property_type ? `<span class="text-[10px] font-semibold uppercase tracking-wide text-brand-500 bg-brand-50 px-2 py-0.5 rounded-full">${esc(item.property_type)}</span>` : '';
  const callPhone = item.call_phone || item.phone || '';
  const whatsappPhone = item.whatsapp_phone || '';
  const distanceLabel = formatDistance(item.distance_km, { approximate: item.is_distance_approximate });
  const contactAttrs = [
    callPhone ? `data-call-phone="${escA(callPhone)}"` : '',
    whatsappPhone ? `data-whatsapp-phone="${escA(whatsappPhone)}"` : '',
  ].filter(Boolean).join(' ');

  const zameenId = item.zameen_id || extractZameenIdFromUrl(item.url);
  const zameenIdAttr = zameenId ? `data-zameen-id="${escA(zameenId)}"` : '';
  const favorited = isFavorite(zameenId);
  const compared = compareHas(zameenId);
  const isNew = isNewSinceLastVisit(item.first_seen_at || item.posted_at);
  const newBadge = isNew
    ? '<span class="absolute top-2 left-2 z-10 text-[10px] font-bold uppercase tracking-wide bg-brand-500 text-white px-2 py-0.5 rounded-full shadow-sm">New</span>'
    : '';
  const favIconFilled = FAV_FILLED_SVG;
  const favIconHollow = FAV_HOLLOW_SVG;
  const hideIcon = HIDE_SVG;
  const compareIcon = COMPARE_SVG;

  return `<div class="card-wrap relative rounded-xl overflow-hidden bg-white border-2 border-transparent cursor-pointer transition-all hover:shadow-lg hover:border-gray-100" data-idx="${idx}" data-url="${escA(item.url || '')}" ${zameenIdAttr} ${areaAttr}>
    ${imgHtml}
    ${newBadge}
    <div class="p-2 sm:p-3">
      <div class="flex items-center justify-between gap-1 sm:gap-2 mb-0.5 sm:mb-1">
        <div class="text-sm sm:text-base font-bold text-gray-800">${esc(fmtPrice(item.price, item.price_text))}</div>
        ${typeLabel}
      </div>
      <div class="text-xs sm:text-sm text-gray-600 line-clamp-1 mb-0.5 sm:mb-1">${esc(item.title || 'Rental Property')}</div>
      ${item.location ? `<div class="flex items-center gap-1 text-[10px] sm:text-xs text-gray-400 mb-1 sm:mb-2">${pinIcon('w-2.5 h-2.5 sm:w-3 sm:h-3 shrink-0')}<span class="line-clamp-1">${esc(item.location)}</span></div>` : ''}
      ${distanceLabel ? `<div class="text-[10px] sm:text-xs font-semibold text-brand-600 mb-1 sm:mb-2">${esc(distanceLabel)}</div>` : ''}
      ${badges.length ? `<div class="flex flex-wrap gap-1.5 sm:gap-3 text-[10px] sm:text-xs text-gray-500">${badges.join('')}</div>` : ''}
      ${(() => {
        const addedRel = item.posted_at ? fmtRelative(item.posted_at) : '';
        const addedLine = addedRel ? `Added ${addedRel}` : (item.added || '');
        const updatedRel = item.updated_at ? fmtRelative(item.updated_at) : '';
        if (!addedLine && !updatedRel) return '';
        return `<div class="mt-2 leading-tight">
          ${addedLine ? `<div class="text-[11px] text-gray-500">${esc(addedLine)}</div>` : ''}
          ${updatedRel ? `<div class="hidden sm:block text-[10px] text-gray-400">Updated ${esc(updatedRel)}</div>` : ''}
        </div>`;
      })()}
      ${item.url ? `<div class="card-action-row pt-1.5 sm:pt-2 mt-1.5 sm:mt-2 border-t border-gray-100">
        <div class="card-action-group">
          <button data-action="favorite" ${zameenIdAttr} aria-pressed="${favorited ? 'true' : 'false'}" class="action-btn fav-btn w-8 h-8 rounded-full transition-colors ${favorited ? 'text-rose-500 bg-rose-50 hover:bg-rose-100' : 'text-gray-400 hover:text-rose-500 hover:bg-rose-50'}" title="${favorited ? 'Remove from favorites' : 'Save to favorites'}" aria-label="${favorited ? 'Remove from favorites' : 'Save to favorites'}">${favorited ? favIconFilled : favIconHollow}</button>
          <button data-action="hide" ${zameenIdAttr} class="action-btn hide-btn w-8 h-8 rounded-full text-gray-400 hover:text-gray-700 hover:bg-gray-100 transition-colors" title="Hide this listing — it won't show up in your results" aria-label="Hide this listing">${hideIcon}</button>
          <button data-action="compare" ${zameenIdAttr} aria-pressed="${compared ? 'true' : 'false'}" class="action-btn compare-btn w-8 h-8 rounded-full transition-colors ${compared ? 'text-brand-600 bg-brand-50 hover:bg-brand-100' : 'text-gray-400 hover:text-brand-600 hover:bg-brand-50'}" title="${compared ? 'Remove from compare' : 'Add to compare'}" aria-label="${compared ? 'Remove from compare' : 'Add to compare'}">${compareIcon}</button>
        </div>
        <div class="card-action-group">
          <a data-action="open" href="${escA(item.url)}" target="_blank" rel="noopener" class="action-btn w-8 h-8 rounded-full text-gray-400 hover:text-brand-500 hover:bg-brand-50 transition-colors" title="Open on Zameen.com" aria-label="Open on Zameen.com">${externalIcon()}</a>
          <button data-action="call" data-url="${escA(item.url)}" ${contactAttrs} class="action-btn w-8 h-8 rounded-full text-gray-400 hover:text-brand-500 hover:bg-brand-50 transition-colors" title="Call" aria-label="Call">${callIcon()}</button>
          <button data-action="whatsapp" data-url="${escA(item.url)}" ${contactAttrs} class="action-btn w-8 h-8 rounded-full text-gray-400 hover:text-green-600 hover:bg-green-50 transition-colors" title="WhatsApp" aria-label="WhatsApp">${whatsappIcon()}</button>
        </div>
      </div>` : ''}
    </div>
  </div>`;
}


export function extractZameenIdFromUrl(url) {
  if (!url) return '';
  // Zameen URL pattern: .../Property/slug-{LISTING_ID}-{AREA_ID}-{PAGE}.html
  // Grab the FIRST of the three trailing numbers (matches scraper.extract_zameen_id).
  const m = url.match(/-(\d{5,10})-\d+-\d+\.html?(?:$|\?|#)/);
  return m ? m[1] : '';
}

function _cssEscape(value) {
  return (window.CSS?.escape || (s => s))(String(value));
}

export function updateFavoriteButton(zameenId, favorited) {
  if (!zameenId) return;
  const selector = `.fav-btn[data-zameen-id="${_cssEscape(zameenId)}"]`;
  document.querySelectorAll(selector).forEach(btn => {
    btn.setAttribute('aria-pressed', favorited ? 'true' : 'false');
    btn.title = favorited ? 'Remove from favorites' : 'Save to favorites';
    btn.setAttribute('aria-label', btn.title);
    btn.classList.toggle('text-rose-500', favorited);
    btn.classList.toggle('bg-rose-50', favorited);
    btn.classList.toggle('hover:bg-rose-100', favorited);
    btn.classList.toggle('text-gray-400', !favorited);
    btn.classList.toggle('hover:text-rose-500', !favorited);
    btn.classList.toggle('hover:bg-rose-50', !favorited);
    btn.innerHTML = favorited ? FAV_FILLED_SVG : FAV_HOLLOW_SVG;
  });
}

export function updateCompareButton(zameenId, compared) {
  if (!zameenId) return;
  const selector = `.compare-btn[data-zameen-id="${_cssEscape(zameenId)}"]`;
  document.querySelectorAll(selector).forEach(btn => {
    btn.setAttribute('aria-pressed', compared ? 'true' : 'false');
    btn.title = compared ? 'Remove from compare' : 'Add to compare';
    btn.setAttribute('aria-label', btn.title);
    btn.classList.toggle('text-brand-600', compared);
    btn.classList.toggle('bg-brand-50', compared);
    btn.classList.toggle('hover:bg-brand-100', compared);
    btn.classList.toggle('text-gray-400', !compared);
    btn.classList.toggle('hover:text-brand-600', !compared);
    btn.classList.toggle('hover:bg-brand-50', !compared);
  });
}

export function hideCardElement(zameenId) {
  if (!zameenId) return;
  const selector = `.card-wrap[data-zameen-id="${(window.CSS?.escape || (s => s))(String(zameenId))}"]`;
  document.querySelectorAll(selector).forEach(card => {
    card.classList.add('card-hidden');
    card.style.display = 'none';
  });
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

/** Contact a listing from a known phone/whatsapp pair (e.g. a compare snapshot).
 *  Falls back to a live contact fetch, then to opening the listing, mirroring
 *  handleContactAction but without needing a card button in the DOM. */
export async function contactFromData(action, listingUrl, { callPhone = '', whatsappPhone = '' } = {}) {
  trackContactIntent({ channel: action, listingUrl, position: null, mode: refs.searchMode, city: S.city, source: 'compare' });
  if (openContact(action, listingUrl, { callPhone, whatsappPhone })) return;
  try {
    const resp = await fetch(`/api/listing-contact?url=${encodeURIComponent(listingUrl)}`);
    const data = await resp.json();
    const fetched = { callPhone: data.call_phone || data.phone || '', whatsappPhone: data.whatsapp_phone || '' };
    syncContactButtons(listingUrl, data);
    if (!openContact(action, listingUrl, fetched)) window.open(listingUrl, '_blank', 'noopener');
  } catch {
    window.open(listingUrl, '_blank', 'noopener');
  }
}

// ===== SKELETON CARDS =====

export function skeletonCard() {
  return `<div class="rounded-xl overflow-hidden bg-white border border-gray-100">
    <div class="aspect-square sm:aspect-[4/3] skeleton"></div>
    <div class="p-2 sm:p-3 space-y-2">
      <div class="skeleton h-4 sm:h-5 w-1/2"></div>
      <div class="skeleton h-3 sm:h-4 w-3/4"></div>
      <div class="skeleton h-3 w-2/3"></div>
      <div class="flex gap-2 sm:gap-3 mt-2"><div class="skeleton h-3 w-10 sm:w-12"></div><div class="skeleton h-3 w-10 sm:w-12"></div></div>
    </div>
  </div>`;
}
