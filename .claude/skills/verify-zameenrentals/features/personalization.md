# Personalization

Without an account, a renter can save homes to favorites, hide listings they don't want, and save the current search as an alert for new matches. Everything is collected in the My rentals panel (tabs: New matches, Saved homes, Viewed, Hidden). State is tied to an anonymous client ID stored in the browser.

## Sub-features

- `fav-toggle` saves or removes a favorite from a card's heart button.
- `hide` hides a listing from results.
- `alert-save` saves the current search as an alert through the Save search modal.
- `alert-delete` deletes an alert from the panel.
- `panel` opens My rentals from the bell, shows four tabs and closes on Escape.

## How to get to it (user POV)

- The heart (`Save to favorites`) and hide buttons on each listing card.
- The Save search button in the header opens the alert modal.
- The bell button in the header opens My rentals.

## Driving it with drive.sh

Preconditions:

- Doctor OK, cards loaded. Each drive starts with a fresh `zr_client_id`, so nothing is saved yet.

- **Favorite.** Run `const card = page.locator(".card-wrap").first(); const zid = await card.getAttribute("data-zameen-id"); await card.locator('[data-action="favorite"]').click()`. The button's `aria-pressed` becomes `true` and `#toastStack` contains `Saved to favorites`. Read back with `api("/api/favorites")` → `json.favorites` includes `zid`.
- **Unfavorite.** Click the same button again. `aria-pressed="false"`, the toast says `Removed from favorites`, and `api("/api/favorites")` no longer lists it.
- **Hide.** Run `card.locator('[data-action="hide"]').click()`. The card leaves the grid and the toast contains `Hidden`. Read back with `api("/api/hidden")` → `json.hidden` includes the ID.
- **Save search.** Set a filter first (for example, Karachi plus area Clifton). Run `page.locator("#saveSearchBtn").click()`. `#saveSearchModal` is visible and `#saveSearchPreview` names the filters. Optionally fill `#saveSearchLabel`, then click `#saveSearchSubmit`. The toast says `Alert saved`. Read back with `api("/api/alerts")` → one alert with those filters.
- **Panel.** Run `page.locator("#alertsBellBtn").click()`. `#personalizationPanel` loses `hidden`, `#personalizationPanel .personalization-drawer` contains `My rentals`, and `[data-ptab="alerts"|"favorites"|"recent"|"hidden"]` are all visible. `#personalizationBody` lists the saved alert. Escape closes the panel.
- **Delete alert.** In the panel, run `page.locator('#personalizationBody [data-alert-action="delete"]').first().click()`. The toast contains `Alert deleted` and the body shows the empty state (`Set up your first alert` or `No alerts yet`).
- **Proof.** Call `proof()` before and after each mutation, each paired with the `api()` readback.

## Gotchas

- The `api()` helper sends the page's `X-Client-Id`. A raw `curl` without it returns 400 or another user's empty state.
- Push notifications (`#alertsEnablePush`) need a browser permission grant and a VAPID push service. Headless runs can't prove delivery, so report it as unreachable.
- Hidden listings stay out of results for this client ID only. A fresh drive sees them again.
- With no filters set, the Save search modal falls back to a generic name (`Get alerts for new rentals`). Set filters first to prove the preview.
