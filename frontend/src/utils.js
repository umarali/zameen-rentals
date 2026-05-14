/** DOM helpers & formatting utilities. */

export const $ = s => document.querySelector(s);
export const $$ = s => [...document.querySelectorAll(s)];

export const esc = s => { const d = document.createElement('div'); d.textContent = s; return d.innerHTML; };
export const escA = s => s.replace(/"/g, '&quot;').replace(/'/g, '&#39;');

export const TYPE_L = {
  house: 'House', apartment: 'Apartment', upper_portion: 'Upper Portion',
  lower_portion: 'Lower Portion', room: 'Room', penthouse: 'Penthouse', farm_house: 'Farm House',
};

export function fmtPrice(p, t) {
  if (t) return t;
  if (!p) return 'Price on request';
  if (p >= 1e7) return 'Rs ' + (p / 1e7).toFixed(1) + ' Crore';
  if (p >= 1e5) return 'Rs ' + (p / 1e5).toFixed(1) + ' Lakh';
  if (p >= 1e3) return 'Rs ' + (p / 1e3).toFixed(0) + 'K';
  return 'Rs ' + p.toLocaleString();
}

export function fmtRelative(iso) {
  if (!iso) return '';
  const t = Date.parse(iso);
  if (!Number.isFinite(t)) return '';
  const sec = Math.max(0, Math.round((Date.now() - t) / 1000));
  if (sec < 60) return 'just now';
  const min = Math.round(sec / 60);
  if (min < 60) return `${min} minute${min === 1 ? '' : 's'} ago`;
  const hr = Math.round(min / 60);
  if (hr < 24) return `${hr} hour${hr === 1 ? '' : 's'} ago`;
  const day = Math.round(hr / 24);
  if (day < 7) return `${day} day${day === 1 ? '' : 's'} ago`;
  if (day < 30) { const w = Math.round(day / 7); return `${w} week${w === 1 ? '' : 's'} ago`; }
  if (day < 365) { const mo = Math.round(day / 30); return `${mo} month${mo === 1 ? '' : 's'} ago`; }
  const yr = Math.round(day / 365);
  return `${yr} year${yr === 1 ? '' : 's'} ago`;
}

export function showToast(message, { tone = 'default', duration = 3200 } = {}) {
  const stack = $('#toastStack');
  if (!stack || !message) return;
  const toast = document.createElement('div');
  toast.className = `toast toast-${tone}`;
  toast.textContent = message;
  stack.appendChild(toast);
  requestAnimationFrame(() => toast.classList.add('toast-visible'));

  window.setTimeout(() => {
    toast.classList.remove('toast-visible');
    window.setTimeout(() => toast.remove(), 220);
  }, duration);
}
