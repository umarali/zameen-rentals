# Filters

The filter bar lets a renter pick a city, narrow by area, property type, bedrooms, price, size, furnished status and sort order, then reset everything. Each change re-runs the search, updates the results count and listing cards, and persists across reloads.

## Sub-features

- `city-switch` switches between Karachi, Lahore and Islamabad, reloading results and clearing area filters.
- `area-pick` picks an area through the autocomplete (type, arrow keys, click).
- `type-pick` filters by one property type (single-select; clicking it again deselects).
- `beds-pick` filters by bedroom count.
- `price-pick` applies a preset or custom PKR range.
- `size-pick` applies a size preset or custom range, in Marla (Lahore/Islamabad default) or Sq Yd (Karachi default).
- `more` covers furnishing (Any / Furnished / Unfurnished), sort order and preset bundles.
- `chip-clear` clears one filter through its chip's X.
- `clear-all` resets every filter and the NL input.

## How to get to it (user POV)

- City tabs at the top of the filter bar.
- Chips in the filter bar: Area, Type, Beds, Price, Size, More. Each opens a dropdown.
- The X inside a chip that has a value.
- The "Clear all" button, shown once any filter is set.
- Keyboard: ArrowDown/Enter inside the area input.

## Driving it with drive.sh

Preconditions:

- Doctor OK, app loaded on Lahore.
- Ready recipe: `drive.sh .claude/skills/verify-zameenrentals/steps/filters.mjs [--mobile]` covers `city-switch`, `area-pick`, `type-pick` and `clear-all`.

- **Switch city.** Choose the Karachi tab. Run `page.locator('.city-tab[data-city="karachi"]').click()`. The tab gains `active`, the first `#listingsGrid .card-wrap` contains `Karachi`, and `localStorage.rk_s` has `city: "karachi"`.
- **Pick area.** Open Area and choose Clifton. Run `page.locator("#areaChip").click()`, `page.locator("#areaInput").fill("Clifton")`, `page.locator(".area-opt", { hasText: "Clifton" }).first().click()`. `#areaChip` gains `has-value`, `#dd-area` loses `open`, and `#listingsTitle` contains `Clifton`.
- **Pick type.** Open Type and choose House. Run `page.locator("#typeChip").click()`, `page.locator('#typeGrid .chip[data-type="house"]').click()`. `#typeChip` gains `has-value`. With Clifton set, `#resultsCount` reads `Showing all 12` and every card says house and Clifton.
- **Pick beds.** Run `page.locator("#bedsChip").click()`, `page.locator('#bedRow .chip[data-beds="3"]').click()`. `#bedsChip` gains `has-value`.
- **Pick price.** Preset: `page.locator("#priceChip").click()`, `page.locator("#priceGrid .chip").first().click()`. Custom: click `'#priceGrid .chip[data-custom="1"]'`, fill `#priceMin` with `50000` and `#priceMax` with `100000`, then press Enter in `#priceMax`. `#priceChip` gains `has-value` and `#dd-price` closes.
- **Pick size.** Run `page.locator("#sizeChip").click()`, `page.locator('#sizeGrid .chip[data-smin="5"][data-smax="10"]').click()`. `#sizeChip` gains `has-value`. In Karachi, `'#sizeUnitToggle [data-unit="sqyd"]'` is `active` and `#sizeGrid` shows `sq yd`.
- **More.** Run `page.locator("#moreChip").click()`, then `page.locator('#furnishingRow [data-furnishing="unfurnished"]').click()` (gains `active`; the search sends `furnished=false`, while "Any" sends no `furnished` param) or `page.locator("#sortSelect").selectOption("price_low")`. `#moreChip` gains `has-value`.
- **Clear one.** Run `page.locator("#areaChip .chip-clear").click()`; for size, `'#sizeChip [data-chip-clear="size"]'`. That chip loses `has-value`.
- **Clear all.** Run `page.locator("#clearAllBtn").click()`. Every chip loses `has-value`, `#clearAllBtn` is hidden, and `#nlInput` is empty.
- **Proof.** Call `proof()` before and after the key filter, and read the same filters back with `api("/api/search?city=karachi&area=Clifton&property_type=house")` → `total > 0`.

## Gotchas

- On desktop, a city switch with no area set titles the list `Rentals in this map view` and counts only listings in the map viewport (Karachi showed 36, against 108 on mobile). Assert on cards or `.city-tab.active`, not the title or the count.
- Lahore autocomplete for `DHA` and `Bah` lists `DHA 11 Rahbar` and `Bahria Nasheman Iris` first. Match by `hasText` rather than taking the first option.
- The area input debounces typing. Wait for `.area-opt` with the expected text rather than sleeping.
- Switching city clears the area filter by design. That's expected, not a bug.
- Filter state persists in `localStorage.rk_s`. A drive that reloads keeps its filters, while a new drive starts clean.
