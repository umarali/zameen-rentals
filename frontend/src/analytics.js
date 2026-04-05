/** PostHog analytics — lean event tracking with privacy guards. */

import posthog from 'posthog-js';
import { S, refs } from './state.js';

let _loaded = false;

/* ── Init ─────────────────────────────────────────────────────────── */

export function initAnalytics() {
  const key = import.meta.env.VITE_POSTHOG_KEY;
  const host = import.meta.env.VITE_POSTHOG_HOST;
  if (!key || !host) return;

  const isDev = import.meta.env.DEV;
  const forceInDev = import.meta.env.VITE_ENABLE_ANALYTICS_DEV === '1';
  if (isDev && !forceInDev) return;

  posthog.init(key, {
    api_host: host,
    person_profiles: 'anonymous',
    autocapture: true,
    capture_pageview: true,
    capture_pageleave: true,
    enable_heatmaps: true,
    session_recording: {
      maskAllInputs: true,
      maskTextSelector: '*',
      sampleRate: 0.2,
    },
  });
  _loaded = true;
}

/* ── Generic track ────────────────────────────────────────────────── */

export function track(event, props) {
  if (!_loaded) return;
  posthog.capture(event, props);
}

/* ── Helpers (internal) ───────────────────────────────────────────── */

function extractListingId(url) {
  if (!url) return null;
  const m = url.match(/-(\d+)\.html/);
  return m ? m[1] : null;
}

function priceBucket(price) {
  const p = Number(price);
  if (!p || !Number.isFinite(p)) return 'unknown';
  if (p < 20000) return '<20k';
  if (p < 40000) return '20k-40k';
  if (p < 60000) return '40k-60k';
  if (p < 100000) return '60k-100k';
  if (p < 150000) return '100k-150k';
  if (p < 250000) return '150k-250k';
  return '250k+';
}

/* ── Typed event helpers ──────────────────────────────────────────── */

export function trackSearchOutcome({ success, data, mode, page, triggeredBy, visibleAreasCount, radiusKm }) {
  if (success) {
    track('search_executed', {
      mode,
      city: S.city,
      area_selected: S.area || null,
      property_type: S.type || null,
      bedrooms: S.beds || null,
      has_price_min: Boolean(S.priceMin),
      has_price_max: Boolean(S.priceMax),
      furnished: S.furnished,
      sort: S.sort || null,
      page,
      total_results: data.total || 0,
      has_results: (data.total || 0) > 0,
      source: data.source || null,
      triggered_by: triggeredBy,
      visible_areas_count: visibleAreasCount || null,
      radius_km: radiusKm || null,
    });
  } else {
    track('search_failed', {
      mode,
      city: S.city,
      area_selected: S.area || null,
    });
  }
}

export function trackNlSearch({ phase, queryLength, parseSuccess, filters }) {
  if (phase === 'submitted') {
    track('nl_search_submitted', { query_length: queryLength });
  } else if (phase === 'parsed') {
    const f = filters || {};
    track('nl_search_parsed', {
      query_length: queryLength,
      parse_success: parseSuccess,
      approximate_area: Boolean(f.area_approximate),
      has_area: Boolean(f.area),
      has_budget: Boolean(f.price_min || f.price_max),
      has_bedrooms: Boolean(f.bedrooms),
      has_property_type: Boolean(f.property_type),
      parsed_fields_count: Object.keys(f).filter(k => !['area_approximate', 'area_query'].includes(k) && f[k]).length,
    });
  }
}

export function trackListingOpen({ item, position, mode, city, area, source }) {
  track('listing_opened', {
    listing_id: extractListingId(item.url),
    position: position ?? null,
    mode,
    city,
    area: area || null,
    property_type: item.property_type || null,
    bedrooms: item.bedrooms || null,
    price_bucket: priceBucket(item.price),
    source: source || null,
  });
}

export function trackContactIntent({ channel, listingUrl, position, mode, city, source }) {
  track('contact_intent', {
    channel,
    listing_id: extractListingId(listingUrl),
    position: position ?? null,
    mode,
    city,
    source: source || null,
  });
}

export function trackCitySwitch({ from, to }) {
  track('city_switched', { from_city: from, to_city: to });
}

export function trackFilterChange({ filter, value, previousValue, mode, city }) {
  track('filter_changed', {
    filter,
    value: value || null,
    previous_value: previousValue || null,
    mode,
    city,
  });
}

export function trackMapMarkerClick({ areaName, markerType, city, mode }) {
  track('map_marker_clicked', {
    area_name: areaName || null,
    marker_type: markerType,
    city,
    mode,
  });
}

export function trackApiError({ endpoint, statusCode, errorMessage, mode, city }) {
  track('api_error', {
    endpoint,
    status_code: statusCode ?? null,
    error_message: errorMessage || null,
    mode,
    city,
  });
}

export function trackScrollDepth({ maxPosition, totalResults, mode, city }) {
  track('results_scroll_depth', {
    max_position_seen: maxPosition,
    total_results: totalResults,
    mode,
    city,
  });
}
