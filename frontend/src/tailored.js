/** Tailored list (paid): the renter describes what they want in their own
 *  words; we return up to 10 local listings with a reason and a trade-off each.
 *  Opened from the search box suggestions. Also wires the search report.
 */
import { esc, escA, TYPE_L } from './utils.js';
import { S, CITY_DEFAULTS } from './state.js';
import { paidFetch } from './credits-gate.js';
import {
  createModal, fetchCredits, creditAmount, costText, insufficientText, newIdempotencyKey, spinner, pkr, initReport,
} from './report.js';

const MAX_CHARS = 600;
const MIN_CHARS = 10;
let _modal = null;
let _openListing = () => {};
let _results = [];
// One idempotency key per brief: a retry of the same brief after an error
// can't be charged twice; a new brief gets a new key.
let _attempt = { brief: '', key: '' };

function cityName(city) {
  return CITY_DEFAULTS[city]?.name || (city ? city[0].toUpperCase() + city.slice(1) : '');
}

function formView(prefill = '') {
  _modal.body.innerHTML = `
    <form data-tl-form novalidate>
      <label for="tailoredBrief" class="block text-sm font-semibold text-gray-800">What are you looking for in ${esc(cityName(S.city))}?</label>
      <p id="tailoredHint" class="text-xs text-gray-500 mt-0.5">Area, budget, bedrooms and anything else that matters. English, Roman Urdu or Urdu.</p>
      <textarea id="tailoredBrief" data-autofocus rows="4" maxlength="${MAX_CHARS}" aria-describedby="tailoredHint tailoredCount"
        class="mt-2 w-full px-3 py-2 text-sm border border-gray-200 rounded-lg outline-none focus:border-brand-500 focus:ring-2 focus:ring-brand-100 resize-y"
        placeholder="2 bed near my office in Gulberg, under 80k, quiet street, parking, family-friendly, not ground floor">${esc(prefill)}</textarea>
      <div class="flex items-center justify-between gap-3 mt-1">
        <span data-tl-cost class="text-xs text-gray-500">${esc(costText(null))}</span>
        <span id="tailoredCount" class="text-[11px] text-gray-400 shrink-0"></span>
      </div>
      <p class="text-[11px] text-gray-500 mt-1">No credits are used if no listings match.</p>
      <div data-tl-error role="alert" class="hidden text-sm text-rose-600 mt-3"></div>
      <div class="flex justify-end mt-4">
        <button type="submit" data-tl-run class="inline-flex items-center gap-2 px-5 py-2.5 text-sm font-semibold text-white bg-brand-600 hover:bg-brand-700 rounded-lg transition-colors disabled:opacity-60">Make my list</button>
      </div>
      <p data-tl-status class="sr-only" aria-live="polite"></p>
    </form>`;
  const ta = _modal.body.querySelector('#tailoredBrief');
  const count = _modal.body.querySelector('#tailoredCount');
  const sync = () => { count.textContent = `${ta.value.length}/${MAX_CHARS}`; };
  ta.addEventListener('input', sync);
  sync();
  _modal.body.querySelector('[data-tl-form]').addEventListener('submit', e => { e.preventDefault(); run(); });
  fetchCredits().then(c => {
    const el = _modal.body.querySelector('[data-tl-cost]');
    if (el && c) el.textContent = costText(c.costs?.tailored_list, c.balance);
  });
}

function showError(msg) {
  const box = _modal.body.querySelector('[data-tl-error]');
  if (!box) return;
  box.textContent = msg;
  box.classList.remove('hidden');
}

async function run() {
  const ta = _modal.body.querySelector('#tailoredBrief');
  const btn = _modal.body.querySelector('[data-tl-run]');
  const status = _modal.body.querySelector('[data-tl-status]');
  const brief = ta.value.trim();
  _modal.body.querySelector('[data-tl-error]').classList.add('hidden');
  if (brief.length < MIN_CHARS) {
    showError(`Add a little more detail (at least ${MIN_CHARS} characters).`);
    ta.focus();
    return;
  }
  if (_attempt.brief !== brief) _attempt = { brief, key: newIdempotencyKey() };
  btn.disabled = true;
  ta.readOnly = true;
  btn.innerHTML = `${spinner}<span>Reading listings…</span>`;
  status.textContent = 'Making your list. This can take up to half a minute.';
  try {
    const data = await paidFetch('/api/ai/tailored', {
      method: 'POST',
      headers: { 'Idempotency-Key': _attempt.key },
      body: JSON.stringify({ brief, city: S.city }),
    });
    _attempt = { brief: '', key: '' };
    resultsView(data, brief);
  } catch (err) {
    showError(err.insufficientCredits ? insufficientText(err.detail) : (err.message || 'Something went wrong.'));
    btn.disabled = false;
    ta.readOnly = false;
    btn.textContent = 'Try again';
    status.textContent = '';
  }
}

function chip(text) {
  return `<span class="inline-flex items-center px-2 py-0.5 rounded-full bg-brand-50 text-brand-700 text-[11px] font-medium">${esc(text)}</span>`;
}

function understoodChips(u = {}) {
  const f = u.filters || {};
  const out = [];
  const areas = f.areas?.length ? f.areas : (f.area ? [f.area] : []);
  out.push(areas.length ? areas.join(' or ') : cityName(u.city));
  if (f.property_type) out.push(TYPE_L[f.property_type] || f.property_type);
  if (f.bedrooms) out.push(`${f.bedrooms}${f.bedrooms_max ? '-' + f.bedrooms_max : ''} bed`);
  if (f.price_max) out.push(`Up to ${pkr(f.price_max)}`);
  else if (f.price_min) out.push(`From ${pkr(f.price_min)}`);
  if (f.furnished === true) out.push('Furnished');
  if (f.furnished === false) out.push('Unfurnished');
  (u.preferences || []).forEach(p => out.push(p));
  return out.map(chip).join(' ');
}

function resultItem(item, i) {
  const facts = [
    item.bedrooms ? `${item.bedrooms} bed` : '',
    item.area_size || '',
    item.location || '',
  ].filter(Boolean).join(' · ');
  const price = item.price ? pkr(item.price) : (item.price_text || 'Rent not stated');
  return `
    <li class="border border-gray-200 rounded-xl p-3 flex gap-3" data-tl-item="${escA(String(item.zameen_id))}">
      ${item.image_url
        ? `<img src="${escA(item.image_url)}" alt="" loading="lazy" class="w-16 h-16 sm:w-20 sm:h-20 rounded-lg object-cover shrink-0 bg-gray-100">`
        : '<div class="w-16 h-16 sm:w-20 sm:h-20 rounded-lg bg-gray-100 shrink-0" aria-hidden="true"></div>'}
      <div class="min-w-0 flex-1">
        <div class="flex items-baseline justify-between gap-2">
          <span class="text-sm font-bold text-gray-800">${esc(price)}<span class="text-xs font-medium text-gray-500">/mo</span></span>
          <span class="text-[11px] text-gray-400 shrink-0">#${i + 1}</span>
        </div>
        <div class="text-xs text-gray-500 truncate">${esc(facts)}</div>
        <p class="text-sm text-gray-700 mt-1.5"><span class="font-semibold text-gray-800">Why it fits:</span> ${esc(item.ai_reason)}</p>
        <p class="text-sm text-gray-600 mt-1"><span class="font-semibold text-gray-700">Trade-off:</span> ${esc(item.ai_trade_off)}</p>
        <button type="button" data-tl-open="${i}" class="mt-2 text-xs font-semibold text-brand-600 hover:text-brand-700 hover:underline underline-offset-2">View details<span class="sr-only"> for listing ${i + 1}</span></button>
      </div>
    </li>`;
}

function resultsView(data, brief) {
  _results = data.results || [];
  const charge = data.charged ? `Used ${creditAmount(data.cost)}.`
    : data.cached ? 'Made in the last few minutes, so no credits were used.'
    : 'No credits were used.';
  const relaxed = (data.relaxed || []).map(n => `<li>${esc(n)}</li>`).join('');
  _modal.body.innerHTML = `
    <div data-tl-results>
      <div class="text-xs text-gray-500">We read your brief as:</div>
      <div class="flex flex-wrap gap-1 mt-1">${understoodChips(data.understood)}</div>
      ${relaxed ? `<ul class="text-xs text-amber-700 bg-amber-50 rounded-lg px-3 py-2 mt-2 list-disc list-inside">${relaxed}</ul>` : ''}
      ${_results.length
        ? `<p class="text-xs text-gray-500 mt-3">${_results.length} of ${data.candidates_considered} matching listings, best first. Reasons use only what each listing says.</p>
           <ol class="mt-2 space-y-2">${_results.map(resultItem).join('')}</ol>`
        : `<p class="text-sm text-gray-700 mt-3">${esc(data.message || 'No listings fit your description yet.')}</p>`}
      <p class="text-[11px] text-gray-500 mt-4">Listings from Zameen.com. Check details with the advertiser before you visit; listings can be gone or out of date.</p>
      <p class="text-[11px] text-gray-500 mt-1">${esc(charge)}</p>
      <div class="flex justify-end mt-3">
        <button type="button" data-tl-again class="px-4 py-2 text-sm font-semibold text-brand-600 hover:text-brand-700 border border-brand-200 hover:bg-brand-50 rounded-lg transition-colors">Change my brief</button>
      </div>
    </div>`;
  _modal.body.querySelector('[data-tl-again]').addEventListener('click', () => { formView(brief); _modal.body.querySelector('#tailoredBrief')?.focus(); });
  _modal.body.querySelectorAll('[data-tl-open]').forEach(btn => btn.addEventListener('click', () => {
    const item = _results[Number(btn.dataset.tlOpen)];
    if (item) _openListing(item);
  }));
  _modal.body.querySelector('[data-tl-results]').setAttribute('tabindex', '-1');
  _modal.body.querySelector('[data-tl-results]').focus();
}

export function openTailored(prefill = '') {
  if (!_modal) {
    _modal = createModal({
      id: 'tailoredModal', title: 'Tailored list',
      subtitle: 'Describe the home you want. We pick up to 10 listings and explain each one.',
    });
  }
  formView(prefill);
  _modal.open();
}

/** Adds the "Tailored list" action to the search box suggestions. */
function addSearchEntry() {
  const box = document.getElementById('nlSuggestions');
  if (!box || document.getElementById('tailoredEntry')) return;
  const btn = document.createElement('button');
  btn.type = 'button';
  btn.id = 'tailoredEntry';
  btn.className = 'w-full text-left mt-1 px-3 py-2.5 border-t border-gray-100 flex items-center gap-2 text-sm text-brand-700 hover:bg-brand-50 transition-colors';
  btn.innerHTML = `
    <svg class="w-4 h-4 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 6h16M4 12h10M4 18h7m9-4l-3 3-1.5-1.5"/></svg>
    <span class="flex-1 min-w-0"><span class="font-semibold">Tailored list</span><span class="block text-xs text-gray-500">Describe every detail and get a ranked shortlist. Uses credits.</span></span>`;
  btn.addEventListener('click', () => {
    box.classList.add('hidden');
    openTailored(document.getElementById('nlInput')?.value.trim() || '');
  });
  box.appendChild(btn);
}

/** Entry for both paid AI features. `openListing(item)` opens the listing drawer. */
export function initAiFeatures({ openListing } = {}) {
  if (openListing) _openListing = openListing;
  addSearchEntry();
  initReport();
}
