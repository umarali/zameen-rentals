# Zameen.com Scraping — Quirks & Learnings

## HTML Structure

Zameen.com listing cards use semantic HTML:
- Cards: `li[role="article"]`
- Title: `h2 > a`
- Price: `span[aria-label="Price"]`
- Beds/Baths: `span[aria-label="Beds"]`, `span[aria-label="Baths"]`
- Area size: `span[aria-label="Area"]`
- Location: `span[aria-label="Location"]`
- Photos: `img[aria-label="Listing photo"]`

## Property Type Detection Pitfalls

When inferring property type from card text:
- Pattern order matters. "Upper portion" must be checked before "house" because a house listing can mention "upper portion" in its description.
- Some listings cross-reference types: "House with separate upper portion entrance"
- **Solution**: When a property type filter is active, override the text-inferred type with the requested type — the URL already filters server-side.

## Total Count Extraction

Zameen.com shows total results in an `h1` heading, e.g., "478 Houses for Rent in Gulshan-e-Iqbal".
- The regex `r'(\d[\d,]*)\s+(?:Flats?|Homes?|Houses?|Properties|Rooms?|Portions?|Penthouses?)'` extracts this.
- This is the cross-page total (all pages), not the per-page count.
- Per page: typically 15 listings.
- **Gotcha**: The total may not match the loaded count. Frontend now shows "Showing X of Y results".

## Location Text Bleeding

The `span[aria-label="Location"]` element sometimes bleeds in area-size numbers from adjacent elements:
```
"DHA Phase 845292 Sq. Yd."  ← "45292 Sq. Yd." bleeds from area-size
```
We strip these with regex: `re.sub(r'[\d,]+\s*(?:Sq\.?\s*(?:Yd|Ft|M)\.?|Marla|Kanal).*$', '', loc_text)`

## Image Extraction

Multiple strategies needed:
1. `img[aria-label="Listing photo"]` — primary, most reliable
2. `picture > source[srcset]` — fallback for lazy-loaded images
3. First `img` inside `a[href*="/Property/"]` — last resort

Must filter out agent avatars/logos using URL pattern matching (skip URLs containing "agent", "profile", "avatar", etc.) and size checks (skip images < 300px).

## Rate Limiting

Zameen.com returns 429 on aggressive scraping. Current approach:
- 2 req/sec rate limit (token bucket in `cache.py`)
- Exponential backoff on 429 responses (up to 3 retries)
- Random User-Agent rotation
- 5-minute cache TTL to minimize requests

## Price Formats

Pakistani prices come in various formats:
- "1.5 Lakh" = 150,000 PKR
- "50 Thousand" = 50,000 PKR
- "2 Crore" = 20,000,000 PKR
- "PKR 50,000" = 50,000 PKR
- "Rs. 1.5 Lac" = 150,000 PKR

The `parse_price()` function handles all these variations.

## Embedded search state (checked 2026-10-07)

Search pages embed their results as JSON in `window.state.algolia.content.hits`,
25 per page, with `nbHits` and `nbPages` alongside. Each hit has:

- `category`: the leaf (highest `level`) is the property type: Flats, Houses,
  Upper Portions, Lower Portions, Rooms, Penthouse, Farm Houses.
- `geography` with `hasExactGeography`.
- `phoneNumber`: phone, mobile, WhatsApp. These are the same numbers the
  `showNumbers` call returns.
- `createdAt` and `updatedAt` as Unix timestamps, `isVerified`, `agency.product`,
  `photoCount`, and Urdu `title_l1` and `shortDescription_l1`.

`scraper.enrich_from_search_state()` overlays type, coordinates and contact
details onto the cards parsed from HTML. When every listing in an area has a
category, the crawler skips the type-specific URLs.

Listing detail pages embed `window.state.property.data`, which includes amenities.

Despite the "algolia" key, the active backend is Elasticsearch. The page
config contains credentials for that cluster. Do not use them: querying a
backend with embedded credentials isn't the same as reading public pages.

## Nearby places

The detail page's Nearby tab calls
`GET /api/places?latitude=&longitude=&category=&radius=` (radius in metres).
Categories are `EDUCATION`, `FOOD_BEVERAGE`, `MEDICAL_HEALTH` and
`FITNESS_RECREATION`. The response is `data[]` with `name`, `location`
(`latitude`, `longitude`), `matched_categories` and `id`. The IDs follow
Geoapify's format, which is built on OpenStreetMap, so the same data can be
pulled from OpenStreetMap directly without going through Zameen.
