/** Search report (paid): rent levels, stock and new listings for this
 *  renter's own searches, with suggestions. Opened from the My rentals panel.
 *
 *  Also exports the small modal and credits helpers that tailored.js uses,
 *  so the two paid AI features look and behave the same.
 */
import { esc } from './utils.js';
import { getClientId } from './personalization.js';
import { paidFetch } from './credits-gate.js';

// ── Shared helpers (used by tailored.js) ─────────────────────────────────────

export function newIdempotencyKey() {
  if (crypto.randomUUID) return crypto.randomUUID();
  const bytes = crypto.getRandomValues(new Uint8Array(16));
  return Array.from(bytes, b => b.toString(16).padStart(2, '0')).join('');
}

/** GET /api/credits, or null. Costs and balance come from the server, never hard-coded. */
export async function fetchCredits() {
  try {
    const r = await fetch('/api/credits', { headers: { 'X-Client-Id': getClientId() } });
    return r.ok ? await r.json() : null;
  } catch { return null; }
}

export const creditAmount = n => `${n} credit${n === 1 ? '' : 's'}`;

export function costText(cost, balance) {
  if (cost == null) return 'Uses credits from your balance.';
  return `Uses ${creditAmount(cost)}.` + (balance != null ? ` You have ${balance}.` : '');
}

export function insufficientText(detail = {}) {
  const need = detail.cost != null ? creditAmount(detail.cost) : 'more credits';
  const have = detail.balance != null ? ` and have ${detail.balance}` : '';
  return `You need ${need}${have}. Add credits to continue.`;
}

export const spinner = '<svg class="w-4 h-4 animate-spin shrink-0" viewBox="0 0 24 24" fill="none" aria-hidden="true"><circle cx="12" cy="12" r="9" stroke="currentColor" stroke-opacity=".25" stroke-width="3"/><path d="M21 12a9 9 0 00-9-9" stroke="currentColor" stroke-width="3" stroke-linecap="round"/></svg>';

const FOCUSABLE = 'button:not([disabled]), textarea:not([disabled]), input:not([disabled]), a[href], [tabindex]:not([tabindex="-1"])';

/** A bottom sheet on phones, a centred dialog on larger screens. `layer`
 *  'below-drawer' lets the listing drawer open on top; 'above-panel' sits
 *  over the My rentals panel. */
export function createModal({ id, title, subtitle, layer = 'below-drawer' }) {
  const above = layer === 'above-panel';
  const root = document.createElement('div');
  root.id = id;
  root.className = 'hidden';
  root.innerHTML = `
    <div data-ai-backdrop class="fixed inset-0 bg-black/40 ${above ? 'z-[290]' : 'z-[190]'}"></div>
    <div role="dialog" aria-modal="true" aria-labelledby="${id}Title" class="fixed ${above ? 'z-[291]' : 'z-[191]'} inset-x-0 bottom-0 sm:bottom-auto sm:left-1/2 sm:top-1/2 sm:-translate-x-1/2 sm:-translate-y-1/2 w-full sm:w-[560px] max-h-[92dvh] sm:max-h-[86vh] bg-white rounded-t-2xl sm:rounded-2xl shadow-2xl flex flex-col">
      <header class="flex items-start justify-between gap-3 px-5 pt-4 pb-3 border-b border-gray-100">
        <div class="min-w-0">
          <h2 id="${id}Title" class="text-base font-bold text-gray-800">${esc(title)}</h2>
          <p class="text-xs text-gray-500 mt-0.5">${esc(subtitle)}</p>
        </div>
        <button type="button" data-ai-close class="w-9 h-9 -mr-2 rounded-full hover:bg-gray-100 flex items-center justify-center text-gray-400 hover:text-gray-600 text-xl shrink-0" aria-label="Close">&times;</button>
      </header>
      <div data-ai-body class="flex-1 overflow-y-auto overscroll-contain px-5 py-4"></div>
    </div>`;
  document.body.appendChild(root);
  const dialog = root.querySelector('[role="dialog"]');
  let trigger = null;

  const modal = {
    root,
    body: root.querySelector('[data-ai-body]'),
    isOpen: () => !root.classList.contains('hidden'),
    open() {
      trigger = document.activeElement;
      root.classList.remove('hidden');
      const first = dialog.querySelector('[data-autofocus]') || dialog.querySelector(FOCUSABLE);
      first?.focus();
    },
    close() {
      root.classList.add('hidden');
      if (trigger && document.contains(trigger)) trigger.focus?.();
      trigger = null;
    },
  };
  root.querySelector('[data-ai-backdrop]').addEventListener('click', modal.close);
  root.querySelector('[data-ai-close]').addEventListener('click', modal.close);
  dialog.addEventListener('keydown', e => {
    if (e.key === 'Escape') {
      e.stopPropagation(); // don't also close the My rentals panel underneath
      modal.close();
    } else if (e.key === 'Tab') {
      const items = [...dialog.querySelectorAll(FOCUSABLE)].filter(el => el.offsetParent !== null);
      if (!items.length) return;
      const first = items[0], last = items[items.length - 1];
      if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus(); }
      else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
    }
  });
  return modal;
}

export const pkr = n => 'PKR ' + Number(n).toLocaleString('en-US');

// ── Search report ────────────────────────────────────────────────────────────

let _modal = null;
let _idemKey = null;

function plural(n, word) { return `${n} ${word}${n === 1 ? '' : 's'}`; }

function activityText(a = {}) {
  const parts = [];
  if (a.alerts) parts.push(plural(a.alerts, 'alert'));
  if (a.favorites) parts.push(plural(a.favorites, 'saved home'));
  if (a.recent_views) parts.push(plural(a.recent_views, 'opened home'));
  if (a.hidden) parts.push(plural(a.hidden, 'hidden home'));
  return parts.join(', ');
}

function stat(label, value) {
  return `<div class="rounded-lg bg-gray-50 px-3 py-2"><dt class="text-[11px] text-gray-500">${esc(label)}</dt><dd class="text-sm font-semibold text-gray-800">${esc(value)}</dd></div>`;
}

function renderSection(s) {
  const st = s.stats || {};
  const tiles = [stat('Homes now', String(st.matching ?? 0))];
  if (st.rent) {
    tiles.push(stat('Median rent', pkr(st.rent.median)));
    tiles.push(stat('Middle half of rents', `${pkr(st.rent.p25)} to ${pkr(st.rent.p75)}`));
  }
  if (st.rent_per_marla_median) tiles.push(stat('Median rent per marla', pkr(st.rent_per_marla_median)));
  tiles.push(stat('New in the last 7 days', String(st.first_seen_last_7_days ?? 0)));
  if (st.size_marla_median) tiles.push(stat('Median size', `${st.size_marla_median} marla`));

  const lists = [];
  if (st.budget_steps?.length) {
    lists.push(`<h5 class="text-xs font-semibold text-gray-600 mt-3">If you raise your budget</h5>
      <ul class="text-sm text-gray-700 mt-1 space-y-0.5">${st.budget_steps.map(b =>
        `<li>+${b.pct}% (${esc(pkr(b.budget))}): ${b.matching} homes</li>`).join('')}</ul>`);
  }
  const areas = st.nearby_areas?.length ? st.nearby_areas : st.top_areas;
  if (areas?.length) {
    lists.push(`<h5 class="text-xs font-semibold text-gray-600 mt-3">${st.nearby_areas?.length ? 'Nearby areas with similar rent' : 'Where the homes are'}</h5>
      <ul class="text-sm text-gray-700 mt-1 space-y-0.5">${areas.map(a =>
        `<li>${esc(a.area)}${a.km != null ? ` (${a.km} km)` : ''}: ${a.count} homes, median ${esc(pkr(a.median))}</li>`).join('')}</ul>`);
  }
  return `
    <li class="border border-gray-200 rounded-xl p-3">
      <div class="text-[11px] text-gray-500">${esc(s.label)}</div>
      <div class="text-sm font-semibold text-gray-800">${esc(s.criteria_text)}</div>
      <dl class="grid grid-cols-2 gap-2 mt-2">${tiles.join('')}</dl>
      ${lists.join('')}
    </li>`;
}

function renderResult(data) {
  const r = data.report || {};
  const charge = data.charged ? `Used ${creditAmount(data.cost)}.` : (data.cached ? 'Made in the last few minutes, so no credits were used.' : '');
  const when = data.generated_at ? new Date(data.generated_at).toLocaleString() : '';
  _modal.body.innerHTML = `
    <div data-report-result>
      <h3 class="text-base font-bold text-gray-800">${esc(r.headline || 'Your search report')}</h3>
      <p class="text-sm text-gray-700 mt-1.5">${esc(r.summary || '')}</p>
      ${r.suggestions?.length ? `
        <h4 class="text-sm font-semibold text-gray-800 mt-4">Suggestions</h4>
        <ul class="mt-1.5 space-y-2">${r.suggestions.map(sg => `
          <li class="text-sm text-gray-700"><span class="font-semibold text-gray-800">${esc(sg.title)}.</span> ${esc(sg.detail)}</li>`).join('')}
        </ul>` : ''}
      <h4 class="text-sm font-semibold text-gray-800 mt-4">The numbers</h4>
      <ul class="mt-1.5 space-y-3">${(data.sections || []).map(renderSection).join('')}</ul>
      <p class="text-[11px] text-gray-500 mt-4">Figures come from active listings in the ZameenRentals index, sourced from Zameen.com. "New" counts listings by when our index first saw them, not their posting date. Listings can be gone or out of date.${when ? ` Made ${esc(when)}.` : ''}</p>
      ${charge ? `<p class="text-[11px] text-gray-500 mt-1">${esc(charge)}</p>` : ''}
    </div>`;
}

function renderReady(info, credits) {
  const cost = credits?.costs?.search_report ?? info.cost;
  const balance = credits?.balance ?? info.balance;
  _modal.body.innerHTML = `
    <p class="text-sm text-gray-700">We'll look at rent levels, how many homes match, how many new ones arrive each week and nearby areas, for the searches behind your activity on this device: ${esc(activityText(info.activity))}.</p>
    <p data-report-cost class="text-xs text-gray-500 mt-3">${esc(costText(cost, balance))}</p>
    <div data-report-error role="alert" class="hidden text-sm text-rose-600 mt-3"></div>
    <div class="flex justify-end mt-4">
      <button type="button" data-report-run data-autofocus class="inline-flex items-center gap-2 px-5 py-2.5 text-sm font-semibold text-white bg-brand-600 hover:bg-brand-700 rounded-lg transition-colors disabled:opacity-60">Make my report</button>
    </div>
    <p data-report-status class="sr-only" aria-live="polite"></p>`;
  _modal.body.querySelector('[data-report-run]').addEventListener('click', runReport);
}

async function runReport() {
  const btn = _modal.body.querySelector('[data-report-run]');
  const errBox = _modal.body.querySelector('[data-report-error]');
  const status = _modal.body.querySelector('[data-report-status]');
  btn.disabled = true;
  btn.innerHTML = `${spinner}<span>Working out the numbers…</span>`;
  status.textContent = 'Making your report';
  errBox.classList.add('hidden');
  _idemKey = _idemKey || newIdempotencyKey();
  try {
    const data = await paidFetch('/api/ai/report', {
      method: 'POST', body: JSON.stringify({}), headers: { 'Idempotency-Key': _idemKey },
    });
    _idemKey = null;
    renderResult(data);
  } catch (err) {
    errBox.textContent = err.insufficientCredits ? insufficientText(err.detail) : (err.message || 'Something went wrong.');
    errBox.classList.remove('hidden');
    btn.disabled = false;
    btn.textContent = 'Try again';
    status.textContent = '';
  }
}

export async function openReport() {
  if (!_modal) {
    _modal = createModal({
      id: 'searchReportModal', title: 'Search report', layer: 'above-panel',
      subtitle: 'Rent levels and stock for what you have been looking at, with suggestions',
    });
  }
  _modal.body.innerHTML = `<div class="py-8 flex items-center justify-center gap-2 text-sm text-gray-500">${spinner}<span>Checking your activity…</span></div>`;
  _modal.open();
  try {
    const [resp, credits] = await Promise.all([
      fetch('/api/ai/report/eligibility', { headers: { 'X-Client-Id': getClientId() } }),
      fetchCredits(),
    ]);
    if (!resp.ok) throw new Error('Could not check your activity. Try again.');
    const info = await resp.json();
    if (!info.eligible) {
      _modal.body.innerHTML = `
        <div data-report-ineligible class="text-sm text-gray-700">
          <p>${esc(info.reason)}</p>
          <p class="text-xs text-gray-500 mt-3">No credits were used.</p>
        </div>`;
      return;
    }
    renderReady(info, credits);
    _modal.body.querySelector('[data-report-run]')?.focus();
  } catch (err) {
    _modal.body.innerHTML = `<p role="alert" class="text-sm text-rose-600">${esc(err.message || 'Something went wrong.')}</p>`;
  }
}

/** Adds a "Search report" button to the My rentals panel header when the
 *  panel is first built (personalization-ui.js mounts it lazily). */
export function initReport() {
  const attach = () => {
    const title = document.getElementById('personalizationTitle');
    if (!title || document.getElementById('searchReportBtn')) return !!title;
    const btn = document.createElement('button');
    btn.type = 'button';
    btn.id = 'searchReportBtn';
    btn.className = 'mt-1.5 inline-flex items-center gap-1 text-xs font-semibold text-brand-600 hover:text-brand-700 underline-offset-2 hover:underline';
    btn.innerHTML = `<svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 17v-6m4 6V7m4 10v-3M5 21h14"/></svg><span>Search report</span>`;
    btn.setAttribute('aria-label', 'Search report: rent levels and stock for your searches. Uses credits.');
    btn.addEventListener('click', openReport);
    title.parentElement.appendChild(btn);
    return true;
  };
  if (attach()) return;
  const observer = new MutationObserver(() => { if (attach()) observer.disconnect(); });
  observer.observe(document.body, { childList: true });
}

