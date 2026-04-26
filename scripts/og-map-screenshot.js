const { chromium } = require('playwright');

const HTML = `<!DOCTYPE html>
<html><head>
<meta charset="utf-8">
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css">
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<style>
  html,body,#map { margin:0; padding:0; height:100%; width:100%; background:#eef4f0; }
  .leaflet-control-attribution { display:none; }
  .leaflet-control-zoom { display:none; }
  .leaflet-container { background:#dde7df; outline:none; }
  .pin {
    width:28px; height:36px; position:relative;
    filter: drop-shadow(0 4px 6px rgba(12,71,53,.35));
  }
  .pin svg { width:100%; height:100%; display:block; }
  .pin-label {
    position:absolute; left:36px; top:6px;
    font: 700 16px/1.2 -apple-system, BlinkMacSystemFont, "Segoe UI", system-ui, sans-serif;
    color:#0f172a;
    background:rgba(255,255,255,.92);
    padding:3px 8px; border-radius:6px;
    box-shadow: 0 1px 2px rgba(0,0,0,.08);
    white-space:nowrap;
  }
</style>
</head>
<body>
<div id="map"></div>
<script>
  const map = L.map('map', { zoomControl:false, attributionControl:false, dragging:false, scrollWheelZoom:false, doubleClickZoom:false });

  // Carto Positron — clean, light tiles, OSM-based, free for commercial use, attribution-friendly
  L.tileLayer('https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png', {
    maxZoom: 18,
    subdomains: 'abcd'
  }).addTo(map);

  const cities = [
    { name: 'Islamabad', lat: 33.68, lng: 73.05 },
    { name: 'Lahore',    lat: 31.55, lng: 74.34 },
    { name: 'Karachi',   lat: 24.86, lng: 67.01 }
  ];

  function pinIcon(name) {
    return L.divIcon({
      className: '',
      html: \`<div class="pin">
        <svg viewBox="0 0 36 46" xmlns="http://www.w3.org/2000/svg">
          <defs><linearGradient id="g" x1="0" y1="0" x2="0" y2="1">
            <stop stop-color="#159A6C"/><stop offset="1" stop-color="#0C5A40"/>
          </linearGradient></defs>
          <path d="M18 0 C 8 0 0 8 0 18 C 0 32 14 44 16.5 45.5 C 17.5 46.2 18.5 46.2 19.5 45.5 C 22 44 36 32 36 18 C 36 8 28 0 18 0 Z" fill="url(#g)"/>
          <circle cx="18" cy="18" r="6.5" fill="#FFFDF8"/>
        </svg>
        <span class="pin-label">\${name}</span>
      </div>\`,
      iconSize: [28, 36],
      iconAnchor: [14, 36]
    });
  }

  cities.forEach(c => L.marker([c.lat, c.lng], { icon: pinIcon(c.name) }).addTo(map));

  // Fit Pakistan-ish bounds with padding so all three cities + country shape shows
  map.fitBounds([[23.5, 61.0], [36.5, 76.5]], { padding: [20, 20] });
</script>
</body></html>`;

(async () => {
  const browser = await chromium.launch();
  // Right half of OG card is ~460 wide × ~540 tall. Use 2x for retina.
  const W = 460, H = 540;
  const page = await browser.newPage({ viewport: { width: W, height: H }, deviceScaleFactor: 2 });
  await page.setContent(HTML, { waitUntil: 'networkidle' });
  await page.waitForTimeout(900);
  await page.screenshot({ path: 'static/og-map-bg.png', clip: { x: 0, y: 0, width: W, height: H } });
  await browser.close();
  console.log('saved static/og-map-bg.png');
})();
