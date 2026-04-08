/** ZameenRentals Service Worker — offline shell, tiered API caching. */

const CACHE_VERSION = 'v1';
const SHELL_CACHE   = `zr-shell-${CACHE_VERSION}`;
const CDN_CACHE     = `zr-cdn-${CACHE_VERSION}`;
const API_STATIC    = `zr-api-static-${CACHE_VERSION}`;
const API_SEARCH    = `zr-api-search-${CACHE_VERSION}`;
const API_DETAIL    = `zr-api-detail-${CACHE_VERSION}`;

const ALL_CACHES = [SHELL_CACHE, CDN_CACHE, API_STATIC, API_SEARCH, API_DETAIL];

const SHELL_URLS = [
  '/',
  '/offline.html',
];

const PRECACHE_API = [
  '/api/cities',
  '/api/areas?city=karachi',
  '/api/areas?city=lahore',
  '/api/areas?city=islamabad',
  '/api/property-types',
];

const API_SEARCH_MAX = 10;
const API_DETAIL_MAX = 20;
const API_STATIC_TTL = 24 * 60 * 60 * 1000; // 24 hours

// ===== INSTALL =====

self.addEventListener('install', (e) => {
  e.waitUntil(
    Promise.all([
      caches.open(SHELL_CACHE).then((cache) => cache.addAll(SHELL_URLS)),
      caches.open(API_STATIC).then((cache) => cache.addAll(PRECACHE_API)),
    ]).then(() => self.skipWaiting()),
  );
});

// ===== ACTIVATE =====

self.addEventListener('activate', (e) => {
  e.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.filter((k) => !ALL_CACHES.includes(k)).map((k) => caches.delete(k))),
    ).then(() => self.clients.claim()),
  );
});

// ===== FETCH =====

self.addEventListener('fetch', (e) => {
  const { request } = e;
  const url = new URL(request.url);

  // Only handle GET (feedback POST is handled client-side)
  if (request.method !== 'GET') return;

  // Same-origin requests
  if (url.origin === self.location.origin) {
    // Hashed Vite bundles — immutable, cache-first
    if (url.pathname.startsWith('/static/assets/')) {
      e.respondWith(cacheFirst(request, SHELL_CACHE));
      return;
    }

    // App shell (root HTML)
    if (url.pathname === '/' || url.pathname === '/index.html') {
      e.respondWith(staleWhileRevalidate(request, SHELL_CACHE));
      return;
    }

    // Static assets (icons, manifest, logo, etc.)
    if (url.pathname.startsWith('/static/') || url.pathname === '/sw.js') {
      e.respondWith(cacheFirst(request, SHELL_CACHE));
      return;
    }

    // Root-served static files (manifest, favicons)
    if (/^\/(site\.webmanifest|favicon|apple-touch-icon|logo\.svg|og-card)/.test(url.pathname)) {
      e.respondWith(cacheFirst(request, SHELL_CACHE));
      return;
    }

    // Offline fallback
    if (url.pathname === '/offline.html') {
      e.respondWith(cacheFirst(request, SHELL_CACHE));
      return;
    }

    // Static API data — stale-while-revalidate with 24h TTL
    if (isStaticApi(url.pathname)) {
      e.respondWith(staleWhileRevalidate(request, API_STATIC));
      return;
    }

    // Search APIs — network-first with cache fallback
    if (isSearchApi(url.pathname)) {
      e.respondWith(networkFirst(request, API_SEARCH, API_SEARCH_MAX));
      return;
    }

    // Detail APIs — network-first with cache fallback
    if (isDetailApi(url.pathname)) {
      e.respondWith(networkFirst(request, API_DETAIL, API_DETAIL_MAX));
      return;
    }

    // All other API calls — network only
    return;
  }

  // External CDN resources (fonts, Leaflet) — cache-first
  if (
    url.hostname === 'fonts.googleapis.com' ||
    url.hostname === 'fonts.gstatic.com' ||
    url.hostname === 'unpkg.com'
  ) {
    e.respondWith(cacheFirst(request, CDN_CACHE));
    return;
  }
});

// ===== URL MATCHERS =====

function isStaticApi(p) {
  return p === '/api/cities' || p.startsWith('/api/areas') || p === '/api/property-types';
}

function isSearchApi(p) {
  return p === '/api/search' || p === '/api/map-search' || p === '/api/nearby-search';
}

function isDetailApi(p) {
  return p === '/api/listing-detail' || p === '/api/listing-contact';
}

// ===== CACHING STRATEGIES =====

async function cacheFirst(request, cacheName) {
  const cached = await caches.match(request);
  if (cached) return cached;
  try {
    const response = await fetch(request);
    if (response.ok) {
      const cache = await caches.open(cacheName);
      cache.put(request, response.clone());
    }
    return response;
  } catch {
    return caches.match('/offline.html');
  }
}

async function staleWhileRevalidate(request, cacheName) {
  const cache = await caches.open(cacheName);
  const cached = await cache.match(request);

  const fetchPromise = fetch(request).then((response) => {
    if (response.ok) cache.put(request, response.clone());
    return response;
  }).catch(() => null);

  return cached || (await fetchPromise) || new Response('Offline', { status: 503 });
}

async function networkFirst(request, cacheName, maxEntries) {
  try {
    const response = await fetch(request);
    if (response.ok) {
      const cache = await caches.open(cacheName);
      cache.put(request, response.clone());
      evictOldEntries(cacheName, maxEntries);
    }
    return response;
  } catch {
    const cached = await caches.match(request);
    return cached || caches.match('/offline.html');
  }
}

// ===== LRU EVICTION =====

async function evictOldEntries(cacheName, max) {
  const cache = await caches.open(cacheName);
  const keys = await cache.keys();
  if (keys.length > max) {
    // Delete oldest entries (first in the list)
    const toDelete = keys.slice(0, keys.length - max);
    await Promise.all(toDelete.map((k) => cache.delete(k)));
  }
}
