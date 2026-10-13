/** Daily shortlists on a saved search, charged when new matches are delivered.
 *
 *  Mounted into each alert card in My rentals (`[data-alert-upgrades]`
 *  slots rendered by personalization-ui.js). Costs and balance come from
 *  GET /api/alerts/upgrades; nothing here hard-codes a price. Toggles go
 *  through paidFetch, so a 402 fires `zr:insufficient-credits` (the
 *  payments track opens its top-up sheet) and we show a short inline note.
 */

import { esc, escA, fmtPrice } from './utils.js';
import { getClientId } from './personalization.js';
import { paidFetch } from './credits-gate.js';

const SHORTLIST = 'daily_shortlist_day';

const COPY = {
  [SHORTLIST]: {
    title: 'Daily shortlist',
    body: hour => `Once a day from ${fmtHour(hour)}, up to 5 new matches from the last 24 hours, each with a short reason. Days with no new matches are free.`,
  },
};

let _root = null;
let _state = null;
const _wiredRoots = new WeakSet();
let _creditsListener = false;

// ── Public entry ────────────────────────────────────────────────────────────

export async function mountAlertUpgrades(root) {
  const slots = root.querySelectorAll('[data-alert-upgrades]');
  if (!slots.length) return;
  _root = root;
  wireRoot(root);
  try {
    _state = await getState();
  } catch (err) {
    console.warn('alert upgrades unavailable', err);
    return; // Free alerts render as before; paid extras simply don't show.
  }
  renderAll();
  openDeepLinkedShortlist();
}

// ── Data ────────────────────────────────────────────────────────────────────

async function getState() {
  const resp = await fetch('/api/alerts/upgrades', { headers: { 'X-Client-Id': getClientId() } });
  if (!resp.ok) throw new Error(`Request failed (${resp.status})`);
  return resp.json();
}

async function getShortlists(alertId) {
  const resp = await fetch(`/api/alerts/${alertId}/shortlists?limit=1`, { headers: { 'X-Client-Id': getClientId() } });
  if (!resp.ok) throw new Error(`Request failed (${resp.status})`);
  return (await resp.json()).shortlists || [];
}

async function dismissNotice(id) {
  await fetch('/api/alerts/upgrades/notices/seen', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'X-Client-Id': getClientId() },
    body: JSON.stringify({ ids: [id] }),
  });
}

// ── Rendering ───────────────────────────────────────────────────────────────

function renderAll() {
  if (!_root || !_state) return;
  renderSummary();
  _root.querySelectorAll('[data-alert-upgrades]').forEach(slot => renderSlot(slot));
}

function credits(n) {
  return `${n} credit${n === 1 ? '' : 's'}`;
}

function fmtHour(h) {
  if (h === 0) return '12 am';
  if (h === 12) return '12 pm';
  return h < 12 ? `${h} am` : `${h - 12} pm`;
}

function fmtDay(day) {
  if (!day) return '';
  if (day === _state?.today) return 'today';
  const d = new Date(`${day}T12:00:00`);
  if (Number.isNaN(d.getTime())) return day;
  return d.toLocaleDateString('en-GB', { day: 'numeric', month: 'short' });
}

function renderSummary() {
  let el = _root.querySelector('#alertUpgradesSummary');
  const list = _root.querySelector('[data-alert-upgrades]')?.closest('ul');
  if (!el && list) {
    el = document.createElement('p');
    el.id = 'alertUpgradesSummary';
    el.className = 'text-xs text-gray-600 px-3 py-2.5 bg-gray-50 border border-gray-200 rounded-lg mb-3';
    el.setAttribute('aria-live', 'polite');
    list.before(el);
  }
  if (!el) return;
  const { balance, daily_cost: cost } = _state;
  el.textContent = cost
    ? `Daily shortlists use up to ${credits(cost)} a day across your enabled searches. Your balance: ${credits(balance)}.`
    : `Daily shortlists are optional. Your balance: ${credits(balance)}.`;
}

function renderSlot(slot) {
  const alertId = slot.dataset.alertUpgrades;
  const info = _state.alerts?.[alertId];
  if (!info) { slot.innerHTML = ''; return; }
  const notices = (_state.notices || []).filter(n => String(n.alert_id) === String(alertId));
  const latest = info.latest_shortlist;
  slot.innerHTML = `
    <section class="mt-3 pt-3 border-t border-gray-100" aria-labelledby="upg-head-${alertId}">
      <h4 id="upg-head-${alertId}" class="text-[11px] font-semibold uppercase tracking-wide text-gray-500 mb-1">Paid extras</h4>
      ${info.paused ? '<p class="text-xs text-gray-500 mb-1">Resume this alert to use paid extras. Paused alerts aren\'t charged.</p>' : ''}
      ${notices.map(n => renderNotice(n)).join('')}
      <ul class="divide-y divide-gray-100">
        ${[SHORTLIST].map(key => renderToggle(alertId, key, info)).join('')}
      </ul>
      <p class="upg-msg text-xs text-rose-600 empty:hidden mt-1" role="status" aria-live="polite"></p>
      ${latest ? renderShortlistButton(alertId, latest) : ''}
      <div id="upg-shortlist-${alertId}" class="upg-shortlist hidden mt-2"></div>
    </section>
  `;
}

function renderNotice(n) {
  const what = COPY[n.upgrade]?.title || 'A paid extra';
  return `
    <div class="flex items-start justify-between gap-2 text-xs text-amber-800 bg-amber-50 border border-amber-200 rounded-lg px-3 py-2 my-1.5">
      <span>${esc(what)} was switched off ${esc(fmtDay(n.day))} because your credits ran out.</span>
      <button type="button" data-upg-dismiss="${escA(String(n.id))}" class="shrink-0 font-semibold underline min-h-[24px]">Dismiss</button>
    </div>
  `;
}

function renderToggle(alertId, key, info) {
  const u = info[key] || {};
  const cost = u.cost_per_day ?? _state.costs?.[key] ?? 0;
  const on = !!u.enabled;
  const body = typeof COPY[key].body === 'function' ? COPY[key].body(_state.shortlist_hour ?? 9) : COPY[key].body;
  const meta = `${on ? 'On · ' : ''}${credits(cost)} per day with new matches, for this search. Stop at any time.`;
  const titleId = `upg-t-${alertId}-${key}`;
  const descId = `upg-d-${alertId}-${key}`;
  const disabled = info.paused && !on;
  return `
    <li class="flex items-start gap-3 py-2">
      <div class="flex-1 min-w-0">
        <div id="${titleId}" class="text-sm font-semibold text-gray-800">${esc(COPY[key].title)}</div>
        <p id="${descId}" class="text-xs text-gray-500 leading-relaxed mt-0.5">${esc(body)}</p>
        <p class="text-[11px] font-medium ${on ? 'text-emerald-700' : 'text-gray-600'} mt-1" data-upg-meta>${esc(meta)}</p>
      </div>
      <button type="button" role="switch" aria-checked="${on}" aria-labelledby="${titleId}" aria-describedby="${descId}"
        data-upg-toggle="${escA(key)}" data-alert-id="${escA(String(alertId))}" ${disabled ? 'disabled' : ''}
        class="shrink-0 min-w-[44px] min-h-[44px] -mr-1 flex items-center justify-center rounded-lg focus-visible:outline-2 focus-visible:outline-brand-500 disabled:opacity-40 disabled:cursor-not-allowed">
        <span class="relative inline-block w-10 h-6 rounded-full transition-colors ${on ? 'bg-brand-600' : 'bg-gray-300'}">
          <span class="absolute top-0.5 ${on ? 'left-[18px]' : 'left-0.5'} w-5 h-5 rounded-full bg-white shadow transition-all"></span>
        </span>
      </button>
    </li>
  `;
}

function renderShortlistButton(alertId, latest) {
  const label = latest.day === _state.today ? "Today's shortlist" : `Shortlist for ${fmtDay(latest.day)}`;
  return `
    <button type="button" data-upg-shortlist="${escA(String(alertId))}" aria-expanded="false" aria-controls="upg-shortlist-${alertId}"
      class="mt-1 inline-flex items-center gap-2 min-h-[36px] text-xs font-semibold text-brand-700 hover:text-brand-800">
      <span>${esc(label)} (${latest.count})</span>
      ${latest.seen ? '' : '<span class="text-[10px] font-bold bg-brand-500 text-white px-1.5 py-0.5 rounded-full">New</span>'}
    </button>
  `;
}

function renderShortlistItems(container, shortlist) {
  if (!shortlist) {
    container.innerHTML = '<p class="text-xs text-gray-500">No shortlist yet.</p>';
    return;
  }
  const items = shortlist.items || [];
  const note = shortlist.ranked_by === 'fallback' ? 'Ordered by newest, then price fit.' : 'Ranked for this alert.';
  container.innerHTML = `
    <p class="text-[11px] text-gray-500 mb-2">${esc(`${items.length} of ${shortlist.match_count} new matches from the last 24 hours. ${note}`)}</p>
    <ol class="space-y-2">
      ${items.map(it => {
        const safeUrl = /^https:\/\//.test(it.url || '') ? it.url : '';
        return `
        <li class="flex gap-3 border border-gray-200 rounded-lg p-2.5">
          ${it.image_url ? `<img src="${escA(it.image_url)}" class="w-14 h-14 rounded object-cover shrink-0" alt="" loading="lazy">` : '<div class="w-14 h-14 rounded bg-gray-100 shrink-0"></div>'}
          <div class="flex-1 min-w-0 text-xs">
            <div class="font-semibold text-gray-800">${esc(fmtPrice(it.price, it.price_text))}</div>
            <div class="text-gray-600 truncate">${esc(it.title || it.location || 'Rental')}</div>
            ${it.reason ? `<p class="mt-1 text-gray-700">${esc(it.reason)}</p>` : ''}
            ${it.trade_off ? `<p class="mt-0.5 text-gray-500">Trade-off: ${esc(it.trade_off)}</p>` : ''}
            ${safeUrl ? `<a href="${escA(safeUrl)}" target="_blank" rel="noopener" class="inline-block mt-1 font-medium text-brand-600 hover:text-brand-700">Open on Zameen.com</a>` : ''}
          </div>
        </li>`;
      }).join('')}
    </ol>
  `;
}

// ── Interaction ─────────────────────────────────────────────────────────────

function wireRoot(root) {
  if (!_creditsListener) {
    _creditsListener = true;
    // A top-up elsewhere (payments track) changes what the balance covers.
    window.addEventListener('zr:credits-changed', () => {
      if (_root?.isConnected && _root.querySelector('[data-alert-upgrades]')) {
        getState().then(s => { _state = s; renderAll(); }).catch(() => {});
      }
    });
  }
  if (_wiredRoots.has(root)) return;
  _wiredRoots.add(root);
  root.addEventListener('click', e => {
    const toggle = e.target.closest('[data-upg-toggle]');
    if (toggle) { onToggle(toggle); return; }
    const sl = e.target.closest('[data-upg-shortlist]');
    if (sl) { onShortlist(sl); return; }
    const dismiss = e.target.closest('[data-upg-dismiss]');
    if (dismiss) onDismiss(dismiss);
  });
}

function slotFor(alertId) {
  return _root?.querySelector(`[data-alert-upgrades="${CSS.escape(String(alertId))}"]`);
}

async function onToggle(btn) {
  const alertId = btn.dataset.alertId;
  const key = btn.dataset.upgToggle;
  const enable = btn.getAttribute('aria-checked') !== 'true';
  const msg = slotFor(alertId)?.querySelector('.upg-msg');
  if (msg) msg.textContent = '';
  btn.disabled = true;
  btn.setAttribute('aria-busy', 'true');
  try {
    const res = await paidFetch(`/api/alerts/${alertId}/upgrades/${key}`, {
      method: 'POST',
      body: JSON.stringify({ enabled: enable }),
    });
    _state.alerts[alertId] = { ..._state.alerts[alertId], ...res.upgrades };
    _state.balance = res.balance;
    _state.daily_cost = res.daily_cost;
    _state.days_covered = res.days_covered;
    renderAll();
    slotFor(alertId)?.querySelector(`[data-upg-toggle="${key}"]`)?.focus();
  } catch (err) {
    btn.disabled = false;
    btn.removeAttribute('aria-busy');
    if (!msg) return;
    if (err.insufficientCredits) {
      const d = err.detail || {};
      msg.textContent = `Not enough credits. ${COPY[key].title} needs ${credits(d.cost ?? 0)} today; you have ${d.balance ?? 0}.`;
    } else {
      msg.textContent = err.message || 'Could not change this. Try again.';
    }
  }
}

async function onShortlist(btn) {
  const alertId = btn.dataset.upgShortlist;
  const container = slotFor(alertId)?.querySelector('.upg-shortlist');
  if (!container) return;
  const open = btn.getAttribute('aria-expanded') === 'true';
  if (open) {
    btn.setAttribute('aria-expanded', 'false');
    container.classList.add('hidden');
    return;
  }
  btn.setAttribute('aria-expanded', 'true');
  container.classList.remove('hidden');
  container.innerHTML = '<p class="text-xs text-gray-400">Loading…</p>';
  try {
    const [latest] = await getShortlists(alertId);
    renderShortlistItems(container, latest);
    btn.querySelector('.bg-brand-500')?.remove(); // Seen now.
    if (_state.alerts[alertId]?.latest_shortlist) _state.alerts[alertId].latest_shortlist.seen = true;
  } catch (err) {
    container.innerHTML = `<p class="text-xs text-rose-600">${esc(err.message || 'Could not load the shortlist.')}</p>`;
  }
}

async function onDismiss(btn) {
  const id = Number(btn.dataset.upgDismiss);
  btn.disabled = true;
  try { await dismissNotice(id); } catch {}
  _state.notices = (_state.notices || []).filter(n => n.id !== id);
  renderAll();
}

function openDeepLinkedShortlist() {
  const params = new URLSearchParams(location.search);
  if (params.get('shortlist') !== '1') return;
  const alertId = params.get('alert_id');
  const btn = alertId && _root.querySelector(`[data-upg-shortlist="${CSS.escape(alertId)}"]`);
  if (!btn || btn.getAttribute('aria-expanded') === 'true') return;
  onShortlist(btn).then(() => btn.scrollIntoView({ block: 'center' }));
}
