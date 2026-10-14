/** Credits: balance line in My rentals, top-up sheet, checkout return, restore codes.
 *
 *  Packs and prices come from GET /api/credits; nothing here hard-codes them.
 *  The server decides what a pack costs and grants credits only after it has
 *  verified the payment, so this module just asks and shows the answer.
 *
 *  Events:
 *    zr:insufficient-credits  {code, action, balance, cost} → open the sheet
 *    zr:credits-changed                                      → refresh balance
 *    zr:open-topup                                           → open the sheet
 */

import { esc } from './utils.js';
import { getClientId } from './personalization.js';

const POLL_INTERVAL_MS = 1500;
const POLL_ATTEMPTS = 40;

let summary = null;
let sheet = null;
let lastFocus = null;
let pollToken = 0;

// ── API ─────────────────────────────────────────────────────────────────────

async function api(path, { method = 'GET', body } = {}) {
  const headers = { 'X-Client-Id': getClientId() };
  const init = { method, headers };
  if (body !== undefined) {
    headers['Content-Type'] = 'application/json';
    init.body = JSON.stringify(body);
  }
  const resp = await fetch(path, init);
  const data = await resp.json().catch(() => ({}));
  if (!resp.ok) {
    const err = new Error(typeof data.detail === 'string' ? data.detail : `Request failed (${resp.status})`);
    err.status = resp.status;
    throw err;
  }
  return data;
}

async function loadSummary() {
  summary = await api('/api/credits');
  renderBalance();
  return summary;
}

const creditWord = n => (Math.abs(n) === 1 ? 'credit' : 'credits');
const fmtCredits = n => `${Number(n).toLocaleString('en-PK')} ${creditWord(n)}`;
const fmtPkr = n => `PKR ${Number(n).toLocaleString('en-PK')}`;

// ── Balance line in My rentals ──────────────────────────────────────────────

function mountPanelLine() {
  const panel = document.getElementById('personalizationPanel');
  const header = panel?.querySelector('.personalization-drawer > header');
  if (!header || document.getElementById('creditsLine')) return !!header;
  const line = document.createElement('div');
  line.id = 'creditsLine';
  line.className = 'flex items-center justify-between gap-3 px-5 py-2.5 border-b border-gray-100 bg-white text-sm';
  line.innerHTML = `
    <span class="text-gray-600">Balance: <span id="creditsBalance" class="font-semibold text-gray-800">…</span></span>
    <span class="flex items-center gap-3">
      <button type="button" id="creditsRestoreBtn" class="text-xs font-semibold text-gray-500 hover:text-brand-600 hover:underline underline-offset-2">Restore code</button>
      <button type="button" id="creditsTopUpBtn" class="text-xs font-semibold text-white bg-brand-600 hover:bg-brand-700 rounded-full px-3 py-1.5 transition-colors">Top up</button>
    </span>`;
  header.insertAdjacentElement('afterend', line);
  line.querySelector('#creditsTopUpBtn').addEventListener('click', () => openTopUp());
  line.querySelector('#creditsRestoreBtn').addEventListener('click', () => openTopUp({ view: 'restore' }));

  // Load the balance when the panel opens, not on every page load.
  new MutationObserver(() => {
    if (!panel.classList.contains('hidden')) loadSummary().catch(() => {});
  }).observe(panel, { attributes: true, attributeFilter: ['class'] });
  if (!panel.classList.contains('hidden')) loadSummary().catch(() => {});
  return true;
}

function renderBalance() {
  const el = document.getElementById('creditsBalance');
  if (el && summary) el.textContent = fmtCredits(summary.balance);
  const sheetBal = document.getElementById('creditsSheetBalance');
  if (sheetBal && summary) sheetBal.textContent = fmtCredits(summary.balance);
}

// ── Sheet scaffolding (dialog semantics, focus trap, Escape) ────────────────

const FOCUSABLE = 'button:not([disabled]), [href], input:not([disabled]), [tabindex]:not([tabindex="-1"])';

function buildSheet() {
  if (sheet) return sheet;
  sheet = document.createElement('div');
  sheet.id = 'creditsSheet';
  sheet.className = 'hidden fixed inset-0 z-[280]';
  sheet.innerHTML = `
    <div class="credits-backdrop absolute inset-0 bg-black/40"></div>
    <div id="creditsDialog" role="dialog" aria-modal="true" aria-labelledby="creditsSheetTitle" tabindex="-1"
      class="absolute inset-x-0 bottom-0 max-h-[92vh] overflow-y-auto bg-white rounded-t-2xl shadow-2xl p-5 pb-6 outline-none sm:inset-x-auto sm:bottom-auto sm:top-1/2 sm:left-1/2 sm:-translate-x-1/2 sm:-translate-y-1/2 sm:w-[420px] sm:rounded-2xl">
      <div class="flex items-start justify-between gap-3 mb-3">
        <h2 id="creditsSheetTitle" class="text-base font-bold text-gray-800">Top up credits</h2>
        <button type="button" id="creditsSheetClose" class="w-8 h-8 -mt-1 -mr-1 rounded-full hover:bg-gray-100 flex items-center justify-center text-gray-400 hover:text-gray-600 text-xl shrink-0" aria-label="Close">&times;</button>
      </div>
      <div id="creditsSheetBody"></div>
    </div>`;
  document.body.appendChild(sheet);
  sheet.querySelector('.credits-backdrop').addEventListener('click', closeSheet);
  sheet.querySelector('#creditsSheetClose').addEventListener('click', closeSheet);
  // Capture phase so Escape closes only this sheet, not My rentals underneath.
  document.addEventListener('keydown', onSheetKeydown, true);
  return sheet;
}

function isOpen() { return sheet && !sheet.classList.contains('hidden'); }

function onSheetKeydown(e) {
  if (!isOpen()) return;
  if (e.key === 'Escape') {
    e.stopPropagation();
    e.preventDefault();
    closeSheet();
    return;
  }
  if (e.key !== 'Tab') return;
  const items = [...sheet.querySelectorAll(FOCUSABLE)].filter(el => el.offsetParent !== null);
  if (!items.length) return;
  const first = items[0];
  const last = items[items.length - 1];
  const dialog = sheet.querySelector('#creditsDialog');
  if (e.shiftKey && (document.activeElement === first || document.activeElement === dialog)) {
    e.preventDefault(); last.focus();
  } else if (!e.shiftKey && document.activeElement === last) {
    e.preventDefault(); first.focus();
  } else if (!sheet.contains(document.activeElement)) {
    e.preventDefault(); first.focus();
  }
}

function showSheet() {
  buildSheet();
  if (!isOpen()) {
    const active = document.activeElement;
    lastFocus = active && active !== document.body ? active : null;
    sheet.classList.remove('hidden');
  }
}

function closeSheet() {
  if (!sheet) return;
  pollToken++;
  sheet.classList.add('hidden');
  if (lastFocus && document.contains(lastFocus) && typeof lastFocus.focus === 'function') lastFocus.focus();
  lastFocus = null;
}

function setView(title, html, focusSelector) {
  showSheet();
  sheet.querySelector('#creditsSheetTitle').textContent = title;
  const body = sheet.querySelector('#creditsSheetBody');
  body.innerHTML = html;
  const target = (focusSelector && body.querySelector(focusSelector)) || body.querySelector(FOCUSABLE)
    || sheet.querySelector('#creditsDialog');
  requestAnimationFrame(() => target.focus());
  return body;
}

// ── Top-up view ─────────────────────────────────────────────────────────────

export async function openTopUp({ need = null, view = 'packs' } = {}) {

  setView('Top up credits', '<p class="py-6 text-center text-sm text-gray-400" role="status">Loading…</p>');
  try {
    await loadSummary();
  } catch (err) {
    setView('Top up credits', `<p class="py-6 text-center text-sm text-rose-600" role="alert">${esc(err.message || 'Could not load packs.')}</p>`);
    return;
  }
  if (view === 'restore') renderRestore();
  else renderPacks(need);
}

function renderPacks(need) {
  const packs = summary.packs || [];
  // The balance we just loaded is fresher than the one in the 402 detail.
  const balance = Number(summary.balance ?? need?.balance ?? 0);
  const cost = Number(need?.cost || 0);
  const shortBy = Math.max(0, cost - balance);
  const preferred = packs.find(p => p.credits >= shortBy && p.id === 'standard')
    || packs.find(p => p.credits >= shortBy) || packs[packs.length - 1];

  const needNote = cost
    ? `<p class="mb-3 rounded-xl bg-amber-50 border border-amber-200 px-3 py-2 text-sm text-amber-900" id="creditsNeedNote">
         This needs ${esc(fmtCredits(cost))}. You have ${esc(fmtCredits(balance))}.
       </p>`
    : '';
  const unavailable = !summary.checkout_available;

  const body = setView('Top up credits', `
    ${needNote}
    ${summary.starter_pending ? '<p id="creditsStarterNote" class="mb-3 text-sm text-gray-600">Free-credit claims from this network have reached today’s limit. Try again after 5 am Pakistan time. Search and the free features still work.</p>' : ''}
    <p class="text-sm text-gray-600 mb-3">Balance: <strong id="creditsSheetBalance" class="text-gray-800">${esc(fmtCredits(summary.balance))}</strong></p>
    <fieldset>
      <legend class="text-xs font-semibold text-gray-500 mb-2">Buy credits</legend>
      <div class="flex flex-col gap-2">
        ${packs.map(p => `
          <label class="credits-pack flex items-center gap-3 rounded-xl border border-gray-200 px-3 py-3 cursor-pointer hover:border-brand-400 has-[:checked]:border-brand-500 has-[:checked]:bg-brand-50">
            <input type="radio" name="creditsPack" value="${esc(p.id)}" class="accent-brand-600 w-4 h-4" ${p === preferred ? 'checked' : ''}>
            <span class="flex-1 text-sm font-semibold text-gray-800">${esc(fmtCredits(p.credits))}</span>
            <span class="text-sm text-gray-600">${esc(fmtPkr(p.price_pkr))}</span>
          </label>`).join('')}
      </div>
    </fieldset>
    <p class="mt-3 text-sm font-semibold text-gray-700">Pay once. Nothing renews.</p>
    <p class="mt-1 text-xs text-gray-500 leading-relaxed">One credit pays for one Tailored list, one Search report, or one day of Daily shortlist for one saved search with new matches. Credits never expire.</p>
    <p class="mt-2 text-xs"><a href="/pricing" target="_blank" rel="noopener" title="Opens in a new tab" aria-label="Pricing and how credits work, opens in a new tab" class="text-brand-700 underline">Pricing and how credits work <span aria-hidden="true">↗</span></a> · <a href="/terms#refunds" target="_blank" rel="noopener" aria-label="Refunds, opens in a new tab" class="text-brand-700 underline">Refunds <span aria-hidden="true">↗</span></a></p>
    <p id="creditsCheckoutError" class="mt-3 text-sm text-rose-600 ${unavailable ? '' : 'hidden'}" role="alert">${unavailable ? 'Payments are not open yet.' : ''}</p>
    <button type="button" id="creditsCheckoutBtn" class="mt-4 w-full py-3 text-sm font-semibold text-white bg-brand-600 hover:bg-brand-700 rounded-xl transition-colors disabled:opacity-50 disabled:cursor-not-allowed" ${unavailable ? 'disabled' : ''}>Continue to payment</button>
    <button type="button" id="creditsShowRestore" class="mt-3 w-full py-2 text-sm font-semibold text-gray-600 hover:text-brand-600">Have a restore code?</button>
  `, 'input[name="creditsPack"]:checked');

  body.querySelector('#creditsShowRestore').addEventListener('click', () => renderRestore());
  body.querySelector('#creditsCheckoutBtn').addEventListener('click', async () => {
    const btn = body.querySelector('#creditsCheckoutBtn');
    const errEl = body.querySelector('#creditsCheckoutError');
    const packId = body.querySelector('input[name="creditsPack"]:checked')?.value;
    if (!packId) return;
    btn.disabled = true;
    btn.textContent = 'Opening checkout…';
    errEl.classList.add('hidden');
    try {
      const { checkout_url: url } = await api('/api/credits/checkout', { method: 'POST', body: { pack_id: packId } });
      window.location.assign(url);
    } catch (err) {
      errEl.textContent = err.status === 503 ? 'Payments are not open yet.' : (err.message || 'Could not open checkout.');
      errEl.classList.remove('hidden');
      btn.disabled = false;
      btn.textContent = 'Continue to payment';
    }
  });
}

// ── Restore view ────────────────────────────────────────────────────────────

function renderRestore() {
  const body = setView('Restore credits', `
    <p class="text-sm text-gray-600 leading-relaxed mb-3">Bought credits on another phone or browser? Enter the restore code you were shown after paying. The credits you bought move to this device.</p>
    <form id="creditsRestoreForm" novalidate>
      <label for="creditsRestoreInput" class="block text-xs font-semibold text-gray-600 mb-1">Restore code</label>
      <input id="creditsRestoreInput" type="text" autocomplete="off" autocapitalize="characters" spellcheck="false"
        maxlength="24" placeholder="XXXX-XXXX-XXXX-XXXX" aria-describedby="creditsRestoreMsg"
        class="w-full px-3 py-2.5 font-mono tracking-wider text-base border border-gray-200 rounded-lg outline-none focus:border-brand-500 focus:ring-2 focus:ring-brand-100">
      <p id="creditsRestoreMsg" class="mt-2 text-sm min-h-[1.25rem]" aria-live="polite"></p>
      <button type="submit" id="creditsRestoreSubmit" class="mt-2 w-full py-3 text-sm font-semibold text-white bg-brand-600 hover:bg-brand-700 rounded-xl transition-colors disabled:opacity-50">Restore credits</button>
    </form>
    ${summary?.can_issue_restore_code ? `<div class="mt-4 border-t border-gray-100 pt-4">
      <p class="text-xs text-gray-600">Need a code for credits on this device? Creating a new code replaces the old one.</p>
      <button type="button" id="creditsNewCode" class="mt-2 w-full py-2 text-sm font-semibold text-brand-700">Create a new restore code</button>
      <p id="creditsNewCodeMsg" class="text-sm text-rose-600" role="status"></p>
    </div>` : ''}
    <button type="button" id="creditsBackToPacks" class="mt-3 w-full py-2 text-sm font-semibold text-gray-600 hover:text-brand-600">Back to packs</button>
  `, '#creditsRestoreInput');

  body.querySelector('#creditsBackToPacks').addEventListener('click', () => openTopUp());
  body.querySelector('#creditsNewCode')?.addEventListener('click', async e => {
    e.currentTarget.disabled = true;
    try {
      const result = await api('/api/credits/restore-code', { method: 'POST' });
      const view = setView('Your restore code', `
        <p id="creditsRestoreCode" class="font-mono text-lg font-bold tracking-wider break-all select-all">${esc(result.restore_code)}</p>
        <p class="mt-3 text-sm text-gray-600">Copy this code somewhere safe. We show it only once. Your previous code no longer works.</p>
        <button id="creditsDone" type="button" class="mt-5 w-full py-3 text-sm font-semibold text-white bg-brand-600 rounded-xl">Done</button>
      `, '#creditsDone');
      view.querySelector('#creditsDone').addEventListener('click', closeSheet);
    } catch (err) {
      body.querySelector('#creditsNewCodeMsg').textContent = err.message;
      body.querySelector('#creditsNewCode').disabled = false;
    }
  });
  body.querySelector('#creditsRestoreForm').addEventListener('submit', async e => {
    e.preventDefault();
    const input = body.querySelector('#creditsRestoreInput');
    const msg = body.querySelector('#creditsRestoreMsg');
    const btn = body.querySelector('#creditsRestoreSubmit');
    const code = input.value.trim();
    if (!code) { msg.className = 'mt-2 text-sm text-rose-600'; msg.textContent = 'Enter your restore code.'; input.focus(); return; }
    btn.disabled = true;
    msg.className = 'mt-2 text-sm text-gray-500';
    msg.textContent = 'Checking…';
    try {
      const result = await api('/api/credits/restore', { method: 'POST', body: { code } });
      window.dispatchEvent(new CustomEvent('zr:credits-changed'));
      renderRestoreDone(result);
    } catch (err) {
      msg.className = 'mt-2 text-sm text-rose-600';
      msg.textContent = err.status === 429
        ? 'Too many tries. Wait a few minutes and try again.'
        : 'That code didn\'t match. Check it and try again.';
      btn.disabled = false;
      input.focus();
    }
  });
}

function renderRestoreDone(result) {
  let text;
  if (result.same_device) text = 'This code is already linked to this device.';
  else if (result.moved > 0) text = `${fmtCredits(result.moved)} moved to this device. The code now works from here.`;
  else text = 'Code accepted. There were no bought credits left to move.';
  const body = setView('Credits restored', `
    <p class="text-sm text-gray-700 leading-relaxed" role="status">${esc(text)}</p>
    <p class="mt-2 text-sm text-gray-600">Balance: <strong id="creditsSheetBalance" class="text-gray-800">${esc(fmtCredits(result.balance))}</strong></p>
    <button type="button" id="creditsDone" class="mt-5 w-full py-3 text-sm font-semibold text-white bg-brand-600 hover:bg-brand-700 rounded-xl">Done</button>
  `, '#creditsDone');
  body.querySelector('#creditsDone').addEventListener('click', closeSheet);
}

// ── Return from checkout ────────────────────────────────────────────────────

function takeReturnParams() {
  const params = new URLSearchParams(window.location.search);
  const paymentId = params.get('payment');
  if (!paymentId || !/^pay_[A-Za-z0-9]{8,60}$/.test(paymentId)) return null;
  const cancelled = params.get('result') === 'cancelled';
  params.delete('payment');
  params.delete('result');
  const qs = params.toString();
  history.replaceState(history.state, '', `${window.location.pathname}${qs ? `?${qs}` : ''}${window.location.hash}`);
  return { paymentId, cancelled };
}

async function showPaymentResult({ paymentId, cancelled }) {
  const token = ++pollToken;
  setView('Checking your payment', `
    <p class="py-4 text-sm text-gray-600" role="status" id="creditsResultStatus">Confirming your payment…</p>`);
  for (let attempt = 0; attempt < POLL_ATTEMPTS; attempt++) {
    if (token !== pollToken) return;
    let status;
    try {
      status = await api(`/api/payments/${encodeURIComponent(paymentId)}`);
    } catch (err) {
      if (err.status === 404 || err.status === 400) { renderResultMessage('Payment not found', 'We couldn\'t find this payment for this device.'); return; }
      status = null;
    }
    if (token !== pollToken) return;
    if (status?.status === 'paid') { renderPaid(status); return; }
    if (status && status.status !== 'pending') {
      renderNotPaid(status.status === 'expired' ? 'expired' : (cancelled ? 'cancelled' : 'failed'));
      return;
    }
    if (cancelled && status?.status === 'pending' && attempt >= 1) { renderNotPaid('cancelled'); return; }
    await new Promise(r => setTimeout(r, POLL_INTERVAL_MS));
  }
  if (token !== pollToken) return;
  renderResultMessage('Still waiting for confirmation',
    'We haven\'t had confirmation from the payment provider yet. Credits are added only after it arrives.',
    { retry: () => showPaymentResult({ paymentId, cancelled: false }) });
}

function renderPaid(status) {
  window.dispatchEvent(new CustomEvent('zr:credits-changed'));
  const code = status.restore_code;
  const body = setView('Payment received', `
    <p class="text-sm text-gray-700" role="status" id="creditsPaidText">${esc(fmtCredits(status.credits))} added. Balance: <strong id="creditsSheetBalance" class="text-gray-800">${esc(fmtCredits(status.balance))}</strong></p>
    ${code ? `
      <div class="mt-4 rounded-xl border border-brand-200 bg-brand-50 p-4">
        <p class="text-xs font-semibold text-brand-700">Your restore code</p>
        <p id="creditsRestoreCode" class="mt-1 font-mono text-lg font-bold tracking-wider text-gray-900 break-all select-all">${esc(code)}</p>
        <p class="mt-2 text-xs text-gray-600 leading-relaxed">Write it down or copy it somewhere safe. Use it to move your credits to another phone or browser. We show it only once.</p>
        <button type="button" id="creditsCopyCode" class="mt-3 px-3 py-1.5 text-xs font-semibold text-brand-700 bg-white border border-brand-200 rounded-full hover:bg-brand-100">Copy code</button>
        <span id="creditsCopyMsg" class="ml-2 text-xs text-gray-500" aria-live="polite"></span>
      </div>` : ''}
    <button type="button" id="creditsDone" class="mt-5 w-full py-3 text-sm font-semibold text-white bg-brand-600 hover:bg-brand-700 rounded-xl">Done</button>
  `, code ? '#creditsCopyCode' : '#creditsDone');
  body.querySelector('#creditsDone').addEventListener('click', closeSheet);
  body.querySelector('#creditsCopyCode')?.addEventListener('click', async () => {
    const msgEl = body.querySelector('#creditsCopyMsg');
    try {
      await navigator.clipboard.writeText(code);
      msgEl.textContent = 'Copied';
    } catch {
      msgEl.textContent = 'Select the code and copy it';
    }
  });
}

function renderNotPaid(kind) {
  const copy = {
    cancelled: ['Checkout cancelled', 'You left checkout. No credits were added.'],
    expired: ['Checkout expired', 'This checkout timed out. No credits were added.'],
    failed: ['Payment didn\'t go through', 'No credits were added. You can try again.'],
  }[kind];
  renderResultMessage(copy[0], copy[1], { tryAgain: true });
}

function renderResultMessage(title, text, { tryAgain = false, retry = null } = {}) {
  const body = setView(title, `
    <p class="text-sm text-gray-700 leading-relaxed" role="status">${esc(text)}</p>
    <div class="mt-5 flex gap-2">
      <button type="button" id="creditsResultClose" class="flex-1 py-3 text-sm font-semibold text-gray-600 border border-gray-200 rounded-xl hover:bg-gray-50">Close</button>
      ${tryAgain ? '<button type="button" id="creditsTryAgain" class="flex-1 py-3 text-sm font-semibold text-white bg-brand-600 hover:bg-brand-700 rounded-xl">Try again</button>' : ''}
      ${retry ? '<button type="button" id="creditsCheckAgain" class="flex-1 py-3 text-sm font-semibold text-white bg-brand-600 hover:bg-brand-700 rounded-xl">Check again</button>' : ''}
    </div>
  `);
  body.querySelector('#creditsResultClose').addEventListener('click', closeSheet);
  body.querySelector('#creditsTryAgain')?.addEventListener('click', () => openTopUp());
  body.querySelector('#creditsCheckAgain')?.addEventListener('click', retry);
}

// ── Init ────────────────────────────────────────────────────────────────────

export function initCredits() {
  if (!mountPanelLine()) {
    const observer = new MutationObserver(() => { if (mountPanelLine()) observer.disconnect(); });
    observer.observe(document.body, { childList: true });
  }
  window.addEventListener('zr:insufficient-credits', e => openTopUp({ need: e.detail || {} }));
  window.addEventListener('zr:credits-changed', () => {
    if (document.getElementById('creditsBalance') || isOpen()) loadSummary().catch(() => {});
  });
  window.addEventListener('zr:open-topup', () => openTopUp());
  const ret = takeReturnParams();
  if (ret) showPaymentResult(ret);
}
