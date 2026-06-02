/** Personalization panel: alerts inbox, favorites, hidden, recently viewed.
 *
 *  One drawer-style panel with four tabs. Mounted lazily on first open so
 *  the initial render path stays untouched.
 */

import { $, $$, esc, escA, fmtPrice, fmtRelative } from './utils.js';
import * as pers from './personalization.js';
import { showToast } from './utils.js';
import { S } from './state.js';
import { bellIcon } from './icons.js';

let _panel = null;
let _activeTab = 'alerts';
let _saveSearchHooks = null;
let _drawerHooks = null;
let _lastTrigger = null;

const TABS = [
  { id: 'alerts', label: 'New matches', icon: 'bell' },
  { id: 'favorites', label: 'Saved homes', icon: 'heart' },
  { id: 'recent', label: 'Viewed', icon: 'eye' },
  { id: 'hidden', label: 'Hidden', icon: 'hide' },
];

export function initPersonalizationUI({ getCurrentFilters, openListingFromCard, refreshSearch } = {}) {
  _saveSearchHooks = { getCurrentFilters, refreshSearch };
  _drawerHooks = { openListingFromCard };
  buildDOM();
  wireHeaderButtons();
  pers.subscribe(state => updateHeaderBadge(state));
  document.addEventListener('keydown', e => {
    if (e.key === 'Escape' && _panel && !_panel.classList.contains('hidden')) {
      closePanel();
    }
  });

  // Auto-open if URL says ?alerts=open (used by push notification redirects).
  const params = new URLSearchParams(location.search);
  if (params.get('alerts') === 'open') {
    setTimeout(() => openPanel({ tab: 'alerts' }), 250);
  }
}

// ── Header bell + save button wiring ────────────────────────────────────────

function wireHeaderButtons() {
  const bell = $('#alertsBellBtn');
  if (bell) bell.addEventListener('click', () => openPanel({ tab: 'alerts' }));
  const saveBtn = $('#saveSearchBtn');
  if (saveBtn) saveBtn.addEventListener('click', openSaveSearchDialog);
}

function updateHeaderBadge(state) {
  const bell = $('#alertsBellBtn');
  if (!bell) return;
  const badge = bell.querySelector('.alerts-badge');
  const count = state.unseenAlertMatches || 0;
  if (badge) {
    if (count > 0) {
      badge.textContent = count > 99 ? '99+' : String(count);
      badge.classList.remove('hidden');
    } else {
      badge.classList.add('hidden');
    }
  }
}

// ── Save Search dialog ──────────────────────────────────────────────────────

function openSaveSearchDialog() {
  const filters = _saveSearchHooks?.getCurrentFilters?.() || {};
  const overlay = document.createElement('div');
  overlay.className = 'fixed inset-0 bg-black/40 z-[265]';
  overlay.id = 'saveSearchOverlay';

  const summary = formatFiltersSummary(filters);
  const modal = document.createElement('div');
  modal.className = 'fixed z-[266] top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[420px] max-w-[92vw] bg-white rounded-2xl shadow-2xl p-6';
  modal.id = 'saveSearchModal';
  modal.setAttribute('role', 'dialog');
  modal.setAttribute('aria-modal', 'true');
  modal.setAttribute('aria-labelledby', 'saveSearchTitle');
  modal.innerHTML = `
    <div class="flex items-center justify-between mb-3">
      <h3 id="saveSearchTitle" class="text-base font-bold text-gray-800">Get alerts for new rentals</h3>
      <button id="saveSearchClose" class="w-8 h-8 rounded-full hover:bg-gray-100 flex items-center justify-center text-gray-400 hover:text-gray-600 text-lg" aria-label="Close">&times;</button>
    </div>
    <p class="text-sm text-gray-600 mb-4">We'll keep watching this search and show you new matches as they arrive.</p>
    <div class="rounded-xl bg-brand-50 border border-brand-100 p-3 text-xs leading-relaxed">
      <div class="font-semibold text-brand-700 mb-1">Watching for:</div>
      <div class="text-gray-600" id="saveSearchPreview">${esc(summary || 'All new rentals')}</div>
    </div>
    <label class="block text-xs font-semibold text-gray-600 mt-4 mb-1">Name this alert <span class="font-normal text-gray-400">(optional)</span></label>
    <input id="saveSearchLabel" type="text" maxlength="80" class="w-full px-3 py-2 text-sm border border-gray-200 rounded-lg outline-none focus:border-brand-500 focus:ring-2 focus:ring-brand-100 transition" placeholder="${esc(summary || 'New rentals')}">
    <p class="mt-3 text-xs text-gray-500 leading-relaxed">You'll find updates in <strong>My rentals</strong>. You can also turn on device notifications after saving.</p>
    <div class="flex justify-end gap-2 mt-5">
      <button id="saveSearchCancel" class="px-4 py-2 text-sm text-gray-500 hover:text-gray-700">Cancel</button>
      <button id="saveSearchSubmit" class="px-5 py-2 text-sm font-semibold text-white bg-brand-600 hover:bg-brand-700 rounded-lg transition-colors">Start alert</button>
    </div>
  `;
  document.body.appendChild(overlay);
  document.body.appendChild(modal);

  const close = () => {
    overlay.remove();
    modal.remove();
    document.removeEventListener('keydown', escClose);
  };
  const escClose = e => { if (e.key === 'Escape') close(); };
  document.addEventListener('keydown', escClose);
  overlay.addEventListener('click', close);
  $('#saveSearchClose').addEventListener('click', close);
  $('#saveSearchCancel').addEventListener('click', close);

  setTimeout(() => $('#saveSearchLabel').focus(), 20);

  $('#saveSearchSubmit').addEventListener('click', async () => {
    const btn = $('#saveSearchSubmit');
    btn.disabled = true;
    btn.textContent = 'Saving...';
    try {
      const label = $('#saveSearchLabel').value.trim();
      await pers.createAlert({ filters, label: label || null, notify_push: true, notify_inapp: true });
      showToast('Alert saved. We\'ll watch for new matches.');
      close();
      openPanel({ tab: 'alerts' });
    } catch (err) {
      console.error(err);
      showToast(err?.message || 'Could not save alert.', { tone: 'error' });
      btn.disabled = false;
      btn.textContent = 'Save alert';
    }
  });
}

function formatFiltersSummary(filters) {
  const parts = [];
  if (filters.bedrooms && filters.bedrooms_max && filters.bedrooms_max !== filters.bedrooms) {
    parts.push(`${filters.bedrooms}-${filters.bedrooms_max} bed`);
  } else if (filters.bedrooms) {
    parts.push(`${filters.bedrooms} bed`);
  }
  if (filters.property_type) parts.push(filters.property_type);
  if (filters.area) parts.push(`in ${filters.area}`);
  else if (filters.city) parts.push(`in ${filters.city[0].toUpperCase() + filters.city.slice(1)}`);
  if (filters.price_min && filters.price_max) {
    parts.push(`${Math.round(filters.price_min / 1000)}K–${Math.round(filters.price_max / 1000)}K PKR`);
  } else if (filters.price_max) {
    parts.push(`under ${Math.round(filters.price_max / 1000)}K PKR`);
  } else if (filters.price_min) {
    parts.push(`over ${Math.round(filters.price_min / 1000)}K PKR`);
  }
  if (filters.furnished) parts.push('furnished');
  return parts.join(' ');
}

// ── Panel scaffolding ───────────────────────────────────────────────────────

function buildDOM() {
  if (_panel) return;
  const el = document.createElement('div');
  el.id = 'personalizationPanel';
  el.className = 'hidden';
  el.setAttribute('role', 'dialog');
  el.setAttribute('aria-modal', 'true');
  el.setAttribute('aria-labelledby', 'personalizationTitle');
  el.innerHTML = `
    <div class="personalization-backdrop fixed inset-0 bg-black/40 z-[270]"></div>
    <div class="personalization-drawer fixed top-0 right-0 bottom-0 z-[271] w-[420px] max-w-[100vw] bg-white shadow-2xl flex flex-col">
      <header class="flex items-center justify-between px-5 py-4 border-b border-gray-200">
        <div>
          <h2 id="personalizationTitle" class="text-lg font-bold text-gray-800">My rentals</h2>
          <p class="text-xs text-gray-500 mt-0.5">Your alerts and saved homes</p>
        </div>
        <button id="personalizationClose" class="w-8 h-8 rounded-full hover:bg-gray-100 flex items-center justify-center text-gray-400 hover:text-gray-600 text-xl" aria-label="Close">&times;</button>
      </header>
      <div id="personalizationTabs" class="flex border-b border-gray-100 bg-gray-50">
        ${TABS.map(t => `
          <button class="personalization-tab flex-1 py-3 px-1 text-[11px] sm:text-xs font-semibold text-gray-500 hover:text-brand-600 transition-colors relative" data-ptab="${t.id}">
            <span class="capitalize">${t.label}</span>
            <span class="ptab-badge hidden absolute top-1.5 right-1/4 text-[10px] font-bold bg-brand-500 text-white px-1.5 py-0.5 rounded-full"></span>
          </button>
        `).join('')}
      </div>
      <div id="personalizationBody" class="flex-1 overflow-y-auto p-4"></div>
    </div>
  `;
  document.body.appendChild(el);
  _panel = el;

  el.querySelector('.personalization-backdrop').addEventListener('click', closePanel);
  el.querySelector('#personalizationClose').addEventListener('click', closePanel);

  el.querySelectorAll('.personalization-tab').forEach(btn => {
    btn.addEventListener('click', () => switchTab(btn.dataset.ptab));
  });
}

export async function openPanel({ tab = 'alerts' } = {}) {
  if (!_panel) buildDOM();
  const active = document.activeElement;
  if (active && active !== document.body) _lastTrigger = active;
  _panel.classList.remove('hidden');
  await switchTab(tab);
}

function closePanel() {
  if (!_panel) return;
  _panel.classList.add('hidden');
  if (_lastTrigger && typeof _lastTrigger.focus === 'function') _lastTrigger.focus();
  _lastTrigger = null;
}

async function switchTab(tab) {
  _activeTab = tab;
  if (!_panel) return;
  _panel.querySelectorAll('.personalization-tab').forEach(btn => {
    btn.classList.toggle('text-brand-600', btn.dataset.ptab === tab);
    btn.classList.toggle('border-b-2', btn.dataset.ptab === tab);
    btn.classList.toggle('border-brand-500', btn.dataset.ptab === tab);
  });
  const body = $('#personalizationBody');
  body.innerHTML = '<div class="py-8 text-center text-sm text-gray-400">Loading…</div>';
  try {
    if (tab === 'alerts') await renderAlertsTab(body);
    else if (tab === 'favorites') await renderFavoritesTab(body);
    else if (tab === 'hidden') await renderHiddenTab(body);
    else if (tab === 'recent') await renderRecentTab(body);
  } catch (err) {
    console.error(err);
    body.innerHTML = `<div class="py-8 text-center text-sm text-rose-500">${esc(err?.message || 'Failed to load')}</div>`;
  }
}

// ── Alerts tab ──────────────────────────────────────────────────────────────

async function renderAlertsTab(body) {
  const alerts = await pers.listAlerts();
  const matches = await pers.listMatches({ limit: 30 });

  const matchesByAlert = matches.reduce((acc, m) => {
    (acc[m.alert_id] = acc[m.alert_id] || []).push(m);
    return acc;
  }, {});

  if (matches.length) {
    pers.markMatchesSeen({}).catch(() => {});
  }

  const filters = _saveSearchHooks?.getCurrentFilters?.();
  const canSaveCurrent = filters && Object.keys(filters).filter(k => k !== 'city').length > 0;
  const newAlertBtn = `<button id="alertsCreateFromCurrent" class="${canSaveCurrent ? 'inline-flex items-center gap-1.5 text-xs font-semibold text-brand-600 hover:text-brand-700 px-3 py-1.5 border border-brand-200 rounded-full hover:bg-brand-50 transition-colors' : 'inline-flex items-center gap-1.5 text-xs font-semibold text-gray-400 px-3 py-1.5 border border-gray-200 rounded-full cursor-not-allowed'}" ${canSaveCurrent ? '' : 'disabled'} title="${canSaveCurrent ? 'Create an alert for the search you are viewing' : 'Choose filters first, then create an alert'}">+ Alert for this search</button>`;

  let pushStatusHtml = '';
  const pushSupported = pers.isPushSupported();
  const perm = pers.notificationPermission();
  const subscribed = pers.getState().pushSubscriptionCount > 0;
  if (!pushSupported) {
    pushStatusHtml = '<div class="text-xs text-gray-500 px-3 py-2.5 bg-gray-50 border border-gray-200 rounded-lg mb-3">Device notifications aren\'t available in this browser. New matches will still appear here.</div>';
  } else if (perm === 'denied') {
    pushStatusHtml = '<div class="text-xs text-amber-700 px-3 py-2.5 bg-amber-50 border border-amber-200 rounded-lg mb-3">Device notifications are blocked in your browser settings. New matches will still appear here.</div>';
  } else if (perm === 'default') {
    pushStatusHtml = `
      <div class="flex items-center justify-between gap-3 text-xs text-gray-700 px-3 py-2.5 bg-brand-50 border border-brand-200 rounded-lg mb-3">
        <span>Want a heads-up when a new rental matches?</span>
        <button id="alertsEnablePush" class="shrink-0 text-xs font-semibold text-white bg-brand-600 hover:bg-brand-700 px-3 py-1.5 rounded-full transition-colors">Notify me</button>
      </div>
    `;
  } else if (perm === 'granted' && !subscribed) {
    pushStatusHtml = `
      <div class="flex items-center justify-between gap-3 text-xs text-gray-700 px-3 py-2.5 bg-amber-50 border border-amber-200 rounded-lg mb-3">
        <span>Notifications need one quick reconnect on this device.</span>
        <button id="alertsEnablePush" class="shrink-0 text-xs font-semibold text-white bg-brand-600 hover:bg-brand-700 px-3 py-1.5 rounded-full transition-colors">Reconnect</button>
      </div>
    `;
  } else if (perm === 'granted' && subscribed) {
    pushStatusHtml = `
      <div class="flex items-center justify-between gap-3 text-xs text-gray-700 px-3 py-2 bg-emerald-50 border border-emerald-200 rounded-lg mb-3">
        <span>Notifications are on for this device.</span>
        <span class="flex gap-2 shrink-0">
          <button id="alertsTestPush" class="text-xs font-medium text-emerald-700 hover:text-emerald-900 underline">Test</button>
          <button id="alertsDisablePush" class="text-xs font-medium text-gray-500 hover:text-gray-700 underline">Turn off</button>
        </span>
      </div>
    `;
  }

  if (!alerts.length) {
    body.innerHTML = `
      ${pushStatusHtml}
      <div class="flex items-center justify-between mb-4">
        <div class="text-xs uppercase tracking-wide text-gray-400 font-semibold">No alerts yet</div>
        ${newAlertBtn}
      </div>
      <div class="text-center py-10 px-4 border-2 border-dashed border-gray-200 rounded-xl">
        <div class="mb-3 flex justify-center text-gray-300">${bellIcon('w-10 h-10')}</div>
        <p class="text-sm font-semibold text-gray-700">Never miss a matching rental</p>
        <p class="mt-1 text-xs text-gray-500 leading-relaxed">Choose your city and filters, then create an alert for that search. New matches will collect here automatically.</p>
      </div>
    `;
    body.querySelector('#alertsCreateFromCurrent')?.addEventListener('click', () => {
      if (canSaveCurrent) { closePanel(); openSaveSearchDialog(); }
    });
    body.querySelector('#alertsEnablePush')?.addEventListener('click', enablePushClick);
    body.querySelector('#alertsTestPush')?.addEventListener('click', testPushClick);
    body.querySelector('#alertsDisablePush')?.addEventListener('click', disablePushClick);
    return;
  }

  const html = `
    ${pushStatusHtml}
    <div class="flex items-center justify-between mb-4">
      <div class="text-xs uppercase tracking-wide text-gray-400 font-semibold">Your alerts (${alerts.length})</div>
      ${newAlertBtn}
    </div>
    <ul class="space-y-3">
      ${alerts.map(a => renderAlertCard(a, matchesByAlert[a.id] || [])).join('')}
    </ul>
  `;
  body.innerHTML = html;

  body.querySelector('#alertsCreateFromCurrent')?.addEventListener('click', () => {
    if (canSaveCurrent) { closePanel(); openSaveSearchDialog(); }
  });
  body.querySelector('#alertsEnablePush')?.addEventListener('click', enablePushClick);
  body.querySelector('#alertsTestPush')?.addEventListener('click', testPushClick);
  body.querySelector('#alertsDisablePush')?.addEventListener('click', disablePushClick);

  body.querySelectorAll('[data-alert-action]').forEach(btn => {
    btn.addEventListener('click', e => handleAlertAction(btn));
  });
  body.querySelectorAll('[data-open-match]').forEach(el => {
    el.addEventListener('click', () => {
      const url = el.dataset.openMatch;
      if (url) window.open(url, '_blank', 'noopener');
    });
  });
}

function renderAlertCard(alert, matches) {
  const f = alert.filters || {};
  const summary = formatFiltersSummary(f) || 'All rentals';
  const unseenBadge = alert.unseen_count > 0
    ? `<span class="text-[10px] font-bold bg-brand-500 text-white px-2 py-0.5 rounded-full">${alert.unseen_count} new</span>`
    : '';
  const matchesHtml = matches.length
    ? `<ul class="mt-3 pt-3 border-t border-gray-100 space-y-2">
        ${matches.slice(0, 5).map(m => `
          <li class="flex items-center gap-3 text-xs cursor-pointer hover:bg-gray-50 -mx-2 px-2 py-1.5 rounded" data-open-match="${escA(m.url || '')}">
            ${m.image_url ? `<img src="${escA(m.image_url)}" class="w-10 h-10 rounded object-cover shrink-0" alt="" loading="lazy">` : '<div class="w-10 h-10 rounded bg-gray-100 shrink-0"></div>'}
            <div class="flex-1 min-w-0">
              <div class="font-semibold text-gray-800 truncate">${esc(fmtPrice(m.price, m.price_text))}</div>
              <div class="text-gray-500 truncate">${esc(m.title || m.location || '—')}</div>
            </div>
            <div class="text-[10px] text-gray-400 shrink-0">${esc(fmtRelative(m.matched_at) || '')}</div>
          </li>
        `).join('')}
      </ul>`
    : '<div class="mt-3 pt-3 border-t border-gray-100 text-xs text-gray-400">No matches yet — we\'re watching.</div>';
  return `
    <li class="border border-gray-200 rounded-xl p-4 bg-white" data-alert-id="${alert.id}">
      <div class="flex items-start justify-between gap-3">
        <div class="min-w-0 flex-1">
          <div class="flex items-center gap-2 flex-wrap">
            <h3 class="text-sm font-bold text-gray-800 truncate">${esc(alert.label)}</h3>
            ${unseenBadge}
            ${alert.paused ? '<span class="text-[10px] font-semibold text-amber-700 bg-amber-50 px-2 py-0.5 rounded-full">Paused</span>' : ''}
          </div>
          <p class="mt-1 text-xs text-gray-500">${esc(summary)}</p>
        </div>
        <div class="flex items-center gap-1 shrink-0">
          <button data-alert-action="toggle-pause" data-alert-id="${alert.id}" data-paused="${alert.paused ? '1' : '0'}" class="text-xs px-2 py-1 rounded hover:bg-gray-100 text-gray-500 hover:text-gray-700">${alert.paused ? 'Resume' : 'Pause'}</button>
          <button data-alert-action="delete" data-alert-id="${alert.id}" class="text-xs px-2 py-1 rounded hover:bg-rose-50 text-gray-400 hover:text-rose-600">Delete</button>
        </div>
      </div>
      ${matchesHtml}
    </li>
  `;
}

async function handleAlertAction(btn) {
  const id = Number(btn.dataset.alertId);
  const action = btn.dataset.alertAction;
  if (action === 'delete') {
    if (!confirm('Delete this alert?')) return;
    try {
      await pers.deleteAlert(id);
      showToast('Alert deleted.');
      switchTab('alerts');
    } catch (err) { showToast(err.message || 'Delete failed', { tone: 'error' }); }
  } else if (action === 'toggle-pause') {
    const paused = btn.dataset.paused === '1';
    try {
      await pers.updateAlert(id, { paused: !paused });
      switchTab('alerts');
    } catch (err) { showToast(err.message || 'Update failed', { tone: 'error' }); }
  }
}

async function enablePushClick() {
  const btn = $('#alertsEnablePush');
  if (btn) { btn.disabled = true; btn.textContent = 'Requesting…'; }
  const result = await pers.ensurePushSubscription({ requestPermission: true });
  if (result.status === 'granted') {
    showToast('Push notifications enabled.');
  } else if (result.status === 'denied') {
    showToast('Push notifications denied.', { tone: 'error' });
  } else {
    showToast('Could not enable push notifications.', { tone: 'error' });
  }
  switchTab('alerts');
}

async function testPushClick() {
  try {
    const result = await pers.sendTestPush();
    if (result?.sent) showToast(`Test push sent to ${result.sent} device(s).`);
    else showToast('No push subscriptions found.', { tone: 'error' });
  } catch (err) {
    showToast(err.message || 'Test push failed', { tone: 'error' });
  }
}

async function disablePushClick() {
  try {
    await pers.disablePushSubscription();
    showToast('Device notifications turned off.');
    switchTab('alerts');
  } catch (err) {
    showToast(err.message || 'Could not turn off notifications.', { tone: 'error' });
  }
}

// ── Favorites tab ───────────────────────────────────────────────────────────

async function renderFavoritesTab(body) {
  const items = await pers.listFavorites(100);
  if (!items.length) {
    body.innerHTML = emptyState('No saved listings yet', 'Tap the heart on any listing to save it for later.');
    return;
  }
  body.innerHTML = `
    <div class="text-xs uppercase tracking-wide text-gray-400 font-semibold mb-3">Saved (${items.length})</div>
    <ul class="space-y-3">${items.map(renderSavedItem).join('')}</ul>
  `;
  wireListingItemListeners(body);
}

// ── Hidden tab ──────────────────────────────────────────────────────────────

async function renderHiddenTab(body) {
  const items = await pers.listHidden(200);
  if (!items.length) {
    body.innerHTML = emptyState('No hidden listings', 'Hide listings you\'re not interested in to clean up your results.');
    return;
  }
  body.innerHTML = `
    <div class="text-xs uppercase tracking-wide text-gray-400 font-semibold mb-3">Hidden (${items.length})</div>
    <ul class="space-y-3">${items.map(item => renderSavedItem(item, { unhide: true })).join('')}</ul>
  `;
  wireListingItemListeners(body, { unhide: true });
}

// ── Recent tab ──────────────────────────────────────────────────────────────

async function renderRecentTab(body) {
  const items = await pers.listRecentViews(50);
  if (!items.length) {
    body.innerHTML = emptyState('Nothing viewed yet', 'Listings you open will show up here for quick re-access.');
    return;
  }
  body.innerHTML = `
    <div class="text-xs uppercase tracking-wide text-gray-400 font-semibold mb-3">Recently viewed (${items.length})</div>
    <ul class="space-y-3">${items.map(item => renderSavedItem(item, { showWhen: item.viewed_at, removable: false })).join('')}</ul>
  `;
  wireListingItemListeners(body);
}

function renderSavedItem(item, { unhide = false, showWhen = null, removable = true } = {}) {
  const url = escA(item.url || '');
  const price = esc(fmtPrice(item.price, item.price_text));
  const title = esc(item.title || item.location || 'Rental');
  const whenLabel = showWhen ? fmtRelative(showWhen) : (item.saved_at ? `saved ${fmtRelative(item.saved_at)}` : item.hidden_at ? `hidden ${fmtRelative(item.hidden_at)}` : '');
  return `
    <li class="border border-gray-200 rounded-xl p-3 bg-white" data-zameen-id="${escA(item.zameen_id)}">
      <div class="flex gap-3 items-stretch">
        ${item.image_url ? `<img src="${escA(item.image_url)}" class="w-20 h-20 rounded-lg object-cover shrink-0" alt="" loading="lazy">` : '<div class="w-20 h-20 rounded-lg bg-gray-100 shrink-0"></div>'}
        <div class="flex-1 min-w-0">
          <div class="text-sm font-bold text-gray-800">${price}</div>
          <div class="text-xs text-gray-600 truncate mt-0.5">${title}</div>
          ${item.location ? `<div class="text-[11px] text-gray-400 truncate mt-0.5">${esc(item.location)}</div>` : ''}
          <div class="flex items-center gap-2 mt-2 text-[11px]">
            ${url ? `<a href="${url}" target="_blank" rel="noopener" class="text-brand-600 hover:text-brand-700 font-medium">Open</a>` : ''}
            ${unhide
              ? `<button data-personalization-action="unhide" data-zameen-id="${escA(item.zameen_id)}" class="text-gray-500 hover:text-gray-700 font-medium">Unhide</button>`
              : removable
              ? `<button data-personalization-action="remove-favorite" data-zameen-id="${escA(item.zameen_id)}" class="text-rose-500 hover:text-rose-700 font-medium">Remove</button>`
              : ''
            }
            ${whenLabel ? `<span class="text-gray-400 ml-auto">${esc(whenLabel)}</span>` : ''}
          </div>
        </div>
      </div>
    </li>
  `;
}

function wireListingItemListeners(body, { unhide = false } = {}) {
  body.querySelectorAll('[data-personalization-action]').forEach(btn => {
    btn.addEventListener('click', async () => {
      const id = btn.dataset.zameenId;
      const action = btn.dataset.personalizationAction;
      try {
        if (action === 'remove-favorite') {
          await pers.removeFavorite(id);
          showToast('Removed from favorites.');
          switchTab('favorites');
        } else if (action === 'unhide') {
          await pers.removeHidden(id);
          showToast('Unhidden.');
          switchTab('hidden');
        }
        _saveSearchHooks?.refreshSearch?.();
      } catch (err) {
        showToast(err.message || 'Action failed', { tone: 'error' });
      }
    });
  });
}

function emptyState(title, body) {
  return `
    <div class="text-center py-12 px-4 border-2 border-dashed border-gray-200 rounded-xl">
      <p class="text-sm font-semibold text-gray-700">${esc(title)}</p>
      <p class="mt-1 text-xs text-gray-500 leading-relaxed">${esc(body)}</p>
    </div>
  `;
}
