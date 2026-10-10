/** DOM helpers & formatting utilities. */

import { t, getLang, fmtPriceUr } from './i18n.js';

export const $ = s => document.querySelector(s);
export const $$ = s => [...document.querySelectorAll(s)];

export const esc = s => { const d = document.createElement('div'); d.textContent = s; return d.innerHTML; };
export const escA = s => s.replace(/"/g, '&quot;').replace(/'/g, '&#39;');

// Property-type labels in the active UI language (read at render time).
export const TYPE_L = Object.defineProperties({}, Object.fromEntries(
  ['house', 'apartment', 'upper_portion', 'lower_portion', 'room', 'penthouse', 'farm_house']
    .map(k => [k, { enumerable: true, get: () => t('type.' + k) }]),
));

export function fmtPrice(p, text) {
  if (getLang() === 'ur') return fmtPriceUr(p, text);
  if (text) return text;
  if (!p) return t('price.onRequest');
  if (p >= 1e7) return 'Rs ' + (p / 1e7).toFixed(1) + ' Crore';
  if (p >= 1e5) return 'Rs ' + (p / 1e5).toFixed(1) + ' Lakh';
  if (p >= 1e3) return 'Rs ' + (p / 1e3).toFixed(0) + 'K';
  return 'Rs ' + p.toLocaleString();
}

export function fmtRelative(iso) {
  if (!iso) return '';
  const ts = Date.parse(iso);
  if (!Number.isFinite(ts)) return '';
  const sec = Math.max(0, Math.round((Date.now() - ts) / 1000));
  if (sec < 60) return t('time.justNow');
  const min = Math.round(sec / 60);
  if (min < 60) return t('time.minutes', { n: min });
  const hr = Math.round(min / 60);
  if (hr < 24) return t('time.hours', { n: hr });
  const day = Math.round(hr / 24);
  if (day < 7) return t('time.days', { n: day });
  if (day < 30) return t('time.weeks', { n: Math.round(day / 7) });
  if (day < 365) return t('time.months', { n: Math.round(day / 30) });
  return t('time.years', { n: Math.round(day / 365) });
}

export function showToast(message, { tone = 'default', duration = 3200, action = null } = {}) {
  const stack = $('#toastStack');
  if (!stack || !message) return;
  const toast = document.createElement('div');
  toast.className = `toast toast-${tone} pointer-events-auto`;
  const messageEl = document.createElement('span');
  messageEl.textContent = message;
  toast.appendChild(messageEl);
  if (action?.label && typeof action.onClick === 'function') {
    const btn = document.createElement('button');
    btn.type = 'button';
    btn.className = 'toast-action';
    btn.textContent = action.label;
    btn.addEventListener('click', () => {
      try { action.onClick(); } finally { dismiss(); }
    });
    toast.appendChild(btn);
    duration = Math.max(duration, 5000); // Give the user time to click.
  }
  stack.appendChild(toast);
  requestAnimationFrame(() => toast.classList.add('toast-visible'));

  let dismissed = false;
  function dismiss() {
    if (dismissed) return;
    dismissed = true;
    toast.classList.remove('toast-visible');
    window.setTimeout(() => toast.remove(), 220);
  }
  window.setTimeout(dismiss, duration);
}
