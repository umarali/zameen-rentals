/** PWA install prompt — subtle bottom banner with 30s delay. */

import { track } from './analytics.js';

const DISMISS_KEY = 'zr_install_dismissed';
const DISMISS_DAYS = 7;
const SHOW_DELAY_MS = 30_000;

let deferredPrompt = null;

export function initInstallPrompt() {
  // Already installed in standalone mode
  if (window.matchMedia('(display-mode: standalone)').matches) return;

  window.addEventListener('beforeinstallprompt', (e) => {
    e.preventDefault();
    deferredPrompt = e;
    scheduleShow();
  });

  // iOS detection — no beforeinstallprompt
  if (isIOS() && !isStandalone()) {
    scheduleShow();
  }

  window.addEventListener('appinstalled', () => {
    deferredPrompt = null;
    hideBanner();
    track('pwa_installed');
  });
}

function scheduleShow() {
  // Check if recently dismissed
  const dismissed = localStorage.getItem(DISMISS_KEY);
  if (dismissed && Date.now() - Number(dismissed) < DISMISS_DAYS * 86400000) return;

  setTimeout(showBanner, SHOW_DELAY_MS);
}

function showBanner() {
  const banner = document.getElementById('installBanner');
  if (!banner) return;

  const msgEl = banner.querySelector('#installMsg');
  if (msgEl && isIOS()) {
    msgEl.textContent = 'Tap Share then "Add to Home Screen" for faster access';
  }

  // Hide install button on iOS (they must use Share menu)
  const installBtn = banner.querySelector('#installBtn');
  if (installBtn && isIOS()) installBtn.classList.add('hidden');

  banner.classList.remove('hidden');
  track('install_banner_shown');

  const dismissBtn = banner.querySelector('#installDismiss');
  if (dismissBtn) dismissBtn.addEventListener('click', dismiss, { once: true });
  if (installBtn) installBtn.addEventListener('click', doInstall, { once: true });
}

function hideBanner() {
  const banner = document.getElementById('installBanner');
  if (banner) banner.classList.add('hidden');
}

function dismiss() {
  localStorage.setItem(DISMISS_KEY, String(Date.now()));
  hideBanner();
  track('install_banner_dismissed');
}

async function doInstall() {
  if (!deferredPrompt) return;
  deferredPrompt.prompt();
  const { outcome } = await deferredPrompt.userChoice;
  track('install_prompt_outcome', { outcome });
  deferredPrompt = null;
  hideBanner();
}

function isIOS() {
  return /iPad|iPhone|iPod/.test(navigator.userAgent) && !window.MSStream;
}

function isStandalone() {
  return window.matchMedia('(display-mode: standalone)').matches || navigator.standalone === true;
}
