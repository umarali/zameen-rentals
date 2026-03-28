# ZameenRentals — Claude Code Guide

## Project Overview
Rental property search engine for Pakistan (Karachi, Lahore, Islamabad), scraping Zameen.com. FastAPI backend + single-file vanilla JS frontend. SQLite database for search history and caching.

## Architecture
```
main.py                  → Entry point (uvicorn)
app/
  __init__.py            → FastAPI app, middleware, CORS, DB lifecycle
  routes.py              → API endpoints (/api/search, /api/parse-query, /api/areas, /api/cities, etc.)
  scraper.py             → HTTP fetching, HTML parsing, search orchestration
  parsing.py             → NLP query parsing (regex + Claude Haiku via Instructor), URL building
  data.py                → Multi-city area definitions, property types, Roman Urdu/Urdu translations
  cache.py               → In-memory cache with 5min TTL, rate limiter (2 req/sec)
  database.py            → SQLite: listing cache, search history, popular/recent searches
  areas.json             → 366 Karachi areas with slugs, IDs, coordinates
  areas_lahore.json      → 462 Lahore areas
  areas_islamabad.json   → 303 Islamabad areas
static/
  index.html             → Entire frontend: HTML + Tailwind CSS + JS (~1100 lines)
tools/
  deep_discover.py       → 3-phase area crawler for Zameen.com
```

## Multi-City Architecture
- `CITIES` dict in data.py: `{"karachi": {name, id, lat, lng, file}, "lahore": ..., "islamabad": ...}`
- `CITY_AREAS` dict: `{"karachi": {area_name: (slug, id, lat, lng)}, ...}`
- `get_areas(city)` returns areas for a specific city
- All backend functions (`build_url`, `match_area`, `search_zameen`, `parse_natural_query`) accept a `city` parameter
- Zameen.com city IDs: Lahore=1, Karachi=2, Islamabad=3
- Frontend state `S.city` drives city selection; city tabs in filter bar

## Key Patterns
- **Area matching**: Fuzzy multi-strategy (exact → substring → token overlap → SequenceMatcher). See `match_area(query, city)` in parsing.py.
- **NLP parsing**: Tries Claude Haiku via Instructor first, falls back to regex. Supports English, Roman Urdu, Urdu script. Roman Urdu aliases currently only for Karachi.
- **URL construction**: `build_url()` maps city+filters to Zameen.com URL structure.
- **Property type detection**: `_extract_property_type()` infers from card text. When a type filter is active, the label is overridden.
- **Frontend state**: Single `S` object holds all filter state including `city`. `loadCityData()` handles city switching (clears markers, re-fetches areas, re-centers map).

## Common Tasks

### Adding a new area
1. Add entry to the appropriate `app/areas_*.json` with slug, id, lat, lng
2. For Karachi: add Roman Urdu aliases to `ROMAN_URDU_AREAS` in data.py
3. For Karachi: optionally add Urdu alias to `URDU_AREAS` in data.py

### Adding a new city
1. Add entry to `CITIES` dict in data.py with name, Zameen.com ID, coords, area file
2. Create `app/areas_<city>.json` (use deep_discover.py or manual crawl)
3. Add city tab in index.html `#cityTabs`
4. Add city defaults in frontend `CITY_DEFAULTS`

### Running locally
```bash
pip install -r requirements.txt
export ANTHROPIC_API_KEY=...   # optional, for Claude NLP parsing
uvicorn main:app --reload --port 8000
```

## Gotchas
- Zameen.com may not have all blocks/sub-areas for every neighborhood
- `_extract_property_type()` pattern priority matters — "upper portion" matches before "house"
- `d.total` from Zameen.com is the cross-page total. Frontend shows "Showing X of Y"
- Roman Urdu aliases (`ROMAN_URDU_AREAS`) only exist for Karachi areas. Lahore/Islamabad use direct name matching.
- When switching cities, old map markers must be cleared (`loadCityData()` handles this)

## Tech Constraints
- Must use open-source tech only
- No build tools — frontend is a single HTML file
- Deployed on Heroku (Procfile)
- SQLite database in `data/zameenrentals.db` for search history
