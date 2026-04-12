/** Welcome overlay — concierge-style onboarding with quick-start cards. */

import { $, $$, esc } from './utils.js';
import { S, CITY_DEFAULTS } from './state.js';
import { track } from './analytics.js';

const WELCOMED_KEY = 'zr_welcomed';

let _deps = null;
let _overlay = null;

export function initWelcome(deps) {
  _deps = deps;
  buildDOM();
  wireEvents();

  if (!localStorage.getItem(WELCOMED_KEY)) {
    setTimeout(showWelcome, 600);
  }
}

export function showWelcome() {
  if (!_overlay) return;
  // Sync city pills to current state
  _overlay.querySelectorAll('[data-wcity]').forEach(btn =>
    btn.classList.toggle('active', btn.dataset.wcity === S.city)
  );
  _overlay.classList.remove('hidden');
  requestAnimationFrame(() => {
    _overlay.querySelector('.welcome-panel').classList.add('welcome-open');
    _overlay.querySelector('.welcome-backdrop').classList.add('welcome-backdrop-open');
  });
  _overlay.querySelector('#welcomeClose').focus();
  document.addEventListener('keydown', onEsc);
  track('welcome_shown');
}

export function hideWelcome() {
  if (!_overlay) return;
  const panel = _overlay.querySelector('.welcome-panel');
  const backdrop = _overlay.querySelector('.welcome-backdrop');
  panel.classList.remove('welcome-open');
  backdrop.classList.remove('welcome-backdrop-open');
  setTimeout(() => _overlay.classList.add('hidden'), 250);
  document.removeEventListener('keydown', onEsc);
  localStorage.setItem(WELCOMED_KEY, '1');
}

function onEsc(e) {
  if (e.key === 'Escape') {
    hideWelcome();
    track('welcome_dismissed', { method: 'escape' });
  }
}

const NL_TIPS = { karachi: '2 bed flat DHA under 50k', lahore: '3 bed house Bahria Town under 80k', islamabad: '2 bed flat F-8 under 60k' };

function getNlTip() { return NL_TIPS[S.city] || NL_TIPS.lahore; }

function detectUserCity() {
  return new Promise(resolve => {
    if (!navigator.geolocation) return resolve(null);
    navigator.geolocation.getCurrentPosition(
      pos => {
        const { latitude: lat, longitude: lng } = pos.coords;
        let closest = null;
        let minDist = Infinity;
        for (const [key, city] of Object.entries(CITY_DEFAULTS)) {
          const d = Math.hypot(lat - city.lat, lng - city.lng);
          if (d < minDist) { minDist = d; closest = key; }
        }
        // Only match if within ~100km (~1 degree)
        resolve(minDist < 1 ? closest : null);
      },
      () => resolve(null),
      { timeout: 4000, maximumAge: 300000 }
    );
  });
}

function buildDOM() {
  const cityOrder = ['lahore', 'karachi', 'islamabad'];
  const cityPills = cityOrder.map(key => {
    const city = CITY_DEFAULTS[key];
    return `<button data-wcity="${key}" class="chip${S.city === key ? ' active' : ''}">${esc(city.name)}</button>`;
  }).join('');

  const cards = [
    { id: 'budget', icon: budgetIcon(), label: 'Budget 1BR', desc: 'Apartments under 40K', type: 'apartment', beds: '1', pmin: '0', pmax: '40000' },
    { id: 'family', icon: familyIcon(), label: 'Family Home', desc: '3 bed house, 50-150K', type: 'house', beds: '3', pmin: '50000', pmax: '150000' },
    { id: 'furnished', icon: furnishedIcon(), label: 'Furnished Flat', desc: 'Ready to move in', type: 'apartment', furnished: true },
    { id: 'nearby', icon: nearbyIcon(), label: 'Near Me', desc: 'Find what\'s close', nearby: true },
  ];

  const cardHtml = cards.map(c => {
    const disabled = c.nearby ? ' data-welcome-nearby' : '';
    return `<button class="welcome-card" data-wcard="${c.id}"${disabled}>
      <div class="welcome-card-icon">${c.icon}</div>
      <div class="welcome-card-label">${c.label}</div>
      <div class="welcome-card-desc">${c.desc}</div>
    </button>`;
  }).join('');

  const el = document.createElement('div');
  el.id = 'welcomeOverlay';
  el.className = 'hidden';
  el.setAttribute('role', 'dialog');
  el.setAttribute('aria-modal', 'true');
  el.setAttribute('aria-labelledby', 'welcomeTitle');
  el.innerHTML = `
    <div class="welcome-backdrop fixed inset-0 bg-black/40 z-[260]"></div>
    <div class="fixed inset-0 z-[261] flex items-center justify-center p-4">
      <div class="welcome-panel bg-white rounded-2xl shadow-2xl w-[92vw] max-w-[520px] max-h-[90dvh] overflow-y-auto p-6 sm:p-8 relative scroll-thin">
        <div class="flex items-center justify-between mb-5">
          <div class="flex items-center gap-2.5">
            <img src="/static/logo.svg" alt="" width="36" height="36" class="brand-mark">
            <span class="font-brand text-sm font-bold tracking-tight text-gray-800">Zameen<span class="brand-wordmark-accent">Rentals</span></span>
          </div>
          <button id="welcomeClose" class="w-8 h-8 rounded-full hover:bg-gray-100 flex items-center justify-center text-gray-400 hover:text-gray-600 transition-colors" aria-label="Close">
            <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"/></svg>
          </button>
        </div>

        <h2 id="welcomeTitle" class="font-brand text-xl sm:text-2xl font-extrabold text-gray-900 leading-tight">Find your rental in seconds</h2>
        <p class="mt-2 text-sm text-gray-500 leading-relaxed">Search Zameen.com listings in plain English or Roman Urdu — with real-time results on an interactive map.</p>

        <div class="flex items-center justify-center gap-2 mt-5" id="welcomeCityRow">${cityPills}</div>

        <div class="mt-5">
          <div class="text-[10px] font-semibold text-gray-400 uppercase tracking-wide mb-2.5">Quick start</div>
          <div class="grid grid-cols-2 gap-2.5">${cardHtml}</div>
        </div>

        <div class="mt-5">
          <button id="welcomeNlTip" class="w-full flex items-center gap-3 border border-gray-200 rounded-full px-4 py-2.5 hover:border-brand-500 hover:bg-brand-50 transition-all group cursor-pointer">
            <svg class="w-4 h-4 text-gray-400 shrink-0 group-hover:text-brand-500 transition-colors" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z"/></svg>
            <span class="flex-1 text-sm text-gray-500 text-left group-hover:text-brand-600 transition-colors" id="welcomeNlText">Or try: ${esc(getNlTip())}</span>
            <svg class="w-4 h-4 text-gray-300 shrink-0 group-hover:text-brand-500 transition-colors" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2.5" d="M14 5l7 7m0 0l-7 7m7-7H3"/></svg>
          </button>
        </div>

        <div class="mt-4 text-center">
          <button id="welcomeDismiss" class="text-sm font-medium text-brand-500 hover:text-brand-700 transition-colors">Explore on my own</button>
        </div>
      </div>
    </div>`;

  document.body.appendChild(el);
  _overlay = el;
  updateNearbyCardState();

  // Try to auto-detect city on first visit
  if (!localStorage.getItem(WELCOMED_KEY)) {
    detectUserCity().then(city => {
      if (city && city !== S.city) {
        S.city = city;
        _deps.onCityChange(city);
        _overlay.querySelectorAll('[data-wcity]').forEach(btn =>
          btn.classList.toggle('active', btn.dataset.wcity === city)
        );
        updateNearbyCardState();
      }
    });
  }
}

function updateNearbyCardState() {
  const card = _overlay?.querySelector('[data-welcome-nearby]');
  if (!card) return;
  const supported = _deps.isNearbySupportedCity();
  card.classList.toggle('welcome-card-disabled', !supported);
  const desc = card.querySelector('.welcome-card-desc');
  if (desc) desc.textContent = supported ? "Find what's close" : `Coming soon for ${CITY_DEFAULTS[S.city]?.name || S.city}`;
}

function wireEvents() {
  const backdrop = _overlay.querySelector('.welcome-backdrop');
  const close = _overlay.querySelector('#welcomeClose');
  const dismiss = _overlay.querySelector('#welcomeDismiss');
  const nlTip = _overlay.querySelector('#welcomeNlTip');

  backdrop.addEventListener('click', () => { hideWelcome(); track('welcome_dismissed', { method: 'backdrop' }); });
  close.addEventListener('click', () => { hideWelcome(); track('welcome_dismissed', { method: 'close' }); });
  dismiss.addEventListener('click', () => { hideWelcome(); track('welcome_dismissed', { method: 'explore' }); });

  // City pills
  _overlay.querySelector('#welcomeCityRow').addEventListener('click', e => {
    const btn = e.target.closest('[data-wcity]');
    if (!btn || btn.dataset.wcity === S.city) return;
    S.city = btn.dataset.wcity;
    _deps.onCityChange(btn.dataset.wcity);
    _overlay.querySelectorAll('[data-wcity]').forEach(b => b.classList.toggle('active', b.dataset.wcity === S.city));
    updateNearbyCardState();
    // Update the NL tip text per city
    const tipEl = _overlay.querySelector('#welcomeNlText');
    if (tipEl) tipEl.textContent = 'Or try: ' + getNlTip();
  });

  // Quick-start cards
  _overlay.querySelectorAll('.welcome-card').forEach(card => {
    card.addEventListener('click', () => {
      const id = card.dataset.wcard;

      if (id === 'nearby') {
        if (!_deps.isNearbySupportedCity()) return;
        hideWelcome();
        track('welcome_quickstart', { card: 'nearby' });
        _deps.triggerNearby();
        return;
      }

      // Apply preset filters
      const presets = {
        budget: { type: 'apartment', beds: '1', pmin: '0', pmax: '40000' },
        family: { type: 'house', beds: '3', pmin: '50000', pmax: '150000' },
        furnished: { type: 'apartment', furnished: true },
      };
      const p = presets[id];
      if (!p) return;

      S.type = p.type || ''; S.beds = p.beds || ''; S.bedsMax = '';
      S.priceMin = p.pmin || ''; S.priceMax = p.pmax || '';
      S.sizeMarlaMin = ''; S.sizeMarlaMax = '';
      if (p.furnished) _deps.setToggle(true);

      $$('#typeGrid .chip').forEach(c => c.classList.toggle('active', c.dataset.type === S.type));
      $$('#bedRow .chip').forEach(c => c.classList.toggle('active', c.dataset.beds === S.beds));
      _deps.syncPriceChips();
      _deps.updateChips();

      hideWelcome();
      track('welcome_quickstart', { card: id });
      _deps.doSearch();
    });
  });

  // NL tip
  nlTip.addEventListener('click', () => {
    const input = $('#nlInput');
    input.value = getNlTip();
    input.focus();
    hideWelcome();
    track('welcome_nl_tip');
    _deps.doNlSearch();
  });

  // Header CTA
  const cta = $('#welcomeBtn');
  if (cta) cta.addEventListener('click', showWelcome);
}

// --- SVG Icons ---

function budgetIcon() {
  return `<svg class="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M2 7a2 2 0 012-2h16a2 2 0 012 2v10a2 2 0 01-2 2H4a2 2 0 01-2-2V7z"/><path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M12 15a3 3 0 100-6 3 3 0 000 6z"/><path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M2 9h2m16 0h2M2 15h2m16 0h2"/></svg>`;
}

function familyIcon() {
  return `<svg class="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M3 21V9l9-6 9 6v12"/><path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M9 21v-6h6v6"/></svg>`;
}

function furnishedIcon() {
  return `<svg class="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M5 12V7a2 2 0 012-2h10a2 2 0 012 2v5"/><path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M3 12h18v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4z"/><path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M5 18v2m14-2v2"/></svg>`;
}

function nearbyIcon() {
  return `<svg class="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><circle cx="12" cy="12" r="3" stroke-width="1.5"/><path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M12 2v3m0 14v3M2 12h3m14 0h3"/><circle cx="12" cy="12" r="8" stroke-width="1.5" opacity="0.4"/></svg>`;
}
