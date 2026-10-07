# ZameenRentals

A fast rental property search engine powered by [Zameen.com](https://www.zameen.com) data. Built with FastAPI and vanilla JavaScript.

Supports **Karachi** (366 areas), **Lahore** (462 areas), and **Islamabad** (303 areas).

## Features

- Search rental listings across 1,100+ areas in Karachi, Lahore, and Islamabad
- Interactive Leaflet map with area labels and result count badges
- Filter by area, property type, bedrooms, price range, and furnishing
- Natural language search (powered by Claude) — e.g. "2 bed flat DHA under 50k"
- Sort by price or date
- Image carousels and detail drawer for each listing
- Quick-access preset chips (Budget 1BR, Family Home, etc.)
- Mobile-friendly responsive UI with full-screen map overlay
- In-memory caching (5 min TTL) and rate limiting

## Tech Stack

- **Backend:** Python, FastAPI, httpx, BeautifulSoup
- **Frontend:** Modular vanilla JavaScript, Vite, Tailwind CSS v4, Leaflet.js
- **Data Source:** Zameen.com public listings

## Getting Started

```bash
pip install -r requirements.txt
npm ci
npm run build
uvicorn main:app --reload --port 8000
```

Open [http://localhost:8000](http://localhost:8000)

Edit frontend source in `frontend/`; `npm run build` regenerates `static/`.

### Database and tests

The app stores SQLite data and push keys in `data/`. Set
`ZAMEENRENTALS_DB_DIR` to use a different directory. If the database is missing
but its `-wal` or `-shm` recovery files remain, startup stops to preserve them.
Restore a verified complete backup before using that directory.

```bash
pip install pytest pytest-asyncio
python3 -m pytest -q
npx playwright install chromium --only-shell
npm test
```

Browser tests run headlessly against a temporary database with sample listings
in all three cities. They start their own server on port 8000 and refuse to
reuse an existing app server. Stop any local server on that port first.
The test server disables live Zameen scraping and uses temporary push keys.

Size-filtered searches currently use local listings only. Live fallback does
not support size bounds, so it cannot supply results for those searches.

### Listing tags (Jev)

`tools/tag_listings.py` asks [TypeSafe Jev](https://api.typesafe.ai) four typed
questions about each crawled listing: who may rent it (family, bachelor, either,
unclear), and whether it states backup power, a separate entrance or a new
build. Answers go in the `listing_tags` table. Search can filter on them
(`tenant`, `backup_power`, `separate_entrance`) and returns a `tags` object per
listing.

Only confident answers count. A tenant answer needs confidence of at least 0.7
and a feature needs probability of at least 0.8. Anything less is shown as
unknown, so an unsure answer never hides a listing. The thresholds are in
`app/listing_tags.py`.

Setup: put `TYPESAFE_API_KEY` in `.env` (never with a `VITE_` prefix, which
would ship it to browsers). Without the key nothing is tagged and search works
as before. The model is pinned to `jev-1.13.0`; override with `TYPESAFE_MODEL`.

```bash
python3 tools/tag_listings.py --dry-run      # count and cost estimate, no API calls
python3 tools/tag_listings.py --limit 2000   # run on a timer next to the crawler
```

The tagger only scores listings that are new, have changed (`content_hash`),
or have gained a description. By default it skips listings without a
description, because titles rarely say who may rent. A listing costs about 270
input tokens from its title, or about 500 with a description, at $0.042 per
million: roughly $0.40 to $0.60 for 30,000 listings.

Check quality before adding filter chips to the UI:

```bash
python3 tools/eval_listing_tags.py sample --n 150 --out labels.csv
# label tenant_fit and the y/n columns by hand, then:
python3 tools/eval_listing_tags.py score labels.csv
```

`score` prints precision and recall for Jev and for a keyword baseline. Where
the keywords do as well, that tag doesn't need Jev.

## API Endpoints

| Endpoint | Description |
|---|---|
| `GET /` | Web app |
| `GET /api/cities` | List all supported cities |
| `GET /api/search` | Search listings (params: `city`, `area`, `property_type`, `bedrooms`, `price_min`, `price_max`, `furnished`, `sort`, `page`, `tenant`, `backup_power`, `separate_entrance`) |
| `GET /api/areas` | List all supported areas (param: `city`) |
| `GET /api/property-types` | List all property types |
| `GET /api/parse-query` | Parse natural language query into filters |
| `GET /api/health` | Health check |

## Project Structure

```
main.py              # Entry point
app/
  __init__.py        # FastAPI app setup
  routes.py          # API endpoints
  scraper.py         # Zameen.com scraper & parser
  data.py            # Multi-city area definitions, property types, translations
  database.py        # SQLite: search history, listing cache
  cache.py           # In-memory cache with TTL
  parsing.py         # Claude-powered NL query parsing
static/
  index.html         # Frontend (HTML + CSS + JS)
tools/
  discover_areas.py  # Utility to discover new areas from Zameen.com
```

## Roadmap

- [x] Lahore support (462 areas)
- [x] Islamabad support (303 areas)
- [ ] Favourites / saved searches
- [ ] Price trend charts
- [ ] Push notifications for new listings

## Disclaimer

This project scrapes publicly available data from Zameen.com for personal use. It is not affiliated with or endorsed by Zameen.com.
