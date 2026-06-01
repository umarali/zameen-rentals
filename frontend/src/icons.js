/** Canonical icon set — one coherent style so every surface (cards, drawer,
 *  compare, panels) shows the same glyph for the same thing.
 *
 *  Style: 24×24 viewBox, stroke-based, stroke-width 2, round caps/joins.
 *  The only fill-based glyphs are the WhatsApp brand logo and the filled-heart
 *  (active favorite) state — brand/solid marks should not be stroked.
 *
 *  Each export is a factory taking an optional CSS class so the SAME geometry
 *  is reused at any size (size lives in CSS/classes, never in the path).
 */

const STROKE_ATTRS = 'fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" viewBox="0 0 24 24"';

function stroke(inner, cls = '') {
  return `<svg ${cls ? `class="${cls}" ` : ''}${STROKE_ATTRS}>${inner}</svg>`;
}
function solid(inner, cls = '') {
  return `<svg ${cls ? `class="${cls}" ` : ''}fill="currentColor" viewBox="0 0 24 24">${inner}</svg>`;
}

const PATHS = {
  bed: '<path d="M2 17V7a2 2 0 012-2h16a2 2 0 012 2v10M2 17h20M6 17v2m12-2v2M6 11h.01M6 7h12v4H6V7z"/>',
  bath: '<path d="M3 13h18v2a4 4 0 01-4 4H7a4 4 0 01-4-4v-2zM5 13V6a2 2 0 012-2h1a2 2 0 012 2v1"/>',
  area: '<path d="M4 8V4m0 0h4M4 4l5 5m11-1V4m0 0h-4m4 0l-5 5M4 16v4m0 0h4m-4 0l5-5m11 5l-5-5m5 5v-4m0 4h-4"/>',
  pin: '<path d="M17.657 16.657L13.414 20.9a1.998 1.998 0 01-2.827 0l-4.244-4.243a8 8 0 1111.314 0z"/><path d="M15 11a3 3 0 11-6 0 3 3 0 016 0z"/>',
  heart: '<path d="M12 21s-7-4.534-7-10a4 4 0 017-2.646A4 4 0 0119 11c0 5.466-7 10-7 10z"/>',
  hide: '<path d="M13.875 18.825A10.05 10.05 0 0112 19c-7 0-10-7-10-7a16.94 16.94 0 014.169-5.249M9.88 5.083A10.052 10.052 0 0112 5c7 0 10 7 10 7a16.927 16.927 0 01-2.062 3.054M3 3l18 18"/>',
  compare: '<path d="M9 4v16M15 4v16M4 9h5M15 9h5M4 15h5M15 15h5"/>',
  external: '<path d="M18 13v6a2 2 0 01-2 2H5a2 2 0 01-2-2V8a2 2 0 012-2h6M15 3h6v6M10 14L21 3"/>',
  eye: '<path d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z"/><path d="M15 12a3 3 0 11-6 0 3 3 0 016 0z"/>',
  phone: '<path d="M3 5a2 2 0 012-2h3.28a1 1 0 01.948.684l1.498 4.493a1 1 0 01-.502 1.21l-2.257 1.13a11.042 11.042 0 005.516 5.516l1.13-2.257a1 1 0 011.21-.502l4.493 1.498a1 1 0 01.684.949V19a2 2 0 01-2 2h-1C9.716 21 3 14.284 3 6V5z"/>',
  bell: '<path d="M15 17h5l-1.4-1.4A2 2 0 0118 14.2V11a6 6 0 10-12 0v3.2a2 2 0 01-.6 1.4L4 17h5m6 0a3 3 0 11-6 0"/>',
  image: '<path d="M2.25 15.75l5.159-5.159a2.25 2.25 0 013.182 0l5.159 5.159m-1.5-1.5l1.409-1.409a2.25 2.25 0 013.182 0l2.909 2.909M3.75 19.5h16.5a1.5 1.5 0 001.5-1.5V6a1.5 1.5 0 00-1.5-1.5H3.75A1.5 1.5 0 002.25 6v12a1.5 1.5 0 001.5 1.5zm10.125-11.25a.375.375 0 11-.75 0 .375.375 0 01.75 0z"/>',
};

// WhatsApp brand logo (fill).
const WHATSAPP_INNER = '<path d="M17.472 14.382c-.297-.149-1.758-.867-2.03-.967-.273-.099-.471-.148-.67.15-.197.297-.767.966-.94 1.164-.173.199-.347.223-.644.075-.297-.15-1.255-.463-2.39-1.475-.883-.788-1.48-1.761-1.653-2.059-.173-.297-.018-.458.13-.606.134-.133.298-.347.446-.52.149-.174.198-.298.298-.497.099-.198.05-.371-.025-.52-.075-.149-.669-1.612-.916-2.207-.242-.579-.487-.5-.669-.51-.173-.008-.371-.01-.57-.01-.198 0-.52.074-.792.372-.272.297-1.04 1.016-1.04 2.479 0 1.462 1.065 2.875 1.213 3.074.149.198 2.096 3.2 5.077 4.487.709.306 1.262.489 1.694.625.712.227 1.36.195 1.871.118.571-.085 1.758-.719 2.006-1.413.248-.694.248-1.289.173-1.413-.074-.124-.272-.198-.57-.347m-5.421 7.403h-.004a9.87 9.87 0 01-5.031-1.378l-.361-.214-3.741.982.998-3.648-.235-.374a9.86 9.86 0 01-1.51-5.26c.001-5.45 4.436-9.884 9.888-9.884 2.64 0 5.122 1.03 6.988 2.898a9.825 9.825 0 012.893 6.994c-.003 5.45-4.437 9.884-9.885 9.884m8.413-18.297A11.815 11.815 0 0012.05 0C5.495 0 .16 5.335.157 11.892c0 2.096.547 4.142 1.588 5.945L.057 24l6.305-1.654a11.882 11.882 0 005.683 1.448h.005c6.554 0 11.89-5.335 11.893-11.893a11.821 11.821 0 00-3.48-8.413z"/>';

export const bedIcon = (cls) => stroke(PATHS.bed, cls);
export const bathIcon = (cls) => stroke(PATHS.bath, cls);
export const areaIcon = (cls) => stroke(PATHS.area, cls);
export const pinIcon = (cls) => stroke(PATHS.pin, cls);
export const hideIcon = (cls) => stroke(PATHS.hide, cls);
export const compareIcon = (cls) => stroke(PATHS.compare, cls);
export const externalIcon = (cls) => stroke(PATHS.external, cls);
export const eyeIcon = (cls) => stroke(PATHS.eye, cls);
export const callIcon = (cls) => stroke(PATHS.phone, cls);
export const bellIcon = (cls) => stroke(PATHS.bell, cls);
export const imageIcon = (cls) => stroke(PATHS.image, cls);
export const favHollowIcon = (cls) => stroke(PATHS.heart, cls);
export const favFilledIcon = (cls) => solid(PATHS.heart, cls);
export const whatsappIcon = (cls) => solid(WHATSAPP_INNER, cls);

// Back-compat string constants (no size class — sized by surrounding CSS).
export const FAV_FILLED_SVG = favFilledIcon();
export const FAV_HOLLOW_SVG = favHollowIcon();
export const HIDE_SVG = hideIcon();
export const COMPARE_SVG = compareIcon();
