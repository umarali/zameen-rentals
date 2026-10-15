/** Photo-local zoom and pan. Browser page zoom remains available outside the gallery. */
export function initGalleryZoom(onSwipe) {
  const stage = document.getElementById('galleryImg');
  const img = stage.querySelector('img');
  const modal = document.getElementById('galleryModal');
  // Keep WebKit's native pinch gesture local to this overlay too.
  for (const type of ['gesturestart', 'gesturechange']) {
    modal.addEventListener(type, e => e.preventDefault(), { passive: false });
  }
  modal.addEventListener('touchmove', e => {
    if (e.touches.length > 1) e.preventDefault();
  }, { passive: false });
  const points = new Map();
  let scale = 1, x = 0, y = 0, start, pinch, multi = false, suppressUntil = 0;
  const clamp = (value, limit) => Math.max(-limit, Math.min(limit, value));
  function render() {
    x = clamp(x, img.clientWidth * (scale - 1) / 2);
    y = clamp(y, img.clientHeight * (scale - 1) / 2);
    img.style.transform = `translate(${x}px, ${y}px) scale(${scale})`;
    document.getElementById('galleryZoomReset').textContent = `${Math.round(scale * 100)}%`;
    document.getElementById('galleryZoomOut').disabled = scale <= 1;
    document.getElementById('galleryZoomIn').disabled = scale >= 4;
  }
  function reset() { points.clear(); start = pinch = null; multi = false; scale = 1; x = y = 0; render(); }
  function zoom(value) { scale = Math.max(1, Math.min(4, value)); render(); }
  function pair() {
    const [a, b] = [...points.values()];
    return { distance: Math.hypot(a.x - b.x, a.y - b.y), x: (a.x + b.x) / 2, y: (a.y + b.y) / 2 };
  }
  function beginPinch() {
    const box = stage.getBoundingClientRect();
    pinch = { ...pair(), scale, panX: x, panY: y, cx: box.left + box.width / 2, cy: box.top + box.height / 2 };
  }
  stage.addEventListener('pointerdown', e => {
    if (e.pointerType === 'mouse' && e.button !== 0) return;
    stage.setPointerCapture(e.pointerId);
    points.set(e.pointerId, { x: e.clientX, y: e.clientY });
    if (points.size === 1) { start = { px: e.clientX, py: e.clientY, x, y }; multi = false; }
    if (points.size === 2) {
      multi = true;
      beginPinch();
    }
  });
  stage.addEventListener('pointermove', e => {
    if (!points.has(e.pointerId)) return;
    points.set(e.pointerId, { x: e.clientX, y: e.clientY });
    if (points.size >= 2 && pinch) {
      const current = pair();
      scale = Math.max(1, Math.min(4, pinch.scale * current.distance / Math.max(1, pinch.distance)));
      x = current.x - pinch.cx - (pinch.x - pinch.cx - pinch.panX) * scale / pinch.scale;
      y = current.y - pinch.cy - (pinch.y - pinch.cy - pinch.panY) * scale / pinch.scale;
      suppressUntil = Date.now() + 400;
      render();
    } else if (start && scale > 1) {
      x = start.x + e.clientX - start.px; y = start.y + e.clientY - start.py;
      suppressUntil = Date.now() + 400;
      render();
    }
  });
  function finish(e) {
    if (!points.has(e.pointerId)) return;
    if (e.type === 'pointerup' && points.size === 1 && !multi && start && scale === 1) {
      const dx = e.clientX - start.px, dy = e.clientY - start.py;
      if (Math.abs(dx) > 50 && Math.abs(dx) > Math.abs(dy) * 1.2) { suppressUntil = Date.now() + 400; onSwipe(dx < 0 ? 1 : -1); }
    }
    points.delete(e.pointerId); pinch = null;
    if (points.size >= 2) beginPinch();
    else if (points.size === 1) { const p = [...points.values()][0]; start = { px: p.x, py: p.y, x, y }; }
    else start = null;
  }
  stage.addEventListener('pointerup', finish);
  stage.addEventListener('pointercancel', finish);
  stage.addEventListener('click', e => { if (Date.now() < suppressUntil) { e.preventDefault(); e.stopImmediatePropagation(); } }, true);
  stage.addEventListener('dblclick', e => { e.preventDefault(); zoom(scale > 1 ? 1 : 2); });
  stage.addEventListener('wheel', e => { e.preventDefault(); zoom(scale * (e.deltaY < 0 ? 1.15 : 1 / 1.15)); }, { passive: false });
  document.getElementById('galleryZoomIn').addEventListener('click', () => zoom(scale + 0.5));
  document.getElementById('galleryZoomOut').addEventListener('click', () => zoom(scale - 0.5));
  document.getElementById('galleryZoomReset').addEventListener('click', reset);
  window.addEventListener('resize', render);
  reset();
  return reset;
}
