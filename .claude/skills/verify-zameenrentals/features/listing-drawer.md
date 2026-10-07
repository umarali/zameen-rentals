# Listing drawer

Clicking a listing card opens a detail drawer with the title, price, photos, a mini map, nearby-area shortcuts and a link to the original Zameen.com page. Photos open in a full-screen gallery. The drawer slides in from the side on desktop and up from the bottom (full screen) on mobile.

## Sub-features

- `drawer-open` opens a drawer from a card, showing the title, price and image area.
- `drawer-close` closes it with the close button, an overlay click or Escape.
- `drawer-link` shows a `View on Zameen.com` link pointing at zameen.com.
- `drawer-nearby` closes the drawer and searches when a nearby area chip is clicked.
- `drawer-minimap` shows a mini map that follows the active layer (street or satellite).
- `gallery` opens a photo gallery from the drawer image, with next/prev, arrow keys, bounds and close.

## How to get to it (user POV)

- Click any listing card in the results grid.
- Inside the drawer: the image (gallery), nearby chips, the close button.
- Close with Escape or by clicking the dimmed overlay.

## Driving it with drive.sh

Preconditions:

- Doctor OK, cards loaded. Any city works.

- **Open.** Run `page.locator(".card-wrap").first().click()`. `#drawer` gains `drawer-open`, `#drawerOverlay` gains `overlay-open`, and `#drawerContent` shows the title and a PKR price.
- **Zameen link.** `page.locator('#drawerContent a[title="View on Zameen.com"]')` is visible and its `href` contains `zameen.com`. Don't click it: it leaves the app.
- **Image and mini map.** `#drawerImgArea` is visible and `#drawerMiniMap` is attached.
- **Close.** Run `page.locator("#drawerClose").click()`, or `page.keyboard.press("Escape")`, or `page.locator("#drawerOverlay").click({ force: true })`. `#drawer` loses `drawer-open`.
- **Nearby.** Reopen the drawer. If `#drawerContent [data-nearby]` exists, click the first one. The drawer closes and `#areaChip` gains `has-value`.
- **Gallery.** In the open drawer, run `page.locator("[data-gallery]").first().click()`. `#galleryModal` loses `hidden` and `#galleryCounter` reads `1 / N`. `#galleryNext` and `#galleryPrev` step through, and `#galleryClose` hides it.
- **Mobile.** Repeat Open with `--mobile`. The drawer opens from the bottom and fills the viewport.
- **Proof.** Call `proof()` with the drawer open and again after closing, and on mobile with `--mobile`.

## Gotchas

- Seeded listings have **one image each** (`/static/favicon-512.png`), so the gallery reads `1 / 1` and next/prev can't advance. The multi-image paths are only covered by `tests/gallery.spec.js`, which mocks a 3-image payload. Report next/prev as unverifiable here rather than faking it.
- Test mode returns null phones from `/api/listing-contact`, so Call and WhatsApp buttons can't prove real contact lookups.
- Listing detail comes from the local DB. Live detail scraping is off, so seeded listings may show few fields.
- Nearby chips depend on area geography and may be absent for a given card. Check the count before clicking.
