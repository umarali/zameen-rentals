// Calls a paid endpoint. When the server answers 402 (not enough credits),
// fires `zr:insufficient-credits` on window with the server's detail
// ({ code, action, balance, cost }) so the credits UI can offer a top-up,
// then throws an error with `.insufficientCredits = true`.
import { getClientId } from './personalization.js';

export async function paidFetch(url, options = {}) {
  const headers = { 'Content-Type': 'application/json', ...(options.headers || {}), 'X-Client-Id': getClientId() };
  const resp = await fetch(url, { ...options, headers });
  if (resp.status === 402) {
    const body = await resp.json().catch(() => ({}));
    const detail = body.detail || {};
    window.dispatchEvent(new CustomEvent('zr:insufficient-credits', { detail }));
    const err = new Error(`Not enough credits: ${detail.cost ?? '?'} needed, ${detail.balance ?? '?'} left.`);
    err.insufficientCredits = true;
    err.detail = detail;
    throw err;
  }
  if (!resp.ok) {
    const body = await resp.json().catch(() => ({}));
    throw new Error(typeof body.detail === 'string' ? body.detail : `Request failed (${resp.status})`);
  }
  // Paid calls change the balance; let any balance display refresh itself.
  window.dispatchEvent(new CustomEvent('zr:credits-changed'));
  return resp.json();
}
