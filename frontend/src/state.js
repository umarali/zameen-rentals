/** Global application state & city config. */

export const CITY_DEFAULTS = {
  karachi:   { lat: 24.8607, lng: 67.0011, zoom: 11, name: 'Karachi' },
  lahore:    { lat: 31.5204, lng: 74.3587, zoom: 11, name: 'Lahore' },
  islamabad: { lat: 33.6844, lng: 73.0479, zoom: 11, name: 'Islamabad' },
};

export const POPULAR_AREAS_BY_CITY = {
  karachi: new Set(['DHA Defence','DHA Phase 5','DHA Phase 6','DHA Phase 8','Clifton','Gulshan-e-Iqbal','Gulistan-e-Jauhar','Bahria Town Karachi','North Nazimabad','Nazimabad','PECHS','North Karachi','Scheme 33','Malir','Korangi','Safoora Goth','Gulberg','Gulshan-e-Maymar','Buffer Zone','Saddar','Federal B Area','Model Colony','Naya Nazimabad','Shahra-e-Faisal','Karsaz','Cantt','Bath Island','Zamzama','University Road','Tariq Road','Bahadurabad']),
  lahore: new Set(['DHA Defence','DHA Phase 5','DHA Phase 6','DHA Phase 8','Bahria Town Lahore','Gulberg','Johar Town','Model Town','Cantt','Garden Town','Iqbal Town','Faisal Town','Township','Valencia Housing Society','Wapda Town','Lake City','Askari','Cavalry Ground','Punjab Coop Housing Society','State Life Housing Society','EME Society','Allama Iqbal Town','Raiwind Road','Main Boulevard Gulberg']),
  islamabad: new Set(['DHA Defence','DHA Phase 2','Bahria Town Islamabad','F-6','F-7','F-8','F-10','F-11','G-9','G-10','G-11','G-13','E-11','I-8','I-10','I-14','Blue Area','Gulberg Greens','B-17','D-12','Soan Garden','PWD Housing Scheme','Pakistan Town','CBR Town']),
};

export const NL_EXAMPLES = {
  karachi: {
    placeholder: 'Try: 2 bed flat DHA under 50k',
    examples: ['2 bed flat in DHA under 50k','gulshan mein sasta ghar','furnished apartment Bahria','3 bedroom house Gulistan-e-Jauhar'],
  },
  lahore: {
    placeholder: 'Try: 3 bed house Bahria Town under 80k',
    examples: ['2 bed flat in DHA Lahore under 50k','Gulberg mein sasta ghar','furnished apartment Bahria Town','3 bedroom house Johar Town'],
  },
  islamabad: {
    placeholder: 'Try: 2 bed flat F-8 under 60k',
    examples: ['2 bed flat in F-8 under 60k','Bahria Town mein sasta ghar','furnished apartment DHA','3 bedroom house G-11'],
  },
};

/** Reactive-ish filter state. */
export const S = {
  city: 'lahore', area: '', type: '', beds: '', bedsMax: '',
  priceMin: '', priceMax: '', furnished: false, sort: '',
  sizeMarlaMin: '', sizeMarlaMax: '',
};

/** Mutable runtime refs (not filter state). */
export const refs = {
  currentPage: 1,
  isLoading: false,
  searchToken: 0,
  searchController: null,
  currentResults: [],
  allAreas: [],
  searchMode: 'city',
  mapLayer: 'osm',
  userLocation: null,
  nearbyRadiusKm: 5,
  map: null,
  mapBaseLayer: null,
  mobileMap: null,
  mobileMapBaseLayer: null,
  mobileMarkerLayer: null,
  listingMarkerLayer: null,
  mobileListingMarkerLayer: null,
  markers: {},
  miniMap: null,
  miniMapBaseLayer: null,
  userLocationMarker: null,
  userLocationCircle: null,
  mobileUserLocationMarker: null,
  mobileUserLocationCircle: null,
  nearbyRadiusLayer: null,
  mobileNearbyRadiusLayer: null,
  mapDriven: false,
  mapTimer: null,
  activeDD: null,
  drawerImages: [],
  galleryIdx: 0,
  areaCounts: {},
  mapAreaTotals: {},
  viewportAreaNames: [],
  viewportVisibleAreas: 0,
  viewportTotal: 0,
  viewportShown: 0,
  viewportRanking: 'default',
  viewportScope: 'area_coverage',
  viewportAttemptedExactBounds: false,
  viewportExactBoundsTotal: null,
  lastViewportSearchKey: '',
  lastSearchTotal: 0,
  pendingMapArea: null,
  hoveredArea: null,
  previewArea: null,
  _openDrawer: null,
  _refreshCoverageUI: null,
  _notify: null,
  _lastTriggeredBy: null,
  _lastSearchSource: null,
};
