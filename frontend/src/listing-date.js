/** The listing date line ("Added 2 weeks ago · Updated 3 hours ago ⓘ") and
 *  its explanation popover.
 *
 *  The dates are Zameen's own, and Zameen's dates can move forward for the
 *  same ad (docs/listing-trust-2026-10-10). The ⓘ says so and adds what we
 *  know ourselves: when ZameenRentals first saw the listing. Hover or focus
 *  shows it on desktop; tap toggles it on touch screens.
 */

import { esc, fmtRelative, fmtShortDate } from './utils.js';

let tipSeq = 0;

/** Zameen's added and updated ages; `updated` is '' when it says the same as `added`. */
function zameenAges(item) {
  const added = item.posted_at ? fmtRelative(item.posted_at)
    : (item.added || '').replace(/^Added:\s*/i, '').trim();
  const updated = item.updated_at ? fmtRelative(item.updated_at) : '';
  return { added, updated: updated && updated !== added ? updated : '' };
}

/** One phrase: "Updated 3 hours ago", else "Added 2 days ago". */
export function zameenDateLabel(item) {
  const { added, updated } = zameenAges(item);
  return updated ? `Updated ${updated}` : added ? `Added ${added}` : '';
}

/** The date line with its ⓘ popover, or '' when Zameen gave no date. */
export function listingDateHtml(item, { className = 'text-xs text-gray-500' } = {}) {
  const { added, updated } = zameenAges(item);
  const label = [added && `Added ${added}`, updated && `Updated ${updated}`].filter(Boolean).join(' · ');
  if (!label) return '';
  const id = `dateTip${++tipSeq}`;
  const firstSeen = fmtShortDate(item.first_seen_at);
  const tip = [
    'Agents can refresh Zameen dates, so the ad may be older.',
    firstSeen ? `On ZameenRentals since ${firstSeen}` : '',
    'Availability not confirmed',
  ].filter(Boolean);
  return `<div class="listing-date ${className}">
    <span>${esc(label)}</span>
    <button type="button" class="date-info" aria-label="About these dates" aria-expanded="false" aria-describedby="${id}">
      <svg viewBox="0 0 20 20" fill="currentColor" aria-hidden="true"><path fill-rule="evenodd" d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-7-4a1 1 0 11-2 0 1 1 0 012 0zM9 9a1 1 0 000 2v3a1 1 0 001 1h1a1 1 0 100-2v-3a1 1 0 00-1-1H9z" clip-rule="evenodd"/></svg>
    </button>
    <span role="tooltip" id="${id}" class="date-tip">${tip.map(t => `<span>${esc(t)}</span>`).join('')}</span>
  </div>`;
}

function closeAll(except) {
  document.querySelectorAll('.date-info[aria-expanded="true"]').forEach(btn => {
    if (btn !== except) btn.setAttribute('aria-expanded', 'false');
  });
}

/** Tap/click toggles a popover; a click elsewhere or Escape closes it. Call once. */
export function initListingDateInfo() {
  document.addEventListener('click', e => {
    const btn = e.target.closest('.date-info');
    if (!btn) { closeAll(); return; }
    e.preventDefault();
    const open = btn.getAttribute('aria-expanded') !== 'true';
    closeAll(btn);
    btn.setAttribute('aria-expanded', String(open));
  });
  document.addEventListener('keydown', e => {
    if (e.key !== 'Escape') return;
    closeAll();
    // Focus would keep it open via :focus-visible.
    document.activeElement?.closest?.('.date-info')?.blur();
  });
}
