/** First-run guided tour (Driver.js, MIT).
 *
 *  Spotlights the core features once per visitor and is re-launchable from the
 *  help modal. Coordinates with welcome.js: it runs on first visit, and on
 *  finish/skip hands back to the lightweight intent strip via `onDone`.
 */

import { driver } from 'driver.js';
import 'driver.js/dist/driver.css';

const TOUR_KEY = 'zr_tour_done';
// A real (non-skeleton, non-hidden) listing card's compare button.
const COMPARE_SEL = '#listingsGrid .card-wrap:not(.card-hidden) button[data-action="compare"]';

let _driver = null;

function isDesktop() { return window.innerWidth >= 1024; }

function buildSteps() {
  const steps = [
    { element: '#nlInput', popover: {
      title: 'Search in plain words',
      description: 'Describe your rental in English or Roman Urdu. Try "2 bed flat DHA under 50k". Check the area, type, beds and budget we found.',
      side: 'bottom', align: 'start',
    } },
    { element: '#cityTabs', popover: {
      title: 'Pick your city',
      description: 'Choose Lahore, Karachi or Islamabad to see rentals in that city.',
      side: 'bottom', align: 'start',
    } },
    { element: '#filterBar', popover: {
      title: 'Refine with filters',
      description: 'Filter by area, type, beds and price. Use Near me to search around your location.',
      side: 'bottom', align: 'start',
    } },
  ];

  // Compare lives on the listing cards, which render after the search resolves.
  const compareBtn = document.querySelector(COMPARE_SEL);
  if (compareBtn) steps.push({ element: compareBtn, popover: {
    title: 'Compare homes side by side',
    description: 'Add up to four homes to compare rent, size, distance and listing dates side by side.',
    side: 'left', align: 'start',
  } });

  steps.push({ element: '#alertsBellBtn', popover: {
    title: 'Save homes & get alerts',
    description: 'Open My rentals for saved homes, recently viewed listings and new matches for your saved searches.',
    side: 'bottom', align: 'end',
  } });

  // The map is desktop-only; on mobile the floating map button opens it.
  const mapSel = isDesktop() ? '#mapPanel' : '#mapFab';
  if (document.querySelector(mapSel)) steps.push({ element: mapSel, popover: {
    title: 'Explore on the map',
    description: 'Green dots show areas with listings. Red pins show locations supplied with listings. Confirm the address before visiting.',
    side: isDesktop() ? 'left' : 'top', align: isDesktop() ? 'center' : 'end',
  } });

  steps.push({ element: '#welcomeBtn', popover: {
    title: 'Help is always here',
    description: 'Tap the help button anytime to reopen tips, search examples and this tour.',
    side: 'bottom', align: 'start',
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
      progressText: '{{current}} of {{total}}',
      allowClose: true,
      disableActiveInteraction: true,   // don't fire the highlighted control mid-tour
      overlayColor: '#0f172a',
      overlayOpacity: 0.55,
      smoothScroll: true,
      stagePadding: 6,
      stageRadius: 12,
      popoverClass: 'zr-tour',
      nextBtnText: 'Next',
      prevBtnText: 'Back',
      doneBtnText: 'Got it',
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
