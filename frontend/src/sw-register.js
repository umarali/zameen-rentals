/** Service worker registration, update handling, offline feedback queue replay. */

import { showToast } from './utils.js';

const FEEDBACK_QUEUE_KEY = 'zr_feedback_queue';

export function registerSW() {
  if (!('serviceWorker' in navigator)) return;

  navigator.serviceWorker.register('/sw.js', { scope: '/' }).then((reg) => {
    // Detect SW updates
    reg.addEventListener('updatefound', () => {
      const newWorker = reg.installing;
      if (!newWorker) return;
      newWorker.addEventListener('statechange', () => {
        if (newWorker.state === 'activated' && navigator.serviceWorker.controller) {
          showToast('App updated. Refresh for the latest version.', {
            action: { label: 'Refresh', onClick: () => location.reload() },
          });
        }
      });
    });
  }).catch((err) => {
    console.warn('SW registration failed:', err);
  });
}

// ===== OFFLINE FEEDBACK QUEUE =====

export function queueFeedback(message, context) {
  try {
    const queue = JSON.parse(localStorage.getItem(FEEDBACK_QUEUE_KEY) || '[]');
    queue.push({ message, context, queuedAt: Date.now() });
    localStorage.setItem(FEEDBACK_QUEUE_KEY, JSON.stringify(queue));
  } catch { /* storage full — silently drop */ }
}

export async function replayFeedbackQueue() {
  let queue;
  try {
    queue = JSON.parse(localStorage.getItem(FEEDBACK_QUEUE_KEY) || '[]');
  } catch { return; }
  if (!queue.length) return;

  const remaining = [];
  for (const item of queue) {
    try {
      const resp = await fetch('/api/feedback', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message: item.message, context: item.context }),
      });
      if (!resp.ok) remaining.push(item);
    } catch {
      remaining.push(item);
    }
  }

  if (remaining.length) {
    localStorage.setItem(FEEDBACK_QUEUE_KEY, JSON.stringify(remaining));
  } else {
    localStorage.removeItem(FEEDBACK_QUEUE_KEY);
    showToast('Queued feedback sent successfully.');
  }
}

// ===== ONLINE/OFFLINE LISTENERS =====

export function initOfflineHandlers() {
  const banner = document.getElementById('offlineBanner');
  if (!banner) return;

  function setOffline(offline) {
    if (offline) {
      banner.classList.remove('hidden');
    } else {
      banner.classList.add('hidden');
      replayFeedbackQueue();
    }
  }

  // Set initial state
  if (!navigator.onLine) setOffline(true);

  window.addEventListener('offline', () => setOffline(true));
  window.addEventListener('online', () => setOffline(false));
}
