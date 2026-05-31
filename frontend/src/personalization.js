/** Personalization client: anonymous client_id, alerts, favorites, hidden,
 *  recently viewed, push notifications.
 *
 *  Identity model: a UUID-style id is generated on first visit and persisted
 *  in localStorage. Every personalization API call attaches it as the
 *  X-Client-Id header. No login, no PII; clearing storage = starting over.
 */

const CLIENT_ID_KEY = 'zr_client_id';
const LOCAL_HIDDEN_KEY = 'zr_hidden_local';
const LOCAL_FAVORITES_KEY = 'zr_favorites_local';

let _clientId = null;

const state = {
  ready: false,
  vapidPublicKey: null,
  favorites: new Set(),
  hidden: new Set(),
  previousVisitAt: null,
  unseenAlertMatches: 0,
  alertCount: 0,
  pushSubscriptionCount: 0,
  listeners: new Set(),
};

const subscribers = new Set();

function emit() {
  for (const fn of subscribers) {
    try { fn(getSnapshot()); } catch (err) { console.warn('personalization listener error', err); }
  }
}

function getSnapshot() {
  return {
    ready: state.ready,
    vapidPublicKey: state.vapidPublicKey,
    favorites: state.favorites,
    hidden: state.hidden,
    previousVisitAt: state.previousVisitAt,
    unseenAlertMatches: state.unseenAlertMatches,
    alertCount: state.alertCount,
    pushSubscriptionCount: state.pushSubscriptionCount,
  };
}

export function subscribe(fn) {
  subscribers.add(fn);
  if (state.ready) fn(getSnapshot());
  return () => subscribers.delete(fn);
}

export function getState() { return getSnapshot(); }

export function isFavorite(zameenId) { return zameenId ? state.favorites.has(String(zameenId)) : false; }
export function isHidden(zameenId) { return zameenId ? state.hidden.has(String(zameenId)) : false; }
export function previousVisitAt() { return state.previousVisitAt; }
export function vapidPublicKey() { return state.vapidPublicKey; }
export function unseenAlertMatches() { return state.unseenAlertMatches; }

// ── client_id management ─────────────────────────────────────────────────────

function generateClientId() {
  if (window.crypto?.randomUUID) {
    return window.crypto.randomUUID().replace(/-/g, '');
  }
  const bytes = new Uint8Array(16);
  (window.crypto || { getRandomValues: arr => arr.forEach((_, i) => arr[i] = Math.floor(Math.random() * 256)) })
    .getRandomValues(bytes);
  return Array.from(bytes, b => b.toString(16).padStart(2, '0')).join('');
}

export function getClientId() {
  if (_clientId) return _clientId;
  try {
    _clientId = localStorage.getItem(CLIENT_ID_KEY);
  } catch { _clientId = null; }
  if (!_clientId || !/^[A-Za-z0-9_-]{8,64}$/.test(_clientId)) {
    _clientId = generateClientId();
    try { localStorage.setItem(CLIENT_ID_KEY, _clientId); } catch {}
  }
  return _clientId;
}

// ── API helper ──────────────────────────────────────────────────────────────

async function apiFetch(path, { method = 'GET', body, signal } = {}) {
  const headers = { 'X-Client-Id': getClientId() };
  const init = { method, headers, signal };
  if (body !== undefined) {
    headers['Content-Type'] = 'application/json';
    init.body = JSON.stringify(body);
  }
  const resp = await fetch(path, init);
  if (!resp.ok) {
    let detail = '';
    try { const e = await resp.json(); detail = e.detail || e.error || ''; } catch {}
    const err = new Error(detail || `${method} ${path} failed: ${resp.status}`);
    err.status = resp.status;
    throw err;
  }
  if (resp.status === 204) return null;
  const ctype = resp.headers.get('content-type') || '';
  if (ctype.includes('application/json')) return resp.json();
  return null;
}

// ── localStorage caches (used before bootstrap completes so the UI doesn't flash) ──

function loadLocalCache(key) {
  try {
    const raw = localStorage.getItem(key);
    if (!raw) return new Set();
    const parsed = JSON.parse(raw);
    return Array.isArray(parsed) ? new Set(parsed.map(String)) : new Set();
  } catch { return new Set(); }
}

function persistLocalCache(key, set) {
  try { localStorage.setItem(key, JSON.stringify([...set])); } catch {}
}

// ── Bootstrap ────────────────────────────────────────────────────────────────

export async function initPersonalization() {
  // Show cached state immediately for instant UI feedback.
  state.hidden = loadLocalCache(LOCAL_HIDDEN_KEY);
  state.favorites = loadLocalCache(LOCAL_FAVORITES_KEY);
  emit();

  try {
    const touch = await apiFetch('/api/personalization/touch', { method: 'POST', body: {} });
    state.previousVisitAt = touch?.previous_visit_at || null;
    state.unseenAlertMatches = touch?.unseen_alert_matches || 0;
    state.vapidPublicKey = touch?.vapid_public_key || null;

    const snapshot = await apiFetch('/api/personalization/state');
    state.favorites = new Set((snapshot.favorites || []).map(String));
    state.hidden = new Set((snapshot.hidden || []).map(String));
    state.alertCount = snapshot.alert_count || 0;
    state.unseenAlertMatches = snapshot.unseen_alert_matches || 0;
    state.pushSubscriptionCount = snapshot.push_subscription_count || 0;
    state.vapidPublicKey = snapshot.vapid_public_key || state.vapidPublicKey;
    persistLocalCache(LOCAL_FAVORITES_KEY, state.favorites);
    persistLocalCache(LOCAL_HIDDEN_KEY, state.hidden);
  } catch (err) {
    console.warn('Personalization bootstrap failed:', err);
  }

  state.ready = true;
  emit();

  // Browser permission can survive a server reset or an interrupted subscribe
  // request. Re-register an existing device subscription quietly on return.
  if (notificationPermission() === 'granted') {
    syncExistingPushSubscription().catch(err => {
      console.warn('Push subscription sync failed:', err);
    });
  }
}

// ── Favorites ────────────────────────────────────────────────────────────────

export async function addFavorite(zameenId, { note = null } = {}) {
  const id = String(zameenId);
  if (!id) return;
  state.favorites.add(id);
  persistLocalCache(LOCAL_FAVORITES_KEY, state.favorites);
  emit();
  try {
    await apiFetch('/api/favorites', { method: 'POST', body: { zameen_id: id, note } });
  } catch (err) {
    state.favorites.delete(id);
    persistLocalCache(LOCAL_FAVORITES_KEY, state.favorites);
    emit();
    throw err;
  }
}

export async function removeFavorite(zameenId) {
  const id = String(zameenId);
  if (!id) return;
  const had = state.favorites.delete(id);
  persistLocalCache(LOCAL_FAVORITES_KEY, state.favorites);
  emit();
  try {
    await apiFetch(`/api/favorites/${encodeURIComponent(id)}`, { method: 'DELETE' });
  } catch (err) {
    if (had) state.favorites.add(id);
    persistLocalCache(LOCAL_FAVORITES_KEY, state.favorites);
    emit();
    throw err;
  }
}

export async function toggleFavorite(zameenId) {
  return isFavorite(zameenId) ? removeFavorite(zameenId) : addFavorite(zameenId);
}

export async function listFavorites(limit = 200) {
  const data = await apiFetch(`/api/favorites?limit=${limit}`);
  return data?.favorites || [];
}

// ── Hidden ───────────────────────────────────────────────────────────────────

export async function addHidden(zameenId) {
  const id = String(zameenId);
  if (!id) return;
  state.hidden.add(id);
  persistLocalCache(LOCAL_HIDDEN_KEY, state.hidden);
  emit();
  try {
    await apiFetch('/api/hidden', { method: 'POST', body: { zameen_id: id } });
  } catch (err) {
    state.hidden.delete(id);
    persistLocalCache(LOCAL_HIDDEN_KEY, state.hidden);
    emit();
    throw err;
  }
}

export async function removeHidden(zameenId) {
  const id = String(zameenId);
  if (!id) return;
  const had = state.hidden.delete(id);
  persistLocalCache(LOCAL_HIDDEN_KEY, state.hidden);
  emit();
  try {
    await apiFetch(`/api/hidden/${encodeURIComponent(id)}`, { method: 'DELETE' });
  } catch (err) {
    if (had) state.hidden.add(id);
    persistLocalCache(LOCAL_HIDDEN_KEY, state.hidden);
    emit();
    throw err;
  }
}

export async function listHidden(limit = 200) {
  const data = await apiFetch(`/api/hidden?limit=${limit}`);
  return data?.hidden || [];
}

// ── Recently viewed ──────────────────────────────────────────────────────────

export async function recordView(zameenId) {
  const id = String(zameenId);
  if (!id) return;
  try {
    await apiFetch('/api/recent-views', { method: 'POST', body: { zameen_id: id } });
  } catch (err) {
    // Non-critical; just log.
    console.warn('recordView failed:', err);
  }
}

export async function listRecentViews(limit = 50) {
  const data = await apiFetch(`/api/recent-views?limit=${limit}`);
  return data?.recent_views || [];
}

// ── Alerts ───────────────────────────────────────────────────────────────────

export async function listAlerts() {
  const data = await apiFetch('/api/alerts');
  state.alertCount = (data?.alerts || []).length;
  emit();
  return data?.alerts || [];
}

export async function createAlert({ filters, label = null, notify_push = true, notify_inapp = true }) {
  const alert = await apiFetch('/api/alerts', {
    method: 'POST',
    body: { filters, label, notify_push, notify_inapp },
  });
  state.alertCount += 1;
  emit();
  return alert;
}

export async function updateAlert(alertId, patch) {
  return apiFetch(`/api/alerts/${alertId}`, { method: 'PATCH', body: patch });
}

export async function deleteAlert(alertId) {
  await apiFetch(`/api/alerts/${alertId}`, { method: 'DELETE' });
  state.alertCount = Math.max(0, state.alertCount - 1);
  emit();
}

export async function listMatches({ alertId = null, unseen = false, limit = 50 } = {}) {
  const params = new URLSearchParams();
  if (alertId) params.set('alert_id', alertId);
  if (unseen) params.set('unseen', '1');
  if (limit) params.set('limit', limit);
  const qs = params.toString();
  const data = await apiFetch('/api/alerts/matches' + (qs ? '?' + qs : ''));
  state.unseenAlertMatches = data?.unseen_count || 0;
  emit();
  return data?.matches || [];
}

export async function markMatchesSeen({ matchIds = null, alertId = null } = {}) {
  const body = {};
  if (matchIds) body.match_ids = matchIds;
  if (alertId) body.alert_id = alertId;
  const data = await apiFetch('/api/alerts/matches/seen', { method: 'POST', body });
  state.unseenAlertMatches = data?.unseen_count || 0;
  emit();
  return data;
}

// ── Push notifications ───────────────────────────────────────────────────────

export function isPushSupported() {
  return 'serviceWorker' in navigator && 'PushManager' in window && 'Notification' in window;
}

export function notificationPermission() {
  return isPushSupported() ? Notification.permission : 'unsupported';
}

function urlBase64ToUint8Array(base64String) {
  const padding = '='.repeat((4 - (base64String.length % 4)) % 4);
  const base64 = (base64String + padding).replace(/-/g, '+').replace(/_/g, '/');
  const raw = atob(base64);
  const out = new Uint8Array(raw.length);
  for (let i = 0; i < raw.length; ++i) out[i] = raw.charCodeAt(i);
  return out;
}

export async function ensurePushSubscription({ requestPermission = true } = {}) {
  if (!isPushSupported()) return { status: 'unsupported' };
  try {
    let perm = Notification.permission;
    if (perm === 'default' && requestPermission) {
      perm = await Notification.requestPermission();
    }
    if (perm !== 'granted') return { status: perm };

    const reg = await navigator.serviceWorker.ready;
    const existing = await reg.pushManager.getSubscription();
    if (existing) {
      await registerSubscription(existing);
      state.pushSubscriptionCount = Math.max(1, state.pushSubscriptionCount);
      emit();
      return { status: 'granted', subscription: existing };
    }

    if (!state.vapidPublicKey) {
      const data = await apiFetch('/api/push/vapid-key');
      state.vapidPublicKey = data?.vapid_public_key || null;
    }
    if (!state.vapidPublicKey) return { status: 'no_vapid_key' };

    const sub = await reg.pushManager.subscribe({
      userVisibleOnly: true,
      applicationServerKey: urlBase64ToUint8Array(state.vapidPublicKey),
    });
    await registerSubscription(sub);
    state.pushSubscriptionCount = Math.max(1, state.pushSubscriptionCount);
    emit();
    return { status: 'granted', subscription: sub };
  } catch (err) {
    console.warn('push subscription failed:', err);
    return { status: 'subscribe_failed', error: err };
  }
}

export async function syncExistingPushSubscription() {
  if (!isPushSupported() || Notification.permission !== 'granted') {
    return { status: notificationPermission() };
  }
  return ensurePushSubscription({ requestPermission: false });
}

async function registerSubscription(sub) {
  const json = sub.toJSON();
  await apiFetch('/api/push/subscribe', {
    method: 'POST',
    body: {
      endpoint: json.endpoint,
      keys: { p256dh: json.keys?.p256dh, auth: json.keys?.auth },
    },
  });
}

export async function disablePushSubscription() {
  if (!isPushSupported()) return false;
  const reg = await navigator.serviceWorker.ready;
  const sub = await reg.pushManager.getSubscription();
  if (!sub) {
    state.pushSubscriptionCount = 0;
    emit();
    return false;
  }
  try { await apiFetch('/api/push/unsubscribe', { method: 'POST', body: { endpoint: sub.endpoint } }); }
  catch (err) { console.warn('unsubscribe API failed:', err); }
  await sub.unsubscribe();
  state.pushSubscriptionCount = Math.max(0, state.pushSubscriptionCount - 1);
  emit();
  return true;
}

export async function sendTestPush() {
  return apiFetch('/api/push/test', { method: 'POST', body: {} });
}

// ── Helpers ─────────────────────────────────────────────────────────────────

/** Returns true if a listing first_seen_at is newer than the user's previous visit. */
export function isNewSinceLastVisit(firstSeenAt) {
  if (!firstSeenAt || !state.previousVisitAt) return false;
  const seen = Date.parse(firstSeenAt);
  const prev = Date.parse(state.previousVisitAt);
  return Number.isFinite(seen) && Number.isFinite(prev) && seen > prev;
}
