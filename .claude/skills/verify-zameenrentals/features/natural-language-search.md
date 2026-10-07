# Natural-language search

A renter types a plain-language request ("2 bed flat in DHA", "house in Clifton", "flat under 50k") and the app turns it into filters, runs the search, and shows what it understood as editable chips. Example suggestions offer one-click queries, and a near-miss area gets an approximate-match notice.

## Sub-features

- `nl-submit` submits a query with Enter or the search button, setting the matching filter chips.
- `nl-suggestions` shows example queries when the empty input is focused, hides them on typing or an outside click, and applies one when clicked.
- `nl-understood` shows the `Understood:` chip row. Removing a chip clears that filter.
- `nl-approx` shows a `No exact match for …` notice when the area is approximate.
- `nl-garbage` keeps the page working after an unparseable query.

## How to get to it (user POV)

- The search box at the top (`#nlInput`). Press Enter or click the search button.
- Focus the empty search box to see example suggestions.
- The `Understood:` row under the box after a search.

## Driving it with drive.sh

Preconditions:

- Doctor OK. Switch to Karachi first, since the queries use Karachi areas: `page.locator('.city-tab[data-city="karachi"]').click()`, then wait for `.card-wrap`.

- **Submit with Enter.** Type `2 bed flat in DHA` and press Enter. Run `page.locator("#nlInput").fill("2 bed flat in DHA")`, `page.locator("#nlInput").press("Enter")`. Cards reload, and `#bedsChip`, `#typeChip` and `#areaChip` all gain `has-value`.
- **Understood chips.** After the submit above, `#nlUnderstood` is visible and contains `Understood:`. Run `page.locator('#nlUnderstood [data-chip-remove="beds"]').click()`. `#bedsChip` loses `has-value` and that chip disappears.
- **Submit with button.** Run `page.locator("#nlInput").fill("house in Clifton")`, `page.locator("#nlSearchBtn").click()`. `#typeChip` and `#areaChip` gain `has-value`, and the cards are Clifton houses.
- **Price parse.** Run `fill("flat under 50k")` then press Enter. `#priceChip` gains `has-value`.
- **Suggestions.** Run `page.locator("#nlInput").focus()`. `#nlSuggestions` is visible. Click `.nl-ex` (first). The input clears and the area, type and beds chips gain `has-value`.
- **Approximate area.** Run `fill("house in gulshan e iqbal block 13")` then press Enter. `#nlUnderstood` contains `No exact match for`.
- **Garbage.** Run `fill("xyz")` then press Enter. `#listingsTitle` stays visible and `run.json` shows no page errors.
- **Proof.** Call `proof()` after submitting, showing both the chip row and the cards, and read back with `api("/api/parse-query?q=2%20bed%20flat%20in%20DHA&city=karachi")` → `filters.bedrooms == 2`.

## Gotchas

- Test mode uses only the **regex parser** (`ZAMEENRENTALS_PLAYWRIGHT=1`). Claude parsing is never exercised here, so a change to the Claude path needs `tests/test_parsing.py` and a manual check against a real `ANTHROPIC_API_KEY`.
- Queries resolve against the active city. "DHA" in Lahore resolves differently than in Karachi.
- Clear all also empties `#nlInput` and resets the title. Don't treat that as a regression.
- Roman Urdu aliases only exist for Karachi.
