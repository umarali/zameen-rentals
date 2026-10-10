# Map

A Leaflet map shows every rental that matches the current filters. On desktop it sits beside the results; on mobile the floating Map button opens it under the search and filter bar. Groups of rentals show as green count circles, single rentals as price pins ("85K", "1.2L"), and rentals that share one map point as a stack pill (dashed when it is a block or society's default pin, so approximate). Clicking a pin opens a preview card; clicking a stack lists its rentals. By default the list follows the map ("Search as I move the map"); turned off, moving the map shows a "Search this area" pill. Street and satellite layers persist across reloads.

## Sub-features

- `map-desktop` shows `#mapPanel` beside the results, with the summary card, layer, GPS and zoom controls.
- `map-summary` shows "N rentals in this view", the auto-search checkbox and a collapsible map key.
- `map-pins` draws clusters (`.map-cluster`), price pins (`.map-pin`) and stacks (`.map-stack`, `.is-approx` when approximate) from `/api/map-pins`.
- `map-preview` opens a popup card from a price pin, then the drawer from "View details".
- `map-stack` opens a stack popup, then lists that point's rentals ("Rentals on one map pin in …").
- `map-sync` highlights a card's pin while the card is hovered, and the card when its pin is clicked.
- `map-autosearch` turns list-follows-map on or off; off shows `.map-search-area` after the user moves the map.
- `map-layers` toggles street and satellite (satellite carries road and place labels), persisted across reloads.
- `map-mobile` opens `#mapOverlay` below `#filtersShell`, with a card rail (`#mapCarousel`), a count bar (`#mapSheetBar`), and Back closing it.

## How to get to it (user POV)

- Desktop: the map panel on the right.
- Mobile: the floating Map button; "Show list" in the bottom bar or the phone's Back closes it.
- The layer control in the map's top-right corner; the map key under the summary card (desktop) or behind the ⓘ button (mobile).

## Driving it with drive.sh

Preconditions:

- Doctor OK. Pick the viewport with or without `--mobile`. Seeded pins sit near each seeded area's centre, so at city zoom they appear as clusters.

- **Desktop panel.** Without `--mobile`, `#mapPanel` is visible, `#mapContainer` has `leaflet-container`, `#mapContainer .leaflet-control-zoom` is visible, and `#mapFab` is hidden.
- **Summary.** `#mapCoverageBadge [data-map-count]` shows a number. Click `[data-map-key-toggle]`; `[data-map-key]` lists the pin, stack, cluster and viewed styles.
- **Pins.** `#mapContainer .map-cluster` count is greater than 0. Click one; the map zooms and `.map-pin`, `.map-stack` or smaller clusters replace it.
- **Preview.** Click a `.map-pin`. `.pin-popup` shows the listing; `[data-preview-open]` opens `#drawer` (`drawer-open`).
- **Stack.** Click a `.map-stack`, then `[data-stack-search]`. `#listingsTitle` reads "Rentals on one map pin …" and `.map-search-area` reads "Show all rentals in this view".
- **Auto-search off.** Uncheck `#mapCoverageBadge [data-map-autosearch]`, focus `#mapContainer` and press an arrow key. `#mapPanel .map-search-area` appears and no `/api/map-search` request fires until it's clicked.
- **Satellite.** Click `#mapContainer [data-map-layer="satellite"]`. It gains `active` and a `.leaflet-tile` `src` contains `arcgisonline`. After `page.reload()` it is still `active`.
- **Mobile overlay.** With `--mobile`, click `#mapFab`. `#mapOverlay` is visible, starts at the bottom of `#filtersShell`, and `#mapCarousel .map-card` appears. Filter chips still open their sheets. `page.goBack()` hides `#mapOverlay`.
- **Proof.** Call `proof()` with the map visible on both viewports, and look at the PNG to judge tiles, clusters and pins.

## Gotchas

- Tiles load from the internet (`tile.openstreetmap.org`, `server.arcgisonline.com`). Offline runs show grey tiles; pins still render. Cancelled tile requests during pan, zoom or city switch are harmless.
- With auto-search on, panning changes the results list. A popup nudging the map into view does not.
- Playwright's mouse drags can fling the map with inertia; pan with the keyboard (focus `#mapContainer`, arrow keys) for predictable moves.
- `.area-label-active` (the selected area's label) is removed at street zoom by design.
- Seeded listings at the same coordinate show as one stack, not overlapping pins.
