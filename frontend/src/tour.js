/** First-run guided tour (Driver.js, MIT).
 *
 *  Spotlights the core features once per visitor and is re-launchable from the
 *  help modal. Coordinates with welcome.js: it runs on first visit, and on
 *  finish/skip hands back to the lightweight intent strip via `onDone`.
 */

import { driver } from 'driver.js';
import 'driver.js/dist/driver.css';
import { t } from './i18n.js';

const TOUR_KEY = 'zr_tour_done';
// A real (non-skeleton, non-hidden) listing card's compare button.
const COMPARE_SEL = '#listingsGrid .card-wrap:not(.card-hidden) button[data-action="compare"]';

let _driver = null;

function isDesktop() { return window.innerWidth >= 1024; }
/** Mirror a horizontal popover side in RTL so it still points at its target. */
function side(s) { return document.dir === 'rtl' ? ({ left: 'right', right: 'left' }[s] || s) : s; }
function align(a) { return document.dir === 'rtl' ? ({ start: 'end', end: 'start' }[a] || a) : a; }

function buildSteps() {
  const steps = [
    { element: '#nlInput', popover: {
      title: t('tour.searchTitle'),
      description: t('tour.searchBody'),
      side: side('bottom'), align: align('start'),
    } },
    { element: '#cityTabs', popover: {
      title: t('tour.cityTitle'),
      description: t('tour.cityBody'),
      side: side('bottom'), align: align('start'),
    } },
    { element: '#filterBar', popover: {
      title: t('tour.filtersTitle'),
      description: t('tour.filtersBody'),
      side: side('bottom'), align: align('start'),
    } },
  ];

  // Compare lives on the listing cards, which render after the search resolves.
  const compareBtn = document.querySelector(COMPARE_SEL);
  if (compareBtn) steps.push({ element: compareBtn, popover: {
    title: t('tour.compareTitle'),
    description: t('tour.compareBody'),
    side: side('left'), align: align('start'),
  } });

  steps.push({ element: '#alertsBellBtn', popover: {
    title: t('tour.alertsTitle'),
    description: t('tour.alertsBody'),
    side: side('bottom'), align: align('end'),
  } });

  // The map is desktop-only; on mobile the floating map button opens it.
  const mapSel = isDesktop() ? '#mapPanel' : '#mapFab';
  if (document.querySelector(mapSel)) steps.push({ element: mapSel, popover: {
    title: t('tour.mapTitle'),
    description: t('tour.mapBody'),
    side: side(isDesktop() ? 'left' : 'top'), align: align(isDesktop() ? 'center' : 'end'),
  } });

  steps.push({ element: '#welcomeBtn', popover: {
    title: t('tour.helpTitle'),
    description: t('tour.helpBody'),
    side: side('bottom'), align: align('start'),
  } });

  return steps;
}

/** Run cb once a real compare button exists (cards load async), or after a
 *  timeout so the tour still runs (minus the compare step) on slow/empty loads. */
function waitForCards(cb, timeoutMs = 7000) {
  if (document.querySelector(COMPARE_SEL)) return cb();
  const grid = document.getElementById('listingsGrid');
  if (!grid) return cb();
  let done = false;
  const finish = () => { if (done) return; done = true; obs.disconnect(); clearTimeout(timer); cb(); };
  const obs = new MutationObserver(() => { if (document.querySelector(COMPARE_SEL)) finish(); });
  obs.observe(grid, { childList: true, subtree: true });
  const timer = setTimeout(finish, timeoutMs);
}

export function tourDone() { return Boolean(localStorage.getItem(TOUR_KEY)); }

export function startTour({ force = false, onDone } = {}) {
  if (_driver) return;                                        // already running
  if (!force && localStorage.getItem(TOUR_KEY)) { onDone?.(); return; }
  waitForCards(() => {
    _driver = driver({
      showProgress: true,
      progressText: t('tour.progress'),
      allowClose: true,
      disableActiveInteraction: true,   // don't fire the highlighted control mid-tour
      overlayColor: '#0f172a',
      overlayOpacity: 0.55,
      smoothScroll: true,
      stagePadding: 6,
      stageRadius: 12,
      popoverClass: 'zr-tour',
      nextBtnText: t('tour.next'),
      prevBtnText: t('tour.back'),
      doneBtnText: t('tour.done'),
      steps: buildSteps(),
      onDestroyed: () => {
        localStorage.setItem(TOUR_KEY, '1');
        _driver = null;
        onDone?.();
      },
    });
    _driver.drive();
  });
}
