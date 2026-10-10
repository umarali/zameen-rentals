# Map

A Leaflet map shows where the listings are. On desktop it sits beside the results. On mobile a floating Map button opens it full screen. Area markers show coverage (green has listings, grey preview only, red exact listing pin). Clicking a red pin opens a preview card with the listing's photo gallery. The user can switch between street and satellite layers. The layer choice survives a reload.

## Sub-features

- `map-desktop` shows `#mapPanel` beside the results on desktop, with zoom, layer and GPS controls.
- `map-mobile` opens a full-viewport `#mapOverlay` from `#mapFab` on mobile, with a close button.
- `map-preview` opens a preview card from a red exact pin: the cover photo first, then the listing's full photo set with arrows and a counter; "View details" or a photo opens the drawer.
- `map-layers` toggles street and satellite, persisted across reloads.
- `map-markers` shows area markers after a city search, plus exact listing pins in area mode.

## How to get to it (user POV)

- Desktop: the map panel on the right.
- Mobile: the floating Map button, then the close button in the overlay.
- The layer control in the map's top-right corner.

## Driving it with drive.sh

Preconditions:

- Doctor OK. Pick the viewport with or without `--mobile`. Switch to Karachi for the marker recipes.

- **Desktop panel.** Without `--mobile`, `#mapPanel` is visible, `#mapContainer` has `leaflet-container`, `#mapContainer .leaflet-control-zoom` is visible, and `#mapFab` is hidden.
- **Pin preview.** Zoom in (`#mapContainer .leaflet-control-zoom-in`) until `#mapContainer .listing-exact-marker` appears, then click one (`{ force: true }`, it's an SVG path). `.pin-popup` shows the listing; `[data-gallery-count]` reads "1 / N" once photos load (test mode doesn't scrape, so mock `/api/listing-detail` to return `images`). `[data-gallery-next]` advances it; `[data-preview-open]` opens `#drawer` (`drawer-open`).
- **Satellite.** Run `page.locator('#mapContainer [data-map-layer="satellite"]').first().click()`. The button gains `active` and `#mapContainer .leaflet-tile` has an `src` containing `arcgisonline`. Run `page.reload()`. Satellite is still `active`.
- **Area markers.** Switch to Karachi. `#mapContainer .area-marker` count is greater than 0.
- **Exact pins.** In Karachi, pick area Clifton (see filters.md). `#mapContainer .listing-exact-marker` appears for the seeded listings that have coordinates.
- **Mobile overlay.** With `--mobile`, run `page.locator("#mapFab").click()`. `#mapOverlay` is visible, its bounding box equals the viewport, and `#mapOverlay .leaflet-tile` is attached. Run `page.locator("#mapOverlayClose").click()`. `#mapOverlay` is hidden.
- **Proof.** Call `proof()` with the map visible, on both viewports, and look at the PNG to judge tile and marker rendering.

## Gotchas

- Tiles load from the internet (`tile.openstreetmap.org`, `server.arcgisonline.com`). Offline runs show grey tiles. Cancelled tile requests in `run.json` during pan, zoom or city switch are harmless.
- On desktop the result list follows the map viewport ("Rentals in this map view"), so panning changes the results count.
- There is no coverage badge or "areas on map" panel; it was removed on purpose.
- Photos beyond the cover come from `/api/listing-detail`, a live Zameen fetch (about 5 s the first time).
- Smooth scrolling and Leaflet's pan animation don't run in a background browser tab; judge the gallery arrows and popup auto-pan headlessly.
- `.area-label-active` is removed at street zoom by design.
