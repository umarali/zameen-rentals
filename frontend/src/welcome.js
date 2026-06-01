/** Welcome / help overlay.
 *
 *  Page load is never blocked: first-time visitors get a slim, non-blocking
 *  "intent strip" above the filter bar whose example chips run a real search.
 *  The full modal is on-demand only (header help button or the strip's "See
 *  tips") and is built around ONE primary action — browse fresh city rentals.
 */

import { $, $$, esc, escA } from './utils.js';
import { S, CITY_DEFAULTS, NL_EXAMPLES } from './state.js';
import { track } from './analytics.js';
import { startTour, tourDone } from './tour.js';

const WELCOMED_KEY = 'zr_welcomed';

let _deps = null;
let _overlay = null;
let _lastTrigger = null;
let _guide = null;

export function initWelcome(deps) {
  _deps = deps;
  buildDOM();
  wireEvents();

  if (!tourDone()) {
    // First-ever visit: run the guided tour, then hand off to the lightweight
    // intent strip so they still get a quick-start search prompt.
    startTour({ onDone: () => { if (!localStorage.getItem(WELCOMED_KEY)) showFirstVisitGuide(); } });
  } else if (!localStorage.getItem(WELCOMED_KEY)) {
    showFirstVisitGuide();
  }
}

function rememberWelcomeSeen() {
  localStorage.setItem(WELCOMED_KEY, '1');
}

/** Retire the first-run guidance for good (remove the strip + set the flag). */
function markFirstRunDone() {
  _guide?.remove();
  _guide = null;
  rememberWelcomeSeen();
}

function cityName() { return CITY_DEFAULTS[S.city]?.name || 'Lahore'; }

function getIntentChips() {
  const ex = (NL_EXAMPLES[S.city] || NL_EXAMPLES.lahore).examples || [];
  return ex.slice(0, 3);
}

function runQuery(q) {
  const input = $('#nlInput');
  if (input) input.value = q;
  _deps.doNlSearch();
}

// ── First-visit intent strip (non-blocking) ──────────────────────────────────

function showFirstVisitGuide() {
  if (_guide || localStorage.getItem(WELCOMED_KEY)) return;
  const chips = getIntentChips().map(c =>
    `<button class="chip intent-chip" data-intent-q="${escA(c)}">${esc(c)}</button>`
  ).join('');

  const el = document.createElement('div');
  el.id = 'firstVisitGuide';
  el.className = 'intent-strip';
  el.innerHTML = `
    <div class="intent-strip-inner">
      <span class="intent-strip-label">What are you looking for in <strong>${esc(cityName())}</strong>?</span>
      <span class="intent-strip-chips">${chips}</span>
      <button id="firstVisitTips" class="intent-strip-tips">See tips</button>
      <button id="firstVisitDismiss" class="intent-strip-x" aria-label="Dismiss getting-started guide">&times;</button>
    </div>`;
  const anchor = $('#filtersShell');
  if (anchor) anchor.insertAdjacentElement('beforebegin', el);
  else document.body.prepend(el);
  _guide = el;

  el.querySelectorAll('[data-intent-q]').forEach(btn => {
    btn.addEventListener('click', () => {
      track('welcome_intent_chip', { q: btn.dataset.intentQ });
      markFirstRunDone();
      runQuery(btn.dataset.intentQ);
    });
  });
  el.querySelector('#firstVisitDismiss').addEventListener('click', () => {
    track('welcome_dismissed', { method: 'strip' });
    markFirstRunDone();
  });
  el.querySelector('#firstVisitTips').addEventListener('click', () => {
    markFirstRunDone();
    showWelcome();
  });

  // If the user starts their own search/filtering, retire the guidance quietly.
  const onSelfStart = () => markFirstRunDone();
  $('#nlInput')?.addEventListener('focus', onSelfStart, { once: true });
  $('#filterBar')?.addEventListener('pointerdown', onSelfStart, { once: true });
}

// ── On-demand welcome / help modal ────────────────────────────────────────────

export function showWelcome() {
  if (!_overlay) return;
  // A peek at help must NOT permanently consume the first-run guidance — only a
  // real dismissal (close/skip/backdrop) or a search does. Just hide the strip.
  _guide?.remove();
  _guide = null;
  // Remember what had focus so we can restore it on close (a11y).
  const active = document.activeElement;
  if (active && active !== document.body) _lastTrigger = active;
  syncModalCity();
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
  rememberWelcomeSeen();
  const trigger = _lastTrigger;
  _lastTrigger = null;
  if (trigger && typeof trigger.focus === 'function') trigger.focus();
}

function onEsc(e) {
  if (e.key === 'Escape') {
    hideWelcome();
    track('welcome_dismissed', { method: 'escape' });
  }
}

function intentChipsHtml() {
  return getIntentChips().map(c =>
    `<button class="chip welcome-intent-chip" data-intent-q="${escA(c)}">${esc(c)}</button>`
  ).join('');
}

/** Keep the modal's city pills, primary-button label, and example chips in
 *  sync with the current city (called on open and whenever a pill is picked). */
function syncModalCity() {
  if (!_overlay) return;
  _overlay.querySelectorAll('[data-wcity]').forEach(btn =>
    btn.classList.toggle('active', btn.dataset.wcity === S.city));
  const browse = _overlay.querySelector('#welcomeBrowse');
  if (browse) browse.textContent = `Browse fresh ${cityName()} rentals`;
  const row = _overlay.querySelector('#welcomeIntentRow');
  if (row) { row.innerHTML = intentChipsHtml(); wireIntentChips(row); }
}

function buildDOM() {
  const cityOrder = ['lahore', 'karachi', 'islamabad'];
  const cityPills = cityOrder.map(key =>
    `<button data-wcity="${key}" class="chip${S.city === key ? ' active' : ''}">${esc(CITY_DEFAULTS[key].name)}</button>`
  ).join('');

  const el = document.createElement('div');
  el.id = 'welcomeOverlay';
  el.className = 'hidden';
  el.setAttribute('role', 'dialog');
  el.setAttribute('aria-modal', 'true');
  el.setAttribute('aria-labelledby', 'welcomeTitle');
  el.innerHTML = `
    <div class="welcome-backdrop fixed inset-0 bg-black/40 z-[260]"></div>
    <div class="welcome-wrapper fixed inset-0 z-[261] flex items-center justify-center p-4">
      <div class="welcome-panel bg-white rounded-2xl shadow-2xl w-[92vw] max-w-[460px] max-h-[90dvh] overflow-y-auto p-6 sm:p-8 relative scroll-thin">
        <div class="flex items-center justify-between mb-5">
          <div class="flex items-center gap-2.5">
            <img src="/static/logo.svg" alt="" width="36" height="36" class="brand-mark">
            <span class="font-brand text-sm font-bold tracking-tight text-gray-800">Zameen<span class="brand-wordmark-accent">Rentals</span></span>
          </div>
          <button id="welcomeClose" class="w-8 h-8 rounded-full hover:bg-gray-100 flex items-center justify-center text-gray-400 hover:text-gray-600 transition-colors" aria-label="Close">
            <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"/></svg>
          </button>
        </div>

        <h2 id="welcomeTitle" class="font-brand text-xl sm:text-2xl font-extrabold text-gray-900 leading-tight">How to find your rental</h2>
        <p class="mt-2 text-sm text-gray-500 leading-relaxed">Search in plain English or Roman Urdu, pick a starter below, or just browse the freshest listings.</p>

        <div class="mt-5">
          <div class="welcome-eyebrow">Searching in</div>
          <div class="flex items-center gap-2 mt-2" id="welcomeCityRow">${cityPills}</div>
        </div>

        <button id="welcomeBrowse" class="welcome-primary mt-5">Browse fresh ${esc(cityName())} rentals</button>

        <div class="mt-5">
          <div class="welcome-eyebrow">Or try a search</div>
          <div class="flex flex-wrap gap-2 mt-2" id="welcomeIntentRow">${intentChipsHtml()}</div>
        </div>

        <div class="mt-5 flex items-center justify-center gap-4">
          <button id="welcomeTour" class="text-sm font-semibold text-brand-600 hover:text-brand-700 transition-colors">Take a quick tour</button>
          <span class="text-gray-300">·</span>
          <button id="welcomeDismiss" class="text-sm font-medium text-gray-500 hover:text-gray-700 transition-colors">Skip</button>
        </div>
      </div>
    </div>`;

  document.body.appendChild(el);
  _overlay = el;
}

function wireIntentChips(container) {
  container.querySelectorAll('[data-intent-q]').forEach(btn => {
    btn.addEventListener('click', () => {
      const q = btn.dataset.intentQ;
      hideWelcome();
      track('welcome_quickstart', { q });
      runQuery(q);
    });
  });
}

function wireEvents() {
  const wrapper = _overlay.querySelector('.welcome-wrapper');
  const close = _overlay.querySelector('#welcomeClose');
  const dismiss = _overlay.querySelector('#welcomeDismiss');
  const browse = _overlay.querySelector('#welcomeBrowse');

  // The wrapper is full-viewport above the visual backdrop, so a click "outside
  // the card" actually hits the wrapper. Treat that as dismiss.
  wrapper.addEventListener('click', e => {
    if (e.target === wrapper) { hideWelcome(); track('welcome_dismissed', { method: 'backdrop' }); }
  });
  close.addEventListener('click', () => { hideWelcome(); track('welcome_dismissed', { method: 'close' }); });
  dismiss.addEventListener('click', () => { hideWelcome(); track('welcome_dismissed', { method: 'skip' }); });

  // Re-launch the guided tour on demand.
  _overlay.querySelector('#welcomeTour')?.addEventListener('click', () => {
    hideWelcome();
    track('welcome_tour');
    startTour({ force: true });
  });

  // Primary action: browse the freshest listings for the chosen city.
  browse.addEventListener('click', () => {
    hideWelcome();
    track('welcome_browse', { city: S.city });
    _deps.doSearch();
  });

  // City pills act as context, not a competing CTA.
  _overlay.querySelector('#welcomeCityRow').addEventListener('click', e => {
    const btn = e.target.closest('[data-wcity]');
    if (!btn || btn.dataset.wcity === S.city) return;
    S.city = btn.dataset.wcity;
    _deps.onCityChange(btn.dataset.wcity);
    syncModalCity();
  });

  wireIntentChips(_overlay.querySelector('#welcomeIntentRow'));

  // Header help trigger.
  const cta = $('#welcomeBtn');
  if (cta) cta.addEventListener('click', showWelcome);
}
