import { esc } from './utils.js';

export function floorSummary(item) {
  const floor = item.floor;
  if (!floor) return '';
  return floor.conflict ? 'Multiple floors mentioned · check details' : `${floor.label} · ${floor.source}`;
}

export function floorDetails(item) {
  if (!item.floor) return '';
  const mentions = item.floor_mentions || [];
  return `<section class="mt-3 rounded-xl border border-gray-200 p-3" aria-label="Floor information">
    <div class="text-sm font-semibold text-gray-800">${esc(item.floor.label)}</div>
    ${item.floor.conflict ? '<p class="text-xs text-amber-800 mt-1">The listing mentions different floors. Confirm which floor is for rent.</p>' : ''}
    ${mentions.length ? `<ul class="mt-1 space-y-1 text-xs text-gray-600">${mentions.map(m => `<li><span class="font-semibold">${esc(m.source)}:</span> ${esc(m.text)}</li>`).join('')}</ul>` : `<p class="mt-1 text-xs text-gray-600">From ${esc(item.floor.source)}</p>`}
  </section>`;
}

export function descriptionHighlights(item) {
  const notes = item.description_highlights || [];
  if (!notes.length) return '';
  return `<section class="mt-4 rounded-xl bg-gray-50 p-3" aria-label="From the description">
    <h3 class="text-sm font-semibold text-gray-800">From the description</h3>
    <p class="text-xs text-gray-500 mt-1 mb-3">The advertiser’s words. Confirm important details before visiting.</p>
    <ul class="space-y-3">${notes.map(note => `<li><div class="text-xs font-semibold text-gray-600">${esc(note.topic)}</div><p class="text-sm text-gray-700 leading-relaxed mt-1">${esc(note.text)}</p></li>`).join('')}</ul>
  </section>`;
}
